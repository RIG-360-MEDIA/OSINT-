"""
Topic classification using Groq llama-3.1-8b-instant.
Returns one of 15 fixed categories; falls back to OTHER on any error.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

VALID_TOPICS: frozenset[str] = frozenset({
    "POLITICS", "GOVERNANCE", "BUSINESS", "FINANCE", "INFRASTRUCTURE",
    "SECURITY", "HEALTH", "LEGAL", "AGRICULTURE", "INTERNATIONAL",
    "TECHNOLOGY", "ENVIRONMENT", "SOCIAL", "SPORTS", "OTHER",
})

_SYSTEM_PROMPT = (
    "Classify this article into exactly one category. "
    "Reply with ONLY the category name — no punctuation, no explanation, nothing else.\n\n"
    "Categories: POLITICS GOVERNANCE BUSINESS FINANCE INFRASTRUCTURE "
    "SECURITY HEALTH LEGAL AGRICULTURE INTERNATIONAL TECHNOLOGY "
    "ENVIRONMENT SOCIAL SPORTS OTHER"
)


async def classify_topic(
    title: str,
    lead_text_translated: str | None,
) -> str:
    """
    Classify article topic using Groq fast model.
    Uses title + first 500 chars of translated lead.
    Returns uppercase category from VALID_TOPICS.
    """
    from backend.nlp.groq_client import classify

    if lead_text_translated:
        user_text = f"Title: {title}\nText: {lead_text_translated[:500]}"
    else:
        user_text = f"Title: {title}"

    try:
        result = await classify(system=_SYSTEM_PROMPT, user=user_text)
        topic = result.strip().upper()
        if topic in VALID_TOPICS:
            return topic
        # Partial match fallback
        for valid in VALID_TOPICS:
            if valid in topic:
                return valid
        return "OTHER"
    except Exception as exc:
        logger.warning("Topic classification failed: %s", exc)
        return "OTHER"
