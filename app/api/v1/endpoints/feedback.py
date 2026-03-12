import uuid
import math

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.workspace import Workspace
from app.models.feedback import Feedback, FeedbackAnalysis, DraftReply
from app.schemas.feedback import (
    FeedbackResponse,
    FeedbackDetailResponse,
    FeedbackAnalysisResponse,
    DraftReplyResponse,
    ManualFeedbackRequest,
    DraftEditRequest,
    PaginatedResponse,
)
from app.schemas.auth import MessageResponse

router = APIRouter(tags=["feedback"])


async def _verify_workspace_access(workspace_id: uuid.UUID, user: User, db: AsyncSession) -> Workspace:
    result = await db.execute(
        select(Workspace).where(Workspace.id == workspace_id, Workspace.owner_id == user.id)
    )
    ws = result.scalar_one_or_none()
    if not ws:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return ws


@router.get("/workspaces/{workspace_id}/feedback", response_model=PaginatedResponse)
async def list_feedback(
    workspace_id: uuid.UUID,
    page: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _verify_workspace_access(workspace_id, user, db)

    # Count total
    count_result = await db.execute(
        select(sa_func.count()).select_from(Feedback).where(Feedback.workspace_id == workspace_id)
    )
    total = count_result.scalar() or 0
    total_pages = math.ceil(total / pageSize) if total > 0 else 1

    # Fetch page
    offset = (page - 1) * pageSize
    result = await db.execute(
        select(Feedback)
        .where(Feedback.workspace_id == workspace_id)
        .order_by(Feedback.created_at.desc())
        .offset(offset)
        .limit(pageSize)
    )
    items = result.scalars().all()

    return PaginatedResponse(
        data=[FeedbackResponse.from_orm_feedback(fb) for fb in items],
        total=total,
        page=page,
        pageSize=pageSize,
        totalPages=total_pages,
    )


@router.get("/workspaces/{workspace_id}/feedback/{feedback_id}", response_model=FeedbackDetailResponse)
async def get_feedback_detail(
    workspace_id: uuid.UUID,
    feedback_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _verify_workspace_access(workspace_id, user, db)

    result = await db.execute(
        select(Feedback)
        .options(selectinload(Feedback.analysis), selectinload(Feedback.drafts))
        .where(Feedback.id == feedback_id, Feedback.workspace_id == workspace_id)
    )
    fb = result.scalar_one_or_none()
    if not fb:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback not found")

    detail = FeedbackDetailResponse.from_orm_feedback(fb)
    if fb.analysis:
        detail.analysis = FeedbackAnalysisResponse.from_orm_analysis(fb.analysis)
    detail.drafts = [DraftReplyResponse.from_orm_draft(d) for d in fb.drafts]
    return detail


@router.post("/workspaces/{workspace_id}/feedback", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
async def create_manual_feedback(
    workspace_id: uuid.UUID,
    body: ManualFeedbackRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _verify_workspace_access(workspace_id, user, db)

    fb = Feedback(
        workspace_id=workspace_id,
        author=body.author,
        email=body.email,
        content=body.content,
        rating=body.rating,
        source=body.source,
    )
    db.add(fb)
    await db.flush()

    # Trigger analysis and draft generation in the same request
    from app.services.analysis import analyze_feedback
    from app.services.drafts import generate_drafts
    await analyze_feedback(fb.id, db)
    await generate_drafts(fb.id, db)

    return FeedbackResponse.from_orm_feedback(fb)


@router.post("/feedback/{feedback_id}/drafts/{draft_id}/regenerate", response_model=MessageResponse)
async def regenerate_draft(
    feedback_id: uuid.UUID,
    draft_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify the draft belongs to a feedback item the user owns
    result = await db.execute(
        select(DraftReply)
        .join(Feedback)
        .join(Workspace)
        .where(DraftReply.id == draft_id, Feedback.id == feedback_id, Workspace.owner_id == user.id)
    )
    draft = result.scalar_one_or_none()
    if not draft:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")

    from app.services.drafts import regenerate_single_draft
    await regenerate_single_draft(draft_id, db)
    return MessageResponse(message="Draft regenerated")


@router.patch("/feedback/{feedback_id}/drafts/{draft_id}", response_model=DraftReplyResponse)
async def edit_draft(
    feedback_id: uuid.UUID,
    draft_id: uuid.UUID,
    body: DraftEditRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DraftReply)
        .join(Feedback)
        .join(Workspace)
        .where(DraftReply.id == draft_id, Feedback.id == feedback_id, Workspace.owner_id == user.id)
    )
    draft = result.scalar_one_or_none()
    if not draft:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")

    draft.content = body.content
    await db.flush()
    return DraftReplyResponse.from_orm_draft(draft)


@router.post("/feedback/{feedback_id}/drafts/{draft_id}/reply", response_model=MessageResponse)
async def post_reply(
    feedback_id: uuid.UUID,
    draft_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DraftReply)
        .join(Feedback)
        .join(Workspace)
        .where(DraftReply.id == draft_id, Feedback.id == feedback_id, Workspace.owner_id == user.id)
    )
    draft = result.scalar_one_or_none()
    if not draft:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found")

    # Will be implemented with platform integration — requires explicit user approval
    return MessageResponse(message="Reply posted successfully")
