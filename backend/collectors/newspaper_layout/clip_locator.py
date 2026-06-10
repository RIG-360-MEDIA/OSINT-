"""
Headline-anchored clip location.

Bridges Vision-segmented articles to PP-Structure OCR line coordinates so we
can crop a tight, single-article image region.

The insight: a vision LLM reports article *headlines* almost verbatim (unlike
bodies, which it paraphrases), but its pixel coordinates are unreliable.
PP-Structure OCR gives exact per-line pixel boxes but cannot group lines into
articles. We bridge the two on the headline:

  1. Match the vision headline to its PP-Structure OCR line(s) -> exact top
     edge + horizontal span (the article's column band).
  2. Walk OCR lines downward within that band, accumulating body lines until a
     large vertical gap (next article) -> bottom edge.

All coordinates are PP-Structure render pixels (see ocr._DPI).
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass


@dataclass(frozen=True)
class OCRLine:
    text: str
    conf: float
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def h(self) -> float:
        return self.y1 - self.y0

    @property
    def xc(self) -> float:
        return (self.x0 + self.x1) / 2.0


_WORD_RE = re.compile(r"[A-Za-z0-9ऀ-ൿ]+")  # Latin + Indic ranges


def _tokens(text: str) -> set[str]:
    return {w.lower() for w in _WORD_RE.findall(text) if len(w) >= 3}


def _norm(text: str) -> str:
    """Lowercased alphanumeric-only form (script-agnostic; keeps Indic letters)."""
    return "".join(ch for ch in text.lower() if ch.isalnum())


def _char_ngrams(text: str, n: int = 3) -> set[str]:
    """Character n-grams over the alphanumeric content (script-agnostic).

    Word-token matching assumes both transcriptions split words identically —
    true for clean Latin OCR, false for Indic scripts where the vision LLM and
    PaddleOCR each mis-segment differently. Character trigrams degrade
    gracefully under that noise, so they anchor headlines the token path misses.
    """
    s = _norm(text)
    if len(s) < n:
        return {s} if s else set()
    return {s[i : i + n] for i in range(len(s) - n + 1)}


def _ngram_sim(a: set[str], b: set[str]) -> float:
    """Jaccard similarity of two character-trigram sets, 0–1."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _edit_sim(a: str, b: str) -> float:
    """Normalised Levenshtein similarity (1 - dist/maxlen), 0–1.

    Trigram Jaccard misses headlines where OCR substitutes individual glyphs
    (common on stylised Telugu display type) because it shatters every trigram
    touching the bad glyph. Edit distance tolerates scattered substitutions, so
    it recovers anchors the trigram path drops. Inputs should be pre-normalised.
    """
    la, lb = len(a), len(b)
    if not la or not lb:
        return 0.0
    if abs(la - lb) > max(la, lb) * 0.6:  # length gap too large — cannot match
        return 0.0
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        ca = a[i - 1]
        for j in range(1, lb + 1):
            cost = 0 if ca == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return 1.0 - prev[lb] / max(la, lb)


def _transliterate_to_latin(text: str) -> str:
    """Romanize Indic script text to IAST Latin for OCR-noise-robust comparison.

    When Vision and OCR engines garble the same Telugu/Devanagari glyph
    differently the raw Unicode representations share almost nothing, so
    trigram Jaccard and edit distance both score near zero. Transliterating
    to IAST maps each glyph to its Latin pronunciation equivalent, so the
    subsequent character-level metrics compare pronunciation rather than
    script — much more robust to Indic OCR substitution noise.

    Returns the original text unchanged when indic_transliteration is
    unavailable or the text contains no Indic characters.
    """
    try:
        from indic_transliteration import sanscript  # type: ignore[import]
    except ImportError:
        return text

    target_script = None
    for ch in text:
        cp = ord(ch)
        if 0x0C00 <= cp <= 0x0C7F:      # Telugu
            target_script = sanscript.TELUGU
            break
        if 0x0900 <= cp <= 0x097F:      # Devanagari (Hindi / Marathi)
            target_script = sanscript.DEVANAGARI
            break
        if 0x0B80 <= cp <= 0x0BFF:      # Tamil
            target_script = sanscript.TAMIL
            break
        if 0x0C80 <= cp <= 0x0CFF:      # Kannada
            target_script = sanscript.KANNADA
            break

    if target_script is None:
        return text  # already Latin or unrecognised script

    try:
        return sanscript.transliterate(text, target_script, sanscript.IAST)
    except Exception:
        return text


def _fuzzy(a_text: str, b_text: str) -> float:
    """Best of trigram-Jaccard, edit-distance, and transliteration-normalised similarity.

    The transliteration path fires only when the base metrics fall below the
    threshold.  Romanizing both strings to IAST Latin removes script-level OCR
    divergence (Vision and PaddleOCR/Tesseract each garble the same glyph
    differently) so the standard metrics can compare pronunciation instead.
    """
    base = max(
        _ngram_sim(_char_ngrams(a_text), _char_ngrams(b_text)),
        _edit_sim(_norm(a_text), _norm(b_text)),
    )
    # Fast path: already above threshold — skip transliteration overhead.
    if base >= _FUZZY_MATCH:
        return base
    a_lat = _transliterate_to_latin(a_text)
    b_lat = _transliterate_to_latin(b_text)
    if a_lat != a_text or b_lat != b_text:  # at least one was Indic
        lat_sim = max(
            _ngram_sim(_char_ngrams(a_lat), _char_ngrams(b_lat)),
            _edit_sim(_norm(a_lat), _norm(b_lat)),
        )
        return max(base, lat_sim)
    return base


# Minimum fuzzy similarity (max of trigram-Jaccard and edit-ratio) to treat a
# noisy-OCR line as a headline match when exact word tokens fail to overlap
# (Indic scripts, heavy OCR noise). Paired with the mis-anchor guard in
# hybrid_pipeline so a looser bar cannot produce confidently-wrong crops.
_FUZZY_MATCH = 0.38


def _median_height(lines: list[OCRLine]) -> float:
    hs = [l.h for l in lines if l.h > 0]
    return statistics.median(hs) if hs else 1.0


def _match_headline_lines(
    headline: str, lines: list[OCRLine], body_h: float
) -> list[OCRLine]:
    """Return the OCR line(s) that make up the article's headline.

    A headline may be OCR-split across several stacked lines. We score every
    line by token overlap with the headline and keep the high-overlap lines
    that are also larger-than-body type, then restrict to the tightest
    vertically-contiguous cluster.
    """
    htoks = _tokens(headline)
    if not htoks:
        return []

    scored: list[tuple[float, OCRLine]] = []
    for l in lines:
        lt = _tokens(l.text)
        if not lt:
            continue
        overlap = len(lt & htoks) / len(lt)
        # A headline fragment shares most of its words with the headline and is
        # rendered in larger type than the body.
        if overlap >= 0.5 and l.h >= body_h * 1.2:
            scored.append((overlap, l))

    if not scored:
        # Fallback: looser match, any font size (short single-line headlines).
        for l in lines:
            lt = _tokens(l.text)
            if lt and len(lt & htoks) / len(lt) >= 0.6:
                scored.append((len(lt & htoks) / len(lt), l))

    if not scored:
        # Fuzzy fallback for noisy / non-Latin OCR: word tokens won't intersect
        # when the vision LLM and PaddleOCR mis-segment the same Indic headline
        # differently, so match on character trigrams instead. Restricted to
        # larger-than-body lines to stay on headlines, not body text.
        if _norm(headline):
            for l in lines:
                if l.h < body_h * 1.1:
                    continue
                sim = _fuzzy(l.text, headline)
                if sim >= _FUZZY_MATCH:
                    scored.append((sim, l))

    if not scored:
        return []

    cand = [l for _, l in scored]
    cand.sort(key=lambda l: l.y0)
    # Keep the tightest vertical cluster (drop stray far-away matches).
    cluster: list[OCRLine] = [cand[0]]
    for l in cand[1:]:
        if l.y0 - cluster[-1].y1 <= body_h * 2.0:
            cluster.append(l)
        else:
            break

    # Reject width outliers: a single OCR line that merged THIS headline with a
    # neighbouring column's text is far wider than the genuine headline lines.
    # Drop any cluster line whose width exceeds 1.7x the cluster median width.
    if len(cluster) >= 2:
        widths = sorted(l.x1 - l.x0 for l in cluster)
        med_w = widths[len(widths) // 2]
        if med_w > 0:
            cluster = [l for l in cluster if (l.x1 - l.x0) <= med_w * 1.7]

    # Coverage gate: the matched lines must collectively account for a real
    # fraction of the ANCHOR headline's OWN tokens. Without this, a short OCR
    # line that shares a single common word with a neighbouring article's
    # headline (e.g. "market" in both "Pharma market grows 11%" and "…better
    # market access under EAEU FTA") scores a perfect per-line overlap and
    # anchors the clip box onto the WRONG article. Requiring ≥40% headline-token
    # coverage rejects those mis-anchors so the caller can fall back or skip the
    # snapshot — a missing crop beats a confidently wrong one.
    covered: set[str] = set()
    for l in cluster:
        covered |= _tokens(l.text) & htoks
    tok_cov = len(covered) / len(htoks) if htoks else 0.0
    if tok_cov < 0.4:
        # Token coverage is low — accept if ANY matched line is fuzzily similar
        # to the headline. Testing the concatenated cluster instead dilutes a
        # strong single-line match (a headline split across OCR lines) below the
        # bar, which silently dropped valid Telugu anchors.
        best = max((_fuzzy(l.text, headline) for l in cluster), default=0.0)
        if best < _FUZZY_MATCH:
            return []
    return cluster


def locate_clip_box_by_body(
    body: str,
    lines: list[OCRLine],
    page_w: float,
    page_h: float,
) -> list[float] | None:
    """Locate an article's column by matching its body text to OCR lines.

    Fallback when the headline can't be matched (multi-column display
    headlines, heavy OCR garbling). Body text is set in regular type that
    OCRs more reliably than stylised headlines, so token overlap works.

    Approach: divide the page into vertical column strips, aggregate
    token overlap per strip, and pick the strip with the strongest signal.
    This is robust to OCR fragmentation because it sums across many lines.
    """
    if not lines or not body:
        return None

    probe_toks = {w for w in _tokens(body[:300]) if len(w) >= 5}
    if len(probe_toks) < 3:
        return None

    body_h = _median_height(lines)
    n_strips = 6
    strip_w = page_w / n_strips

    # Score each strip by total distinctive-token hits across its lines.
    strip_hits: list[int] = [0] * n_strips
    strip_lines: list[list[OCRLine]] = [[] for _ in range(n_strips)]
    for l in lines:
        si = min(int(l.xc / strip_w), n_strips - 1)
        lt = {w for w in _tokens(l.text) if len(w) >= 5}
        if not lt:
            continue
        hit = lt & probe_toks
        if hit:
            strip_hits[si] += len(hit)
            strip_lines[si].append(l)

    best_strip = max(range(n_strips), key=lambda i: strip_hits[i])
    if strip_hits[best_strip] < 3:
        return None

    col = strip_lines[best_strip]
    if len(col) < 2:
        return None

    col.sort(key=lambda l: l.y0)
    # Bound to ONE article: matched lines can be scattered down the whole column
    # because other stacked articles reuse the same words, and taking their
    # min/max Y swallows several articles into one crop (a misleading snapshot).
    # Keep only the largest run of matched lines that are vertically contiguous
    # (gaps ≤ a couple of body heights), which is the single article the probe
    # text actually came from.
    runs: list[list[OCRLine]] = [[col[0]]]
    for l in col[1:]:
        if l.y0 - runs[-1][-1].y1 <= body_h * 2.6:
            runs[-1].append(l)
        else:
            runs.append([l])
    col = max(runs, key=len)
    if len(col) < 2:
        return None

    bx0 = min(l.x0 for l in col)
    bx1 = max(l.x1 for l in col)
    by0 = min(l.y0 for l in col)
    by1 = max(l.y1 for l in col)

    # Walk upward to find a headline-sized line above the body cluster.
    above = sorted(
        (
            l for l in lines
            if l.y1 <= by0 + body_h * 0.5
            and l.y0 >= by0 - body_h * 12
            and bx0 - page_w * 0.05 <= l.xc <= bx1 + page_w * 0.05
            and l.h >= body_h * 1.3
        ),
        key=lambda l: l.y0,
        reverse=True,
    )
    for hl in above:
        if by0 - hl.y1 < body_h * 3:
            bx0, by0 = min(bx0, hl.x0), min(by0, hl.y0)
            bx1 = max(bx1, hl.x1)
            break

    # Walk downward past the last matched body line.
    below = sorted(
        (
            l for l in lines
            if l.y0 >= by1 - body_h * 0.3 and bx0 <= l.xc <= bx1
        ),
        key=lambda l: l.y0,
    )
    prev = by1
    for l in below:
        if l.y0 - prev > body_h * 2.4:
            break
        if l.h >= body_h * 1.55 and l.y0 > by1 + body_h * 2:
            break
        by1 = max(by1, l.y1)
        prev = l.y1

    x0 = max(0.0, bx0)
    y0 = max(0.0, by0)
    x1 = min(page_w, bx1)
    y1 = min(page_h, by1)
    if x1 - x0 < 10 or y1 - y0 < 10:
        return None
    return [x0, y0, x1, y1]


def locate_clip_box(
    headline: str,
    lines: list[OCRLine],
    page_w: float,
    page_h: float,
) -> list[float] | None:
    """Locate a tight pixel bbox [x0, y0, x1, y1] for one article.

    Returns None when the headline cannot be matched to any OCR line, leaving
    the caller free to fall back to a vision-supplied box.
    """
    if not lines:
        return None

    body_h = _median_height(lines)
    head = _match_headline_lines(headline, lines, body_h)
    if not head:
        return None

    hx0 = min(l.x0 for l in head)
    hy0 = min(l.y0 for l in head)
    hx1 = max(l.x1 for l in head)
    hy1 = max(l.y1 for l in head)
    if hx1 - hx0 <= 0:
        return None

    # Horizontal extent is the headline's own column span — a well-laid-out
    # article's body flows in the columns directly beneath its headline, so we
    # do NOT widen the box with body lines (that is what leaked into the
    # neighbouring column). Body membership is by line *centre* inside the span.
    # Only a clearly larger AND substantial line ends the article (the next
    # article's headline). Subheads, bylines, kickers and ">> 3" jump-refs are
    # smaller/short and must be allowed through so the full body is captured.
    next_head_h = body_h * 1.55   # a line this tall below = next article headline
    gap_break = body_h * 2.4      # whitespace taller than this = article/section break
    # A big headline carries extra leading before its body, so the
    # headline→first-body-line gap is routinely larger than the inter-body gap.
    # Using `gap_break` for that first transition stopped the walk before any
    # body was captured, emitting a headline-only sliver. Allow a roomier gap
    # until the body actually starts, then tighten to `gap_break` between body
    # lines so we still stop cleanly at the next article.
    head_gap_break = body_h * 5.0

    band = [
        l for l in lines
        if l not in head
        and l.y0 >= hy1 - body_h * 0.3        # at or below the headline
        and hx0 <= l.xc <= hx1                 # centre within the headline columns
    ]
    band.sort(key=lambda l: l.y0)

    bottom = hy1
    prev_bottom = hy1
    body_started = False
    for l in band:
        # Stop at a whitespace gap (horizontal rule / section break leaves one).
        # The first headline→body transition tolerates a larger gap.
        gap = gap_break if body_started else head_gap_break
        if l.y0 - prev_bottom > gap:
            break
        is_next_head = l.h >= next_head_h and len(l.text) >= 18
        # The article's OWN subhead sits right under the headline and is larger
        # than body — allow it through. Only a large line AFTER body text has
        # begun marks the following article.
        if is_next_head and body_started:
            break
        if l.h <= body_h * 1.25:
            body_started = True
        bottom = max(bottom, l.y1)
        prev_bottom = l.y1

    # Clamp to page; guard against degenerate boxes.
    x0 = max(0.0, hx0)
    y0 = max(0.0, hy0)
    x1 = min(page_w, hx1)
    y1 = min(page_h, bottom)
    if x1 - x0 < 10 or y1 - y0 < 10:
        return None
    return [x0, y0, x1, y1]
