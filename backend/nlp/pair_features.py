#!/usr/bin/env python3
"""
pair_features.py — CANONICAL pair-feature extractor (SSOT for train AND serve).

Why this exists
---------------
The original `analytics.pair_scores` builder (the per-feature UPDATE passes) is lost
(only the table DDL survives in rig-news `0009-pair-scores.sql`). Two features we now
need did not exist then anyway (`shared_numbers`; V4 cosine is a serve-time signal).
So per the analytics-chat decision (2026-06-02) we make ONE module the single source
of truth and import it from BOTH places that compute features:

  * the training-CSV generator (scripts/maintenance/extract_edge_features.py)
  * the production clustering job (#7)

If the same code computes features on both sides, train/serve skew is impossible.
The module is VERSION-STAMPED so we can never silently diverge again.

Semantics preserved from the lost builder where confirmed against the 28,300 stored
rows (validated, errors ~0): trgm_* = pg_trgm similarity(); same_source/same_language
= id/lang equality; canonical_url_match = url equality; length_ratio = max/min word
count (the NUMERIC(5,1) >=1 column). Where the original source is unrecoverable, the
field is defined sensibly here and BECOMES canonical (we own serve too):
  * time_diff_hours = |collected_at delta| in hours
  * event_date_match = published_at::date equality
  * shared_actors/locations = name-intersection of entities_extracted by `type`
Fields with NO recoverable substrate are emitted as 0 and FLAGGED (never dropped),
per the feature-extract spec:
  * idf_loc_score (needs the lost location-IDF table)
  * shared_speakers (no clean speaker source in entities_extracted)

`shared_numbers` (NEW): count of exact numeric tokens shared between the two
articles' title+lead — language-independent; POSITIVE-only signal (matching "82 dead"
boosts same-event; differing numbers are NOT a different-event signal — proven in the
v2 mine). Years are dropped so boilerplate cannot inflate it.
"""
from __future__ import annotations

import re

PAIR_FEATURES_VERSION = "pf-v1-2026-06-02"

# Exact CSV header the fit-edge-scorer harness expects, + shared_numbers (NEW, last).
FEATURE_HEADER = [
    "a_id", "b_id", "label", "a_language", "b_language",
    "trgm_subject", "trgm_title", "shared_actors", "shared_speakers",
    "shared_locations", "shared_primary_loc", "idf_loc_score",
    "canonical_url_match", "event_date_match", "length_ratio",
    "time_diff_hours", "same_source", "shared_numbers",
]

# Fields with no recoverable production source — emitted 0 + reported as a coverage gap.
FLAGGED_NULL_FEATURES = ("idf_loc_score", "shared_speakers")

# entities_extracted[].type buckets (array of {name,type,label,confidence,prominence}).
ACTOR_TYPES = ("person",)
LOCATION_TYPES = ("location", "constituency", "gpe")

_YEARS = {"2021", "2022", "2023", "2024", "2025", "2026", "2027", "2028"}
_NUM_RE = re.compile(r"\d+(?:[.,]\d+)*")


def numbers_of(text: str) -> set[str]:
    """Salient numeric tokens (commas stripped; ubiquitous years + all-zero dropped).

    Shared verbatim with the miner so the training signal matches what serve sees.
    """
    out: set[str] = set()
    for tok in _NUM_RE.findall(text or ""):
        norm = tok.replace(",", "")
        if norm in _YEARS or norm.strip("0.") == "":
            continue
        out.add(norm)
    return out


def shared_numbers(a_text: str, b_text: str) -> int:
    return len(numbers_of(a_text) & numbers_of(b_text))


def structured_sql(staging_table: str) -> str:
    """SQL computing every STRUCTURED feature for the (a_id,b_id) pairs in
    `staging_table` (which must also carry a `label` column). Also returns the
    raw title+lead text per side so the caller computes `shared_numbers` in Python
    (one number-extraction code path, reused at serve)."""
    actor = ",".join("'%s'" % t for t in ACTOR_TYPES)
    loc = ",".join("'%s'" % t for t in LOCATION_TYPES)
    return f"""
    SELECT
      p.a_id, p.b_id, p.label,
      a.language_detected AS a_language, b.language_detected AS b_language,
      similarity(coalesce(a.primary_subject,''), coalesce(b.primary_subject,'')) AS trgm_subject,
      similarity(coalesce(a.title,''),           coalesce(b.title,''))           AS trgm_title,
      (SELECT count(*) FROM (
         SELECT lower(e->>'name') n FROM jsonb_array_elements(coalesce(a.entities_extracted,'[]'::jsonb)) e WHERE e->>'type' IN ({actor})
         INTERSECT
         SELECT lower(e->>'name')   FROM jsonb_array_elements(coalesce(b.entities_extracted,'[]'::jsonb)) e WHERE e->>'type' IN ({actor})
      ) z) AS shared_actors,
      0 AS shared_speakers,                                   -- FLAGGED: no clean source
      (SELECT count(*) FROM (
         SELECT lower(e->>'name') n FROM jsonb_array_elements(coalesce(a.entities_extracted,'[]'::jsonb)) e WHERE e->>'type' IN ({loc})
         INTERSECT
         SELECT lower(e->>'name')   FROM jsonb_array_elements(coalesce(b.entities_extracted,'[]'::jsonb)) e WHERE e->>'type' IN ({loc})
      ) z) AS shared_locations,
      (a.geo_primary IS NOT NULL AND a.geo_primary = b.geo_primary) AS shared_primary_loc,
      0::numeric AS idf_loc_score,                            -- FLAGGED: lost IDF table
      coalesce(a.canonical_url = b.canonical_url, false) AS canonical_url_match,
      coalesce(a.published_at::date = b.published_at::date, false) AS event_date_match,
      CASE WHEN least(a.word_count, b.word_count) > 0
           THEN round(greatest(a.word_count,b.word_count)::numeric
                      / least(a.word_count,b.word_count), 1) END AS length_ratio,
      round((abs(extract(epoch FROM a.collected_at - b.collected_at)) / 3600.0)::numeric, 1) AS time_diff_hours,
      (a.source_id = b.source_id) AS same_source,
      (coalesce(a.title,'') || ' ' || coalesce(a.lead_text_translated,'')) AS a_numtext,
      (coalesce(b.title,'') || ' ' || coalesce(b.lead_text_translated,'')) AS b_numtext
    FROM {staging_table} p
    JOIN articles a ON a.id = p.a_id
    JOIN articles b ON b.id = p.b_id
    """


def row_to_feature(cols: list[str], raw) -> dict:
    """One (cursor.description cols, raw row) -> feature dict. Extracted as the single
    per-row core shared by rows_to_features (batch) and iter_features (streaming), so
    both paths emit byte-identical dicts — no train/serve and no batch/stream skew."""
    r = dict(zip(cols, raw))
    return {
        "a_id": r["a_id"], "b_id": r["b_id"], "label": r["label"],
        "a_language": r["a_language"] or "", "b_language": r["b_language"] or "",
        "trgm_subject": _num(r["trgm_subject"]), "trgm_title": _num(r["trgm_title"]),
        "shared_actors": r["shared_actors"] or 0,
        "shared_speakers": r["shared_speakers"] or 0,
        "shared_locations": r["shared_locations"] or 0,
        "shared_primary_loc": _b(r["shared_primary_loc"]),
        "idf_loc_score": _num(r["idf_loc_score"]),
        "canonical_url_match": _b(r["canonical_url_match"]),
        "event_date_match": _b(r["event_date_match"]),
        "length_ratio": _num(r["length_ratio"]),
        "time_diff_hours": _num(r["time_diff_hours"]),
        "same_source": _b(r["same_source"]),
        "shared_numbers": shared_numbers(r["a_numtext"], r["b_numtext"]),
    }


def rows_to_features(cursor) -> list[dict]:
    """Run a cursor already executed on structured_sql(); fold in shared_numbers.
    Returns dicts keyed by FEATURE_HEADER (booleans as 0/1, label passthrough)."""
    cols = [d[0] for d in cursor.description]
    return [row_to_feature(cols, raw) for raw in cursor.fetchall()]


def iter_features(cursor, batch: int = 20000):
    """Streaming twin of rows_to_features: yields the SAME feature dicts one at a time,
    fetching `batch` rows at a time so a large candidate set never fully materialises.
    Pair with a server-side (named) psycopg2 cursor to also bound libpq's client buffer
    — at whole-corpus scale (500K+ candidate pairs) fetchall() alone peaks multi-GiB."""
    cols = None
    while True:
        chunk = cursor.fetchmany(batch)
        if not chunk:
            break
        if cols is None:  # named (server-side) cursors populate .description only AFTER first fetch
            cols = [d[0] for d in cursor.description]
        for raw in chunk:
            yield row_to_feature(cols, raw)


def _b(v) -> int:
    return 1 if v else 0


def _num(v):
    return "" if v is None else float(v)
