import json
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.feedback import Feedback, FeedbackAnalysis

logger = logging.getLogger(__name__)

ANALYSIS_PROMPT = """You are a customer feedback analyst for a business. Analyze the following customer feedback and return a structured JSON response.

Feedback:
---
{content}
---

Rating: {rating}

Return ONLY valid JSON with this exact structure:
{{
  "summary": "A concise 1-2 sentence summary of the feedback",
  "sentiment": "positive" | "neutral" | "negative",
  "risk_level": "low" | "medium" | "high" | "critical",
  "key_issues": ["issue1", "issue2"],
  "suggested_actions": ["action1", "action2"],
  "topics_detected": ["topic1", "topic2"]
}}

Rules:
- sentiment must be one of: positive, neutral, negative
- risk_level: low (praise/minor), medium (complaints), high (threats to leave/legal), critical (safety/legal/media risk)
- key_issues: list the specific problems mentioned (empty list if none)
- suggested_actions: practical steps the business could take
- topics_detected: categories like "service", "pricing", "delay", "communication", "quality", "staff", "product", "cleanliness", etc.
- Use neutral, non-judgmental language
- Do not include PII in the summary"""


async def analyze_feedback(feedback_id: UUID, db: AsyncSession) -> FeedbackAnalysis | None:
    result = await db.execute(select(Feedback).where(Feedback.id == feedback_id))
    feedback = result.scalar_one_or_none()
    if not feedback:
        logger.error(f"Feedback {feedback_id} not found for analysis")
        return None

    # Check if analysis already exists
    existing = await db.execute(
        select(FeedbackAnalysis).where(FeedbackAnalysis.feedback_id == feedback_id)
    )
    if existing.scalar_one_or_none():
        logger.info(f"Analysis already exists for feedback {feedback_id}")
        return None

    # Create a placeholder analysis while generating
    analysis = FeedbackAnalysis(
        feedback_id=feedback_id,
        summary="Analyzing...",
        key_issues=[],
        suggested_actions=[],
        topics_detected=[],
        is_generating=True,
    )
    db.add(analysis)
    await db.flush()

    try:
        prompt = ANALYSIS_PROMPT.format(
            content=feedback.content,
            rating=feedback.rating or "Not provided",
        )
        result_json = await _call_llm(prompt)

        analysis.summary = result_json.get("summary", "Analysis could not be completed")
        analysis.key_issues = result_json.get("key_issues", [])
        analysis.suggested_actions = result_json.get("suggested_actions", [])
        analysis.topics_detected = result_json.get("topics_detected", [])
        analysis.is_generating = False

        # Update feedback sentiment and risk from analysis
        if result_json.get("sentiment"):
            feedback.sentiment = result_json["sentiment"]
        if result_json.get("risk_level"):
            feedback.risk_level = result_json["risk_level"]

        await db.flush()
        return analysis

    except Exception as e:
        logger.error(f"Analysis failed for feedback {feedback_id}: {e}")
        analysis.summary = "Analysis could not be completed at this time."
        analysis.is_generating = False
        await db.flush()
        return analysis


async def _call_llm(prompt: str) -> dict:
    # Try OpenAI first (primary), then Anthropic as fallback
    if settings.OPENAI_API_KEY:
        return await _call_openai(prompt)
    elif settings.ANTHROPIC_API_KEY:
        return await _call_anthropic(prompt)
    else:
        return _heuristic_analysis(prompt)


async def _call_anthropic(prompt: str) -> dict:
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    message = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    text = message.content[0].text
    return json.loads(text)


async def _call_openai(prompt: str) -> dict:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    text = response.choices[0].message.content
    return json.loads(text)


def _heuristic_analysis(prompt: str) -> dict:
    """Basic keyword-based analysis when no LLM API key is configured."""
    content_lower = prompt.lower()

    negative_words = ["terrible", "awful", "worst", "horrible", "disappointed", "angry", "frustrated", "unacceptable", "rude", "never again"]
    positive_words = ["great", "excellent", "amazing", "wonderful", "love", "fantastic", "best", "perfect", "outstanding", "recommend"]

    neg_count = sum(1 for w in negative_words if w in content_lower)
    pos_count = sum(1 for w in positive_words if w in content_lower)

    if neg_count > pos_count:
        sentiment = "negative"
        risk_level = "high" if neg_count >= 3 else "medium"
    elif pos_count > neg_count:
        sentiment = "positive"
        risk_level = "low"
    else:
        sentiment = "neutral"
        risk_level = "low"

    topics = []
    topic_keywords = {
        "service": ["service", "staff", "employee", "help"],
        "pricing": ["price", "cost", "expensive", "cheap", "value", "money"],
        "quality": ["quality", "broken", "defect", "work"],
        "delay": ["wait", "slow", "late", "delay", "time"],
        "communication": ["respond", "reply", "contact", "call", "email"],
    }
    for topic, keywords in topic_keywords.items():
        if any(k in content_lower for k in keywords):
            topics.append(topic)

    return {
        "summary": "Feedback received and categorized using basic analysis. Configure an LLM API key for detailed analysis.",
        "sentiment": sentiment,
        "risk_level": risk_level,
        "key_issues": ["Detailed analysis requires LLM API key"],
        "suggested_actions": ["Review feedback manually", "Configure LLM API key for automated analysis"],
        "topics_detected": topics or ["general"],
    }
