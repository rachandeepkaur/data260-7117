"""Password hashing, JWT bearer authentication and role checks (HW7).

Passwords are hashed with PBKDF2-HMAC-SHA256 (stdlib, salted) and only the
hash is stored in the MySQL `users` table. POST /auth/login verifies the
password and returns a signed HS256 JWT access token; protected routes read
it from `Authorization: Bearer <token>`.

    get_current_user        any valid token          -> the User, else 401
    require_roles(*roles)   valid token + role check -> the User, else 401 / 403

HW4's server-side session cookie (sessions table) is kept only as history at
the hw4 tag; no HW7 route accepts it.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Callable

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from database import get_db
from models import User

ROLES = ("reader", "writer", "moderator")

# Set a real secret via env in any deployment; this default is for local dev only.
JWT_SECRET = os.getenv("JWT_SECRET", "s7117-dev-only-jwt-secret-change-me-0123456789")
JWT_ALGORITHM = "HS256"
JWT_ISSUER = "s7117-inspections-api"
ACCESS_TOKEN_TTL = timedelta(minutes=int(os.getenv("ACCESS_TOKEN_TTL_MINUTES", "30")))

_PBKDF2_ITERATIONS = 200_000

# auto_error=False: a missing header is turned into our own 401 (with
# WWW-Authenticate: Bearer) instead of FastAPI's default response.
bearer_scheme = HTTPBearer(auto_error=False, description="JWT from POST /auth/login")


def hash_password(password: str) -> str:
    """Salted PBKDF2-SHA256 hash in the form pbkdf2_sha256$<iterations>$<salt>$<digest>."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Constant-time check of `password` against a hash from hash_password()."""
    try:
        _algo, iterations, salt, expected = stored_hash.split("$")
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations))
    return hmac.compare_digest(digest.hex(), expected)


def create_access_token(user: User, *, ttl: timedelta = ACCESS_TOKEN_TTL, now: datetime | None = None) -> str:
    """Sign a JWT for `user`: sub=username, uid, role, iat, exp, iss."""
    issued = now or datetime.now(timezone.utc)
    claims = {
        "sub": user.username,
        "uid": user.id,
        "role": user.role,
        "iss": JWT_ISSUER,
        "iat": issued,
        "exp": issued + ttl,
    }
    return jwt.encode(claims, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Verify signature, expiry and issuer; raise HTTPException 401 on any failure."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM], issuer=JWT_ISSUER,
                          options={"require": ["sub", "uid", "role", "exp", "iat"]})
    except jwt.ExpiredSignatureError as exc:
        raise _unauthorized("Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise _unauthorized("Invalid token") from exc


def _unauthorized(detail: str) -> HTTPException:
    """401 with the header RFC 6750 asks for."""
    return HTTPException(status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"})


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db_session_basede26: Session = Depends(get_db),
) -> User:
    """Resolve the bearer token to a User row, or 401 (missing, invalid, expired, deleted user)."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized("Not authenticated")
    claims = decode_access_token(credentials.credentials)
    user = db_session_basede26.get(User, claims["uid"])
    if user is None or user.username != claims["sub"]:
        raise _unauthorized("Invalid token")
    return user


def require_roles(*allowed: str) -> Callable[..., User]:
    """Dependency factory: valid token AND a role in `allowed`, else 403.

    The role comes from the users table (not the token), so a role change
    takes effect on the next request."""
    unknown = set(allowed) - set(ROLES)
    if unknown:
        raise ValueError(f"unknown role(s): {sorted(unknown)}")

    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=403,
                detail=f"Role '{user.role}' may not perform this action (requires: {', '.join(allowed)})",
            )
        return user

    return dependency
