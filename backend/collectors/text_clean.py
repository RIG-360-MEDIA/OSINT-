"""HTML-safe lead-text cleaning for collector ingestion.

`lead_text_original` is surfaced to the v1 API as `summary_original` (the native
short summary). RSS `<description>` payloads and some scraped bodies arrive with
raw markup (`<img>`, `<figure>`, `<a>`, WordPress footers, HTML entities), which
then leaked verbatim to clients (Defect B, 2026-07-16). `strip_html_lead` is the
single choke point that turns raw markup into clean native text.

Hardened against the failure modes a naive ``<[^>]+>`` strip misses:
  * HTML entities (``&amp;``, ``&#8217;``)
  * comments containing ``>`` (``<!-- a > b -->``)
  * a tag truncated by an upstream slice (``<a href="http://…`` with no close)
  * the WordPress ``The post … appeared first on …`` boilerplate footer

Order is load-bearing: strip tags FIRST, unescape entities SECOND.

Unescaping first (as this module originally did) destroys ordinary copy. Given
``5 &lt; 10 and profit &gt; loss for the quarter``, unescape produces
``5 < 10 and profit > loss ...``; the tag pass then matches ``< 10 and profit >``
as a tag and deletes it, yielding ``5 loss for the quarter``. On a news wire
carrying "profit > loss" that is silent content loss.

Stripping first means an escaped ``&lt;b&gt;`` survives as the literal text
``<b>`` -- which is correct: a source that escaped it meant it to be *read*, not
parsed. Nothing re-parses it after this point.

Kept deliberately in step with ``analytics.strip_html_lead`` (see
scripts/backfills/strip_html_lead.sql), which cleans the historical rows. If you
change one, change the other, or old and new rows drift apart.
"""
from __future__ import annotations

import html as _html
import re

DEFAULT_LEAD_MAX_CHARS = 2000

_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_DANGLING_TAG_RE = re.compile(r"<[^>]*$")  # tag truncated at end of a sliced snippet
_WP_FOOTER_RE = re.compile(
    r"\s*The post\b.*?\bappeared first on\b.*?$", re.IGNORECASE | re.DOTALL
)
_WS_RE = re.compile(r"\s+")


def strip_html_lead(raw: str | None, max_chars: int | None = DEFAULT_LEAD_MAX_CHARS) -> str | None:
    """Return clean native lead text, or ``None`` if nothing survives.

    Tags are stripped before entities are unescaped (see the module docstring --
    the other order eats ordinary "a > b" copy). Slice only at the very end, so a
    tag can never be cut mid-token by an upstream truncation.
    """
    if not raw:
        return None
    # Comments first: a comment body can itself contain '>' and would otherwise
    # defeat the tag pass.
    s = _COMMENT_RE.sub(" ", raw)
    s = _SCRIPT_STYLE_RE.sub(" ", s)
    s = _TAG_RE.sub(" ", s)
    s = _DANGLING_TAG_RE.sub(" ", s)
    # Only now -- nothing below re-parses markup, so a decoded '<' is safe.
    s = _html.unescape(s)
    s = _WP_FOOTER_RE.sub("", s)
    s = _WS_RE.sub(" ", s).strip()
    if not s:
        return None
    if max_chars is not None:
        s = s[:max_chars].strip()
    return s or None
