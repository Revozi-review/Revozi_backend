import json
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.feedback import Feedback, DraftReply
from app.models.workspace import Workspace

logger = logging.getLogger(__name__)

DRAFT_PROMPT = """You are a professional customer response writer for a business.

Business tone preference: {brand_tone}

Customer feedback:
---
{content}
---

Rating: {rating}

Generate 3 different response drafts as a JSON array. Each draft should be a different approach:
1. "short" — A concise, public-safe acknowledgement (2-3 sentences)
2. "empathetic" — A warm, empathetic repair response (3-5 sentences)
3. "neutral" — A professional, neutral acknowledgement (2-4 sentences)

Return ONLY valid JSON:
[
  {{"tone": "short", "content": "..."}},
  {{"tone": "empathetic", "content": "..."}},
  {{"tone": "neutral", "content": "..."}}
]

Rules:
- NEVER admit fault or liability on behalf of the business
- Do not make promises that cannot be kept
- Use {brand_tone} tone throughout
- Keep responses platform-safe (suitable for public posting)
- Be genuine, not formulaic
- Reference specific details from the feedback where appropriate"""


async def generate_drafts(feedback_id: UUID, db: AsyncSession) -> list[DraftReply]:
    result = await db.execute(
        select(Feedback).where(Feedback.id == feedback_id)
    )
    feedback = result.scalar_one_or_none()
    if not feedback:
        logger.error(f"Feedback {feedback_id} not found for draft generation")
        return []

    # Check if drafts already exist
    existing = await db.execute(
        select(DraftReply).where(DraftReply.feedback_id == feedback_id)
    )
    if existing.scalars().all():
        logger.info(f"Drafts already exist for feedback {feedback_id}")
        return []

    # Get workspace brand tone
    ws_result = await db.execute(
        select(Workspace).where(Workspace.id == feedback.workspace_id)
    )
    workspace = ws_result.scalar_one_or_none()
    brand_tone = workspace.brand_tone if workspace else "neutral"

    try:
        prompt = DRAFT_PROMPT.format(
            content=feedback.content,
            rating=feedback.rating or "Not provided",
            brand_tone=brand_tone,
        )
        drafts_json = await _call_llm_for_drafts(prompt)

        drafts = []
        for draft_data in drafts_json:
            draft = DraftReply(
                feedback_id=feedback_id,
                content=draft_data["content"],
                tone=draft_data["tone"],
                is_generating=False,
            )
            db.add(draft)
            drafts.append(draft)

        await db.flush()
        return drafts

    except Exception as e:
        logger.error(f"Draft generation failed for feedback {feedback_id}: {e}")
        # Create fallback drafts
        return await _create_fallback_drafts(feedback_id, feedback.content, brand_tone, db)


async def regenerate_single_draft(draft_id: UUID, db: AsyncSession) -> DraftReply | None:
    result = await db.execute(
        select(DraftReply).where(DraftReply.id == draft_id)
    )
    draft = result.scalar_one_or_none()
    if not draft:
        return None

    fb_result = await db.execute(select(Feedback).where(Feedback.id == draft.feedback_id))
    feedback = fb_result.scalar_one_or_none()
    if not feedback:
        return None

    ws_result = await db.execute(select(Workspace).where(Workspace.id == feedback.workspace_id))
    workspace = ws_result.scalar_one_or_none()
    brand_tone = workspace.brand_tone if workspace else "neutral"

    prompt = f"""You are a professional customer response writer. Business tone: {brand_tone}

Customer feedback: {feedback.content}
Rating: {feedback.rating or 'Not provided'}

Generate a single {draft.tone} response draft. Return ONLY the response text, no JSON wrapping.

Rules: Never admit fault. Use {brand_tone} tone. Keep it platform-safe."""

    try:
        if settings.OPENAI_API_KEY:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
            )
            draft.content = response.choices[0].message.content
        elif settings.ANTHROPIC_API_KEY:
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
            message = await client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )
            draft.content = message.content[0].text
        else:
            draft.content = "Thank you for your feedback. We appreciate you taking the time to share your experience with us."

        draft.is_generating = False
        await db.flush()
        return draft

    except Exception as e:
        logger.error(f"Draft regeneration failed: {e}")
        return draft


async def _call_llm_for_drafts(prompt: str) -> list[dict]:
    if settings.OPENAI_API_KEY:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content)
        # OpenAI json_object mode wraps in an object
        if isinstance(result, dict) and "drafts" in result:
            return result["drafts"]
        if isinstance(result, list):
            return result
        return list(result.values())[0] if isinstance(result, dict) else []
    elif settings.ANTHROPIC_API_KEY:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        message = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return json.loads(message.content[0].text)
    else:
        return _fallback_drafts()


def _fallback_drafts() -> list[dict]:
    return [
        {
            "tone": "short",
            "content": "Thank you for your feedback. We value your input and will use it to improve our service.",
        },
        {
            "tone": "empathetic",
            "content": "Thank you for taking the time to share your experience with us. We understand how important this is to you, and we want you to know that your feedback has been heard. Our team is reviewing your comments and we're committed to making improvements based on what you've shared.",
        },
        {
            "tone": "neutral",
            "content": "We appreciate you sharing your feedback. Your comments have been noted and forwarded to the relevant team for review. Should you wish to discuss this further, please don't hesitate to reach out.",
        },
    ]


async def _create_fallback_drafts(feedback_id: UUID, content: str, brand_tone: str, db: AsyncSession) -> list[DraftReply]:
    fallback = _fallback_drafts()
    drafts = []
    for d in fallback:
        draft = DraftReply(
            feedback_id=feedback_id,
            content=d["content"],
            tone=d["tone"],
            is_generating=False,
        )
        db.add(draft)
        drafts.append(draft)
    await db.flush()
    return drafts
