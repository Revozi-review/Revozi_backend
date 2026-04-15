import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.workspace import WorkspaceResponse, WorkspaceUpdateRequest, WorkspaceNotificationsRequest

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.get("", response_model=list[WorkspaceResponse])
async def list_workspaces(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Workspace).where(Workspace.owner_id == user.id, Workspace.deleted_at.is_(None)))
    workspaces = result.scalars().all()
    return [WorkspaceResponse.from_orm_workspace(ws) for ws in workspaces]


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Workspace).where(Workspace.id == workspace_id, Workspace.owner_id == user.id, Workspace.deleted_at.is_(None))
    )
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    # Count feedback items for this workspace
    from app.models.feedback import Feedback
    count_result = await db.execute(
        select(sa_func.count()).select_from(Feedback).where(Feedback.workspace_id == workspace_id)
    )
    feedback_count = count_result.scalar() or 0

    return WorkspaceResponse.from_orm_workspace(ws, member_count=1, feedback_count=feedback_count)


@router.patch("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: uuid.UUID,
    body: WorkspaceUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Workspace).where(Workspace.id == workspace_id, Workspace.owner_id == user.id, Workspace.deleted_at.is_(None))
    )
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    if body.name is not None:
        ws.name = body.name
    if body.brandTone is not None:
        ws.brand_tone = body.brandTone
    if body.replyStyle is not None:
        ws.reply_style = body.replyStyle
    if body.businessType is not None:
        ws.business_type = body.businessType
    if body.logoUrl is not None:
        ws.logo_url = body.logoUrl
    if body.onboardingComplete is not None:
        ws.onboarding_complete = body.onboardingComplete
    if body.slug is not None:
        import re
        if not re.match(r"^[a-z0-9-]+$", body.slug):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Slug must be lowercase alphanumeric with hyphens")
        slug_check = await db.execute(select(Workspace).where(Workspace.slug == body.slug, Workspace.id != workspace_id))
        if slug_check.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug already taken")
        ws.slug = body.slug

    await db.flush()
    return WorkspaceResponse.from_orm_workspace(ws)


@router.delete("/{workspace_id}", status_code=204)
async def delete_workspace(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Workspace).where(Workspace.id == workspace_id, Workspace.owner_id == user.id, Workspace.deleted_at.is_(None))
    )
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    
    ws.deleted_at = sa_func.now()
    await db.commit()

@router.delete("/{workspace_id}/permanent", status_code=204)
async def permanently_delete_workspace(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Permanently delete a workspace (hard delete - cannot be recovered)"""
    result = await db.execute(
        select(Workspace).where(
            Workspace.id == workspace_id, 
            Workspace.owner_id == user.id
        )
    )
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Workspace not found"
        )
    
    # Hard delete - actually remove from database permanently
    await db.delete(ws)
    await db.commit()



@router.patch("/{workspace_id}/notifications", response_model=WorkspaceResponse)
async def update_notifications(
    workspace_id: uuid.UUID,
    body: WorkspaceNotificationsRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Workspace).where(Workspace.id == workspace_id, Workspace.owner_id == user.id, Workspace.deleted_at.is_(None))
    )
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    prefs = dict(ws.notification_preferences or {})
    if body.oneStarAlerts is not None:
        prefs["oneStarAlerts"] = body.oneStarAlerts
    if body.dailySummary is not None:
        prefs["dailySummary"] = body.dailySummary
    if body.weeklyPerformance is not None:
        prefs["weeklyPerformance"] = body.weeklyPerformance
    ws.notification_preferences = prefs

    await db.commit()
    await db.refresh(ws)
    return WorkspaceResponse.from_orm_workspace(ws)


# ─── Location Management ───────────────────────────────────────────────────

LOCATION_PLAN_LIMITS = {
    "free": 0,
    "starter": 1,
    "growth": 5,
    "enterprise": None,  # unlimited
}


@router.get("/{workspace_id}/locations")
async def list_workspace_locations(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all Google Business locations for a workspace with sync status."""
    from app.models.platform_connection import PlatformConnection

    result = await db.execute(
        select(Workspace).where(Workspace.id == workspace_id, Workspace.owner_id == user.id, Workspace.deleted_at.is_(None))
    )
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    conn_result = await db.execute(
        select(PlatformConnection).where(
            PlatformConnection.workspace_id == workspace_id,
            PlatformConnection.platform == "google_reviews",
        )
    )
    connection = conn_result.scalar_one_or_none()
    if not connection:
        return {"locations": [], "planLimit": LOCATION_PLAN_LIMITS.get(ws.plan, 1)}

    metadata = connection.metadata_json or {}
    stored_locations = metadata.get("locations", [])
    if not stored_locations and metadata.get("location_name"):
        stored_locations = [{
            "id": metadata.get("location_name"),
            "name": metadata.get("location_name"),
            "title": metadata.get("location_title", ""),
            "syncEnabled": True,
            "connected": True,
        }]

    locations = []
    for loc in stored_locations:
        locations.append({
            "id": loc.get("name") or loc.get("id"),
            "name": loc.get("title") or loc.get("name"),
            "address": loc.get("address", ""),
            "placeId": loc.get("placeId", ""),
            "phone": loc.get("phone", ""),
            "connected": True,
            "syncEnabled": loc.get("sync_enabled", loc.get("syncEnabled", False)),
            "lastSyncAt": loc.get("lastSyncAt"),
            "reviewCount": loc.get("reviewCount", 0),
        })

    plan_limit = LOCATION_PLAN_LIMITS.get(ws.plan, 1)
    return {
        "locations": locations,
        "planLimit": plan_limit,
        "locationCount": len(locations),
    }


@router.post("/{workspace_id}/locations")
async def add_workspace_location(
    workspace_id: uuid.UUID,
    body: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a Google Business location to a workspace, subject to plan limits."""
    from app.models.platform_connection import PlatformConnection

    result = await db.execute(
        select(Workspace).where(Workspace.id == workspace_id, Workspace.owner_id == user.id, Workspace.deleted_at.is_(None))
    )
    ws = result.scalar_one_or_none()
    if not ws:
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

    metadata = connection.metadata_json or {}
    stored_locations = list(metadata.get("locations", []))

    # Enforce plan-based limit
    plan_limit = LOCATION_PLAN_LIMITS.get(ws.plan, 1)
    if plan_limit is not None and len(stored_locations) >= plan_limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "LOCATION_LIMIT_REACHED",
                "limit": plan_limit,
                "plan": ws.plan,
            }
        )

    new_loc = {
        "name": body.get("placeId") or body.get("name"),
        "title": body.get("name", ""),
        "placeId": body.get("placeId"),
        "sync_enabled": body.get("syncEnabled", True),
        "address": body.get("address", ""),
        "phone": body.get("phone", ""),
    }
    stored_locations.append(new_loc)
    new_metadata = dict(metadata)
    new_metadata["locations"] = stored_locations
    connection.metadata_json = new_metadata
    await db.commit()

    return {
        "id": new_loc["name"],
        "name": new_loc["title"],
        "syncEnabled": new_loc["sync_enabled"],
        "connected": True,
    }


@router.post("/{workspace_id}/locations/{location_id}/toggle")
async def toggle_workspace_location(
    workspace_id: uuid.UUID,
    location_id: str,
    body: dict,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Toggle sync on/off for a specific location by location_id."""
    from app.models.platform_connection import PlatformConnection

    result = await db.execute(
        select(Workspace).where(Workspace.id == workspace_id, Workspace.owner_id == user.id, Workspace.deleted_at.is_(None))
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

    metadata = connection.metadata_json or {}
    stored_locations = list(metadata.get("locations", []))
    sync_enabled = body.get("syncEnabled", True)

    for loc in stored_locations:
        if loc.get("name") == location_id or loc.get("placeId") == location_id:
            loc["sync_enabled"] = sync_enabled
            break

    new_metadata = dict(metadata)
    new_metadata["locations"] = stored_locations
    connection.metadata_json = new_metadata
    await db.commit()

    return {"id": location_id, "syncEnabled": sync_enabled}
