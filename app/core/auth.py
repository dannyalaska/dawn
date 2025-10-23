from __future__ import annotations

import os
from dataclasses import dataclass
from secrets import token_urlsafe
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext
from sqlalchemy import select

from app.core.config import settings
from app.core.db import session_scope
from app.core.models import User
from app.core.redis_client import redis_sync

TOKEN_PREFIX = "dawn:auth:token:"
TOKEN_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days
DEFAULT_USER_EMAIL = os.getenv("DAWN_DEFAULT_USER_EMAIL", "local@dawn.internal")

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)
credentials_dependency = Depends(bearer_scheme)


@dataclass(slots=True)
class UserContext:
    id: int
    email: str
    full_name: str | None = None
    is_default: bool = False


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def _select_user_by_email(email: str):
    return select(User).where(User.email == email)


def issue_token(user_id: int) -> str:
    token = token_urlsafe(32)
    redis_sync.setex(f"{TOKEN_PREFIX}{token}", TOKEN_TTL_SECONDS, str(user_id))
    return token


def _get_user_by_token(token: str) -> UserContext | None:
    key = f"{TOKEN_PREFIX}{token}"
    user_id = redis_sync.get(key)
    if not user_id:
        return None
    with session_scope() as session:
        user = session.get(User, int(user_id))
        if user is None or not user.is_active:
            return None
        return UserContext(id=user.id, email=user.email, full_name=user.full_name)


def ensure_default_user() -> UserContext:
    with session_scope() as session:
        user = session.execute(_select_user_by_email(DEFAULT_USER_EMAIL)).scalar_one_or_none()
        if user is None:
            user = User(
                email=DEFAULT_USER_EMAIL,
                password_hash=hash_password(token_urlsafe(16)),
                full_name="Local Default",
                is_active=True,
            )
            session.add(user)
            session.flush()
        return UserContext(id=user.id, email=user.email, full_name=user.full_name, is_default=True)


def create_user(email: str, password: str, full_name: str | None = None) -> UserContext:
    with session_scope() as session:
        existing = session.execute(_select_user_by_email(email)).scalar_one_or_none()
        if existing is not None:
            raise ValueError("User already exists")
        user = User(
            email=email.lower(),
            password_hash=hash_password(password),
            full_name=full_name,
            is_active=True,
        )
        session.add(user)
        session.flush()
        session.refresh(user)
        return UserContext(id=user.id, email=user.email, full_name=user.full_name)


def authenticate_user(email: str, password: str) -> UserContext | None:
    with session_scope() as session:
        user = session.execute(_select_user_by_email(email)).scalar_one_or_none()
        if user is None or not user.is_active:
            return None
        if not verify_password(password, user.password_hash):
            return None
        return UserContext(id=user.id, email=user.email, full_name=user.full_name)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = credentials_dependency,
) -> UserContext:
    if credentials:
        token = credentials.credentials
        user = _get_user_by_token(token)
        if user is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        return user

    if settings.AUTH_REQUIRED:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )

    return ensure_default_user()


CurrentUser = Annotated[UserContext, Depends(get_current_user)]
