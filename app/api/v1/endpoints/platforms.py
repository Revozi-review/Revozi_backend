import uuid
import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.workspace import Workspace
from app.models.platform_connection import PlatformConnection
from app.schemas.auth import MessageResponse
from app.services.google_reviews import (
    get_google_auth_url,
    exchange_code_for_tokens,
    list_accounts,
    list_locations,
    sync_reviews_to_workspace,
)

router = APIRouter(prefix="/platforms", tags=["platforms"])


@router.get("/google/connect")
async def connect_google(
    workspaceId: uuid.UUID = Query(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Initiate Google OAuth flow for connecting Google Reviews."""
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google API not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.",
        )

    # Verify workspace ownership
    result = await db.execute(
        select(Workspace).where(Workspace.id == workspaceId, Workspace.owner_id == user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    # Encode workspace + user in state for the callback
    state = json.dumps({"workspace_id": str(workspaceId), "user_id": str(user.id)})
    auth_url = get_google_auth_url(state)
    return {"url": auth_url}


@router.get("/google/callback")
async def google_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Handle Google OAuth callback — exchange code for tokens and store connection."""
    try:
        state_data = json.loads(state)
        workspace_id = uuid.UUID(state_data["workspace_id"])
        user_id = uuid.UUID(state_data["user_id"])
    except (json.JSONDecodeError, KeyError, ValueError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid state parameter")

    # Exchange code for tokens
    try:
        token_data = await exchange_code_for_tokens(code)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Token exchange failed: {e}")

    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")

    if not access_token:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="No access token received")

    # Discover the user's Google Business account and first location
    metadata = {}
    try:
        accounts = await list_accounts(access_token)
        if accounts:
            account = accounts[0]
            account_name = account.get("name", "")
            metadata["account_name"] = account_name
            metadata["account_display_name"] = account.get("accountName", "")

            locations = await list_locations(access_token, account_name)
            if locations:
                location = locations[0]
                metadata["location_name"] = location.get("name", "")
                metadata["location_title"] = location.get("title", "")
    except Exception as e:
        # Store connection even if account/location discovery fails — user can configure later
        metadata["discovery_error"] = str(e)

    # Check for existing connection
    existing = await db.execute(
        select(PlatformConnection).where(
            PlatformConnection.workspace_id == workspace_id,
            PlatformConnection.platform == "google_reviews",
        )
    )
    connection = existing.scalar_one_or_none()
    if connection:
        connection.access_token = access_token
        connection.refresh_token = refresh_token or connection.refresh_token
        connection.metadata_json = metadata
    else:
        connection = PlatformConnection(
            workspace_id=workspace_id,
            platform="google_reviews",
            access_token=access_token,
            refresh_token=refresh_token,
            metadata_json=metadata,
        )
        db.add(connection)

    await db.flush()
    await db.commit()

    # Redirect back to frontend integration page
    return RedirectResponse(url="https://revozi.com/integration?connected=google")


@router.get("/{workspace_id}/connections")
async def list_connections(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all platform connections for a workspace."""
    result = await db.execute(
        select(Workspace).where(Workspace.id == workspace_id, Workspace.owner_id == user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    connections_result = await db.execute(
        select(PlatformConnection).where(PlatformConnection.workspace_id == workspace_id)
    )
    connections = connections_result.scalars().all()

    return [
        {
            "id": str(c.id),
            "platform": c.platform,
            "connectedAt": c.connected_at.isoformat() if c.connected_at else None,
            "metadata": {
                "accountName": (c.metadata_json or {}).get("account_display_name"),
                "locationTitle": (c.metadata_json or {}).get("location_title"),
            },
        }
        for c in connections
    ]


@router.delete("/{workspace_id}/connections/{connection_id}", response_model=MessageResponse)
async def disconnect_platform(
    workspace_id: uuid.UUID,
    connection_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a platform connection."""
    result = await db.execute(
        select(Workspace).where(Workspace.id == workspace_id, Workspace.owner_id == user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    conn_result = await db.execute(
        select(PlatformConnection).where(
            PlatformConnection.id == connection_id,
            PlatformConnection.workspace_id == workspace_id,
        )
    )
    connection = conn_result.scalar_one_or_none()
    if not connection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")

    await db.delete(connection)
    await db.flush()
    return MessageResponse(message="Platform disconnected")


@router.post("/{workspace_id}/sync/google", response_model=MessageResponse)
async def sync_google_reviews(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger a sync of Google Reviews for a workspace."""
    result = await db.execute(
        select(Workspace).where(Workspace.id == workspace_id, Workspace.owner_id == user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    conn_result = await db.execute(
        select(PlatformConnection).where(
            PlatformConnection.workspace_id == workspace_id,
            PlatformConnection.platform == "google_reviews",
        )
    )
    connection = conn_result.scalar_one_or_none()
    if not connection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Google Reviews not connected")

    imported = await sync_reviews_to_workspace(workspace_id, connection, db)

    # Trigger analysis for new feedback
    if imported > 0:
        from sqlalchemy import select as sa_select
        from app.models.feedback import Feedback, FeedbackAnalysis
        from app.services.analysis import analyze_feedback
        from app.services.drafts import generate_drafts

        # Find feedback without analysis
        unanalyzed = await db.execute(
            sa_select(Feedback)
            .outerjoin(FeedbackAnalysis)
            .where(
                Feedback.workspace_id == workspace_id,
                Feedback.source == "google_reviews",
                FeedbackAnalysis.id.is_(None),
            )
        )
        for fb in unanalyzed.scalars().all():
            await analyze_feedback(fb.id, db)
            await generate_drafts(fb.id, db)

    return MessageResponse(message=f"Synced {imported} new reviews from Google")
