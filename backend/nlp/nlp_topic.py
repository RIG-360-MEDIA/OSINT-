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


# =====================================================================
# topic_fine — richer 25-bucket taxonomy (additive).
#
# Written to the NEW articles.topic_fine column (migration 084). The
# original classify_topic above and articles.topic_category are LEFT
# UNTOUCHED so existing consumers keep working byte-for-byte. The two
# improvements here — a don't-hedge instruction and India-aware buckets
# (WELFARE / ENTERTAINMENT / CRIME / EDUCATION / ...) — rescue most of
# what the old 15-bucket classifier dumped into OTHER.
# =====================================================================

VALID_TOPICS_FINE: frozenset[str] = frozenset({
    # Original 15
    "POLITICS", "GOVERNANCE", "BUSINESS", "FINANCE", "INFRASTRUCTURE",
    "SECURITY", "HEALTH", "LEGAL", "AGRICULTURE", "INTERNATIONAL",
    "TECHNOLOGY", "ENVIRONMENT", "SOCIAL", "SPORTS", "OTHER",
    # Added 10
    "WELFARE", "DEFENCE", "CRIME", "EDUCATION", "DISASTER",
    "SCIENCE", "ENTERTAINMENT", "RELIGION", "LIFESTYLE", "OBITUARY",
})

# Collapse a fine bucket to one of the original 15 (mirror of
# topic_categories.rolls_up_to). Buckets not in the map are already one
# of the original 15 and roll up to themselves.
FINE_TO_COARSE: dict[str, str] = {
    "WELFARE": "GOVERNANCE",
    "DEFENCE": "SECURITY",
    "CRIME": "SECURITY",
    "EDUCATION": "SOCIAL",
    "DISASTER": "ENVIRONMENT",
    "SCIENCE": "TECHNOLOGY",
    "ENTERTAINMENT": "SOCIAL",
    "RELIGION": "SOCIAL",
    "LIFESTYLE": "SOCIAL",
    "OBITUARY": "SOCIAL",
}

# "/no_think" disables qwen3's chain-of-thought so the model returns the
# bare category (cleaner parse + far fewer tokens — this is a one-word
# classification, no reasoning needed).
_SYSTEM_PROMPT_FINE = (
    "/no_think\n"
    "You are a precise news topic classifier for Indian and international "
    "news. Classify the article into EXACTLY ONE category from the list "
    "below. Choose the single best-fitting category. Use OTHER ONLY when "
    "genuinely nothing else fits — never choose OTHER out of uncertainty. "
    "Reply with ONLY the category name in uppercase. No punctuation, no "
    "explanation.\n\n"
    "Categories:\n"
    "POLITICS - party politics, elections, legislators, govt formation\n"
    "GOVERNANCE - policy, administration, bureaucracy, govt programs\n"
    "WELFARE - ration, pensions, subsidies, scholarships, welfare schemes\n"
    "BUSINESS - companies, corporate deals, industry, trade\n"
    "FINANCE - stocks, banking, earnings, RBI, mutual funds, economy\n"
    "INFRASTRUCTURE - roads, rail, metro, power, water, construction\n"
    "SECURITY - military ops, terrorism, border, internal security\n"
    "DEFENCE - armed forces, weapons, defence deals, military exercises\n"
    "CRIME - murder, theft, fraud, arrests, police cases\n"
    "LEGAL - court judgments, litigation, judiciary, constitutional law\n"
    "HEALTH - disease, hospitals, medicine, public health\n"
    "EDUCATION - schools, universities, exams, results, admissions\n"
    "AGRICULTURE - farming, crops, farmers, MSP, irrigation\n"
    "ENVIRONMENT - climate, pollution, wildlife, forests, conservation\n"
    "DISASTER - floods, earthquakes, accidents, fires, cyclones, rescue\n"
    "TECHNOLOGY - IT, software, AI, gadgets, internet, startups\n"
    "SCIENCE - research, space, ISRO, discoveries, scientific studies\n"
    "INTERNATIONAL - foreign affairs, diplomacy, world events\n"
    "SPORTS - cricket, football, IPL, tournaments, athletes\n"
    "ENTERTAINMENT - films, music, celebrities, OTT, TV, cinema\n"
    "RELIGION - temples, festivals, religious events, faith\n"
    "SOCIAL - society, caste, gender, communities, human interest\n"
    "LIFESTYLE - food, travel, fashion, wellness, culture\n"
    "OBITUARY - deaths, tributes, passing of notable people\n"
    "OTHER - genuinely none of the above\n\n"
    "Examples:\n"
    "Title: IPL 2026: RCB beat CSK by 5 wickets => SPORTS\n"
    "Title: State govt launches new ration card scheme for poor families => WELFARE\n"
    "Title: Top actor's new film crosses 100 crore at box office => ENTERTAINMENT\n"
    "Title: Group-1 exam results declared, cutoffs released => EDUCATION\n"
    "Title: Three killed as car rams truck on highway => DISASTER\n"
    "Title: Man arrested for ATM card fraud => CRIME\n"
    "Title: Temple festival draws lakhs of devotees => RELIGION\n"
)


async def classify_topic_fine(
    title: str,
    lead_text_translated: str | None,
) -> str:
    """
    Classify into the richer 25-bucket taxonomy (articles.topic_fine).

    Returns an uppercase member of VALID_TOPICS_FINE; "OTHER" on error.
    Additive sibling of classify_topic — does not affect topic_category.
    """
    from backend.nlp.groq_client import classify

    if lead_text_translated:
        user_text = f"Title: {title}\nText: {lead_text_translated[:500]}"
    else:
        user_text = f"Title: {title}"

    try:
        result = await classify(system=_SYSTEM_PROMPT_FINE, user=user_text)
        topic = result.strip().upper()
        if topic in VALID_TOPICS_FINE:
            return topic
        # Partial-match fallback: longest valid token contained in the
        # reply (guards against stray reasoning/punctuation around it).
        matches = sorted(
            (v for v in VALID_TOPICS_FINE if v in topic),
            key=len,
            reverse=True,
        )
        return matches[0] if matches else "OTHER"
    except Exception as exc:
        logger.warning("Fine topic classification failed: %s", exc)
        return "OTHER"


def coarse_from_fine(topic_fine: str) -> str:
    """Collapse a topic_fine value to one of the original 15 buckets."""
    return FINE_TO_COARSE.get(topic_fine, topic_fine)
