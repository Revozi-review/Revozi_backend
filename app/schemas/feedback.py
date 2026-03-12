import uuid
from datetime import datetime

from pydantic import BaseModel


class FeedbackResponse(BaseModel):
    id: uuid.UUID
    workspaceId: uuid.UUID
    author: str
    email: str | None = None
    content: str
    rating: int | None = None
    sentiment: str | None = None
    riskLevel: str
    status: str
    source: str
    createdAt: datetime
    updatedAt: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_feedback(cls, fb) -> "FeedbackResponse":
        return cls(
            id=fb.id,
            workspaceId=fb.workspace_id,
            author=fb.author,
            email=fb.email,
            content=fb.content,
            rating=fb.rating,
            sentiment=fb.sentiment,
            riskLevel=fb.risk_level,
            status=fb.status,
            source=fb.source,
            createdAt=fb.created_at,
            updatedAt=fb.updated_at,
        )


class FeedbackAnalysisResponse(BaseModel):
    id: uuid.UUID
    feedbackId: uuid.UUID
    summary: str
    keyIssues: list[str]
    suggestedActions: list[str]
    topicsDetected: list[str]
    isGenerating: bool
    createdAt: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_analysis(cls, a) -> "FeedbackAnalysisResponse":
        return cls(
            id=a.id,
            feedbackId=a.feedback_id,
            summary=a.summary,
            keyIssues=a.key_issues or [],
            suggestedActions=a.suggested_actions or [],
            topicsDetected=a.topics_detected or [],
            isGenerating=a.is_generating,
            createdAt=a.created_at,
        )


class DraftReplyResponse(BaseModel):
    id: uuid.UUID
    feedbackId: uuid.UUID
    content: str
    tone: str
    isGenerating: bool
    createdAt: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_draft(cls, d) -> "DraftReplyResponse":
        return cls(
            id=d.id,
            feedbackId=d.feedback_id,
            content=d.content,
            tone=d.tone,
            isGenerating=d.is_generating,
            createdAt=d.created_at,
        )


class FeedbackDetailResponse(FeedbackResponse):
    analysis: FeedbackAnalysisResponse | None = None
    drafts: list[DraftReplyResponse] = []


class ManualFeedbackRequest(BaseModel):
    author: str
    email: str | None = None
    content: str
    rating: int | None = None
    source: str = "manual"


class DraftEditRequest(BaseModel):
    content: str


class PaginatedResponse(BaseModel):
    data: list
    total: int
    page: int
    pageSize: int
    totalPages: int
