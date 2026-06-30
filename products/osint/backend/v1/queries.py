"""Scope-filtered read queries for /v1 — the data layer of the gateway.

Every query here is constrained to the caller's provisioned scope, and selects
ONLY client-safe columns (this is where field-whitelisting is enforced at the
source — internal columns like embeddings, substrate status, scoring internals
are never named in a SELECT).

Grounded in the live schema (see docs/handoffs/db-reference):
  * articles            — filter recency on collected_at (NOT NULL); source
                          name via JOIN sources; language_detected; is_duplicate.
  * article_entity_mentions (matview) — article_id ↔ entity_id link.
  * article_stances     — actor_entity_id IS the TARGET (legacy-named 'actor');
                          ~45% populated, so sentiment is an honest sample.
  * entity_dictionary   — id, canonical_name, entity_type, redirected_to.

Honesty: where the underlying data is partial (stale matview, sparse stance
links), the serializers label outputs as sampled/estimated rather than implying
exhaustiveness.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text

from .pagination import decode_cursor, encode_cursor

# Map a client sentiment label to the set of raw stance values it covers.
_STANCE_SETS = {
    "supportive": ("supportive", "positive"),
    "critical": ("critical", "negative"),
    "neutral": ("neutral",),
}

# Hard ceiling on how many entities we'll enumerate for an all_entities org.
_ALL_ENTITIES_LIST_CAP = 500


# ── Entities ────────────────────────────────────────────────────────────────

async def list_scoped_entities(db, entity_ids: list[str], all_entities: bool, limit: int) -> list[dict[str, Any]]:
    """The org's visible entities (id, name, type). Empty scope => []."""
    if all_entities:
        rows = (await db.execute(text("""
            SELECT id::text AS id, canonical_name AS name, entity_type AS type
              FROM entity_dictionary
             WHERE redirected_to IS NULL AND canonical_name IS NOT NULL
             ORDER BY canonical_name
             LIMIT :lim
        """), {"lim": min(limit, _ALL_ENTITIES_LIST_CAP)})).fetchall()
    elif entity_ids:
        rows = (await db.execute(text("""
            SELECT id::text AS id, canonical_name AS name, entity_type AS type
              FROM entity_dictionary
             WHERE id = ANY(CAST(:ids AS uuid[]))
             ORDER BY canonical_name
        """), {"ids": entity_ids})).fetchall()
    else:
        return []
    return [{"id": r.id, "name": r.name, "type": r.type} for r in rows]


async def get_entity_row(db, entity_id: str) -> dict[str, Any] | None:
    row = (await db.execute(text("""
        SELECT id::text AS id, canonical_name AS name, entity_type AS type
          FROM entity_dictionary
         WHERE id = CAST(:id AS uuid)
    """), {"id": entity_id})).fetchone()
    return {"id": row.id, "name": row.name, "type": row.type} if row else None


# NOTE (trust dependency): entity_coverage_count + sentiment_split take a bare
# entity_id with no scope clause of their own. Callers MUST pass an id that has
# already cleared require_entity_in_scope() — every current call site does. Keep
# that invariant if you add new callers.
async def entity_coverage_count(db, entity_id: str, window_hours: int) -> int:
    row = (await db.execute(text("""
        SELECT count(DISTINCT a.id) AS n
          FROM articles a
          JOIN article_entity_mentions aem ON aem.article_id = a.id
         WHERE aem.entity_id = CAST(:eid AS uuid)
           AND a.collected_at > now() - make_interval(hours => :h)
           AND NOT COALESCE(a.is_duplicate, false)
    """), {"eid": entity_id, "h": window_hours})).fetchone()
    return int(row.n) if row else 0


# ── Sentiment (directed stance toward a target entity) ──────────────────────

async def sentiment_split(db, entity_id: str, window_hours: int) -> dict[str, Any]:
    """Stance split toward one target entity over the window.

    Joins on actor_entity_id (the TARGET). Only ~45% of stance rows carry it,
    so this is an honest sample of *classified, entity-linked* coverage, not a
    census — the serializer labels it as such.
    """
    rows = (await db.execute(text("""
        SELECT lower(st.stance) AS stance, count(*) AS n
          FROM article_stances st
         WHERE st.actor_entity_id = CAST(:eid AS uuid)
           AND st.created_at > now() - make_interval(hours => :h)
         GROUP BY lower(st.stance)
    """), {"eid": entity_id, "h": window_hours})).fetchall()

    supportive = neutral = critical = 0
    for r in rows:
        s = (r.stance or "").strip()
        if s in _STANCE_SETS["supportive"]:
            supportive += int(r.n)
        elif s in _STANCE_SETS["critical"]:
            critical += int(r.n)
        elif s in _STANCE_SETS["neutral"]:
            neutral += int(r.n)
    total = supportive + neutral + critical
    net_lean = round((supportive - critical) / total, 4) if total else 0.0
    return {
        "supportive": supportive,
        "neutral": neutral,
        "critical": critical,
        "total": total,
        "net_lean": net_lean,
    }


# ── Coverage volume (scoped article counts per day) ─────────────────────────

async def coverage_daily(db, entity_ids: list[str], all_entities: bool, window_hours: int) -> dict[str, Any]:
    if not all_entities and not entity_ids:
        return {"total": 0, "daily": []}
    mention_clause = "" if all_entities else """
           AND EXISTS (SELECT 1 FROM article_entity_mentions aem
                        WHERE aem.article_id = a.id
                          AND aem.entity_id = ANY(CAST(:eids AS uuid[])))"""
    sql = f"""
        SELECT date_trunc('day', a.collected_at)::date AS day, count(*) AS n
          FROM articles a
         WHERE a.collected_at > now() - make_interval(hours => :h)
           AND NOT COALESCE(a.is_duplicate, false){mention_clause}
         GROUP BY day ORDER BY day
    """
    params: dict[str, Any] = {"h": window_hours}
    if not all_entities:
        params["eids"] = entity_ids
    rows = (await db.execute(text(sql), params)).fetchall()
    daily = [{"date": r.day.isoformat(), "count": int(r.n)} for r in rows]
    return {"total": sum(d["count"] for d in daily), "daily": daily}


# ── Articles (the filterable coverage feed) ─────────────────────────────────

def _stance_set_for(sentiment: str | None) -> list[str] | None:
    if not sentiment:
        return None
    return list(_STANCE_SETS.get(sentiment, ()))


async def list_scoped_articles(
    db,
    *,
    entity_ids: list[str],
    all_entities: bool,
    window_hours: int,
    language: str | None,
    sentiment: str | None,
    cursor: str | None,
    limit: int,
) -> tuple[list[dict[str, Any]], str | None]:
    """Scoped, filtered, keyset-paginated article list.

    Returns (rows, next_cursor). An org with empty scope (and not all_entities)
    gets [] — never the whole corpus.
    """
    if not all_entities and not entity_ids:
        return [], None

    clauses = [
        "a.collected_at > now() - make_interval(hours => :h)",
        "NOT COALESCE(a.is_duplicate, false)",
    ]
    params: dict[str, Any] = {"h": window_hours, "lim": limit}

    if not all_entities:
        clauses.append("""EXISTS (SELECT 1 FROM article_entity_mentions aem
                                   WHERE aem.article_id = a.id
                                     AND aem.entity_id = ANY(CAST(:eids AS uuid[])))""")
        params["eids"] = entity_ids

    if language:
        clauses.append("a.language_detected = :lang")
        params["lang"] = language

    stance_set = _stance_set_for(sentiment)
    if stance_set:
        # Coverage carrying the requested tone toward an in-scope target.
        if all_entities:
            clauses.append("""EXISTS (SELECT 1 FROM article_stances st
                                       WHERE st.article_id = a.id
                                         AND lower(st.stance) = ANY(:stances))""")
        else:
            clauses.append("""EXISTS (SELECT 1 FROM article_stances st
                                       WHERE st.article_id = a.id
                                         AND st.actor_entity_id = ANY(CAST(:eids AS uuid[]))
                                         AND lower(st.stance) = ANY(:stances))""")
        params["stances"] = stance_set

    cur = decode_cursor(cursor)
    if cur is not None:
        clauses.append("(a.collected_at, a.id) < (CAST(:ct AS timestamptz), CAST(:ci AS uuid))")
        params["ct"], params["ci"] = cur

    where = " AND ".join(clauses)
    sql = f"""
        SELECT a.id::text AS id, a.title AS headline,
               COALESCE(NULLIF(a.lead_text_translated, ''), NULLIF(a.lead_text_original, '')) AS summary,
               s.name AS source, a.url, a.language_detected AS language,
               a.published_at, a.collected_at, a.geo_primary
          FROM articles a
          JOIN sources s ON s.id = a.source_id
         WHERE {where}
         ORDER BY a.collected_at DESC, a.id DESC
         LIMIT :lim
    """
    rows = (await db.execute(text(sql), params)).fetchall()

    next_cursor = None
    if len(rows) == limit:
        last = rows[-1]
        next_cursor = encode_cursor(last.collected_at, last.id)

    return [dict(r._mapping) for r in rows], next_cursor


async def get_scoped_article(db, article_id: str, entity_ids: list[str], all_entities: bool) -> dict[str, Any] | None:
    """One article, only if it's within the caller's scope (IDOR guard).

    For a non-all_entities org the article must mention a scoped entity, else
    None (the route turns that into an identical 404).
    """
    clauses = ["a.id = CAST(:aid AS uuid)", "NOT COALESCE(a.is_duplicate, false)"]
    params: dict[str, Any] = {"aid": article_id}
    if not all_entities:
        if not entity_ids:
            return None
        clauses.append("""EXISTS (SELECT 1 FROM article_entity_mentions aem
                                   WHERE aem.article_id = a.id
                                     AND aem.entity_id = ANY(CAST(:eids AS uuid[])))""")
        params["eids"] = entity_ids
    where = " AND ".join(clauses)
    row = (await db.execute(text(f"""
        SELECT a.id::text AS id, a.title AS headline,
               COALESCE(NULLIF(a.lead_text_translated, ''), NULLIF(a.lead_text_original, '')) AS summary,
               s.name AS source, a.url, a.language_detected AS language,
               a.published_at, a.geo_primary
          FROM articles a
          JOIN sources s ON s.id = a.source_id
         WHERE {where}
         LIMIT 1
    """), params)).fetchone()
    return dict(row._mapping) if row else None


_PILLAR_PARTS = ("article", "clip", "cutting")


async def entity_multi_coverage(
    db,
    *,
    entity_id: str,
    window_hours: int,
    language: str | None,
    pillars: list[str],
    limit: int,
) -> list[dict[str, Any]]:
    """Unified recent coverage about ONE (already scope-verified) entity across
    news articles, YouTube clips, and newspaper cuttings — one merged feed.

    Each pillar joins its own live entity-mention matview on entity_id. The
    caller MUST have cleared require_entity_in_scope(entity_id) first. The
    f-string only interpolates a FIXED language clause (value bound via :lang).
    """
    parts: list[str] = []
    params: dict[str, Any] = {"eid": entity_id, "h": window_hours, "lim": limit}
    lang_a = "AND a.language_detected = :lang" if language else ""
    lang_c = "AND c.transcript_language = :lang" if language else ""
    lang_cl = "AND COALESCE(cl.detected_language, cl.language) = :lang" if language else ""
    if language:
        params["lang"] = language

    if "article" in pillars:
        parts.append(f"""
            SELECT 'article' AS type, a.id::text AS id, a.title AS headline,
                   s.name AS source, a.url AS url, a.language_detected AS language,
                   a.published_at AS published_at, a.collected_at AS sortdate
              FROM articles a
              JOIN sources s ON s.id = a.source_id
              JOIN article_entity_mentions aem ON aem.article_id = a.id
             WHERE aem.entity_id = CAST(:eid AS uuid)
               AND a.collected_at > now() - make_interval(hours => :h)
               AND NOT COALESCE(a.is_duplicate, false) {lang_a}
        """)
    if "clip" in pillars:
        parts.append(f"""
            SELECT 'clip' AS type, c.id::text AS id, c.video_title AS headline,
                   c.channel_name AS source, c.video_url AS url,
                   c.transcript_language AS language,
                   c.video_published_at AS published_at,
                   COALESCE(c.created_at, c.video_published_at) AS sortdate
              FROM youtube_clips_v2 c
              JOIN youtube_clip_entity_mentions m ON m.clip_id = c.id
             WHERE m.entity_id = CAST(:eid AS uuid)
               AND COALESCE(c.created_at, c.video_published_at) > now() - make_interval(hours => :h)
               {lang_c}
        """)
    if "cutting" in pillars:
        parts.append(f"""
            SELECT 'cutting' AS type, cl.id::text AS id,
                   COALESCE(cl.headline_translated, cl.headline) AS headline,
                   ns.name AS source, NULL::text AS url,
                   COALESCE(cl.detected_language, cl.language) AS language,
                   cl.edition_date::timestamptz AS published_at,
                   cl.collected_at AS sortdate
              FROM clippings cl
              JOIN clipping_entity_mentions m ON m.clipping_id = cl.id
              LEFT JOIN newspaper_sources ns ON ns.id = cl.newspaper_source_id
             WHERE m.entity_id = CAST(:eid AS uuid)
               AND cl.collected_at > now() - make_interval(hours => :h)
               AND NOT COALESCE(cl.is_duplicate, false) {lang_cl}
        """)

    if not parts:
        return []
    union = " UNION ALL ".join(parts)
    sql = f"SELECT * FROM ({union}) u ORDER BY sortdate DESC NULLS LAST LIMIT :lim"
    rows = (await db.execute(text(sql), params)).fetchall()
    return [dict(r._mapping) for r in rows]


async def article_entities(
    db, article_id: str, entity_ids: list[str], all_entities: bool
) -> list[dict[str, Any]]:
    """Entities mentioned in one article — SCOPED.

    A scoped client only ever sees entities within their own scope, never the
    other entities an article happens to mention (which could be another org's
    provisioned entity). all_entities orgs see the full mention list.
    """
    if all_entities:
        rows = (await db.execute(text("""
            SELECT entity_id::text AS id, canonical_name AS name, entity_type AS type
              FROM article_entity_mentions
             WHERE article_id = CAST(:aid AS uuid)
             LIMIT 25
        """), {"aid": article_id})).fetchall()
    elif entity_ids:
        rows = (await db.execute(text("""
            SELECT entity_id::text AS id, canonical_name AS name, entity_type AS type
              FROM article_entity_mentions
             WHERE article_id = CAST(:aid AS uuid)
               AND entity_id = ANY(CAST(:eids AS uuid[]))
             LIMIT 25
        """), {"aid": article_id, "eids": entity_ids})).fetchall()
    else:
        return []
    return [{"id": r.id, "name": r.name, "type": r.type} for r in rows]
