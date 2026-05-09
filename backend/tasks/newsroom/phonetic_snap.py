"""
Phonetic entity snapping.

After reconcile, the canonical text contains proper-noun candidates.
ASR systems regularly mangle Indian proper nouns ("Revant Reddi" for
"Revanth Reddy"), so exact-match lookup against entity_dictionary
misses many references. We add a phonetic fallback:

  1. Tokenise the canonical text into capitalised n-grams (1–3 words)
  2. For each candidate, compute Soundex + Metaphone codes
  3. Compare against pre-computed codes for entity_dictionary entries
     (canonical_name + aliases). Edit distance ≤ 2 = match.
  4. Snap to the canonical entity, mark `was_phonetic=True`.

The entity codes table is built lazily once per worker process from a
single SELECT against entity_dictionary. Refresh-on-version is left
to the existing entity_dict_version mechanism — when a new version
ships, the worker restarts on the next deploy.

Returns a list of (entity_id, span_start, span_end, was_phonetic)
tuples to be inserted into newsroom_entity_mentions.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EntityMention:
    entity_id: str
    span_start: int
    span_end: int
    was_phonetic: bool


_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z'-]+")

# Tightening (2026-05-09): the v1 phonetic snap was too generous — edit
# distance ≤ 2 + 1-gram + 3-char minimum produced lots of false matches
# ("Bajaj Holdings", "Badminton Association", "Aditya Birla Health
# Insurance", "Announcement of corporate tax rate cuts" against a Telugu
# BJP-MLA story). New rules:
#   - Phonetic match: edit distance ≤ 1 (was 2)
#   - Minimum candidate phrase length: 5 chars (was 3)
#   - Minimum entity name length: 5 chars
#   - Skip 1-grams entirely; only 2- and 3-token phrases
#   - Skip entities whose canonical_name is multi-sentence ("Defected
#     from..." style — those are notes, not entities — len ≥ 40 OR
#     contains a period mid-name)
_MIN_TOKEN_LEN = 5
_MAX_EDIT_DIST = 1
_MIN_NGRAM = 2
_MAX_NGRAM = 3
_MAX_ENTITY_NAME_LEN = 40


# Cached per-process entity index: list of dicts {id, name, soundex, metaphone, lower}
_ENTITY_INDEX: list[dict] | None = None


def _ascii_fold(s: str) -> str:
    """Strip diacritics so Indian-script entities compare against
    transliterated variants (e.g. 'రేవంత్ రెడ్డి' canonicalised
    aliases include 'Revanth Reddy')."""
    return "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    )


def _phonetic_codes(name: str) -> tuple[str, str]:
    """Return (soundex, metaphone). Empty string if input is empty."""
    folded = _ascii_fold(name).strip()
    if not folded:
        return ("", "")
    try:
        from pyphonetics import Soundex
        from metaphone import doublemetaphone
    except ImportError:
        # Phonetic libs not yet installed — return empty so callers
        # downgrade to exact-match-only.
        return ("", "")

    try:
        sx = Soundex().phonetics(folded)
    except Exception:  # noqa: BLE001
        sx = ""
    try:
        mp_primary, _ = doublemetaphone(folded)
    except Exception:  # noqa: BLE001
        mp_primary = ""
    return (sx, mp_primary)


def load_entity_index(db) -> list[dict]:
    """Load the entity index lazily on first call. `db` is a sync
    psycopg2 cursor or sqlalchemy Session — caller passes whatever.

    Schema expected: entity_dictionary(id uuid, canonical_name text,
    aliases text[]). We expand each entity into one index entry per
    name (canonical + each alias)."""
    global _ENTITY_INDEX
    if _ENTITY_INDEX is not None:
        return _ENTITY_INDEX

    rows = db.execute(
        "SELECT id, canonical_name, COALESCE(aliases, ARRAY[]::text[]) FROM entity_dictionary"
    ).fetchall()
    index: list[dict] = []
    for r in rows:
        ent_id = str(r[0])
        canonical = r[1]
        aliases = list(r[2] or [])
        for n in [canonical] + aliases:
            if not n:
                continue
            sx, mp = _phonetic_codes(n)
            index.append({
                "id": ent_id,
                "name": n,
                "lower": _ascii_fold(n).lower(),
                "soundex": sx,
                "metaphone": mp,
                "is_alias": n != canonical,
            })
    _ENTITY_INDEX = index
    logger.info("phonetic_snap: loaded %d entity index entries", len(index))
    return index


def snap_text(text: str, entity_index: list[dict]) -> list[EntityMention]:
    """Find entity mentions in `text`. Returns deduped EntityMention list."""
    if not text or not entity_index:
        return []

    out: list[EntityMention] = []
    seen: set[tuple[str, int, int]] = set()
    text_lower = _ascii_fold(text).lower()

    # Pass 1: exact substring match on canonical name + aliases.
    # Fast and high-precision. Skip pathologically short or sentence-
    # length names — those produce false hits.
    for entry in entity_index:
        nm = entry["lower"]
        if not nm or len(nm) < _MIN_TOKEN_LEN:
            continue
        if len(nm) > _MAX_ENTITY_NAME_LEN or "." in nm:
            continue
        # Reject GENERIC aliases that would over-match. Single-word
        # lowercase aliases like "district", "minister", "court" wreck
        # results — we saw 18 Gujarat-district rows fire on "district"
        # appearing in a Telangana transcript. Allow alias only if:
        #   - multi-word (e.g. "Narendra Modi"), OR
        #   - all-uppercase acronym (e.g. "BJP", "TMC", "NDA"), OR
        #   - ≥6 chars AND has at least one uppercase letter (proper-noun-y).
        if entry.get("is_alias"):
            raw = entry["name"].strip()
            if " " in raw:
                pass
            elif raw.isupper() and len(raw) >= 2:
                pass
            elif len(raw) >= 6 and any(c.isupper() for c in raw):
                pass
            else:
                continue
        idx = text_lower.find(nm)
        while idx != -1:
            # Only count exact substring matches if the surrounding
            # characters are word boundaries (avoid "ram" inside "framework")
            left_ok = idx == 0 or not text_lower[idx - 1].isalnum()
            right_end = idx + len(nm)
            right_ok = right_end == len(text_lower) or not text_lower[right_end].isalnum()
            if left_ok and right_ok:
                key = (entry["id"], idx, right_end)
                if key not in seen:
                    seen.add(key)
                    out.append(EntityMention(
                        entity_id=entry["id"],
                        span_start=idx,
                        span_end=right_end,
                        was_phonetic=False,
                    ))
            idx = text_lower.find(nm, idx + 1)

    # Pass 2: phonetic n-gram match. Only for tokens not already
    # covered by an exact match.
    tokens = list(_TOKEN_RE.finditer(text))
    covered_offsets: set[int] = set()
    for m in out:
        covered_offsets.update(range(m.span_start, m.span_end))

    # Try only 2- and 3-grams (1-grams are too noisy on common short names).
    # Longest first so we don't double-count.
    for n in range(_MAX_NGRAM, _MIN_NGRAM - 1, -1):
        for i in range(len(tokens) - n + 1):
            grp = tokens[i:i + n]
            sp_start = grp[0].start()
            sp_end = grp[-1].end()
            if any(o in covered_offsets for o in range(sp_start, sp_end)):
                continue
            phrase = text[sp_start:sp_end]
            if not phrase[0].isupper():
                continue                    # only proper-noun candidates
            sx, mp = _phonetic_codes(phrase)
            if not sx and not mp:
                continue
            best = _phonetic_match(phrase, sx, mp, entity_index)
            if best:
                key = (best["id"], sp_start, sp_end)
                if key not in seen:
                    seen.add(key)
                    out.append(EntityMention(
                        entity_id=best["id"],
                        span_start=sp_start,
                        span_end=sp_end,
                        was_phonetic=True,
                    ))
                    covered_offsets.update(range(sp_start, sp_end))

    return out


def _phonetic_match(phrase: str, sx: str, mp: str, index: list[dict]) -> dict | None:
    """Find the entity whose phonetic code matches and is closest by
    edit-distance to `phrase`. Returns None if no match within
    `_MAX_EDIT_DIST`. Skips entities whose canonical name looks like
    a sentence (commas, periods, > _MAX_ENTITY_NAME_LEN chars)."""
    if len(phrase) < _MIN_TOKEN_LEN:
        return None
    candidates = [
        e for e in index
        if ((sx and e["soundex"] == sx) or (mp and e["metaphone"] == mp))
        and len(e["lower"]) >= _MIN_TOKEN_LEN
        and len(e["lower"]) <= _MAX_ENTITY_NAME_LEN
        and "." not in e["lower"]
    ]
    if not candidates:
        return None
    phrase_l = _ascii_fold(phrase).lower()
    best = None
    best_d = 1e9
    for c in candidates:
        d = _levenshtein(phrase_l, c["lower"])
        if d < best_d:
            best_d = d
            best = c
    return best if best_d <= _MAX_EDIT_DIST else None


def _levenshtein(a: str, b: str) -> int:
    """Iterative Levenshtein. Caps at len(longer)+1 → trivial cost
    here since names are short."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            curr[j] = min(
                curr[j - 1] + 1,
                prev[j] + 1,
                prev[j - 1] + (0 if ca == cb else 1),
            )
        prev = curr
    return prev[-1]
