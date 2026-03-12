"""Seed script to create a demo test account with sample data.

Usage: python -m scripts.seed
Requires: PostgreSQL running with the revozi database created and migrations applied.
"""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone, date

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.core.config import settings
from app.core.database import Base
from app.core.security import hash_password
from app.models.user import User
from app.models.workspace import Workspace
from app.models.feedback import Feedback, FeedbackAnalysis, DraftReply
from app.models.subscription import Subscription
from app.models.insight import Insight

DEMO_EMAIL = "demo@revozi.com"
DEMO_PASSWORD = "demo123"

SAMPLE_FEEDBACK = [
    {
        "author": "Sarah M.",
        "content": "Absolutely love this service! The team went above and beyond to help me. Fast response times and very professional. Will definitely recommend to friends.",
        "rating": 5,
        "sentiment": "positive",
        "risk_level": "low",
    },
    {
        "author": "James K.",
        "content": "Waited over 45 minutes for what should have been a 10-minute job. Staff seemed disorganized and unfriendly. Very disappointed with the experience.",
        "rating": 2,
        "sentiment": "negative",
        "risk_level": "medium",
    },
    {
        "author": "Priya R.",
        "content": "Good overall but the pricing feels a bit high compared to competitors. The quality is there but I'm not sure if the value matches the cost.",
        "rating": 3,
        "sentiment": "neutral",
        "risk_level": "low",
    },
    {
        "author": "Tom W.",
        "content": "Terrible experience. Product arrived broken and nobody will respond to my emails. Considering filing a complaint. This is unacceptable.",
        "rating": 1,
        "sentiment": "negative",
        "risk_level": "high",
    },
    {
        "author": "Emma L.",
        "content": "Really nice atmosphere and the staff are always friendly. My only suggestion would be to extend opening hours on weekends.",
        "rating": 4,
        "sentiment": "positive",
        "risk_level": "low",
    },
]


async def seed():
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as db:
        # Create demo user
        user = User(
            email=DEMO_EMAIL,
            password_hash=hash_password(DEMO_PASSWORD),
            first_name="Demo",
            last_name="User",
            role="admin",
            email_verified=True,
        )
        db.add(user)
        await db.flush()
        print(f"Created demo user: {DEMO_EMAIL} / {DEMO_PASSWORD}")

        # Create workspace
        workspace = Workspace(
            name="Demo Workspace",
            slug=f"demo-workspace-{uuid.uuid4().hex[:6]}",
            owner_id=user.id,
            plan="pro",
            brand_tone="friendly",
            onboarding_complete=True,
        )
        db.add(workspace)
        await db.flush()
        print(f"Created workspace: {workspace.name}")

        # Create subscription
        sub = Subscription(
            workspace_id=workspace.id,
            plan="pro",
            status="active",
            seats=5,
        )
        db.add(sub)

        # Create sample feedback with analyses and drafts
        now = datetime.now(timezone.utc)
        for i, fb_data in enumerate(SAMPLE_FEEDBACK):
            fb = Feedback(
                workspace_id=workspace.id,
                author=fb_data["author"],
                content=fb_data["content"],
                rating=fb_data["rating"],
                sentiment=fb_data["sentiment"],
                risk_level=fb_data["risk_level"],
                status="open",
                source="manual",
                created_at=now - timedelta(days=i),
                updated_at=now - timedelta(days=i),
            )
            db.add(fb)
            await db.flush()

            # Add analysis
            analysis = FeedbackAnalysis(
                feedback_id=fb.id,
                summary=f"Customer feedback from {fb_data['author']} with {fb_data['sentiment']} sentiment.",
                key_issues=["See full analysis with LLM API key configured"],
                suggested_actions=["Review feedback", "Follow up with customer"],
                topics_detected=["service", "quality"],
                is_generating=False,
            )
            db.add(analysis)

            # Add drafts
            for tone, content in [
                ("short", "Thank you for your feedback. We value your input."),
                ("empathetic", "Thank you for sharing your experience. We hear you and appreciate you taking the time to let us know. Your feedback helps us improve."),
                ("neutral", "We acknowledge your feedback and have forwarded it to the relevant team for review. Thank you for bringing this to our attention."),
            ]:
                draft = DraftReply(
                    feedback_id=fb.id,
                    content=content,
                    tone=tone,
                    is_generating=False,
                )
                db.add(draft)

        # Create an insight
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        insight = Insight(
            workspace_id=workspace.id,
            top_issues=[
                {"label": "service", "count": 3, "percentage": 42.9, "trend": "stable"},
                {"label": "quality", "count": 2, "percentage": 28.6, "trend": "up"},
                {"label": "pricing", "count": 1, "percentage": 14.3, "trend": "stable"},
                {"label": "communication", "count": 1, "percentage": 14.3, "trend": "down"},
            ],
            weekly_summary="This week: 5 feedback items received. 2 positive, 1 neutral, 2 negative. Most discussed topic: service.",
            week_start=week_start,
            week_end=week_start + timedelta(days=6),
        )
        db.add(insight)

        await db.commit()
        print(f"Seeded {len(SAMPLE_FEEDBACK)} feedback items with analyses and drafts")
        print(f"Created insight for week of {week_start}")
        print("\nDemo account ready!")
        print(f"  Email: {DEMO_EMAIL}")
        print(f"  Password: {DEMO_PASSWORD}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
