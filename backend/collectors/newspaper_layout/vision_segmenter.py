"""
Vision-LLM page segmentation.

Sends one rendered newspaper page image to a Groq vision model and returns the
distinct articles it sees (headline + body + section + language). This is the
segmentation engine — it does not provide reliable pixel coordinates; clip
boxes come from clip_locator via headline matching against OCR lines.
"""
from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

# One article object inside the "articles" array. Used to salvage complete
# objects when the model truncates the JSON (dense pages hit the token cap).
_ARTICLE_OBJ = re.compile(r"\{[^{}]*\}", re.S)


def _loads_tolerant(content: str) -> dict:
    """Parse the JSON; on failure (truncation), salvage complete article objects.

    A dense page can exhaust the token budget mid-array, leaving invalid JSON
    that drops the WHOLE page. Instead we extract every complete `{...}` object
    and keep the ones that parse — losing only the single truncated tail item.
    """
    try:
        return json.loads(content)
    except Exception:  # noqa: BLE001
        pass
    arts = []
    for m in _ARTICLE_OBJ.finditer(content):
        try:
            obj = json.loads(m.group(0))
        except Exception:  # noqa: BLE001
            continue
        if isinstance(obj, dict) and obj.get("headline"):
            arts.append(obj)
    if arts:
        logger.info("segment_page: salvaged %d articles from truncated JSON", len(arts))
    return {"articles": arts}


def _failed_generation(exc) -> str:
    """Pull the partial model output out of a Groq json_validate_failed 400."""
    try:
        body = getattr(exc, "body", None) or {}
        if isinstance(body, dict):
            return body.get("error", {}).get("failed_generation", "") or ""
    except Exception:  # noqa: BLE001
        pass
    return ""

_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

_PROMPT = (
    "You are reading one page of a newspaper. Identify every distinct news "
    "article on the page. Ignore advertisements, mastheads, page furniture, "
    "weather boxes, stock tables, and index/brief boxes.\n"
    "For EACH article return these fields:\n"
    '  - "headline": the main headline, exactly as printed (verbatim).\n'
    '  - "subheadline": the deck / standfirst / strap line printed directly '
    "under the headline (verbatim). Use an empty string if there is none.\n"
    '  - "byline": the author and/or dateline line, e.g. "By R. Sharma, New '
    'Delhi". Use an empty string if there is none.\n'
    '  - "body": the article body text, cleaned of OCR noise. Preserve the '
    "article's paragraph structure: put a literal \\n\\n between consecutive "
    "paragraphs. Do NOT return the body as one unbroken block, and do NOT "
    "repeat the headline, subheadline, or byline inside the body.\n"
    '  - "section": one of Politics, Business, Sports, National, Local, '
    "International, Opinion, Other.\n"
    '  - "language": 2-letter ISO code (en/te/hi/ta/ml/kn/bn/gu/mr/pa/ur).\n'
    "Return ONLY JSON (no markdown):\n"
    '{"articles":[{"headline":"...","subheadline":"...","byline":"...",'
    '"body":"...","section":"...","language":"xx"}]}'
)


async def segment_page(b64_jpeg: str, groq_manager) -> list[dict]:
    """Return [{headline, body, section, language}] for one page image."""
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": _PROMPT},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64_jpeg}"},
            },
        ],
    }]

    try:
        from groq import APIStatusError, RateLimitError  # type: ignore
    except Exception:  # noqa: BLE001
        APIStatusError = Exception  # type: ignore
        RateLimitError = Exception  # type: ignore

    for attempt in range(3):
        try:
            key_index, client = await groq_manager.get_key()
        except Exception as exc:  # noqa: BLE001
            logger.warning("segment_page: no Groq key: %s", exc)
            return []

        content = ""
        try:
            resp = await client.chat.completions.create(
                model=_VISION_MODEL,
                messages=messages,
                max_tokens=8192,
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            content = (resp.choices[0].message.content or "").strip()
        except RateLimitError:  # type: ignore
            try:
                await groq_manager.mark_exhausted(key_index)
            except Exception:  # noqa: BLE001
                pass
            continue
        except APIStatusError as exc:  # type: ignore
            # A dense page can overflow the token cap → json_validate_failed 400.
            # The partial output is in the error body; salvage it rather than
            # losing the whole page.
            content = _failed_generation(exc)
            if not content:
                logger.warning("segment_page: APIStatusError %s", exc)
                return []
        except Exception as exc:  # noqa: BLE001
            logger.warning("segment_page: request failed %s", exc)
            return []

        if content.startswith("```"):
            content = content.split("```", 2)[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()
        data = _loads_tolerant(content)

        out: list[dict] = []
        for a in data.get("articles", []):
            headline = (a.get("headline") or "").strip()
            body = (a.get("body") or "").strip()
            if not headline or len(body) < 20:
                continue
            from .postprocess import normalize_section

            out.append({
                "headline": headline[:500],
                "subheadline": (a.get("subheadline") or "").strip()[:500],
                "byline": (a.get("byline") or "").strip()[:300],
                "body": body[:10000],
                "section": normalize_section((a.get("section") or "").strip()),
                "language": (a.get("language") or "").strip().lower(),
            })
        return out

    return []
