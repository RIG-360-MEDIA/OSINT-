"""Content-quality post-processing for segmented newspaper articles.

Three independent passes applied after Vision segmentation:
  • normalize_section  — collapse Indic / variant section labels to a canonical
    English set (Vision returns Telugu/Hindi labels on some pages).
  • is_notice          — flag statutory / legal / IPO / auction notices that
    Vision picks up as "Business" articles but are not editorial news.
  • mark_duplicates    — flag cross-page duplicates (front-page teasers repeated
    as the full inside-page story), keeping the most complete copy as canonical.
"""
from __future__ import annotations

import re

# ── Section normalization ─────────────────────────────────────────────────────

CANONICAL_SECTIONS = {
    "Politics", "Business", "Economy", "Sports", "National",
    "International", "Local", "Opinion", "Other",
}

# Lower-cased label (any script) → canonical English section.
_SECTION_MAP = {
    # English variants
    "auto zone": "Business", "auto": "Business", "automobile": "Business",
    "markets": "Business", "market": "Business", "corporate": "Business",
    "economy": "Economy", "world": "International", "nation": "National",
    "editorial": "Opinion", "op-ed": "Opinion", "sport": "Sports",
    "city": "Local", "region": "Local", "states": "National",
    # Telugu
    "అంతర్జాతీయం": "International", "జాతీయం": "National", "రాజకీయం": "Politics",
    "రాజకీయాలు": "Politics", "క్రీడలు": "Sports", "వ్యాపారం": "Business",
    "వాణిజ్యం": "Business", "స్థానికం": "Local", "సంపాదకీయం": "Opinion",
    "ఆర్థికం": "Economy", "ప్రపంచం": "International",
    # Hindi
    "अंतरराष्ट्रीय": "International", "अंतर्राष्ट्रीय": "International",
    "राष्ट्रीय": "National", "राजनीति": "Politics", "खेल": "Sports",
    "व्यापार": "Business", "कारोबार": "Business", "स्थानीय": "Local",
    "संपादकीय": "Opinion", "अर्थव्यवस्था": "Economy", "विश्व": "International",
}


def normalize_section(section: str) -> str:
    """Map any section label (incl. Indic) to a canonical English section."""
    s = (section or "").strip()
    if not s:
        return "Other"
    if s in CANONICAL_SECTIONS:
        return s
    low = s.lower()
    if low in _SECTION_MAP:
        return _SECTION_MAP[low]
    title = s.title()
    if title in CANONICAL_SECTIONS:
        return title
    return "Other"


# ── Notice / statutory-filing detector ────────────────────────────────────────

# High-precision statutory phrases. Presence of any (in headline or body lead)
# marks the item a legal/IPO/auction notice rather than editorial news.
_NOTICE_PHRASES = (
    "possession notice", "demand notice", "public notice", "sale notice",
    "auction notice", "e-auction", "e auction", "red herring prospectus",
    "draft red herring", "anchor investor", "annual general meeting",
    "extraordinary general meeting", "extra-ordinary general meeting",
    "postal ballot", "buy-back of equity", "buyback of equity",
    "corrigendum to the", "debts recovery tribunal", "sarfaesi",
    "rule 8(", "sec.13(2)", "sec 13(2)", "section 13(2)", "locker break",
    "notice of the", "notice to eligible", "scrutinizer", "appendix iv",
    "offer for sale", "symbolic possession", "notice for auction",
    "to be listed on", "bidding date opened", "tender notice",
)

_COMPANY_SUFFIX = re.compile(r"\b(LIMITED|LTD\.?|PVT|PRIVATE)\b")


def _upper_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha() and c.isascii()]
    if not letters:
        return 0.0
    return sum(c.isupper() for c in letters) / len(letters)


def is_notice(headline: str, body: str) -> bool:
    """True if the item is a legal / IPO / auction / public notice, not news."""
    hl = headline or ""
    probe = f"{hl}\n{(body or '')[:300]}".lower()
    if any(p in probe for p in _NOTICE_PHRASES):
        return True
    # An ALL-CAPS company-name headline ("ZEPTO LIMITED", "WIPRO LIMITED") with
    # few words is a notice masthead, not a news headline.
    words = hl.split()
    if (
        _COMPANY_SUFFIX.search(hl)
        and len(words) <= 8
        and _upper_ratio(hl) >= 0.75
    ):
        return True
    return False


# ── Cross-page de-duplication ─────────────────────────────────────────────────

_WORD = re.compile(r"[A-Za-z0-9ऀ-ൿ]+")
_DEDUP_STOP = {
    "the", "for", "and", "with", "from", "into", "amid", "says", "after",
    "over", "its", "his", "her", "are", "was", "has", "have", "may", "will",
}


def _key_tokens(headline: str) -> set[str]:
    return {
        w.lower() for w in _WORD.findall(headline or "")
        if len(w) >= 3 and w.lower() not in _DEDUP_STOP
    }


def _similar(a: set[str], b: set[str]) -> bool:
    if len(a) < 3 or len(b) < 3:
        return False
    inter = len(a & b)
    union = len(a | b)
    jacc = inter / union if union else 0.0
    # 0.5 Jaccard, or a strong shared-token core (teaser vs full story reword).
    return jacc >= 0.5 or inter >= max(3, min(len(a), len(b)) - 1)


def mark_duplicates(articles: list[dict]) -> None:
    """Flag cross-page duplicates in place: keep the most complete copy as
    canonical (is_duplicate=False), flag the rest (is_duplicate=True,
    duplicate_of=canonical page_number). Articles are NOT removed — the writer
    decides whether to drop or just down-rank.
    """
    for a in articles:
        a.setdefault("is_duplicate", False)
        a.setdefault("duplicate_of", None)

    toks = [_key_tokens(a.get("headline", "")) for a in articles]
    for i, a in enumerate(articles):
        if a["is_duplicate"]:
            continue
        group = [i]
        for j in range(i + 1, len(articles)):
            if articles[j]["is_duplicate"]:
                continue
            if _similar(toks[i], toks[j]):
                group.append(j)
        if len(group) == 1:
            continue
        # Canonical = the copy with the longest body (the full story, not teaser).
        canon = max(group, key=lambda k: len(articles[k].get("text") or ""))
        canon_pg = articles[canon].get("page_number")
        for k in group:
            if k != canon:
                articles[k]["is_duplicate"] = True
                articles[k]["duplicate_of"] = canon_pg
