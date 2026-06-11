"""
Groq text-LLM normalization pass for raw article candidates.

Takes the raw articles from the assembler (which may have broken
hyphenation, OCR artifacts, mis-split headlines) and:
  - Cleans headline and body text
  - Detects language (2-letter ISO)
  - Identifies section (Politics / Business / Sports / ...)
  - Returns the same list in the same order, fields updated in-place

Uses llama-3.1-8b-instant (cheap and fast text model) in batches of 8.
Falls back gracefully to the unmodified input on any Groq failure.
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_MODEL = "llama-3.1-8b-instant"
_SYSTEM = """\
You receive a JSON list of newspaper article candidates extracted via PDF parsing.
Each has a "headline" and "body" that may have broken hyphenation, run-together words,
or stray characters from the extraction process.

For EACH article:
1. Clean the headline: fix obvious word-breaks, remove stray punctuation.
2. Clean the body: join broken lines, fix hyphenation at line ends.
3. Detect language as a 2-letter ISO code (en/te/hi/ta/ml/kn/bn/gu/mr/pa/ur).
4. Identify section: one of Politics, Business, Sports, National, Local, International, Opinion, Other.

Return ONLY valid JSON (no markdown fences):
{"articles": [{"headline": "...", "body": "...", "language": "xx", "section": "..."}]}

Keep the same count and order as input. Never drop or merge articles."""


async def normalize_articles(
    articles: list[dict],
    detected_language: str = "en",
    batch_size: int = 8,
) -> list[dict]:
    """
    Run a Groq text-LLM normalization pass over the assembled articles.
    Returns the same-length list with updated headline/text/detected_language/section.
    Falls back to the original list on any error.
    """
    if not articles:
        return []

    try:
        from backend.nlp.groq_client import groq_manager
    except Exception as exc:
        logger.warning("groq_manager unavailable — skipping normalization: %s", exc)
        return articles

    out: list[dict] = []
    for i in range(0, len(articles), batch_size):
        batch = articles[i : i + batch_size]
        out.extend(await _normalize_batch(batch, groq_manager, detected_language))
    return out


async def _normalize_batch(
    batch: list[dict],
    groq_manager: Any,
    language: str,
) -> list[dict]:
    # Send up to 2000 chars of body for language/section context.
    # The original full body is preserved below — LLM output only overwrites
    # headline (cleaned) + detected_language + section. Body stays canonical.
    payload = [
        {
            "headline": a.get("headline", ""),
            "body": (a.get("text") or "")[:2000],
        }
        for a in batch
    ]
    user_msg = f"Language hint: {language}\n\n{json.dumps(payload, ensure_ascii=False)}"

    for attempt in range(2):
        try:
            key_index, client = await groq_manager.get_key()
        except Exception as exc:
            logger.warning("No Groq key available: %s", exc)
            return batch

        try:
            resp = await client.chat.completions.create(
                model=_MODEL,
                messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": user_msg},
                ],
                max_tokens=2048,
                temperature=0.1,
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            logger.warning("Groq normalize attempt %d failed: %s", attempt + 1, exc)
            continue

        content = (resp.choices[0].message.content or "").strip()
        try:
            data = json.loads(content)
            normed = data.get("articles") or []
            if len(normed) != len(batch):
                logger.warning(
                    "Normalizer returned %d items for %d inputs — using raw",
                    len(normed), len(batch),
                )
                return batch

            result: list[dict] = []
            for orig, n in zip(batch, normed):
                merged = {**orig}
                # Headline: use LLM cleaned version if non-empty
                merged["headline"] = (n.get("headline") or "").strip() or orig.get("headline", "")
                # Body: always keep the original full text — LLM only saw [:2000]
                merged["text"] = orig.get("text", "")
                merged["detected_language"] = (n.get("language") or language).strip()
                merged["section"] = (n.get("section") or orig.get("section") or "").strip()
                result.append(merged)
            return result

        except Exception as exc:
            logger.warning("Normalizer JSON parse failed: %s (content[:100]=%s)", exc, content[:100])

    return batch
