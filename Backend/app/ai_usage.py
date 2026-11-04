"""Database-backed per-account quotas shared by workers. No process-local counters."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import os
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import update

from .models import AIRequestLease, AuthRateLimit, User


def request_limit(kind):
    default = 5 if kind == "review" else 10
    setting = "REVIEW_REQUESTS_PER_MINUTE" if kind == "review" else "CHAT_REQUESTS_PER_MINUTE"
    try:
        return max(1, min(int(os.getenv(setting, default)), 1000))
    except ValueError:
        return default


@contextmanager
def ai_request(db, user_id, kind):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    lease_id = str(uuid4())
    # This short write serializes quota checks for an account on both SQLite and PostgreSQL.
    # Commit before the external request so no database lock is held during Gemini generation.
    locked = db.execute(update(User).where(User.id == user_id, User.blocked_at.is_(None)).values(name=User.name))
    if locked.rowcount != 1:
        db.rollback()
        account = db.get(User, user_id)
        if account and account.blocked_at:
            raise HTTPException(status_code=403, detail="Your account is blocked. Contact the site owner.")
        raise HTTPException(status_code=401, detail="Sign in again to continue.")
    db.query(AIRequestLease).filter(AIRequestLease.expires_at <= now).delete(synchronize_session=False)
    db.query(AuthRateLimit).filter(AuthRateLimit.expires_at <= now).delete(synchronize_session=False)
    key = hashlib.sha256(f"ai:{kind}:{user_id}:{int(now.replace(tzinfo=timezone.utc).timestamp()) // 60}".encode()).hexdigest()
    counter = db.get(AuthRateLimit, key)
    if counter and counter.attempts >= request_limit(kind):
        db.rollback()
        raise HTTPException(status_code=429, detail="You have reached the request limit. Wait a minute and try again.", headers={"Retry-After": "60"})
    if db.query(AIRequestLease).filter_by(user_id=user_id).count() >= 2:
        db.rollback()
        raise HTTPException(status_code=429, detail="Two AI requests are already running for your account. Wait for one to finish.", headers={"Retry-After": "10"})
    if not counter:
        counter = AuthRateLimit(key_hash=key, attempts=0, expires_at=now + timedelta(minutes=2))
        db.add(counter)
    counter.attempts += 1
    db.add(AIRequestLease(id=lease_id, user_id=user_id, expires_at=now + timedelta(seconds=90)))
    db.commit()
    try:
        yield
    finally:
        # Failed generations must release their slot too. Expiry recovers crashed workers.
        db.rollback()
        db.query(AIRequestLease).filter_by(id=lease_id).delete(synchronize_session=False)
        db.commit()
