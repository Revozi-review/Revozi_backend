import json
import logging
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.feedback import Feedback, FeedbackAnalysis
from app.models.insight import Insight

logger = logging.getLogger(__name__)


async def generate_weekly_insight(workspace_id: UUID, db: AsyncSession) -> Insight | None:
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    # Check if insight already exists for this week
    existing = await db.execute(
        select(Insight).where(
            Insight.workspace_id == workspace_id,
            Insight.week_start == week_start,
        )
    )
    if existing.scalar_one_or_none():
        return None

    # Get feedback for this week
    result = await db.execute(
        select(Feedback).where(
            Feedback.workspace_id == workspace_id,
            Feedback.created_at >= str(week_start),
            Feedback.created_at <= str(week_end + timedelta(days=1)),
        )
    )
    feedback_items = result.scalars().all()

    if not feedback_items:
        return None

    # Get analyses for these feedback items
    feedback_ids = [fb.id for fb in feedback_items]
    analyses_result = await db.execute(
        select(FeedbackAnalysis).where(FeedbackAnalysis.feedback_id.in_(feedback_ids))
    )
    analyses = analyses_result.scalars().all()

    # Aggregate topics
    topic_counts: dict[str, int] = {}
    for analysis in analyses:
        for topic in (analysis.topics_detected or []):
            topic_counts[topic] = topic_counts.get(topic, 0) + 1

    total_topics = sum(topic_counts.values()) or 1
    top_issues = []
    for label, count in sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
        top_issues.append({
            "label": label,
            "count": count,
            "percentage": round((count / total_topics) * 100, 1),
            "trend": "stable",
        })

    # Generate summary
    total = len(feedback_items)
    sentiments = {"positive": 0, "neutral": 0, "negative": 0}
    for fb in feedback_items:
        if fb.sentiment in sentiments:
            sentiments[fb.sentiment] += 1

    summary = (
        f"This week: {total} feedback items received. "
        f"{sentiments['positive']} positive, {sentiments['neutral']} neutral, {sentiments['negative']} negative. "
    )
    if top_issues:
        top_topic = top_issues[0]["label"]
        summary += f"Most discussed topic: {top_topic}."

    insight = Insight(
        workspace_id=workspace_id,
        top_issues=top_issues,
        weekly_summary=summary,
        week_start=week_start,
        week_end=week_end,
    )
    db.add(insight)
    await db.flush()
    return insight


async def get_latest_insight(workspace_id: UUID, db: AsyncSession) -> Insight | None:
    result = await db.execute(
        select(Insight)
        .where(Insight.workspace_id == workspace_id)
        .order_by(Insight.week_start.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
