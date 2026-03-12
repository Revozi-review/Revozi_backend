import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.insight import InsightResponse
from app.services.insights import get_latest_insight, generate_weekly_insight

router = APIRouter(tags=["insights"])


@router.get("/workspaces/{workspace_id}/insights", response_model=InsightResponse | None)
async def get_insights(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify workspace access
    result = await db.execute(
        select(Workspace).where(Workspace.id == workspace_id, Workspace.owner_id == user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    # Try to get existing insight, generate if none exists
    insight = await get_latest_insight(workspace_id, db)
    if not insight:
        insight = await generate_weekly_insight(workspace_id, db)

    if not insight:
        return None

    return InsightResponse.from_orm_insight(insight)
