"""Revocable sessions, legacy provider identity, and owner-only access records."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import os
import re
import secrets
from urllib.parse import urlparse
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from google.auth.exceptions import GoogleAuthError, TransportError
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token
from pydantic import BaseModel, Field, StrictBool
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import get_db
from .default_answers import DEFAULT_SAMPLES
from .models import (AccessToken, AuthSession, ChatConversation, EmailCredential, EmailVerification, LoginChallenge,
                     OwnerAccount, SampleAnswer, SignInEvent, Submission, User)

router = APIRouter(prefix="/auth", tags=["Authentication"])
admin_router = APIRouter(prefix="/admin", tags=["Owner"])
bearer = HTTPBearer(auto_error=False)
SESSION_COOKIE = "codecheck_session"
CHALLENGE_COOKIE = "codecheck_login"
SESSION_DAYS = 7
ACCESS_MINUTES = 10
BLOCKED_MESSAGE = "Your account has been blocked by the site owner."


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def digest(value):
    return sha256(value.encode("utf-8")).hexdigest()


def allowed_origins():
    configured = os.getenv("ALLOWED_ORIGINS", "")
    if configured.strip():
        return [origin.strip().rstrip("/") for origin in configured.split(",") if origin.strip()]
    if os.getenv("APP_ENV", "development") == "production":
        return []
    return ["http://localhost:5173", "http://127.0.0.1:5173"]


def trusted_origin(request: Request):
    if request.headers.get("origin") not in allowed_origins():
        raise HTTPException(403, "This website is not allowed to start or change a sign-in session.")


def configured():
    client = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    # Never publish an API key accidentally pasted into the client-ID setting.
    return bool(re.fullmatch(r"[A-Za-z0-9_-]+\.apps\.googleusercontent\.com", client))


def provider_configuration():
    microsoft_client = os.getenv("MICROSOFT_CLIENT_ID", "").strip()
    tenant = os.getenv("MICROSOFT_TENANT_ID", "common").strip()
    def uuid_value(value):
        try:
            UUID(value)
            return True
        except (ValueError, TypeError):
            return False
    microsoft = bool(uuid_value(microsoft_client) and
                     (tenant in {"common", "organizations", "consumers"} or uuid_value(tenant)) and
                     os.getenv("MICROSOFT_CLIENT_SECRET", "").strip())
    return [{"id": "google", "name": "Google", "enabled": configured()},
            {"id": "github", "name": "GitHub", "enabled": bool(os.getenv("GITHUB_CLIENT_ID", "").strip() and os.getenv("GITHUB_CLIENT_SECRET", "").strip())},
            {"id": "microsoft", "name": "Microsoft", "enabled": microsoft}]


def secure_cookies():
    return os.getenv("APP_ENV", "development") == "production"


def set_cookie(response, key, value, seconds):
    response.set_cookie(key, value, max_age=seconds, httponly=True,
                        secure=secure_cookies(), samesite="lax", path="/auth")


def clear_cookie(response, key):
    response.delete_cookie(key, path="/auth", httponly=True,
                           secure=secure_cookies(), samesite="lax")


def stamp(value):
    return value.replace(tzinfo=timezone.utc).isoformat()


def is_owner(user, db):
    pinned = db.get(OwnerAccount, 1)
    return bool(pinned and secrets.compare_digest(pinned.google_sub, user.google_sub))


def owner_access_approved(user, db):
    if not user:
        return False
    pinned = db.get(OwnerAccount, 1)
    return bool(pinned and pinned.local_access_approved_at and secrets.compare_digest(pinned.google_sub, user.google_sub))


def email_access_allowed(user, credential, db):
    return bool(credential and (credential.verified_at or owner_access_approved(user, db)))


def ensure_not_blocked(user):
    if user and user.blocked_at:
        raise HTTPException(403, BLOCKED_MESSAGE)


def user_info(user, db):
    provider = user.auth_provider
    subject = user.google_sub if provider == "google" else user.google_sub.removeprefix(provider + ":")
    credential = db.get(EmailCredential, user.id) if provider == "email" else None
    verified = bool(credential and credential.verified_at) if provider == "email" else provider in {"google", "github"}
    return {"id": user.id, "name": user.name, "email": user.email, "email_verified": verified,
            "owner_access_approved": owner_access_approved(user, db),
            "is_blocked": bool(user.blocked_at), "blocked_at": stamp(user.blocked_at) if user.blocked_at else None,
            "picture": user.picture, "is_owner": is_owner(user, db),
            "provider": provider, "provider_subject": subject}


def issue_access(session, user, db):
    # Serialize token issuance with the owner's block action on this user row.
    user = db.query(User).filter_by(id=user.id).populate_existing().with_for_update().one()
    ensure_not_blocked(user)
    current = db.get(AuthSession, session.token_hash, populate_existing=True)
    if not current or current.expires_at <= now():
        raise HTTPException(401, "Your session has expired. Please sign in again.")
    token = secrets.token_urlsafe(32)
    expires = min(now() + timedelta(minutes=ACCESS_MINUTES), session.expires_at)
    db.query(AccessToken).filter(AccessToken.expires_at <= now()).delete(synchronize_session=False)
    db.add(AccessToken(token_hash=digest(token), session_hash=session.token_hash, expires_at=expires))
    db.commit()
    return {"user": user_info(user, db), "access_token": token, "expires_at": stamp(expires)}


def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)):
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(401, "Sign in to continue.")
    access = db.get(AccessToken, digest(credentials.credentials))
    session = db.get(AuthSession, access.session_hash) if access and access.expires_at > now() else None
    user = db.get(User, session.user_id) if session and session.expires_at > now() else None
    if not user:
        raise HTTPException(401, "Your session has expired. Please sign in again.")
    ensure_not_blocked(user)
    if user.auth_provider == "email":
        credential = db.get(EmailCredential, user.id)
        if not email_access_allowed(user, credential, db):
            raise HTTPException(401, "Verify your email before continuing. Please sign in again.")
    if now() - user.last_seen_at > timedelta(minutes=1):
        user.last_seen_at = now()
        db.commit()
    return user


def require_owner(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not is_owner(user, db):
        raise HTTPException(403, "Only the site owner can manage user access.")
    return user


class GoogleLogin(BaseModel):
    credential: str = Field(min_length=1, max_length=16000)


class VerificationRequest(GoogleRequest):
    def __call__(self, *args, **kwargs):
        kwargs["timeout"] = 10
        return super().__call__(*args, **kwargs)


def verify_google(credential):
    # google-auth verifies Google's signature, the audience, expiry and issuer.
    claims = id_token.verify_oauth2_token(credential, VerificationRequest(), os.environ["GOOGLE_CLIENT_ID"].strip())
    if claims.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise ValueError("Invalid issuer")
    if claims.get("email_verified") is not True or not claims.get("sub") or not claims.get("email"):
        raise ValueError("A verified Google account is required")
    return claims


def pin_owner(user, claims, db):
    if db.get(OwnerAccount, 1) or user.auth_provider != os.getenv("OWNER_PROVIDER", "google").strip().lower():
        return
    expected_sub = os.getenv("OWNER_SUBJECT", "").strip()
    if user.auth_provider == "google":
        expected_sub = expected_sub or os.getenv("OWNER_GOOGLE_SUB", "").strip()
    subject = user.google_sub if user.auth_provider == "google" else user.google_sub.removeprefix(user.auth_provider + ":")
    if expected_sub:
        if not secrets.compare_digest(expected_sub, subject):
            return
    elif user.auth_provider == "google":
        if user.email.casefold() != os.getenv("OWNER_EMAIL", "").strip().casefold():
            return
        if not (user.email.lower().endswith("@gmail.com") or claims.get("hd")):
            raise HTTPException(403, "Owner identity needs OWNER_GOOGLE_SUB for this Google account's email domain.")
    else:
        # Provider email claims never confer owner rights or link other accounts.
        return
    db.add(OwnerAccount(id=1, google_sub=user.google_sub))
    claim_legacy_data(user, db)


def claim_legacy_data(user, db):
    # Preserve previous anonymous data for the owner, never the first arbitrary visitor.
    db.query(Submission).filter(Submission.user_id.is_(None)).update({Submission.user_id: user.id})
    db.query(ChatConversation).filter(ChatConversation.user_id.is_(None)).update({ChatConversation.user_id: user.id})
    builtin_keys = {(language, title) for language, entries in DEFAULT_SAMPLES.items() for title in entries}
    for sample in db.query(SampleAnswer).filter(SampleAnswer.user_id.is_(None)):
        if (sample.language, sample.question_title) not in builtin_keys:
            sample.user_id = user.id


def complete_login(provider, subject, email, name, picture, claims, request, response, db):
    identity = subject if provider == "google" else provider + ":" + subject
    try:
        user = db.query(User).filter_by(google_sub=identity, auth_provider=provider).populate_existing().with_for_update().first()
        if not user:
            user = User(id=str(uuid4()), google_sub=identity, auth_provider=provider, first_login_at=now(), login_count=0)
            db.add(user)
        ensure_not_blocked(user)
        user.email = str(email or "").strip()[:320]
        user.name = str(name or user.email or f"{provider.title()} user")[:200]
        parsed = urlparse(picture) if isinstance(picture, str) else None
        host = parsed.hostname if parsed else ""
        allowed = "googleusercontent.com" if provider == "google" else "avatars.githubusercontent.com" if provider == "github" else ""
        user.picture = picture if parsed and parsed.scheme == "https" and allowed and host and (host == allowed or host.endswith("." + allowed)) else None
        user.last_login_at = user.last_seen_at = now()
        user.login_count += 1
        db.flush()
        pin_owner(user, claims, db)
        previous = db.get(AuthSession, digest(request.cookies.get(SESSION_COOKIE, "")))
        if previous:
            db.query(AccessToken).filter_by(session_hash=previous.token_hash).delete(synchronize_session=False)
            db.delete(previous)
        session_token = secrets.token_urlsafe(32)
        session = AuthSession(token_hash=digest(session_token), user_id=user.id, created_at=now(), expires_at=now() + timedelta(days=SESSION_DAYS))
        db.add(session)
        db.add(SignInEvent(id=str(uuid4()), user_id=user.id, signed_in_at=now()))
        db.flush()
        result = issue_access(session, user, db)
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "Sign-in changed in another window. Please try again.") from error
    set_cookie(response, SESSION_COOKIE, session_token, SESSION_DAYS * 86400)
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get("/config")
def auth_config(response: Response):
    response.headers["Cache-Control"] = "no-store"
    providers = provider_configuration()
    from .mailer import mail_configured
    return {"configured": True, "email_verification_required": True, "email_delivery_ready": mail_configured(),
            "email_password": True,
            "client_id": os.getenv("GOOGLE_CLIENT_ID", "").strip() if configured() else None, "providers": providers}


@router.post("/challenge", dependencies=[Depends(trusted_origin)])
def create_challenge(response: Response, request: Request, db: Session = Depends(get_db)):
    if not configured():
        raise HTTPException(503, "Google sign-in needs a valid GOOGLE_CLIENT_ID in Backend/.env.")
    previous = request.cookies.get(CHALLENGE_COOKIE)
    if previous:
        db.query(LoginChallenge).filter_by(token_hash=digest(previous)).delete(synchronize_session=False)
    db.query(LoginChallenge).filter(LoginChallenge.expires_at <= now()).delete(synchronize_session=False)
    token, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    db.add(LoginChallenge(token_hash=digest(token), nonce_hash=digest(nonce), expires_at=now() + timedelta(minutes=5)))
    db.commit()
    set_cookie(response, CHALLENGE_COOKIE, token, 300)
    response.headers["Cache-Control"] = "no-store"
    return {"nonce": nonce}


@router.post("/google", dependencies=[Depends(trusted_origin)])
def google_login(data: GoogleLogin, request: Request, response: Response, db: Session = Depends(get_db)):
    if not configured():
        raise HTTPException(503, "Google sign-in is not configured yet.")
    challenge_token = request.cookies.get(CHALLENGE_COOKIE, "")
    challenge = db.get(LoginChallenge, digest(challenge_token)) if challenge_token else None
    if not challenge or challenge.expires_at <= now():
        raise HTTPException(401, "Sign-in expired. Refresh the sign-in button and try again.")
    try:
        claims = verify_google(data.credential)
    except TransportError as error:
        raise HTTPException(503, "Google could not be reached to verify your sign-in. Please try again.") from error
    except (ValueError, GoogleAuthError) as error:
        raise HTTPException(401, "Google sign-in could not be verified. Please try again.") from error
    if not isinstance(claims.get("nonce"), str) or not secrets.compare_digest(digest(claims["nonce"]), challenge.nonce_hash):
        raise HTTPException(401, "Sign-in verification failed. Refresh the sign-in button and try again.")
    # Atomic single-use challenge consumption prevents credential replay.
    if db.query(LoginChallenge).filter_by(token_hash=challenge.token_hash).delete(synchronize_session=False) != 1:
        raise HTTPException(401, "This sign-in has already been used. Please try again.")
    result = complete_login("google", claims["sub"], claims["email"], claims.get("name"), claims.get("picture"), claims, request, response, db)
    clear_cookie(response, CHALLENGE_COOKIE)
    return result


@router.get("/me")
def current_session(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(SESSION_COOKIE, "")
    session = db.get(AuthSession, digest(token)) if token else None
    user = db.get(User, session.user_id) if session and session.expires_at > now() else None
    if not user:
        raise HTTPException(401, "Sign in to continue.")
    ensure_not_blocked(user)
    if user.auth_provider == "email":
        credential = db.get(EmailCredential, user.id)
        if not email_access_allowed(user, credential, db):
            raise HTTPException(401, "Verify your email before continuing. Please sign in again.")
    response.headers["Cache-Control"] = "no-store"
    return issue_access(session, user, db)


@router.post("/logout", status_code=204, dependencies=[Depends(trusted_origin)])
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(SESSION_COOKIE, "")
    session = db.get(AuthSession, digest(token)) if token else None
    if session:
        db.query(AccessToken).filter_by(session_hash=session.token_hash).delete(synchronize_session=False)
        db.delete(session)
        db.commit()
    clear_cookie(response, SESSION_COOKIE)
    clear_cookie(response, CHALLENGE_COOKIE)
    response.headers["Cache-Control"] = "no-store"


@admin_router.get("/users", dependencies=[Depends(require_owner)])
def access_users(offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.last_seen_at.desc(), User.id).offset(offset).limit(limit).all()
    return {"total": db.query(User).count(), "total_sign_ins": db.query(SignInEvent).count(), "items": [
        {**user_info(user, db), "first_login_at": stamp(user.first_login_at), "last_login_at": stamp(user.last_login_at),
         "last_seen_at": stamp(user.last_seen_at), "login_count": user.login_count,
         "review_count": db.query(func.count(Submission.id)).filter_by(user_id=user.id).scalar()}
        for user in users]}


@admin_router.get("/sign-ins", dependencies=[Depends(require_owner)])
def sign_in_events(offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db)):
    rows = db.query(SignInEvent, User).join(User, SignInEvent.user_id == User.id).order_by(SignInEvent.signed_in_at.desc(), SignInEvent.id).offset(offset).limit(limit).all()
    return {"total": db.query(SignInEvent).count(), "items": [
        {"id": event.id, "name": user.name, "email": user.email, "provider": user.auth_provider, "signed_in_at": stamp(event.signed_in_at)}
        for event, user in rows]}


class UserAccessChange(BaseModel):
    blocked: StrictBool


@admin_router.patch("/users/{user_id}/access", dependencies=[Depends(trusted_origin)])
def change_user_access(user_id: str, data: UserAccessChange,
                       owner: User = Depends(require_owner), db: Session = Depends(get_db)):
    target = db.query(User).filter_by(id=user_id).populate_existing().with_for_update().first()
    if not target:
        raise HTTPException(404, "User account not found.")
    if data.blocked and (target.id == owner.id or is_owner(target, db)):
        raise HTTPException(400, "The site owner's account cannot be blocked.")
    target.blocked_at = (target.blocked_at or now()) if data.blocked else None
    if data.blocked:
        sessions = db.query(AuthSession.token_hash).filter_by(user_id=target.id)
        db.query(AccessToken).filter(AccessToken.session_hash.in_(sessions)).delete(synchronize_session=False)
        db.query(AuthSession).filter_by(user_id=target.id).delete(synchronize_session=False)
        credential = db.get(EmailCredential, target.id)
        if credential:
            db.query(EmailVerification).filter_by(email=credential.email).delete(synchronize_session=False)
    db.commit()
    return user_info(target, db)
