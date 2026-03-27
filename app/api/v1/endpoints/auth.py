from fastapi import APIRouter, Depends, HTTPException, Response, Request, status
from app.services.email import send_email
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import re
import uuid

from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token, decode_token
from app.core.config import settings
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.auth import SignupRequest, LoginRequest, TokenResponse, ForgotPasswordRequest, MessageResponse

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE_KEY = "refresh_token"
REFRESH_COOKIE_MAX_AGE = settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_KEY,
        value=token,
        httponly=True,
        secure=settings.APP_ENV != "development",
        samesite="lax",
        max_age=REFRESH_COOKIE_MAX_AGE,
        path="/",
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=REFRESH_COOKIE_KEY, path="/")


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def signup(body: SignupRequest, response: Response, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        first_name=body.firstName,
        last_name=body.lastName,
    )
    db.add(user)
    await db.flush()

    # Auto-create a workspace for the new user
    slug_base = re.sub(r"[^a-z0-9]", "-", f"{body.firstName}-{body.lastName}".lower()).strip("-")
    slug = f"{slug_base}-{uuid.uuid4().hex[:6]}"
    workspace = Workspace(
        name=f"{body.firstName}'s Workspace",
        slug=slug,
        owner_id=user.id,
    )
    db.add(workspace)
    await db.flush()

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    _set_refresh_cookie(response, refresh_token)

    # Send welcome email
    try:
        await send_email(
            to_email=user.email,
            subject="Welcome to Revozi",
            template_name="welcome",
            name=user.first_name or user.email.split("@")[0],
            dashboard_url="https://revozi.com/dashboard"
        )
    except Exception as e:
        print(f"Welcome email failed: {e}")
    return TokenResponse(accessToken=access_token)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    _set_refresh_cookie(response, refresh_token)

    return TokenResponse(accessToken=access_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    token = request.cookies.get(REFRESH_COOKIE_KEY)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token")

    payload = decode_token(token)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    access_token = create_access_token(user.id)
    new_refresh = create_refresh_token(user.id)
    _set_refresh_cookie(response, new_refresh)

    return TokenResponse(accessToken=access_token)


@router.post("/logout", response_model=MessageResponse)
async def logout(response: Response):
    _clear_refresh_cookie(response)
    return MessageResponse(message="Logged out")


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if user:
        import secrets
        from datetime import datetime, timedelta, timezone
        token = secrets.token_urlsafe(32)
        user.reset_token = token
        user.reset_token_expires = datetime.now(timezone.utc) + timedelta(hours=1)
        await db.commit()
        try:
            await send_email(
                to_email=user.email,
                subject="Reset Your Password - Revozi",
                template_name="reset_password",
                reset_url=f"https://revozi.com/reset-password?token={token}",
                name=user.first_name,
            )
        except Exception as e:
            print(f"Reset email failed: {e}")
    return MessageResponse(message="If an account with that email exists, a reset link has been sent.")


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(token: str, new_password: str, db: AsyncSession = Depends(get_db)):
    from datetime import datetime, timezone
    result = await db.execute(select(User).where(User.reset_token == token))
    user = result.scalar_one_or_none()
    if not user or not user.reset_token_expires or user.reset_token_expires < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    user.password_hash = hash_password(new_password)
    user.reset_token = None
    user.reset_token_expires = None
    await db.commit()
    return MessageResponse(message="Password reset successful.")
