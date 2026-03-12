from fastapi import APIRouter, Depends
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_admin_user
from app.models.user import User
from app.models.workspace import Workspace
from app.models.feedback import Feedback
from app.models.subscription import Subscription
from app.schemas.workspace import WorkspaceResponse

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/workspaces", response_model=list[WorkspaceResponse])
async def list_all_workspaces(
    user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Workspace).order_by(Workspace.created_at.desc()))
    workspaces = result.scalars().all()
    return [WorkspaceResponse.from_orm_workspace(ws) for ws in workspaces]


@router.get("/metrics")
async def get_metrics(
    user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    total_users = (await db.execute(select(sa_func.count()).select_from(User))).scalar() or 0
    total_workspaces = (await db.execute(select(sa_func.count()).select_from(Workspace))).scalar() or 0
    total_feedback = (await db.execute(select(sa_func.count()).select_from(Feedback))).scalar() or 0
    active_subscriptions = (
        await db.execute(
            select(sa_func.count()).select_from(Subscription).where(Subscription.status == "active")
        )
    ).scalar() or 0

    return {
        "totalUsers": total_users,
        "totalWorkspaces": total_workspaces,
        "totalFeedback": total_feedback,
        "activeSubscriptions": active_subscriptions,
    }
