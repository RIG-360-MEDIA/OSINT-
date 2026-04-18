"""
Entity extraction with two-layer resolution:
  Layer 1 — SpaCy NER for candidate spans
  Layer 2 — entity_dictionary table for canonical resolution + prominence scoring
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# ── Module-level singleton ─────────────────────────────────────────────────────
# Keyed by lowercased canonical name AND all lowercased aliases → same entry dict.
# Loaded once at worker startup via load_entity_dictionary(); O(1) lookup per span.

_ENTITY_DICT: dict[str, dict] = {}
_DICT_LOADED: bool = False
_LOADED_VERSION: int = 0
_LAST_VERSION_CHECK: float = 0.0

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
        entry = {
            "canonical_name": row.canonical_name,
            "entity_type": row.entity_type,
            "state": row.state,
            "party": row.party,
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


def compute_prominence(entity_name: str, title: str, text: str) -> float:
    """
    Score how prominently an entity features in an article. Returns 0.0–1.0.

    Scoring rationale (prevents sidebar contamination):
      Title mention      → +3.0  (headline entity — high signal)
      First 300 chars    → +2.0  (lede paragraph — strong signal)
      Each body mention  → +1.0  (cap at 5 occurrences)
      Normalised         → score / 5.0, capped at 1.0

    A sidebar-only entity mentioned once in the body scores 0.2.
    A headline entity scores at least 0.6 before any body count.
    """
    name = entity_name.lower()
    title_l = (title or "").lower()
    text_l = (text or "").lower()

    score = 0.0
    if name in title_l:
        score += 3.0
    if name in text_l[:300]:
        score += 2.0
    score += min(text_l.count(name), 5) * 1.0

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
        if not key or key == "none" or len(key) < 2:
            continue
        if key not in _ENTITY_DICT:
            continue
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
            "prominence": round(compute_prominence(canonical, title, text), 3),
        })

    # Direct title scan — catches entities SpaCy missed (e.g. Kaleshwaram → NORP)
    title_lower = (title or "").lower()
    for key, entry in _ENTITY_DICT.items():
        if not key or key == "none" or len(key) < 3:
            continue
        if key.lower() in _COMMON_WORDS:
            continue
        if key not in title_lower:
            continue
        canonical = entry["canonical_name"]
        if canonical in seen_canonical:
            continue
        seen_canonical.add(canonical)
        entities.append({
            "name": canonical,
            "type": entry["entity_type"],
            "label": "DICT_MATCH",
            "confidence": 0.85,
            "prominence": round(compute_prominence(canonical, title, text), 3),
        })

    entities.sort(key=lambda x: x["prominence"], reverse=True)
    return entities[:20]
