import uuid
from typing import List

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_user, get_db
from app.models.feedback import DraftReply, Feedback
from app.models.user import User

router = APIRouter(tags=["social-publish"])

VALID_PLATFORMS = {"instagram", "twitter", "tiktok", "facebook", "reddit", "telegram", "pinterest", "gmb"}


class PublishToSocialRequest(BaseModel):
    platforms: List[str]


@router.post("/feedback/{feedback_id}/drafts/{draft_id}/publish-social")
async def publish_reply_to_social(
    feedback_id: uuid.UUID,
    draft_id: uuid.UUID,
    body: PublishToSocialRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Takes an approved Revozi draft reply and schedules it as a post on the
    specified social platforms via the automation service.
    """
    # Validate platforms
    invalid = set(body.platforms) - VALID_PLATFORMS
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid platforms: {', '.join(invalid)}. Valid: {', '.join(sorted(VALID_PLATFORMS))}",
        )

    # Load the draft and verify it belongs to this user's workspace
    result = await db.execute(
        select(DraftReply, Feedback)
        .join(Feedback, DraftReply.feedback_id == Feedback.id)
        .where(DraftReply.id == draft_id, DraftReply.feedback_id == feedback_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")

    draft, feedback = row

    # Verify workspace ownership via the feedback's workspace
    from app.models.workspace import Workspace
    ws = await db.get(Workspace, feedback.workspace_id)
    if not ws or ws.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # Schedule a post for each selected platform via the automation proxy
    scheduled_ids = []
    async with httpx.AsyncClient(timeout=15.0) as client:
        for platform in body.platforms:
            resp = await client.post(
                f"{settings.AUTOMATION_SERVICE_URL}/admin/schedule-post",
                json={
                    "platform": platform,
                    "caption": draft.content,
                    "workspace_id": str(feedback.workspace_id),
                },
                headers={
                    "X-Revozi-User-Id": str(user.id),
                    "X-Revozi-Workspace-Id": str(feedback.workspace_id),
                    "X-Internal-Secret": settings.INTERNAL_SECRET,
                },
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                scheduled_ids.append({"platform": platform, "postId": data.get("id")})

    return {"scheduled": scheduled_ids, "total": len(scheduled_ids)}
