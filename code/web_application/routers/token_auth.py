"""JWT authentication API (HW7 Part 1).

    POST /auth/login   {username, password} -> 200 {access_token, token_type, expires_in, role}
                                               401 invalid credentials
    GET  /auth/me      Authorization: Bearer <token> -> 200 {id, username, role, name}
                                                        401 missing / invalid / expired token

Login fetches the user from the MySQL `users` table and verifies the password
against its PBKDF2 hash; the token is signed only after that succeeds.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from models import User
from security import ACCESS_TOKEN_TTL, create_access_token, get_current_user, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64, examples=["s7117_writer"])
    password: str = Field(min_length=1, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str


class MeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: str
    name: str


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, db_session_basede26: Session = Depends(get_db)) -> TokenOut:
    """Verify username + password against the users table and return a JWT."""
    user = db_session_basede26.execute(
        select(User).where(User.username == payload.username)
    ).scalar_one_or_none()
    # Same message for unknown user and wrong password, so the response does
    # not reveal which usernames exist.
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password",
                            headers={"WWW-Authenticate": "Bearer"})
    return TokenOut(access_token=create_access_token(user),
                    expires_in=int(ACCESS_TOKEN_TTL.total_seconds()), role=user.role)


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user)) -> User:
    """The authenticated user's identity and role."""
    return user
