import uuid
from datetime import datetime

from pydantic import BaseModel


class SubscriptionResponse(BaseModel):
    id: uuid.UUID
    workspaceId: uuid.UUID
    plan: str
    status: str
    renewalDate: datetime | None = None
    cancelAtPeriodEnd: bool
    seats: int

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_subscription(cls, s) -> "SubscriptionResponse":
        return cls(
            id=s.id,
            workspaceId=s.workspace_id,
            plan=s.plan,
            status=s.status,
            renewalDate=s.renewal_date,
            cancelAtPeriodEnd=s.cancel_at_period_end,
            seats=s.seats,
        )


class CheckoutRequest(BaseModel):
    workspaceId: uuid.UUID
    plan: str = "pro"


class CheckoutResponse(BaseModel):
    url: str
