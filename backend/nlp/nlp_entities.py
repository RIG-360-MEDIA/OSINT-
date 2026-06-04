"""
Entity extraction with two-layer resolution:
  Layer 1 — SpaCy NER for candidate spans
  Layer 2 — entity_dictionary table for canonical resolution + prominence scoring
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# ── Module-level singleton ─────────────────────────────────────────────────────
# Keyed by lowercased canonical name AND all lowercased aliases → same entry dict.
# Loaded once at worker startup via load_entity_dictionary(); O(1) lookup per span.

_ENTITY_DICT: dict[str, dict] = {}
_DICT_LOADED: bool = False
_LOADED_VERSION: int = 0
_LAST_VERSION_CHECK: float = 0.0

# Migration 095 (2026-06-04) Tier 4: durable NER fix. Strip leading honorifics/office-titles/
# article-particles BEFORE the entity_dictionary lookup so a span like "Chief Minister Revanth
# Reddy" resolves to the bare "Revanth Reddy" entry, EVEN IF no alias was pre-loaded for it.
# Without this, NER on a fresh "Chief Minister Smith" article (Smith not yet in dict variants)
# would emit a brand-new titled row and re-create the dupe class. Regex anchored at start,
# case-insensitive, dot optional. Must match the migration 095 strip regex byte-for-byte.
_TITLE_STRIP_RE = re.compile(
    r"^(chief minister|deputy chief minister|prime minister|deputy prime minister|"
    r"vice president|president|minister|senator|justice|governor|mayor|"
    r"honourable|honorable|hon\.?|speaker|"
    r"sri|shri|smt|sm|dr|mr|mrs|ms|prof|capt|col|gen|lt|maj|adv|engr|"
    r"a|an|the|cm|pm)\.?\s+",
    re.IGNORECASE,
)


def _strip_title(key: str) -> str:
    """Strip a single leading title/honorific/article from a lowercase entity-span key.
    Returns the bare form, or the original key if no prefix matched. Used as a fallback at
    dict-lookup time when the full span isn't directly in _ENTITY_DICT — preserves canonical
    resolution for NEW (not-yet-aliased) entities."""
    bare = _TITLE_STRIP_RE.sub("", key, count=1).strip()
    return bare if bare and bare != key and len(bare) > 2 else key


_COMMON_WORDS: frozenset[str] = frozenset({
    "india", "indian", "new", "united",
    "national", "state", "party", "press",
    "times", "news", "world", "global",
    # Short common words exposed by lowering the 3-char minimum
    "the", "and", "for", "act", "law",
    "web", "net", "gov", "per", "via",
    "day", "age", "era", "end", "set",
})


async def load_entity_dictionary(db_conn) -> int:
    """
    Populate _ENTITY_DICT from entity_dictionary table.
    Idempotent — subsequent calls return immediately if already loaded.
    Returns number of lookup keys registered.
    db_conn is a SQLAlchemy AsyncSession.
    """
    global _ENTITY_DICT, _DICT_LOADED
    if _DICT_LOADED:
        return len(_ENTITY_DICT)

    from sqlalchemy import text

    result = await db_conn.execute(
        text(
            "SELECT canonical_name, entity_type, aliases, state, party "
            "FROM entity_dictionary"
        )
    )
    rows = result.fetchall()

    new_dict: dict[str, dict] = {}
    for row in rows:
        surfaces = [row.canonical_name] + [
            (a or "").strip() for a in (row.aliases or []) if (a or "").strip()
        ]
        entry = {
            "canonical_name": row.canonical_name,
            "entity_type": row.entity_type,
            "state": row.state,
            "party": row.party,
            "surfaces": surfaces,  # canonical + aliases -> word-boundary prominence scoring
        }
        new_dict[row.canonical_name.lower()] = entry
        if row.aliases:
            for alias in row.aliases:
                stripped = (alias or "").strip()
                if stripped:
                    new_dict[stripped.lower()] = entry

    _ENTITY_DICT = new_dict
    _DICT_LOADED = True
    logger.info(
        "Entity dictionary loaded: %d entities, %d lookup keys",
        len(rows),
        len(_ENTITY_DICT),
    )

    # Capture current version so the reload task can detect future changes
    try:
        version_row = await db_conn.execute(
            text("SELECT version FROM entity_dict_meta WHERE id = 1")
        )
        vr = version_row.fetchone()
        if vr:
            global _LOADED_VERSION
            _LOADED_VERSION = vr.version
    except Exception:
        pass  # version tracking is advisory; never block NLP startup

    return len(_ENTITY_DICT)


async def check_and_reload_if_stale(db_conn) -> bool:
    """
    Check DB version against the version loaded into memory.
    Reloads _ENTITY_DICT if the DB version is newer.
    Called every 5 minutes by Celery Beat — never on every article.
    Returns True if reloaded, False if already current.
    """
    import time
    global _LOADED_VERSION, _DICT_LOADED, _ENTITY_DICT, _LAST_VERSION_CHECK

    now = time.time()
    # Rate-limit: skip if checked within the last 60 s (guards against burst calls)
    if now - _LAST_VERSION_CHECK < 60:
        return False
    _LAST_VERSION_CHECK = now

    try:
        from sqlalchemy import text as _text
        result = await db_conn.execute(
            _text("SELECT version, entry_count FROM entity_dict_meta WHERE id = 1")
        )
        row = result.fetchone()
        if not row:
            return False

        db_version = row.version
        if db_version <= _LOADED_VERSION:
            logger.debug("Entity dict current (v%d)", _LOADED_VERSION)
            return False

        logger.info(
            "Entity dict version changed %d → %d. Reloading %d entries...",
            _LOADED_VERSION,
            db_version,
            row.entry_count,
        )

        _ENTITY_DICT.clear()
        _DICT_LOADED = False
        count = await load_entity_dictionary(db_conn)
        # _LOADED_VERSION is updated inside load_entity_dictionary via the try block
        if _LOADED_VERSION != db_version:
            _LOADED_VERSION = db_version  # fallback if meta table read failed inside

        logger.info("Entity dict reloaded: %d lookup keys, version %d", count, db_version)
        return True

    except Exception as exc:
        logger.warning("Entity dict version check failed: %s", exc)
        return False


_WB_CACHE: dict[str, "re.Pattern"] = {}


def _wb(s: str) -> "re.Pattern":
    """Cached word-boundary regex for a surface form."""
    p = _WB_CACHE.get(s)
    if p is None:
        p = re.compile(r"\b" + re.escape(s) + r"\b")
        _WB_CACHE[s] = p
    return p


def compute_prominence(surface_forms, title: str, text: str) -> float:
    """
    Score how prominently an entity features in an article (0.0–1.0), matching ANY of its
    surface forms (canonical + aliases) on WORD BOUNDARIES.

    Two fixes over the old substring version:
      * word-boundary, not substring — "Man" no longer matches "Rah-man"/"Mani-pur";
      * scored over ALL surface forms — a "PM Modi" headline scores "Narendra Modi" via the
        "Modi" surface instead of 0 (the canonical never substring-matched the headline).
    Title +3.0, lede (first 300) +2.0, each body mention +1.0 (cap 5), /5.0 capped 1.0.
    Forms shorter than 3 chars are ignored (kills ambiguous 2-char aliases like "US").
    """
    title_l = (title or "").lower()
    lede_l = (text or "").lower()[:300]
    body_l = (text or "").lower()[:5000]
    forms = [f.lower() for f in (surface_forms or []) if f and len(f) >= 3]
    if not forms:
        return 0.0
    score = 0.0
    if any(_wb(f).search(title_l) for f in forms):
        score += 3.0
    if any(_wb(f).search(lede_l) for f in forms):
        score += 2.0
    score += min(sum(len(_wb(f).findall(body_l)) for f in forms), 5) * 1.0
    return min(score / 5.0, 1.0)


def extract_entities(
    title: str,
    text: str,
    nlp_model,  # spacy Language
) -> list[dict]:
    """
    Extract and resolve entities using SpaCy + dictionary matching.

    Returns up to 20 entity dicts sorted by prominence desc:
      {name, type, label, confidence, prominence}
    """
    if not title and not text:
        return []

    combined = f"{title or ''} {text or ''}"
    seen_canonical: set[str] = set()
    entities: list[dict] = []

    # Layer 1 — SpaCy candidate spans
    spacy_spans: list[tuple[str, str]] = []
    try:
        doc = nlp_model(combined[:1000])
        spacy_spans = [
            (ent.text, ent.label_)
            for ent in doc.ents
            if ent.label_ in ("PERSON", "ORG", "GPE", "LOC", "PRODUCT", "NORP")
        ]
    except Exception as exc:
        logger.warning("SpaCy NER failed: %s", exc)

    # Layer 2 — dictionary resolution of SpaCy spans
    for span_text, spacy_label in spacy_spans:  # noqa: B007 (spacy_label unused after fix2)
        key = span_text.lower().strip()
        # min length 3 + common-word guard (matches the title-scan path) — stops a SpaCy
        # "US"/"IT"/"UN" span resolving to a short-alias entity (e.g. US -> United Spirits).
        if not key or key == "none" or len(key) < 3 or key in _COMMON_WORDS:
            continue
        if key not in _ENTITY_DICT:
            # Tier 4 fallback: strip leading title/honorific/article and re-try ONCE. Catches
            # NEW articles whose titled span isn't yet aliased in dict ("Chief Minister Smith"
            # -> "smith") so we don't keep creating dupes downstream.
            bare = _strip_title(key)
            if bare == key or bare not in _ENTITY_DICT:
                continue
            key = bare
        entry = _ENTITY_DICT[key]
        canonical = entry["canonical_name"]
        if canonical in seen_canonical:
            continue
        seen_canonical.add(canonical)
        entities.append({
            "name": canonical,
            "type": entry["entity_type"],
            "label": entry["entity_type"],
            "confidence": 0.9,
            "prominence": round(compute_prominence(entry["surfaces"], title, text), 3),
        })

    # Direct title scan via word + 1-3gram lookup (O(title), word-boundary BY CONSTRUCTION:
    # "man" only matches the whole word, never "Rah-man"). Replaces the old O(17K-dict)
    # substring loop that both polluted the set and was the backfill's hot path.
    title_lower = (title or "").lower()
    words = re.findall(r"\b[\w']+\b", title_lower)
    cands: set[str] = set()
    for i in range(len(words)):
        cands.add(words[i])
        if i + 1 < len(words):
            cands.add(f"{words[i]} {words[i+1]}")
        if i + 2 < len(words):
            cands.add(f"{words[i]} {words[i+1]} {words[i+2]}")
    for key in cands:
        if len(key) < 3 or key in _COMMON_WORDS:
            continue
        if key not in _ENTITY_DICT:
            # Tier 4 fallback (mirrors the SpaCy-resolution branch above)
            bare = _strip_title(key)
            if bare == key or bare not in _ENTITY_DICT or bare in _COMMON_WORDS:
                continue
            key = bare
        entry = _ENTITY_DICT[key]
        canonical = entry["canonical_name"]
        if canonical in seen_canonical:
            continue
        seen_canonical.add(canonical)
        entities.append({
            "name": canonical,
            "type": entry["entity_type"],
            "label": "DICT_MATCH",
            "confidence": 0.85,
            "prominence": round(compute_prominence(entry["surfaces"], title, text), 3),
        })

    entities.sort(key=lambda x: x["prominence"], reverse=True)
    return entities[:20]
