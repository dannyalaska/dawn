from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from app.core.auth import CurrentUser, authenticate_user, create_user, issue_token

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    full_name: str | None = None
    is_default: bool = False


class TokenResponse(BaseModel):
    token: str
    user: UserResponse


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest) -> TokenResponse:
    try:
        user = create_user(payload.email, payload.password, full_name=payload.full_name)
    except ValueError as exc:  # user already exists
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    token = issue_token(user.id)
    return TokenResponse(
        token=token,
        user=UserResponse(id=user.id, email=user.email, full_name=user.full_name, is_default=False),
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest) -> TokenResponse:
    user = authenticate_user(payload.email, payload.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = issue_token(user.id)
    return TokenResponse(
        token=token,
        user=UserResponse(id=user.id, email=user.email, full_name=user.full_name, is_default=False),
    )


@router.get("/me", response_model=UserResponse)
def me(current_user: CurrentUser) -> UserResponse:
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        is_default=current_user.is_default,
    )
