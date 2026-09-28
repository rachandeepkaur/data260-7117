"""JSON auth API for the React client (HW4): register, login, logout, me.

Login verifies email + password against the `users` table, inserts a row in
`sessions`, and sets an HttpOnly cookie holding only that row's opaque token.
"""
from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from database import get_db
from models import User, UserSession
from security import (
    COOKIE_SECURE,
    SESSION_COOKIE_NAME,
    SESSION_TTL,
    create_session,
    get_current_user,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    name: str
    email: str


@router.post("/register", response_model=UserOut, status_code=201)
def register(payload: RegisterIn, db_session_basede26: Session = Depends(get_db)) -> User:
    email = payload.email.lower()
    if db_session_basede26.execute(select(User).where(User.email == email)).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(name=payload.name, email=email, password_hash=hash_password(payload.password))
    db_session_basede26.add(user)
    db_session_basede26.commit()
    return user


@router.post("/login", response_model=UserOut)
def login(payload: LoginIn, response: Response, db_session_basede26: Session = Depends(get_db)) -> User:
    user = db_session_basede26.execute(
        select(User).where(User.email == payload.email.lower())
    ).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    user_session = create_session(db_session_basede26, user)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=user_session.id,
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
        max_age=int(SESSION_TTL.total_seconds()),
        path="/",
    )
    return user


@router.post("/logout", status_code=204)
def logout(
    response: Response,
    s7117_session: str | None = Cookie(default=None),
    db_session_basede26: Session = Depends(get_db),
) -> Response:
    if s7117_session:
        db_session_basede26.execute(delete(UserSession).where(UserSession.id == s7117_session))
        db_session_basede26.commit()
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.status_code = 204
    return response


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user
