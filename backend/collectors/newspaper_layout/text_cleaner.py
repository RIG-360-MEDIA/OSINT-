"""
Guarded LLM clean-up for crop-OCR article body text.

Crop-OCR yields the full article prose but with (a) character-level OCR errors
and (b) embedded infographic/chart fragments that colour filtering can't catch
(black-on-white chart labels). An LLM can fix spelling and strip chart
fragments — but LLMs tend to *summarise* newspaper text, silently deleting
sentences.

Guard: we keep the result ONLY if it preserves most of the input length.
If the model shrank the text below `min_ratio`, it summarised — we reject the
clean text and fall back to the raw OCR. The raw text is always the stored
source of truth; the cleaned text is a display-only convenience.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

_MODEL = "qwen/qwen3-32b"

_PROMPT = (
    "Below is OCR text of ONE newspaper article. It contains the article prose "
    "plus possible chart/infographic labels and OCR spelling errors. Produce the "
    "clean article body:\n"
    "  - Fix obvious OCR spelling errors and broken hyphenation.\n"
    "  - Remove embedded chart/infographic fragments, stray labels, 'SOURCE:' "
    "lines, and jump references like '>> 3'.\n"
    "  - Keep EVERY article sentence, in order. Do NOT summarise, shorten or "
    "paraphrase the prose.\n"
    'Return ONLY JSON: {"body":"<cleaned text>"}\n\nOCR TEXT:\n'
)


async def clean_body(raw: str, groq_manager, min_ratio: float = 0.5) -> tuple[str, bool]:
    """Return (text, was_cleaned).

    On success returns the cleaned text and True. If the LLM is unavailable,
    errors, or summarised below `min_ratio` of the raw length, returns the
    untouched raw text and False.
    """
    raw = (raw or "").strip()
    if len(raw) < 80:
        return raw, False

    try:
        from groq import RateLimitError  # type: ignore
    except Exception:  # noqa: BLE001
        RateLimitError = Exception  # type: ignore

    for _ in range(3):
        try:
            key_index, client = await groq_manager.get_key()
        except Exception as exc:  # noqa: BLE001
            logger.warning("clean_body: no Groq key: %s", exc)
            return raw, False
        try:
            resp = await client.chat.completions.create(
                model=_MODEL,
                messages=[{"role": "user", "content": _PROMPT + raw[:6000]}],
                max_tokens=2400,
                temperature=0.0,
                response_format={"type": "json_object"},
            )
        except RateLimitError:  # type: ignore
            try:
                groq_manager.mark_exhausted(key_index)
            except Exception:  # noqa: BLE001
                pass
            continue
        except Exception as exc:  # noqa: BLE001
            logger.warning("clean_body: request failed %s", exc)
            return raw, False

        content = (resp.choices[0].message.content or "").strip()
        if content.startswith("```"):
            content = content.split("```", 2)[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()
        try:
            cleaned = (json.loads(content).get("body") or "").strip()
        except Exception:  # noqa: BLE001
            return raw, False

        # Length guard: reject summarisation.
        if cleaned and len(cleaned) >= min_ratio * len(raw):
            return cleaned, True
        logger.info(
            "clean_body: rejected (len %d < %.0f%% of %d) — keeping raw",
            len(cleaned), min_ratio * 100, len(raw),
        )
        return raw, False

    return raw, False
