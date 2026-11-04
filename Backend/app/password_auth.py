"""Email/password accounts using salted scrypt hashes and the shared sessions."""
import base64
from datetime import timedelta
from hashlib import scrypt
import re
import secrets
from threading import BoundedSemaphore
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, SecretStr, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import (claim_legacy_data, complete_login, digest, email_access_allowed, ensure_not_blocked, now, trusted_origin)
from .database import get_db
from .mailer import mail_configured, send_verification_email, EmailDeliveryError
from .models import (AccessToken, AuthRateLimit, AuthSession, EmailCredential, EmailVerification,
                     OwnerAccount, OwnerInvite, User)

router = APIRouter(prefix="/auth", tags=["Authentication"])
HASH_SLOTS = BoundedSemaphore(2)
EMAIL_RE = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}")
PASSWORD_MIN_LENGTH = 15
COMMON_PASSWORD_STEMS = {"password", "passphrase", "qwerty", "letmein", "welcome", "admin", "administrator",
                         "iloveyou", "changeme", "default", "codecheck", "codecheckai", "aicodereviewer"}
PREDICTABLE_ROWS = ("abcdefghijklmnopqrstuvwxyz", "0123456789", "qwertyuiopasdfghjklzxcvbnm",
                    "qwertyuiop", "asdfghjkl", "zxcvbnm")


def password_policy_error(password, email=""):
    if len(password) < PASSWORD_MIN_LENGTH or not password.strip():
        return "Choose a password with at least 15 characters."
    folded = password.casefold()
    # Reject whole predictable choices, while allowing spaces, Unicode and long
    # passphrases without arbitrary uppercase/number/symbol composition rules.
    for period in range(1, len(folded) // 2 + 1):
        pattern = folded[:period]
        if (pattern * ((len(folded) + period - 1) // period))[:len(folded)] == folded:
            return "Avoid repeated characters or repeated password patterns."
    trimmed = folded.strip()
    for row in PREDICTABLE_ROWS:
        for sequence in (row, row[::-1]):
            if trimmed in sequence * (1 + len(trimmed) // len(sequence)):
                return "Avoid alphabet, number or keyboard sequences."
    core = re.sub(r"[\d\W_]+$", "", folded).translate(str.maketrans({"@": "a", "0": "o", "1": "i", "3": "e", "$": "s", "!": "i"}))
    local = email.split("@", 1)[0].casefold() if email else ""
    if core in COMMON_PASSWORD_STEMS or (local and (folded == email.casefold() or core == local)):
        return "Choose a less predictable password; avoid common passwords, your email or the app name."
    return ""


class EmailLogin(BaseModel):
    email: str = Field(max_length=320)
    password: SecretStr
    owner_token: str = Field(default="", max_length=128)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value):
        value = value.strip().casefold()
        if not EMAIL_RE.fullmatch(value) or ".." in value or value.startswith(".") or ".@" in value:
            raise ValueError("Enter a valid email address.")
        return value

    @field_validator("password")
    @classmethod
    def valid_password(cls, value):
        plain = value.get_secret_value()
        if not 1 <= len(plain) <= 128 or "\x00" in plain:
            raise ValueError("Use a password of 1 to 128 characters.")
        return value


class EmailRegistration(EmailLogin):
    @field_validator("password")
    @classmethod
    def strong_password(cls, value, info):
        message = password_policy_error(value.get_secret_value(), info.data.get("email", ""))
        if message:
            raise ValueError(message)
        return value


def derive_password(password, salt):
    # Limit memory pressure while keeping OWASP's scrypt N=2^17, r=8, p=1 cost.
    if not HASH_SLOTS.acquire(blocking=False):
        raise HTTPException(429, "Sign-in is busy. Please try again shortly.", headers={"Retry-After": "2"})
    try:
        return scrypt(password.encode("utf-8"), salt=salt, n=2**17, r=8, p=1,
                      dklen=32, maxmem=256 * 1024 * 1024)
    finally:
        HASH_SLOTS.release()


def hash_password(password):
    salt = secrets.token_bytes(16)
    key = derive_password(password, salt)
    return "scrypt$131072$8$1$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(key).decode()


def verify_password(password, encoded):
    salt, expected, valid = bytes(16), bytes(32), False
    try:
        algorithm, cost, block, parallel, salt_text, key_text = (encoded or "").split("$")
        candidate_salt = base64.b64decode(salt_text, validate=True)
        candidate_key = base64.b64decode(key_text, validate=True)
        if (algorithm, cost, block, parallel) == ("scrypt", "131072", "8", "1") and len(candidate_salt) == 16 and len(candidate_key) == 32:
            salt, expected, valid = candidate_salt, candidate_key, True
    except (ValueError, TypeError):
        pass
    actual = derive_password(password, salt)
    return secrets.compare_digest(actual, expected) and valid


def limit_attempts(email, request, db):
    current = now()
    bucket = int(current.timestamp()) // 900
    host = request.client.host if request.client else "unknown"
    db.query(AuthRateLimit).filter(AuthRateLimit.expires_at <= current).delete(synchronize_session=False)
    for scope, limit in (("email:" + email, 10), ("ip:" + host, 100)):
        key = digest(f"{scope}:{bucket}")
        try:
            with db.begin_nested():
                db.add(AuthRateLimit(key_hash=key, attempts=0, expires_at=current + timedelta(minutes=16)))
                db.flush()
        except IntegrityError:
            pass
        updated = db.query(AuthRateLimit).filter(AuthRateLimit.key_hash == key, AuthRateLimit.attempts < limit).update(
            {AuthRateLimit.attempts: AuthRateLimit.attempts + 1}, synchronize_session=False)
        if not updated:
            db.commit()
            raise HTTPException(429, "Too many sign-in attempts. Please try again in 15 minutes.", headers={"Retry-After": "900"})
    db.commit()


def owner_invite(token_hash, db):
    invitation = db.get(OwnerInvite, token_hash)
    if db.get(OwnerAccount, 1) or not invitation or invitation.expires_at <= now():
        raise HTTPException(400, "This owner setup link is invalid or expired.")
    return invitation


def claim_owner(user, token, db, hashed=False):
    if not token:
        return
    token_hash = token if hashed else digest(token)
    owner_invite(token_hash, db)
    consumed = db.query(OwnerInvite).filter(OwnerInvite.token_hash == token_hash, OwnerInvite.expires_at > now()).delete(synchronize_session=False)
    if consumed != 1:
        raise HTTPException(400, "This owner setup link has already been used.")
    db.add(OwnerAccount(id=1, google_sub=user.google_sub))
    db.flush()
    claim_legacy_data(user, db)


def require_email_delivery():
    if not mail_configured():
        raise HTTPException(503, "Email verification is not available yet. The site owner must configure email delivery.")


def start_verification(email, password_hash, owner_hash, response, db, replacing=None):
    credential = db.query(EmailCredential).filter_by(email=email).first()
    if credential:
        ensure_not_blocked(db.get(User, credential.user_id))
    require_email_delivery()
    if owner_hash:
        owner_invite(owner_hash, db)
    db.query(EmailVerification).filter(EmailVerification.created_at < now() - timedelta(days=1)).delete(synchronize_session=False)
    previous = db.query(EmailVerification).filter_by(email=email).first()
    if previous and now() - previous.created_at < timedelta(seconds=60):
        raise HTTPException(429, "Please wait a minute before requesting another verification code.", headers={"Retry-After": "60"})
    token, code = secrets.token_urlsafe(32), f"{secrets.randbelow(1000000):06d}"
    if replacing and (not previous or previous.token_hash != replacing):
        raise HTTPException(400, "This verification request has changed. Sign in again to request a code.")
    if previous:
        db.delete(previous)
        db.flush()
    pending = EmailVerification(token_hash=digest(token), email=email, password_hash=password_hash,
                                owner_token_hash=owner_hash, code_hash=digest(token + ":" + code), attempts=0,
                                created_at=now(), expires_at=now() + timedelta(minutes=10))
    db.add(pending)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "A verification request is already in progress. Please try again.") from error
    try:
        send_verification_email(email, code)
    except EmailDeliveryError as error:
        db.query(EmailVerification).filter_by(token_hash=digest(token)).delete(synchronize_session=False)
        db.commit()
        raise HTTPException(503, "We could not send your verification code. Please try again or contact the site owner.") from error
    response.status_code = 202
    response.headers["Cache-Control"] = "no-store"
    return {"verification_required": True, "challenge_token": token, "email": email, "expires_in": 600, "resend_after": 60}


@router.post("/register", dependencies=[Depends(trusted_origin)])
def register(data: EmailRegistration, request: Request, response: Response, db: Session = Depends(get_db)):
    limit_attempts(data.email, request, db)
    credential = db.query(EmailCredential).filter_by(email=data.email).first()
    if credential:
        ensure_not_blocked(db.get(User, credential.user_id))
    if credential and email_access_allowed(db.get(User, credential.user_id), credential, db):
        raise HTTPException(409, "Unable to create an account with these details. Try signing in.")
    require_email_delivery()
    owner_hash = digest(data.owner_token) if data.owner_token else None
    if owner_hash:
        owner_invite(owner_hash, db)
    return start_verification(data.email, hash_password(data.password.get_secret_value()), owner_hash, response, db)


@router.post("/login", dependencies=[Depends(trusted_origin)])
def login(data: EmailLogin, request: Request, response: Response, db: Session = Depends(get_db)):
    limit_attempts(data.email, request, db)
    credential = db.query(EmailCredential).filter_by(email=data.email).first()
    if not verify_password(data.password.get_secret_value(), credential.password_hash if credential else None):
        raise HTTPException(401, "Email or password is incorrect.")
    user = db.get(User, credential.user_id)
    ensure_not_blocked(user)
    if not email_access_allowed(user, credential, db):
        return start_verification(data.email, credential.password_hash, digest(data.owner_token) if data.owner_token else None, response, db)
    claim_owner(user, data.owner_token, db)
    return complete_login("email", user.id, user.email, user.name, None, {}, request, response, db)


class VerificationRequest(BaseModel):
    challenge_token: SecretStr

    @field_validator("challenge_token")
    @classmethod
    def valid_token(cls, value):
        if not 1 <= len(value.get_secret_value()) <= 128:
            raise ValueError("Start email verification again.")
        return value


class VerifyEmailRequest(VerificationRequest):
    code: SecretStr

    @field_validator("code")
    @classmethod
    def valid_code(cls, value):
        if not re.fullmatch(r"[0-9]{6}", value.get_secret_value()):
            raise ValueError("Enter the six-digit code from your email.")
        return value


@router.post("/resend-verification", dependencies=[Depends(trusted_origin)])
def resend(data: VerificationRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    token_hash = digest(data.challenge_token.get_secret_value())
    pending = db.get(EmailVerification, token_hash)
    if not pending or pending.created_at < now() - timedelta(days=1):
        raise HTTPException(400, "This verification request has expired. Start again.")
    email, password_hash, owner_hash = pending.email, pending.password_hash, pending.owner_token_hash
    limit_attempts(email, request, db)
    return start_verification(email, password_hash, owner_hash, response, db, replacing=token_hash)


@router.post("/verify-email", dependencies=[Depends(trusted_origin)])
def verify_email(data: VerifyEmailRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    token = data.challenge_token.get_secret_value()
    token_hash = digest(token)
    pending = db.get(EmailVerification, token_hash)
    if not pending or pending.expires_at <= now():
        raise HTTPException(400, "Your verification code has expired or changed. Request a new code.")
    email, password_hash, owner_hash, expected_code_hash = pending.email, pending.password_hash, pending.owner_token_hash, pending.code_hash
    updated = db.query(EmailVerification).filter(EmailVerification.token_hash == token_hash,
              EmailVerification.expires_at > now(), EmailVerification.attempts < 5).update(
              {EmailVerification.attempts: EmailVerification.attempts + 1}, synchronize_session=False)
    db.commit()
    if not updated:
        raise HTTPException(429, "Too many incorrect codes. Request a new verification code.")
    if not secrets.compare_digest(digest(token + ":" + data.code.get_secret_value()), expected_code_hash):
        raise HTTPException(400, "That code is incorrect. Check your email and try again.")
    consumed = db.query(EmailVerification).filter(EmailVerification.token_hash == token_hash,
               EmailVerification.expires_at > now(), EmailVerification.code_hash == expected_code_hash).delete(synchronize_session=False)
    if consumed != 1:
        raise HTTPException(400, "This verification code has already been used.")
    try:
        credential = db.query(EmailCredential).filter_by(email=email).first()
        user = db.get(User, credential.user_id) if credential else None
        ensure_not_blocked(user)
        if not user:
            user_id = str(uuid4())
            user = User(id=user_id, google_sub="email:" + user_id, auth_provider="email", email=email,
                        name=email.split("@", 1)[0], first_login_at=now(), last_login_at=now(), last_seen_at=now(), login_count=0)
            db.add(user)
            db.flush()
            credential = EmailCredential(user_id=user.id, email=email)
            db.add(credential)
        # The inbox owner chooses the final password, avoiding takeover by an
        # earlier unverified registration. Revoke that account's old sessions.
        credential.password_hash, credential.verified_at = password_hash, now()
        sessions = db.query(AuthSession.token_hash).filter_by(user_id=user.id)
        db.query(AccessToken).filter(AccessToken.session_hash.in_(sessions)).delete(synchronize_session=False)
        db.query(AuthSession).filter_by(user_id=user.id).delete(synchronize_session=False)
        db.flush()
        claim_owner(user, owner_hash, db, hashed=True)
        return complete_login("email", user.id, user.email, user.name, None, {}, request, response, db)
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "Email verification changed in another window. Please sign in again.") from error
