import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class AdminWorkspaceResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    plan: str
    ownerId: uuid.UUID
    ownerEmail: Optional[str] = None
    createdAt: datetime
    feedbackCount: int
    memberCount: int
    locationCount: int = 0
    status: Optional[str] = "active"
    mrr: float = 0.0

    model_config = {"from_attributes": True}


class AdminPlatformConnectionResponse(BaseModel):
    id: uuid.UUID
    workspaceId: uuid.UUID
    platform: str
    connectedAt: datetime
    metadataJson: dict | None = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_connection(cls, pc):
        return cls(
            id=pc.id,
            workspaceId=pc.workspace_id,
            platform=pc.platform,
            connectedAt=pc.connected_at,
            metadataJson=pc.metadata_json
        )


class AdminPlatformConnectionCreate(BaseModel):
    platform: str
    accessToken: str | None = None
    refreshToken: str | None = None
    metadataJson: dict | None = None


class InvoiceItem(BaseModel):
    id: str
    amount: float
    status: str
    paidAt: Optional[str] = None


class AdminBillingResponse(BaseModel):
    workspaceId: uuid.UUID
    plan: str
    status: str
    billingPeriodStart: Optional[datetime] = None
    billingPeriodEnd: Optional[datetime] = None
    currentPeriodRevenue: float = 0.0
    reviewCount: int
    reviewLimit: Optional[int] = None
    overageCount: int = 0
    overageCharge: float = 0.0
    paymentMethod: Optional[str] = None
    allowOverage: bool = False
    invoiceHistory: List[InvoiceItem] = []
    # Legacy fields kept for backwards compat
    currentUsage: int = 0
    limit: int = 0
    tier: str = ""
