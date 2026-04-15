from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response, Request, status
from app.services.email import send_email
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import re
import uuid

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token, decode_token
from app.core.config import settings
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.auth import SignupRequest, LoginRequest, TokenResponse, RefreshRequest, ForgotPasswordRequest, MessageResponse, ChangePasswordRequest

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

router = APIRouter(prefix="/auth", redirect_slashes=False, tags=["auth"])

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

    access_token = create_access_token(user.id, user.token_version)
    refresh_token = create_refresh_token(user.id, user.token_version)
    _set_refresh_cookie(response, refresh_token)

    # Send welcome + verify email
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

    # Send verification email
    import secrets
    from datetime import datetime, timedelta, timezone
    verify_token = secrets.token_urlsafe(32)
    user.reset_token = verify_token
    user.reset_token_expires = datetime.now(timezone.utc) + timedelta(hours=24)
    await db.commit()
    try:
        await send_email(
            to_email=user.email,
            subject="Verify your email - Revozi",
            template_name="verify",
            name=user.first_name or user.email.split("@")[0],
            verification_url=f"{settings.FRONTEND_URL}/verify-email?token={verify_token}",
        )
    except Exception as e:
        print(f"Verify email failed: {e}")

    return TokenResponse(accessToken=access_token)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    access_token = create_access_token(user.id, user.token_version)
    refresh_token = create_refresh_token(user.id, user.token_version)
    _set_refresh_cookie(response, refresh_token)

    return TokenResponse(accessToken=access_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: Request, response: Response, body: RefreshRequest = None, db: AsyncSession = Depends(get_db)):
    # Try to get refresh token from request body first (cross-domain),
    # then fall back to cookie (same-domain)
    token = None
    if body and body.refreshToken:
        token = body.refreshToken
    if not token:
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

    if payload.get("ver") != user.token_version:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has been invalidated")

    access_token = create_access_token(user.id, user.token_version)
    new_refresh = create_refresh_token(user.id, user.token_version)
    _set_refresh_cookie(response, new_refresh)

    return TokenResponse(accessToken=access_token, refreshToken=new_refresh)


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


# ── Google OAuth ──────────────────────────────────────────────

@router.get("/google")
async def google_login():
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=500, detail="Google OAuth is not configured")
    params = urlencode({
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_AUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",
    })
    return RedirectResponse(f"{GOOGLE_AUTH_URL}?{params}", status_code=302)


@router.get("/google-callback")
async def google_callback(code: str = None, error: str = None, response: Response = None, db: AsyncSession = Depends(get_db)):
    # Exchange code for tokens
    if not code:
        return RedirectResponse(f"{settings.FRONTEND_URL}/login?error=google_failed")

    print("🔵 [OAuth] Callback started")

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": settings.GOOGLE_AUTH_REDIRECT_URI,
            "grant_type": "authorization_code",
        })
    if token_resp.status_code != 200:
        print(f"❌ [OAuth] Token exchange failed: {token_resp.status_code}")
        return RedirectResponse(f"{settings.FRONTEND_URL}/login?error=google_failed")

    tokens = token_resp.json()
    print(f"✅ [OAuth] Token exchange successful")

    # Fetch user info
    async with httpx.AsyncClient() as client:
        info_resp = await client.get(GOOGLE_USERINFO_URL, headers={
            "Authorization": f"Bearer {tokens['access_token']}",
        })
    if info_resp.status_code != 200:
        print(f"❌ [OAuth] User info fetch failed: {info_resp.status_code}")
        return RedirectResponse(f"{settings.FRONTEND_URL}/login?error=google_failed")

    info = info_resp.json()
    email = info["email"]
    first_name = info.get("given_name", "")
    last_name = info.get("family_name", "")
    print(f"✅ [OAuth] User info retrieved: {email}")

    # Find or create user
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if not user:
        print(f"🆕 [OAuth] Creating new user: {email}")
        user = User(
            email=email,
            password_hash=None,
            first_name=first_name,
            last_name=last_name,
            avatar_url=info.get("picture"),
            email_verified=True,
        )
        db.add(user)
        await db.flush()
        print(f"✅ [OAuth] User flushed to DB: {user.id}")

        slug_base = re.sub(r"[^a-z0-9]", "-", f"{first_name}-{last_name}".lower()).strip("-")
        slug = f"{slug_base}-{uuid.uuid4().hex[:6]}"
        workspace = Workspace(
            name=f"{first_name}'s Workspace",
            slug=slug,
            owner_id=user.id,
        )
        db.add(workspace)
        await db.flush()
        print(f"✅ [OAuth] Workspace flushed to DB: {workspace.id}")
    else:
        print(f"👤 [OAuth] Existing user found: {email}")
        ws_result = await db.execute(
            select(Workspace)
            .where(Workspace.owner_id == user.id, Workspace.deleted_at.is_(None))
            .order_by(Workspace.created_at.desc())
            .limit(1)
        )
        workspace = ws_result.scalars().first()

    # CRITICAL: Ensure ALL database changes are fully committed before proceeding
    await db.commit()
    print(f"✅ [OAuth] Database transaction COMMITTED for user: {user.id}")

    # Create tokens ONLY after successful commit
    access_token = create_access_token(user.id, user.token_version)
    refresh_token = create_refresh_token(user.id, user.token_version)
    print(f"✅ [OAuth] Tokens created for user: {user.id}")

    # Redirect to frontend callback with user info
    # Include refreshToken in URL params to handle cross-domain cookie dropping
    # Check if user has completed onboarding by checking their workspace
    onboarding_complete = "true" if workspace and workspace.onboarding_complete else "false"

    params = urlencode({
        "token": access_token,
        "refreshToken": refresh_token,
        "firstName": first_name or "",
        "lastName": last_name or "",
        "email": email or "",
        "id": str(user.id),
        "onboardingComplete": onboarding_complete,
    })

    # Create response with redirect
    redirect = RedirectResponse(f"{settings.FRONTEND_URL}/auth-callback?{params}", status_code=302)

    # Set cookie as fallback for same-domain setups
    redirect.set_cookie(
        key=REFRESH_COOKIE_KEY,
        value=refresh_token,
        httponly=True,
        secure=settings.APP_ENV != "development",
        samesite="lax",
        max_age=REFRESH_COOKIE_MAX_AGE,
        path="/",
    )

    print(f"✅ [OAuth] Redirecting user to frontend with tokens")
    return redirect


@router.post("/send-verification", response_model=MessageResponse)
async def send_verification(request: Request, db: AsyncSession = Depends(get_db)):
    from app.core.deps import get_current_user
    import secrets
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = auth_header.split(" ")[1]
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.email_verified:
        return MessageResponse(message="Email already verified")
    verify_token = secrets.token_urlsafe(32)
    user.reset_token = verify_token
    from datetime import datetime, timedelta, timezone
    user.reset_token_expires = datetime.now(timezone.utc) + timedelta(hours=24)
    await db.commit()
    try:
        await send_email(
            to_email=user.email,
            subject="Verify your email - Revozi",
            template_name="verify",
            name=user.first_name or user.email.split("@")[0],
            verification_url=f"{settings.FRONTEND_URL}/verify-email?token={verify_token}",
        )
    except Exception as e:
        print(f"Verify email failed: {e}")
    return MessageResponse(message="Verification email sent.")


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not user.password_hash or not verify_password(body.currentPassword, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.password_hash = hash_password(body.newPassword)
    await db.commit()
    return MessageResponse(message="Password changed successfully.")


@router.post("/sign-out-all", response_model=TokenResponse)
async def sign_out_all(
    response: Response,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user.token_version += 1
    await db.commit()
    await db.refresh(user)

    access_token = create_access_token(user.id, user.token_version)
    refresh_token = create_refresh_token(user.id, user.token_version)
    _set_refresh_cookie(response, refresh_token)
    
    return TokenResponse(accessToken=access_token)


@router.get("/verify-email", response_model=MessageResponse)
async def verify_email(token: str, db: AsyncSession = Depends(get_db)):
    from datetime import datetime, timezone
    result = await db.execute(select(User).where(User.reset_token == token))
    user = result.scalar_one_or_none()
    if not user or not user.reset_token_expires:
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")
    expires = user.reset_token_expires
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")
    user.email_verified = True
    user.reset_token = None
    user.reset_token_expires = None
    await db.commit()
    return MessageResponse(message="Email verified successfully.")
