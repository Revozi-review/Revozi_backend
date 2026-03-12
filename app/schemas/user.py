import uuid
from datetime import datetime

from pydantic import BaseModel


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    firstName: str
    lastName: str
    role: str
    avatarUrl: str | None = None
    createdAt: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_user(cls, user) -> "UserResponse":
        return cls(
            id=user.id,
            email=user.email,
            firstName=user.first_name,
            lastName=user.last_name,
            role=user.role,
            avatarUrl=user.avatar_url,
            createdAt=user.created_at,
        )
