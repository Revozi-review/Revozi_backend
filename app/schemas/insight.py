import uuid
from datetime import date, datetime

from pydantic import BaseModel


class TopIssue(BaseModel):
    label: str
    count: int
    percentage: float
    trend: str  # up, down, stable


class InsightResponse(BaseModel):
    id: uuid.UUID
    workspaceId: uuid.UUID
    topIssues: list[TopIssue]
    weeklySummary: str
    weekStart: date
    weekEnd: date
    generatedAt: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_insight(cls, i) -> "InsightResponse":
        return cls(
            id=i.id,
            workspaceId=i.workspace_id,
            topIssues=[TopIssue(**issue) for issue in (i.top_issues or [])],
            weeklySummary=i.weekly_summary,
            weekStart=i.week_start,
            weekEnd=i.week_end,
            generatedAt=i.generated_at,
        )
