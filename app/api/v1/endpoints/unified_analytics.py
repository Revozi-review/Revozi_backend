import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.automation import AutomationEngagement, AutomationPostQueue
from app.models.feedback import Feedback
from app.models.user import User
from app.models.workspace import Workspace

router = APIRouter(prefix="/unified-analytics", tags=["unified-analytics"])


@router.get("/{workspace_id}/overview")
async def unified_overview(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns combined Revozi feedback KPIs and automation engagement KPIs
    in a single response for the unified dashboard.
    """
    # Verify workspace ownership
    ws = await db.get(Workspace, workspace_id)
    if not ws or ws.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # --- Revozi KPIs ---
    feedback_result = await db.execute(
        select(
            func.count(Feedback.id).label("total"),
            func.avg(Feedback.rating).label("avg_rating"),
        ).where(Feedback.workspace_id == workspace_id)
    )
    feedback_row = feedback_result.one()
    total_feedback = feedback_row.total or 0
    avg_rating = round(float(feedback_row.avg_rating or 0), 2)

    pending_replies_result = await db.execute(
        select(func.count(Feedback.id)).where(
            Feedback.workspace_id == workspace_id,
            Feedback.status == "open",
        )
    )
    pending_replies = pending_replies_result.scalar() or 0

    # --- Automation KPIs ---
    posts_result = await db.execute(
        select(func.count(AutomationPostQueue.id)).where(
            AutomationPostQueue.workspace_id == workspace_id,
            AutomationPostQueue.status == "posted",
        )
    )
    total_posts_posted = posts_result.scalar() or 0

    # Total engagements (sum likes + shares + comments + views)
    eng_result = await db.execute(
        select(
            func.coalesce(func.sum(AutomationEngagement.likes), 0).label("likes"),
            func.coalesce(func.sum(AutomationEngagement.shares), 0).label("shares"),
            func.coalesce(func.sum(AutomationEngagement.comments), 0).label("comments"),
            func.coalesce(func.sum(AutomationEngagement.views), 0).label("views"),
        )
    )
    eng_row = eng_result.one()
    total_engagements = int(eng_row.likes + eng_row.shares + eng_row.comments + eng_row.views)

    # Top performing platform (most posted)
    top_platform_result = await db.execute(
        select(AutomationPostQueue.platform, func.count(AutomationPostQueue.id).label("cnt"))
        .where(
            AutomationPostQueue.workspace_id == workspace_id,
            AutomationPostQueue.status == "posted",
        )
        .group_by(AutomationPostQueue.platform)
        .order_by(func.count(AutomationPostQueue.id).desc())
        .limit(1)
    )
    top_platform_row = top_platform_result.first()
    top_platform = top_platform_row.platform if top_platform_row else None

    return {
        "avgRating": avg_rating,
        "totalFeedback": total_feedback,
        "pendingReplies": pending_replies,
        "totalPostsPosted": total_posts_posted,
        "totalEngagements": total_engagements,
        "topPlatform": top_platform,
    }
