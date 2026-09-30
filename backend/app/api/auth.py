"""Local user auth (register / login). Used to scope Instagram data per user."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core import security
from app.core.rate_limit import auth_limiter, limit
from app.db.session import get_session
from app.models.instagram import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(limit(auth_limiter, "auth"))],
)
async def register(body: RegisterRequest, session: AsyncSession = Depends(get_session)):
    existing = await session.execute(select(User).where(User.email == body.email.lower()))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    if len(body.password) < 8:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Password must be at least 8 characters"
        )
    user = User(
        name=body.name.strip(),
        email=body.email.lower(),
        password_hash=security.hash_password(body.password),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return TokenResponse(access_token=security.create_access_token(user.id))


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(limit(auth_limiter, "auth"))],
)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(User).where(User.email == body.email.lower()))
    user = result.scalar_one_or_none()
    if user is None or not security.verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    return TokenResponse(access_token=security.create_access_token(user.id))


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user
