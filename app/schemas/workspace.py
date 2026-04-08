import uuid
from datetime import datetime

from pydantic import BaseModel


class WorkspaceResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    logoUrl: str | None = None
    plan: str
    ownerId: uuid.UUID
    brandTone: str | None = None
    replyStyle: str | None = None
    businessType: str | None = None
    onboardingComplete: bool | None = None
    createdAt: datetime
    status: str | None = None
    memberCount: int | None = None
    feedbackCount: int | None = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_workspace(cls, ws, member_count: int = 1, feedback_count: int = 0) -> "WorkspaceResponse":
        return cls(
            id=ws.id,
            name=ws.name,
            slug=ws.slug,
            logoUrl=ws.logo_url,
            plan=ws.plan,
            ownerId=ws.owner_id,
            brandTone=ws.brand_tone,
            replyStyle=ws.reply_style,
            businessType=ws.business_type,
            onboardingComplete=ws.onboarding_complete,
            createdAt=ws.created_at,
            status="active",
            memberCount=member_count,
            feedbackCount=feedback_count,
        )


class WorkspaceUpdateRequest(BaseModel):
    name: str | None = None
    slug: str | None = None
    brandTone: str | None = None
    replyStyle: str | None = None
    businessType: str | None = None
    logoUrl: str | None = None
    onboardingComplete: bool | None = None


class WorkspaceNotificationsRequest(BaseModel):
    oneStarAlerts: bool | None = None
    dailySummary: bool | None = None
    weeklyPerformance: bool | None = None
