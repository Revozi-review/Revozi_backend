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
    result = await db.execute(select(Workspace).where(Workspace.owner_id == user.id))
    workspaces = result.scalars().all()
    return [WorkspaceResponse.from_orm_workspace(ws) for ws in workspaces]


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Workspace).where(Workspace.id == workspace_id, Workspace.owner_id == user.id)
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
        select(Workspace).where(Workspace.id == workspace_id, Workspace.owner_id == user.id)
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
    if body.logoUrl is not None:
        ws.logo_url = body.logoUrl
    if body.onboardingComplete is not None:
        ws.onboarding_complete = body.onboardingComplete

    await db.flush()
    return WorkspaceResponse.from_orm_workspace(ws)


@router.delete("/{workspace_id}", status_code=204)
async def delete_workspace(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Workspace).where(Workspace.id == workspace_id, Workspace.owner_id == user.id)
    )
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
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
        select(Workspace).where(Workspace.id == workspace_id, Workspace.owner_id == user.id)
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
