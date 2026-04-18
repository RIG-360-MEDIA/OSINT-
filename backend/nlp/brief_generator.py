"""
Daily intelligence brief generator.

Six sections, six concurrent Groq calls via asyncio.gather.
Each section gets role-specific prompts and targeted article context.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date

from backend.nlp.groq_client import QUALITY_MODEL, generate

logger = logging.getLogger(__name__)

# ── Section system prompts ────────────────────────────────────────────────────

SITUATION_SYSTEM = """You are an intelligence analyst writing a classified morning situation summary for a senior government official.

Write 2-3 sentences on the overall state of their monitored world today.
What is the dominant story? What is the mood? What requires immediate attention?

Rules:
- Write for the specific role provided
- No bullet points — flowing prose
- No generic phrases like "it is important to note"
- Specific, concrete, actionable
- Maximum 80 words
- Do not start with "Today" or "As of"
"""

DEVELOPMENTS_SYSTEM = """You are an intelligence analyst writing KEY DEVELOPMENTS for a classified morning brief.

Write 5-7 numbered intelligence items. Each item is 2-3 sentences.
Format:
① [Development headline]
  [2-3 sentences of intelligence prose]

Rules:
- Synthesise, do not summarise
- Connect each development to why it matters for the official's role
- Specific details: names, numbers, places, institutions
- No vague language
- Write for the role provided
"""

ENTITIES_SYSTEM = """You are writing the ENTITIES TODAY section of a classified intelligence brief.

For each entity provided that appears in today's coverage, write 2-3 sentences on what happened, what was said, what changed, and what it means.

Format:
[ENTITY NAME]
[2-3 sentences of intelligence prose]

Only include entities that actually have substantive coverage today.
Skip entities with no meaningful coverage.
"""

SIGNALS_SYSTEM = """You are writing the SIGNALS TO WATCH section of a classified intelligence brief.

Identify 2-3 developing situations from today's coverage that are not yet crises but warrant monitoring. These are early warning signals.

Format:
⚑ [Signal headline]
  [2 sentences: what is developing and why it matters]

Focus on: trajectory, not current state. What could this become?
"""

FINANCIAL_SYSTEM = """You are writing the FINANCIAL PULSE section of a classified intelligence brief.

Summarise financial and economic intelligence from today's coverage in 3-5 sentences.

Cover: state finances, scheme disbursements, central allocations, investment news, economic indicators.

If no financial content in today's coverage, write:
"No significant financial developments in today's coverage."
"""

SOURCES_SYSTEM = """You are writing the SOURCE COVERAGE section of a classified intelligence brief.

List the sources that contributed to today's brief in this format:
[Source name] — [brief description of what they covered]

Then add one sentence on coverage quality: are there any notable gaps in today's source coverage?
"""


# ── Main generator ────────────────────────────────────────────────────────────

async def generate_brief(
    user_id: str,
    user_profile: dict,
    user_entities: list[dict],
    articles: list[dict],
) -> dict:
    """
    Generate a complete daily brief for one user.

    Returns dict with:
      content: str (full markdown)
      articles_used: int
      sections: dict (individual section texts)
    """
    if not articles:
        return {
            "content": None,
            "articles_used": 0,
            "error": "No relevant articles",
        }

    role_context = user_profile.get("role_context", "Senior government official")
    geo = user_profile.get("geo_primary", "India")
    entity_names = [e["canonical_name"] for e in user_entities if e.get("canonical_name")]

    all_context = _format_articles(articles, max_articles=30)

    finance_articles = [
        a for a in articles
        if a.get("topic_category") in ("FINANCE", "BUSINESS", "INFRASTRUCTURE")
    ]
    finance_context = (
        _format_articles(finance_articles, max_articles=10)
        if finance_articles
        else all_context
    )

    sources = sorted(set(a.get("source_name", "Unknown") for a in articles))

    tasks = [
        # Section 1: Situation Status
        generate(
            system=SITUATION_SYSTEM,
            user=(
                f"Official role: {role_context}\n"
                f"Focus geography: {geo}\n"
                f"Today's top stories:\n{all_context[:2000]}"
            ),
            task_type="brief_generation",
        ),
        # Section 2: Key Developments
        generate(
            system=DEVELOPMENTS_SYSTEM,
            user=(
                f"Official role: {role_context}\n"
                f"Today's articles:\n{all_context[:3000]}"
            ),
            task_type="brief_generation",
        ),
        # Section 3: Entities Today
        generate(
            system=ENTITIES_SYSTEM,
            user=(
                f"Official role: {role_context}\n"
                f"Monitored entities: {', '.join(entity_names[:15])}\n"
                f"Today's coverage:\n{all_context[:2000]}"
            ),
            task_type="brief_generation",
        ),
        # Section 4: Signals to Watch
        generate(
            system=SIGNALS_SYSTEM,
            user=(
                f"Official role: {role_context}\n"
                f"Today's articles:\n{all_context[:2000]}"
            ),
            task_type="brief_generation",
        ),
        # Section 5: Financial Pulse
        generate(
            system=FINANCIAL_SYSTEM,
            user=(
                f"Official role: {role_context}\n"
                f"Financial articles:\n{finance_context[:2000]}"
            ),
            task_type="brief_generation",
        ),
        # Section 6: Source Coverage
        generate(
            system=SOURCES_SYSTEM,
            user=(
                f"Sources used today: {', '.join(sources)}\n"
                f"Coverage sample:\n{all_context[:1000]}"
            ),
            task_type="brief_generation",
        ),
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    section_names = [
        "SITUATION STATUS",
        "KEY DEVELOPMENTS",
        "ENTITIES TODAY",
        "SIGNALS TO WATCH",
        "FINANCIAL PULSE",
        "SOURCE COVERAGE",
    ]

    sections: dict[str, str] = {}
    for name, result in zip(section_names, results):
        if isinstance(result, Exception):
            logger.error("Section %s failed: %s", name, result)
            sections[name] = f"[Generation failed: {str(result)[:100]}]"
        else:
            sections[name] = result or "[No content generated]"

    today_str = date.today().strftime("%A, %d %B %Y")

    content = f"""# DAILY INTELLIGENCE BRIEF
## {today_str}
*Generated for: {role_context[:80]}*

---

## SITUATION STATUS

{sections["SITUATION STATUS"]}

---

## KEY DEVELOPMENTS

{sections["KEY DEVELOPMENTS"]}

---

## ENTITIES TODAY

{sections["ENTITIES TODAY"]}

---

## SIGNALS TO WATCH

{sections["SIGNALS TO WATCH"]}

---

## FINANCIAL PULSE

{sections["FINANCIAL PULSE"]}

---

## SOURCE COVERAGE

{sections["SOURCE COVERAGE"]}

---
*{len(articles)} articles · {QUALITY_MODEL} · RIG SURVEILLANCE*"""

    return {
        "content": content,
        "articles_used": len(articles),
        "sections": sections,
    }


# ── Article formatter ─────────────────────────────────────────────────────────

def _format_articles(articles: list[dict], max_articles: int = 30) -> str:
    lines: list[str] = []
    for i, a in enumerate(articles[:max_articles]):
        title = a.get("title", "")
        source = a.get("source_name", "")
        topic = a.get("topic_category", "")
        geo = a.get("geo_primary", "")
        text = (
            a.get("lead_text_translated")
            or a.get("lead_text_original")
            or ""
        )[:400]
        score = a.get("score_final") or 0

        lines.append(
            f"[{i + 1}] {title}\n"
            f"Source: {source} | Topic: {topic} | Geo: {geo} | Score: {score:.2f}\n"
            f"{text}\n"
        )

    return "\n".join(lines)
