"""Google Business Profile API integration for fetching Google Reviews.

Flow:
1. User clicks "Connect Google Reviews" in frontend
2. Backend redirects to Google OAuth consent screen
3. Google redirects back with auth code
4. Backend exchanges code for access/refresh tokens
5. Backend uses tokens to list accounts -> locations -> reviews
6. Reviews are stored as Feedback items in the workspace

Google API scopes needed:
- https://www.googleapis.com/auth/business.manage (read reviews)

Prerequisites:
- Google Cloud project with Business Profile API enabled
- OAuth 2.0 credentials (Client ID + Secret)
"""
import logging
from urllib.parse import urlencode
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.feedback import Feedback
from app.models.platform_connection import PlatformConnection

logger = logging.getLogger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_BUSINESS_API = "https://mybusinessbusinessinformation.googleapis.com/v1"
GOOGLE_REVIEWS_API = "https://mybusinessaccountmanagement.googleapis.com/v1"

SCOPES = "https://www.googleapis.com/auth/business.manage"


def get_google_auth_url(state: str) -> str:
    """Generate the Google OAuth consent URL."""
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_tokens(code: str) -> dict:
    """Exchange the authorization code for access and refresh tokens."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            },
        )
        response.raise_for_status()
        return response.json()


async def refresh_access_token(refresh_token: str) -> dict:
    """Refresh an expired access token."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        response.raise_for_status()
        return response.json()


async def list_accounts(access_token: str) -> list[dict]:
    """List Google Business Profile accounts."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{GOOGLE_REVIEWS_API}/accounts",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response.raise_for_status()
        return response.json().get("accounts", [])


async def list_locations(access_token: str, account_name: str) -> list[dict]:
    """List locations for a Google Business account."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{GOOGLE_BUSINESS_API}/{account_name}/locations",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"readMask": "name,title"},
        )
        response.raise_for_status()
        return response.json().get("locations", [])


async def fetch_reviews(access_token: str, location_name: str, page_size: int = 50) -> list[dict]:
    """Fetch reviews for a specific location."""
    # The reviews endpoint uses the account management API
    # location_name format: accounts/{account_id}/locations/{location_id}
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://mybusiness.googleapis.com/v4/{location_name}/reviews",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"pageSize": page_size},
        )
        response.raise_for_status()
        return response.json().get("reviews", [])


def _star_rating_to_int(star_rating: str) -> int:
    """Convert Google's star rating enum to an integer."""
    mapping = {
        "ONE": 1,
        "TWO": 2,
        "THREE": 3,
        "FOUR": 4,
        "FIVE": 5,
    }
    return mapping.get(star_rating, 0)


async def sync_reviews_to_workspace(
    workspace_id: UUID,
    connection: PlatformConnection,
    db: AsyncSession,
) -> int:
    """Fetch reviews from Google and store them as Feedback items.
    Returns the number of new reviews imported.
    """
    access_token = connection.access_token
    metadata = connection.metadata_json or {}
    account_name = metadata.get("account_name")
    
    stored_locations = metadata.get("locations", [])
    if not stored_locations and metadata.get("location_name"):
        stored_locations = [{"name": metadata.get("location_name"), "title": metadata.get("location_title", ""), "sync_enabled": True}]
        
    sync_locations = [loc["name"] for loc in stored_locations if loc.get("sync_enabled", False)]

    if not account_name or not sync_locations:
        logger.error(f"Missing account or no enabled locations in platform connection {connection.id}")
        return 0

    # Limit Enforcement Start
    from app.models.workspace import Workspace
    from app.models.subscription import Subscription
    from app.api.v1.endpoints.billing import TIER_LIMITS
    from datetime import datetime, timezone
    from sqlalchemy import func as sa_func

    ws_result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
    ws = ws_result.scalar_one_or_none()
    sub_result = await db.execute(select(Subscription).where(Subscription.workspace_id == workspace_id))
    sub = sub_result.scalar_one_or_none()

    plan = sub.plan if sub else (ws.plan if ws else "free")
    allow_overage = sub.allow_overage if sub else False
    limit = TIER_LIMITS.get(plan.lower(), 50)

    now = datetime.now(timezone.utc)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    count_result = await db.execute(
        select(sa_func.count()).select_from(Feedback).where(
            Feedback.workspace_id == workspace_id,
            Feedback.created_at >= start_of_month
        )
    )
    current_usage = count_result.scalar() or 0

    if current_usage >= limit and not allow_overage:
        logger.warning(f"Workspace {workspace_id} at review limit ({limit}). New reviews stored as pending_approval.")
        # Don't return 0 — fall through to store reviews in pending state
    # Limit Enforcement End

    # Refresh token if needed
    if connection.refresh_token:
        try:
            token_data = await refresh_access_token(connection.refresh_token)
            access_token = token_data["access_token"]
            connection.access_token = access_token
            await db.flush()
        except Exception as e:
            logger.warning(f"Token refresh failed, using existing token: {e}")

    imported = 0
    for location_name in sync_locations:
        try:
            reviews = await fetch_reviews(access_token, location_name)
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to fetch reviews for {location_name}: {e}")
            continue

        for review in reviews:
            review_id = review.get("reviewId") or review.get("name", "")

            # Skip if already imported (deduplication)
            existing = await db.execute(
                select(Feedback).where(Feedback.external_id == review_id)
            )
            if existing.scalar_one_or_none():
                continue

            comment = review.get("comment", "")
            if not comment:
                continue

            star_rating = review.get("starRating", "")
            reviewer = review.get("reviewer", {})
            display_name = reviewer.get("displayName", "Google Reviewer")

            is_over_limit = (limit is not None) and (current_usage + imported >= limit) and not allow_overage
            review_status = "pending_approval" if is_over_limit else "open"

            fb = Feedback(
                workspace_id=workspace_id,
                author=display_name,
                content=comment,
                rating=_star_rating_to_int(star_rating),
                source="google_reviews",
                external_id=review_id,
                status=review_status,
            )
            db.add(fb)
            imported += 1

        # After each location, no hard-stop anymore — pending_approval handles it

    if imported > 0:
        await db.flush()
        
        # Post-import overage invoicing
        if allow_overage:
            new_billable = max(0, imported - max(0, limit - current_usage))
            if new_billable > 0 and sub and sub.stripe_subscription_id and settings.STRIPE_SECRET_KEY:
                import stripe
                stripe.api_key = settings.STRIPE_SECRET_KEY
                try:
                    stripe_sub = stripe.Subscription.retrieve(sub.stripe_subscription_id)
                    stripe.InvoiceItem.create(
                        customer=stripe_sub.customer,
                        amount=new_billable * 10, # $0.10 per extra review
                        currency="usd",
                        description=f"Overage: {new_billable} extra reviews synced"
                    )
                except Exception as e:
                    logger.error(f"Failed to create Stripe invoice item: {e}")

    return imported
