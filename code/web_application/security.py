"""Password hashing and the server-side session dependency (HW4).

Passwords are hashed with PBKDF2-HMAC-SHA256 (stdlib, salted). A successful
login creates a row in the `sessions` table keyed by a random opaque token;
the browser only ever receives that token, in an HttpOnly cookie.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from models import User, UserSession

SESSION_COOKIE_NAME = "s7117_session"
SESSION_TTL = timedelta(hours=int(os.getenv("SESSION_TTL_HOURS", "8")))
# Local dev runs over plain http; set COOKIE_SECURE=1 when served over https.
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "0") == "1"

_PBKDF2_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        _algo, iterations, salt, expected = stored_hash.split("$")
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations))
    return hmac.compare_digest(digest.hex(), expected)


def utcnow() -> datetime:
    # MySQL DATETIME has no timezone; store naive UTC consistently.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def create_session(db_session_basede26: Session, user: User) -> UserSession:
    now = utcnow()
    user_session = UserSession(
        id=secrets.token_urlsafe(32),
        user_id=user.id,
        created_at=now,
        expires_at=now + SESSION_TTL,
    )
    db_session_basede26.add(user_session)
    db_session_basede26.commit()
    return user_session


def get_current_user(
    s7117_session: str | None = Cookie(default=None),
    db_session_basede26: Session = Depends(get_db),
) -> User:
    """Resolve the session cookie to a user via the sessions table, or 401."""
    if not s7117_session:
        raise HTTPException(status_code=401, detail="Login required")
    user_session = db_session_basede26.execute(
        select(UserSession).where(UserSession.id == s7117_session)
    ).scalar_one_or_none()
    if user_session is None or user_session.expires_at <= utcnow():
        raise HTTPException(status_code=401, detail="Login required")
    return db_session_basede26.get(User, user_session.user_id)
