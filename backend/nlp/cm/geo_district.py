"""
District-level geo resolver for the CM Page v2.

This module is the **second** geographic step in the article enrichment
pipeline. The existing ``backend/nlp/nlp_geo.py`` step already extracts
``geo_primary`` / ``geo_secondary`` as raw NER strings (cities, states,
countries — sometimes a mix). That output stays untouched.

What this module does:
    Given an article's title, body and already-extracted entity list,
    return the set of Telangana districts the article touches, with
    per-district confidence scores. Used by:

      - tasks.cm.backfill_district_geo  (one-shot historical backfill)
      - nlp_processor._process_single   (live, hooked in a follow-up)

Design choices:
    1. **Reuse existing entity extraction.** ``entities_extracted``
       (jsonb on articles) already has GPE/LOC entries from spaCy. We
       match those against the gazetteer rather than re-running NER.
    2. **Word-boundary matching.** Substring matching pollutes results
       (e.g., "Khammam" inside "Khammama" — fictional but illustrative).
       We use ``\\b...\\b`` regexes built from district names + aliases.
    3. **Confidence by region.** Title match counts most (1.0), body
       first 300 chars counts mid (0.7), deeper body counts least (0.4).
       Multi-mention summed, capped at 1.0.
    4. **Multi-district by design.** An article that mentions Khammam,
       Hyderabad and Warangal returns three rows. ``is_primary`` flags
       only the single highest-confidence district.
    5. **Landmarks.** A small curated dict maps proper nouns that are
       not district names (Musi, Hussain Sagar, Nagarjuna Sagar) to one
       or more parent districts.

The gazetteer is loaded from the ``districts`` table once per worker
process and held in a module-level cache.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Confidence weights for where a mention is found.
# ---------------------------------------------------------------------------

WEIGHT_TITLE = 1.0
WEIGHT_BODY_LEAD = 0.7        # first 300 chars
WEIGHT_BODY_DEEP = 0.4        # rest of the body
WEIGHT_ENTITY = 0.85          # entity_extracted hit (NER already filtered)
LEAD_CHAR_BUDGET = 300


# ---------------------------------------------------------------------------
# Curated landmarks → parent district(s).
# Add to this dict carefully. A misattribution puts coverage on the
# wrong district and breaks the heatmap. Personal verification before
# every addition.
# ---------------------------------------------------------------------------

LANDMARKS: dict[str, tuple[str, ...]] = {
    # Hydra / Musi narrative
    "musi river":        ("hyderabad", "rangareddy"),
    "musi rejuvenation": ("hyderabad", "rangareddy"),
    "hussain sagar":     ("hyderabad",),
    "charminar":         ("hyderabad",),
    "begumpet":           ("hyderabad",),
    "secunderabad":      ("hyderabad",),
    "old city":          ("hyderabad",),
    # Reservoirs
    "nagarjuna sagar":     ("nalgonda", "suryapet"),
    "srisailam":           ("nagarkurnool",),
    "mid manair":          ("rajanna-sircilla",),
    "lower manair":        ("karimnagar",),
    "singur":              ("medak",),
    "srsp":                ("nizamabad",),
    "kinnerasani":         ("khammam", "bhadradri"),
    # Universities and institutions tied to a district capital
    "kakatiya university": ("hanumakonda", "warangal"),
    "osmania university":  ("hyderabad",),
    "university of hyderabad": ("hyderabad", "rangareddy"),
    # Forts / heritage
    "warangal fort":       ("warangal",),
    "elgandal fort":       ("karimnagar",),
    "khammam fort":        ("khammam",),
    "kuntala falls":       ("adilabad",),
    "pochera falls":       ("adilabad",),
    # Industrial parks / projects with public name recognition
    "kakatiya mega textile park": ("warangal",),
    "metro phase-2":       ("hyderabad", "rangareddy", "medchal"),
    "metro phase 2":       ("hyderabad", "rangareddy", "medchal"),
    "outer ring road":     ("rangareddy", "medchal"),
    "orr":                 ("rangareddy", "medchal"),
    "shamshabad airport":  ("rangareddy",),
    "rajiv gandhi international airport": ("rangareddy",),
}


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DistrictMatch:
    """One district-tag for an article. Multiple per article are allowed."""

    district_id: str
    mention_count: int
    confidence: float           # clamped to [0, 1]
    is_primary: bool


@dataclass(frozen=True)
class GazetteerEntry:
    """One row from the ``districts`` table, pre-compiled for matching."""

    district_id: str
    state_code: str
    name: str                  # uppercase canonical
    hq_city: str
    pattern: re.Pattern[str]   # combined regex for name + aliases + hq_city


# ---------------------------------------------------------------------------
# Gazetteer — loaded once, cached per worker process.
# ---------------------------------------------------------------------------

_GAZETTEER_CACHE: list[GazetteerEntry] | None = None
_LANDMARK_PATTERN: re.Pattern[str] | None = None


def _build_landmark_pattern() -> re.Pattern[str]:
    """Compile a single regex that matches any landmark phrase."""
    parts = [re.escape(k) for k in sorted(LANDMARKS.keys(), key=len, reverse=True)]
    return re.compile(r"\b(?:" + "|".join(parts) + r")\b", re.IGNORECASE)


def _build_district_pattern(name: str, hq_city: str, aliases: Iterable[str]) -> re.Pattern[str]:
    """Compile a regex that matches a district by name, hq_city, or alias.

    Order parts by length (longest first) so that "Komaram Bheem" is
    matched as a unit, not just "Bheem".
    """
    raw_parts: list[str] = [name, hq_city]
    raw_parts.extend(a for a in aliases if a)
    # de-dup case-insensitively, preserve longest-first ordering
    seen: set[str] = set()
    parts: list[str] = []
    for p in sorted(raw_parts, key=len, reverse=True):
        key = p.lower()
        if key in seen:
            continue
        seen.add(key)
        parts.append(re.escape(p))
    return re.compile(r"\b(?:" + "|".join(parts) + r")\b", re.IGNORECASE)


async def load_gazetteer(db: AsyncSession, *, force: bool = False) -> list[GazetteerEntry]:
    """Load the districts table into the module cache.

    Cheap: 33 rows for Telangana. Idempotent, safe to call from any task.
    Pass ``force=True`` to bypass the cache (used by tests).
    """
    global _GAZETTEER_CACHE, _LANDMARK_PATTERN
    if _GAZETTEER_CACHE is not None and not force:
        return _GAZETTEER_CACHE

    rows = (await db.execute(
        text(
            """
            SELECT id, state_code, name, hq_city, aliases
            FROM districts
            ORDER BY id
            """
        )
    )).all()

    entries: list[GazetteerEntry] = []
    for r in rows:
        aliases = list(r.aliases or [])
        entries.append(
            GazetteerEntry(
                district_id=r.id,
                state_code=r.state_code,
                name=r.name,
                hq_city=r.hq_city,
                pattern=_build_district_pattern(r.name, r.hq_city, aliases),
            )
        )

    _GAZETTEER_CACHE = entries
    _LANDMARK_PATTERN = _build_landmark_pattern()
    logger.info("geo_district gazetteer loaded: %d districts", len(entries))
    return entries


def reset_cache() -> None:
    """Test helper — drop the in-memory cache so the next ``load_gazetteer``
    refetches from the DB."""
    global _GAZETTEER_CACHE, _LANDMARK_PATTERN
    _GAZETTEER_CACHE = None
    _LANDMARK_PATTERN = None


# ---------------------------------------------------------------------------
# Tagging
# ---------------------------------------------------------------------------


def _entity_names(entities: list[dict] | None) -> list[str]:
    """Pull plain name strings from the article's entities_extracted JSONB."""
    if not entities:
        return []
    out: list[str] = []
    for e in entities:
        if not isinstance(e, dict):
            continue
        name = e.get("name") or e.get("text") or e.get("canonical_name")
        if isinstance(name, str) and name.strip():
            out.append(name.strip())
    return out


def _count_matches(pattern: re.Pattern[str], haystack: str) -> int:
    if not haystack:
        return 0
    return sum(1 for _ in pattern.finditer(haystack))


def _apply_landmarks(text_blob: str, weight: float, scores: dict[str, float], counts: dict[str, int]) -> None:
    """Add landmark hits to scores in-place, attributing to all parent districts."""
    if _LANDMARK_PATTERN is None:
        return
    for m in _LANDMARK_PATTERN.finditer(text_blob):
        phrase = m.group(0).lower()
        for district_id in LANDMARKS.get(phrase, ()):
            scores[district_id] = scores.get(district_id, 0.0) + weight
            counts[district_id] = counts.get(district_id, 0) + 1


def tag_districts(
    *,
    title: str | None,
    body: str | None,
    entities: list[dict] | None,
    gazetteer: list[GazetteerEntry],
) -> list[DistrictMatch]:
    """Resolve which districts an article touches.

    Args:
        title:  article title (already translated when needed)
        body:   lead/full body text (already translated)
        entities: existing entities_extracted JSONB list
        gazetteer: from ``load_gazetteer(db)``

    Returns:
        A list of DistrictMatch, possibly empty. Multi-district by
        design — one row per matched district. ``is_primary`` flags
        the single highest-confidence match.
    """
    if not gazetteer:
        return []

    title = title or ""
    body = body or ""
    body_lead = body[:LEAD_CHAR_BUDGET]
    body_deep = body[LEAD_CHAR_BUDGET:] if len(body) > LEAD_CHAR_BUDGET else ""
    entity_blob = " ".join(_entity_names(entities))

    scores: dict[str, float] = {}
    counts: dict[str, int] = {}

    for gz in gazetteer:
        n_title = _count_matches(gz.pattern, title)
        n_lead = _count_matches(gz.pattern, body_lead)
        n_deep = _count_matches(gz.pattern, body_deep)
        n_ent = _count_matches(gz.pattern, entity_blob)
        contribution = (
            n_title * WEIGHT_TITLE
            + n_lead * WEIGHT_BODY_LEAD
            + n_deep * WEIGHT_BODY_DEEP
            + n_ent * WEIGHT_ENTITY
        )
        n_total = n_title + n_lead + n_deep + n_ent
        if n_total == 0:
            continue
        scores[gz.district_id] = scores.get(gz.district_id, 0.0) + contribution
        counts[gz.district_id] = counts.get(gz.district_id, 0) + n_total

    # Landmark sweep — runs across title + body, not entities.
    _apply_landmarks(title, WEIGHT_TITLE, scores, counts)
    _apply_landmarks(body_lead, WEIGHT_BODY_LEAD, scores, counts)
    if body_deep:
        _apply_landmarks(body_deep, WEIGHT_BODY_DEEP, scores, counts)

    if not scores:
        return []

    # Clamp confidence to [0, 1] and pick the primary.
    primary_id = max(scores, key=lambda k: scores[k])
    matches: list[DistrictMatch] = []
    for district_id, raw_score in scores.items():
        confidence = min(1.0, raw_score / 2.0)  # scale so a single title hit ≈ 0.5; multiple hits saturate.
        matches.append(
            DistrictMatch(
                district_id=district_id,
                mention_count=counts[district_id],
                confidence=round(confidence, 4),
                is_primary=(district_id == primary_id),
            )
        )

    # Stable order: highest confidence first, then alphabetic.
    matches.sort(key=lambda m: (-m.confidence, m.district_id))
    return matches


__all__ = [
    "DistrictMatch",
    "GazetteerEntry",
    "LANDMARKS",
    "WEIGHT_BODY_DEEP",
    "WEIGHT_BODY_LEAD",
    "WEIGHT_ENTITY",
    "WEIGHT_TITLE",
    "load_gazetteer",
    "reset_cache",
    "tag_districts",
]
