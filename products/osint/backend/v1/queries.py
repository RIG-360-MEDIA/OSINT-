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

from datetime import datetime
from typing import Any

from sqlalchemy import text

from .errors import bad_request
from .pagination import decode_cursor, encode_cursor

# Map a client sentiment label to the set of raw stance values it covers.
# Covers BOTH the legacy article_stances vocab AND the v2 (article_entity_sentiment)
# vocab (positive/negative/neutral) so one filter works across the cutover.
_STANCE_SETS = {
    "supportive": ("supportive", "positive"),
    "critical": ("critical", "negative"),
    "neutral": ("neutral",),
}

# v2 raw stance (positive/negative/neutral) -> client label bucket.
_V2_TO_CLIENT = {"positive": "supportive", "negative": "critical", "neutral": "neutral"}

# Hard ceiling on how many entities we'll enumerate for an all_entities org.
_ALL_ENTITIES_LIST_CAP = 500

# The partner-API contract for `summary` is English ("summary / full_text --
# English (translation-preferred) summary and body" in the API reference).
#
# lead_text_translated does NOT honour that contract on its own: substrate's
# corpus pass (backend/tasks/substrate/run_corpus_pass.py) overwrites it with
# the native trafilatura body, so for most non-English articles it carries
# native script. The LLM-written summary_executive / summary_preview columns
# already hold real English for ~65% of those rows, so we fall back to them
# whenever the lead itself is not English.
#
# Tier order is deliberate:
#   1. an English lead wins -- it is the article's actual lead paragraph, and
#      preferring it means English articles keep their existing summary
#      verbatim (measured blast radius: 0.66% of already-English rows change,
#      and those are rows currently serving raw HTML, so they improve);
#   2/3. the generated English summaries, only reached when tier 1 would hand
#      the client Telugu/Hindi/Urdu text;
#   4/5. the historic behaviour, so a row can never lose its summary.
#
# ASCII is a deliberately cheap English proxy -- the failure mode we care about
# is non-Latin script, not diacritics. octet_length = char_length is true iff
# every character is single-byte (ASCII) under UTF-8: it is exactly equivalent
# to `~ '^[[:ascii:]]+$'` (verified over 108,480 rows: zero mismatches), but it
# avoids a regex AND avoids the POSIX class `[[:ascii:]]`, whose embedded
# colons SQLAlchemy's text() would parse as an `:ascii` bind parameter.
# Evaluated in the SELECT list (post-LIMIT), so it costs nothing on the scan.
_SUMMARY_SQL = """COALESCE(
                   NULLIF(CASE WHEN octet_length(a.lead_text_translated) = char_length(a.lead_text_translated)
                               THEN a.lead_text_translated END, ''),
                   NULLIF(CASE WHEN octet_length(a.summary_executive) = char_length(a.summary_executive)
                               THEN a.summary_executive END, ''),
                   NULLIF(CASE WHEN octet_length(a.summary_preview) = char_length(a.summary_preview)
                               THEN a.summary_preview END, ''),
                   NULLIF(a.lead_text_translated, ''),
                   NULLIF(a.lead_text_original, ''))"""


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

# Per-pillar sentiment sources: (stance table, its id col, recency table, that id col).
_PILLAR_SRC = {
    "articles":  ("analytics.article_entity_sentiment",  "article_id",  "public.articles",  "id"),
    "newspaper": ("analytics.clipping_entity_sentiment", "clipping_id", "public.clippings", "id"),
}


def _bucket_split(rows: Any) -> dict[str, Any]:
    """Bucket (stance, impact, n) rows into the client sentiment shape (two-field)."""
    supportive = neutral = critical = 0
    impact = {"positive": 0, "negative": 0, "neutral": 0, "not_relevant": 0}
    for r in rows:
        n = int(r.n)
        client = _V2_TO_CLIENT.get((r.stance or "").strip())
        if client == "supportive":
            supportive += n
        elif client == "critical":
            critical += n
        elif client == "neutral":
            neutral += n
        imp = (r.impact or "").strip()
        if imp in impact:
            impact[imp] += n
    total = supportive + neutral + critical
    return {
        "supportive": supportive, "neutral": neutral, "critical": critical,
        "total": total,
        "net_lean": round((supportive - critical) / total, 4) if total else 0.0,
        "impact": impact,
    }


async def _pillar_split(db, pillar: str, entity_id: str, window_hours: int) -> dict[str, Any]:
    """Two-field sentiment toward one entity from ONE pillar (v2 engine, resolved
    entity_id, recency on the item's own collected_at)."""
    stbl, idcol, jtbl, jid = _PILLAR_SRC[pillar]
    rows = (await db.execute(text(f"""
        SELECT lower(e.stance) AS stance, lower(e.impact) AS impact, count(*) AS n
          FROM {stbl} e
          JOIN {jtbl} j ON j.{jid} = e.{idcol}
         WHERE e.entity_id = CAST(:eid AS uuid)
           AND j.collected_at > now() - make_interval(hours => :h)
           AND NOT COALESCE(j.is_duplicate, false)
         GROUP BY lower(e.stance), lower(e.impact)
    """), {"eid": entity_id, "h": window_hours})).fetchall()
    return _bucket_split(rows)


async def sentiment_split(db, entity_id: str, window_hours: int) -> dict[str, Any]:
    """Two-field sentiment toward one entity, split PER PILLAR (news articles vs
    newspaper cuttings) with a combined headline. v2 gold-tuned stance+impact.
    """
    arts = await _pillar_split(db, "articles", entity_id, window_hours)
    news = await _pillar_split(db, "newspaper", entity_id, window_hours)
    combined = _bucket_split([])  # zeroed base; sum the pillars into it
    for p in (arts, news):
        combined["supportive"] += p["supportive"]
        combined["neutral"] += p["neutral"]
        combined["critical"] += p["critical"]
        for k in combined["impact"]:
            combined["impact"][k] += p["impact"][k]
    combined["total"] = combined["supportive"] + combined["neutral"] + combined["critical"]
    combined["net_lean"] = (round((combined["supportive"] - combined["critical"]) / combined["total"], 4)
                            if combined["total"] else 0.0)
    combined["by_pillar"] = {"articles": arts, "newspaper": news}
    return combined


async def sentiment_daily(db, entity_id: str, window_hours: int) -> list[dict[str, Any]]:
    """Per-day supportive/neutral/critical toward one entity, COMBINED across news
    articles + newspaper cuttings (v2), for trend lines."""
    rows = (await db.execute(text("""
        SELECT day, sum(sup) AS sup, sum(crit) AS crit, sum(neu) AS neu FROM (
          SELECT date_trunc('day', a.collected_at)::date AS day,
                 count(*) FILTER (WHERE lower(e.stance)='positive') AS sup,
                 count(*) FILTER (WHERE lower(e.stance)='negative') AS crit,
                 count(*) FILTER (WHERE lower(e.stance)='neutral')  AS neu
            FROM analytics.article_entity_sentiment e JOIN public.articles a ON a.id = e.article_id
           WHERE e.entity_id = CAST(:eid AS uuid)
             AND a.collected_at > now() - make_interval(hours => :h) AND NOT COALESCE(a.is_duplicate, false)
           GROUP BY 1
          UNION ALL
          SELECT date_trunc('day', c.collected_at)::date AS day,
                 count(*) FILTER (WHERE lower(e.stance)='positive') AS sup,
                 count(*) FILTER (WHERE lower(e.stance)='negative') AS crit,
                 count(*) FILTER (WHERE lower(e.stance)='neutral')  AS neu
            FROM analytics.clipping_entity_sentiment e JOIN public.clippings c ON c.id = e.clipping_id
           WHERE e.entity_id = CAST(:eid AS uuid)
             AND c.collected_at > now() - make_interval(hours => :h) AND NOT COALESCE(c.is_duplicate, false)
           GROUP BY 1
        ) u GROUP BY day ORDER BY day
    """), {"eid": entity_id, "h": window_hours})).fetchall()
    return [
        {"date": r.day.isoformat(), "supportive": int(r.sup),
         "neutral": int(r.neu), "critical": int(r.crit)}
        for r in rows
    ]


async def resolve_entity_by_name(db, name: str, entity_ids: list[str], all_entities: bool) -> str | None:
    """Resolve a display name to a canonical entity id, restricted to the caller's scope.

    Never probes outside scope: a non-all_entities org only resolves names that map to
    one of its provisioned ids. Returns None if unresolved/out-of-scope (caller -> 404).
    """
    n = (name or "").strip()
    if all_entities:
        row = (await db.execute(text("""
            SELECT ed.id::text AS id FROM entity_dictionary ed
             WHERE ed.redirected_to IS NULL
               AND (lower(ed.canonical_name) = lower(:n)
                    OR EXISTS (SELECT 1 FROM entity_lookup el
                                WHERE el.entity_id = ed.id AND el.name_norm = lower(:n)))
             ORDER BY ed.canonical_name LIMIT 1
        """), {"n": n})).fetchone()
    elif entity_ids:
        row = (await db.execute(text("""
            SELECT ed.id::text AS id FROM entity_dictionary ed
             WHERE ed.id = ANY(CAST(:ids AS uuid[]))
               AND (lower(ed.canonical_name) = lower(:n)
                    OR EXISTS (SELECT 1 FROM entity_lookup el
                                WHERE el.entity_id = ed.id AND el.name_norm = lower(:n)))
             LIMIT 1
        """), {"n": n, "ids": entity_ids})).fetchone()
    else:
        return None
    return row.id if row else None


# ── Coverage volume (scoped article counts per day) ─────────────────────────

async def coverage_daily(db, entity_ids: list[str], all_entities: bool, window_hours: int) -> dict[str, Any]:
    if not all_entities and not entity_ids:
        return {"total": 0, "daily": []}
    mention_clause = "" if all_entities else """
           AND EXISTS (SELECT 1 FROM article_entity_mentions aem
                        WHERE aem.article_id = a.id
                          AND aem.entity_id = ANY(CAST(:eids AS uuid[])))"""
    days = max(1, window_hours // 24)
    # Calendar-aligned, exactly `days` buckets, zero-filled — no partial boundary day
    # (the old rolling-hours grouping returned N+1 buckets and dropped empty days).
    sql = f"""
        WITH series AS (
            SELECT generate_series(now()::date - make_interval(days => :days - 1),
                                   now()::date, interval '1 day')::date AS day
        ), counts AS (
            SELECT a.collected_at::date AS day, count(*) AS n
              FROM articles a
             WHERE a.collected_at >= now()::date - make_interval(days => :days - 1)
               AND NOT COALESCE(a.is_duplicate, false){mention_clause}
             GROUP BY 1
        )
        SELECT s.day AS day, COALESCE(c.n, 0) AS n
          FROM series s LEFT JOIN counts c ON c.day = s.day
         ORDER BY s.day
    """
    params: dict[str, Any] = {"days": days}
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


async def topics_breakdown(db, entity_ids: list[str], all_entities: bool, window_hours: int, limit: int) -> list[dict[str, Any]]:
    """Most-covered topics in the caller's scope over the window (OTHER excluded)."""
    if not all_entities and not entity_ids:
        return []
    mention = "" if all_entities else """
        AND EXISTS (SELECT 1 FROM article_entity_mentions aem
                     WHERE aem.article_id = a.id
                       AND aem.entity_id = ANY(CAST(:eids AS uuid[])))"""
    params: dict[str, Any] = {"h": window_hours, "lim": limit}
    if not all_entities:
        params["eids"] = entity_ids
    rows = (await db.execute(text(f"""
        SELECT a.topic_category AS name, count(*) AS n
          FROM articles a
         WHERE a.collected_at > now() - make_interval(hours => :h)
           AND NOT COALESCE(a.is_duplicate, false)
           AND a.topic_category IS NOT NULL AND a.topic_category <> 'OTHER'
           {mention}
         GROUP BY a.topic_category
         ORDER BY n DESC
         LIMIT :lim
    """), params)).fetchall()
    return [{"name": r.name, "count": int(r.n)} for r in rows]


async def outlets_for_entity(db, entity_id: str, window_hours: int, limit: int) -> list[dict[str, Any]]:
    """Per-outlet coverage volume + net lean toward one (already scope-verified) entity.

    net_lean = (supportive − critical) / classified-stances, from article_stances
    directed at the entity — an honest sample, same basis as sentiment_split.
    """
    rows = (await db.execute(text("""
        WITH arts AS (
            SELECT a.id, a.source_id
              FROM articles a
              JOIN article_entity_mentions aem ON aem.article_id = a.id
             WHERE aem.entity_id = CAST(:eid AS uuid)
               AND a.collected_at > now() - make_interval(hours => :h)
               AND NOT COALESCE(a.is_duplicate, false)
        ), st AS (
            SELECT e.article_id, lower(e.stance) AS stance
              FROM analytics.article_entity_sentiment e
             WHERE e.entity_id = CAST(:eid AS uuid)
        )
        SELECT so.name AS name,
               count(DISTINCT arts.id) AS n,
               count(*) FILTER (WHERE st.stance IN ('supportive','positive')) AS sup,
               count(*) FILTER (WHERE st.stance IN ('critical','negative'))  AS crit,
               count(*) FILTER (WHERE st.stance = 'neutral')                  AS neu
          FROM arts
          JOIN sources so ON so.id = arts.source_id
          LEFT JOIN st ON st.article_id = arts.id
         GROUP BY so.name
         ORDER BY n DESC
         LIMIT :lim
    """), {"eid": entity_id, "h": window_hours, "lim": limit})).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        tot = int(r.sup) + int(r.crit) + int(r.neu)
        net = round((int(r.sup) - int(r.crit)) / tot, 4) if tot else 0.0
        out.append({"name": r.name, "count": int(r.n), "net_lean": net})
    return out


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
    source: tuple[str, ...] = (),
    mute_terms: tuple[str, ...] = (),
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

    if source:
        # Outlet drill-down: match by source display name (what /analytics/outlets returns).
        clauses.append("s.name = ANY(:sources)")
        params["sources"] = list(source)

    stance_set = _stance_set_for(sentiment)
    if stance_set:
        # Drill-down symmetry: match the SAME v2 rows /analytics/sentiment counts
        # (analytics.article_entity_sentiment, scoped by resolved entity_id).
        if all_entities:
            clauses.append("""EXISTS (SELECT 1 FROM analytics.article_entity_sentiment e
                                       WHERE e.article_id = a.id
                                         AND lower(e.stance) = ANY(:stances))""")
        else:
            clauses.append("""EXISTS (SELECT 1 FROM analytics.article_entity_sentiment e
                                       WHERE e.article_id = a.id
                                         AND e.entity_id = ANY(CAST(:eids AS uuid[]))
                                         AND lower(e.stance) = ANY(:stances))""")
        params["stances"] = stance_set

    if mute_terms:
        clauses.append("NOT (lower(coalesce(a.title,'')) LIKE ANY(:mpats) "
                       "OR lower(coalesce(a.lead_text_translated, a.lead_text_original, '')) LIKE ANY(:mpats))")
        params["mpats"] = ["%" + m.lower() + "%" for m in mute_terms]

    cur = decode_cursor(cursor)
    if cur is not None:
        # Bind the timestamp as a real datetime — asyncpg resolves the param type from
        # CAST(:ct AS timestamptz) and rejects a str. Parse (and fail-closed on garbage).
        try:
            ct = datetime.fromisoformat(cur[0])
        except (TypeError, ValueError):
            raise bad_request("Invalid cursor")
        clauses.append("(a.collected_at, a.id) < (:ct, CAST(:ci AS uuid))")
        params["ct"], params["ci"] = ct, cur[1]

    where = " AND ".join(clauses)
    # Strongest stance toward the scoped entity (or any, for all_entities orgs).
    stance_scope = "" if all_entities else "AND e.entity_id = ANY(CAST(:eids AS uuid[]))"
    sql = f"""
        SELECT a.id::text AS id, a.title AS headline,
               {_SUMMARY_SQL} AS summary,
               COALESCE(NULLIF(a.full_text_translated, ''), NULLIF(a.full_text_scraped, '')) AS full_text,
               NULLIF(a.lead_text_original, '') AS summary_original,
               NULLIF(a.full_text_scraped, '') AS full_text_original,
               s.name AS source, a.url, a.language_detected AS language,
               a.thread_id::text AS story_id, sent.stance AS stance, sent.intensity AS intensity,
               s.political_lean AS political_lean,
               EXISTS (SELECT 1 FROM analytics.low_credibility_sources lc WHERE lc.source_id = a.source_id) AS low_credibility,
               (a.substrate_status='ok' AND NOT COALESCE(a.is_duplicate,false)
                AND a.title IS NOT NULL AND a.topic_category IS NOT NULL AND a.topic_category<>'OTHER'
                AND a.labse_embedding_v4 IS NOT NULL
                AND jsonb_typeof(a.entities_extracted)='array' AND jsonb_array_length(a.entities_extracted)>0) AS api_ready,
               a.published_at, a.collected_at, a.updated_at AS last_updated, a.geo_primary
          FROM articles a
          JOIN sources s ON s.id = a.source_id
          LEFT JOIN LATERAL (
              SELECT e.stance, e.impact_confidence AS intensity FROM analytics.article_entity_sentiment e
               WHERE e.article_id = a.id {stance_scope}
               ORDER BY e.impact_confidence DESC NULLS LAST LIMIT 1
          ) sent ON true
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
    stance_scope = "" if all_entities else "AND e.entity_id = ANY(CAST(:eids AS uuid[]))"
    row = (await db.execute(text(f"""
        SELECT a.id::text AS id, a.title AS headline,
               {_SUMMARY_SQL} AS summary,
               COALESCE(NULLIF(a.full_text_translated, ''), NULLIF(a.full_text_scraped, '')) AS full_text,
               NULLIF(a.lead_text_original, '') AS summary_original,
               NULLIF(a.full_text_scraped, '') AS full_text_original,
               s.name AS source, a.url, a.language_detected AS language,
               a.thread_id::text AS story_id, sent.stance AS stance, sent.intensity AS intensity,
               s.political_lean AS political_lean,
               EXISTS (SELECT 1 FROM analytics.low_credibility_sources lc WHERE lc.source_id = a.source_id) AS low_credibility,
               (a.substrate_status='ok' AND NOT COALESCE(a.is_duplicate,false)
                AND a.title IS NOT NULL AND a.topic_category IS NOT NULL AND a.topic_category<>'OTHER'
                AND a.labse_embedding_v4 IS NOT NULL
                AND jsonb_typeof(a.entities_extracted)='array' AND jsonb_array_length(a.entities_extracted)>0) AS api_ready,
               a.published_at, a.updated_at AS last_updated, a.geo_primary
          FROM articles a
          JOIN sources s ON s.id = a.source_id
          LEFT JOIN LATERAL (
              SELECT e.stance, e.impact_confidence AS intensity FROM analytics.article_entity_sentiment e
               WHERE e.article_id = a.id {stance_scope}
               ORDER BY e.impact_confidence DESC NULLS LAST LIMIT 1
          ) sent ON true
         WHERE {where}
         LIMIT 1
    """), params)).fetchone()
    return dict(row._mapping) if row else None


# ── Stories (surfaceable v9 clusters, scoped) ───────────────────────────────

async def list_scoped_stories(
    db,
    *,
    entity_ids: list[str],
    all_entities: bool,
    regions: tuple[str, ...],
    country: str | None,
    cursor: str | None,
    limit: int,
    since_hours: int | None = None,
    order_by: str = "importance",
    mute_terms: tuple[str, ...] = (),
) -> tuple[list[dict[str, Any]], str | None]:
    """Surfaceable v9 stories (analytics.story_clusters_v8) narrowed to the caller's scope.

    Surfaceable = the canonical night-desk filter: status='active', NOT a template
    family, and >=3 independent (wire-deduped) outlets — or a rescued story.
    Scope = a member article mentions a scoped entity, OR subject_region is in the
    org's provisioned regions. all_entities orgs see the whole surfaceable pool; an
    org with neither entities nor regions (and not all_entities) gets [] — never the
    corpus. Ranked by importance_score. Outlets: the deduped `independent_source_count`
    for the count, and top-3 distinct source names off members (NOT via articles, which
    is lossy once old member articles are retention-purged).
    """
    if not all_entities and not entity_ids and not regions:
        return [], None

    clauses = [
        "c.status = 'active'",
        "c.is_template_family IS FALSE",
        "(c.independent_source_count >= 3 OR c.rescued_from_story_id IS NOT NULL)",
    ]
    params: dict[str, Any] = {"lim": limit}

    if not all_entities:
        scope_or: list[str] = []
        if entity_ids:
            # A scoped entity must be a PRINCIPAL of the story (mentioned in a meaningful
            # share of its members), not a 0.2% cameo — else a global mega with one
            # tangential mention of a scoped entity leaks in and outranks real local stories.
            scope_or.append("""(SELECT count(DISTINCT m.article_id)
                                  FROM analytics.story_cluster_members_v8 m
                                  JOIN article_entity_mentions aem ON aem.article_id = m.article_id
                                 WHERE m.story_id = c.story_id
                                   AND aem.entity_id = ANY(CAST(:eids AS uuid[])))
                               >= GREATEST(2, 0.15 * c.article_count)""")
            params["eids"] = entity_ids
        if regions:
            # Substring match: subject_region is granular ('Hyderabad, Telangana',
            # 'Medak, Telangana, India'), so exact-equality would drop district-level stories.
            scope_or.append("EXISTS (SELECT 1 FROM unnest(CAST(:regions AS text[])) rg "
                            "WHERE c.subject_region ILIKE '%' || rg || '%')")
            params["regions"] = list(regions)
        clauses.append("(" + " OR ".join(scope_or) + ")")

    if country:
        clauses.append("c.subject_country = :country")
        params["country"] = country

    if since_hours:
        clauses.append("c.last_seen_at > now() - make_interval(hours => :since)")
        params["since"] = since_hours

    if mute_terms:
        clauses.append("NOT (lower(coalesce(c.representative_title,'')) LIKE ANY(:mpats))")
        params["mpats"] = ["%" + m.lower() + "%" for m in mute_terms]

    cur = decode_cursor(cursor)
    if cur is not None:
        try:
            ci_val = float(cur[0])  # importance is numeric; bind as a real, not text
        except (TypeError, ValueError):
            raise bad_request("Invalid cursor")
        clauses.append("(COALESCE(c.importance_score, -1), c.story_id) "
                       "< (CAST(:ci AS double precision), CAST(:cs AS uuid))")
        params["ci"], params["cs"] = ci_val, cur[1]

    order_sql = ("c.last_seen_at DESC NULLS LAST, c.story_id DESC" if order_by == "recent"
                 else "COALESCE(c.importance_score, -1) DESC, c.story_id DESC")
    where = " AND ".join(clauses)
    sql = f"""
        SELECT c.story_id::text AS id, c.representative_title AS title, c.topic,
               c.subject_country, c.subject_region, c.event_type,
               c.article_count, c.independent_source_count AS outlets,
               c.languages, c.importance_score,
               (CASE WHEN EXISTS (SELECT 1 FROM articles ra WHERE ra.id = c.representative_article_id
                                   AND NOT COALESCE(ra.is_duplicate, false))
                     THEN c.representative_article_id::text END) AS representative_article_id,
               c.first_seen_at, c.last_seen_at, ol.top_outlets
          FROM analytics.story_clusters_v8 c
          LEFT JOIN LATERAL (
              SELECT array_agg(name ORDER BY n DESC) AS top_outlets FROM (
                  SELECT so.name, count(*) AS n
                    FROM analytics.story_cluster_members_v8 m
                    JOIN sources so ON so.id = m.source_id
                   WHERE m.story_id = c.story_id
                   GROUP BY so.name ORDER BY count(*) DESC LIMIT 3
              ) x
          ) ol ON true
         WHERE {where}
         ORDER BY {order_sql}
         LIMIT :lim
    """
    rows = (await db.execute(text(sql), params)).fetchall()
    next_cursor = None
    if order_by != "recent" and len(rows) == limit:  # keyset cursor is importance-based
        last = rows[-1]
        imp = last.importance_score if last.importance_score is not None else -1
        next_cursor = encode_cursor(imp, last.id)
    return [dict(r._mapping) for r in rows], next_cursor


async def story_detail(db, *, story_id: str, entity_ids: list[str], all_entities: bool,
                       regions: tuple[str, ...], limit: int) -> dict[str, Any] | None:
    """One surfaceable, in-scope story: metadata + chronological member timeline + outlet
    breakdown. Assembled from the v8 keeper tables (robust). Out-of-scope/unknown/unsurfaceable
    id => None (caller -> identical 404, no existence oracle)."""
    params: dict[str, Any] = {"sid": story_id}
    scope_ok = "TRUE"
    if not all_entities:
        parts: list[str] = []
        if entity_ids:
            parts.append("""(SELECT count(DISTINCT m.article_id)
                               FROM analytics.story_cluster_members_v8 m
                               JOIN article_entity_mentions aem ON aem.article_id = m.article_id
                              WHERE m.story_id = c.story_id
                                AND aem.entity_id = ANY(CAST(:eids AS uuid[])))
                            >= GREATEST(2, 0.15 * c.article_count)""")
            params["eids"] = entity_ids
        if regions:
            parts.append("EXISTS (SELECT 1 FROM unnest(CAST(:regions AS text[])) rg "
                         "WHERE c.subject_region ILIKE '%' || rg || '%')")
            params["regions"] = list(regions)
        if not parts:
            return None
        scope_ok = "(" + " OR ".join(parts) + ")"
    c = (await db.execute(text(f"""
        SELECT c.story_id::text AS id, c.representative_title AS title, c.topic,
               c.subject_country, c.subject_region, c.event_type,
               c.article_count, c.independent_source_count AS outlets, c.languages,
               c.importance_score, c.representative_article_id::text AS representative_article_id,
               c.first_seen_at, c.last_seen_at
          FROM analytics.story_clusters_v8 c
         WHERE c.story_id = CAST(:sid AS uuid)
           AND c.status = 'active' AND c.is_template_family IS FALSE
           AND {scope_ok}
    """), params)).fetchone()
    if c is None:
        return None
    timeline = (await db.execute(text("""
        SELECT a.id::text AS id, a.title AS headline, s.name AS source, a.url,
               a.language_detected AS language, a.published_at, m.is_representative
          FROM analytics.story_cluster_members_v8 m
          JOIN articles a ON a.id = m.article_id
          JOIN sources s ON s.id = a.source_id
         WHERE m.story_id = CAST(:sid AS uuid) AND NOT COALESCE(a.is_duplicate, false)
         ORDER BY COALESCE(a.published_at, a.collected_at) ASC LIMIT :lim
    """), {"sid": story_id, "lim": limit})).fetchall()
    outlets = (await db.execute(text("""
        SELECT so.name AS name, count(*) AS n
          FROM analytics.story_cluster_members_v8 m
          JOIN sources so ON so.id = m.source_id
         WHERE m.story_id = CAST(:sid AS uuid)
         GROUP BY so.name ORDER BY count(*) DESC LIMIT 12
    """), {"sid": story_id})).fetchall()
    return {
        "story": dict(c._mapping),
        "timeline": [dict(r._mapping) for r in timeline],
        "outlets": [{"name": r.name, "count": int(r.n)} for r in outlets],
    }


# ── Geography (district-level, India gazetteer, scoped) ─────────────────────

async def geo_coverage(db, *, entity_ids: list[str], all_entities: bool,
                       state_codes: list[str], window_hours: int) -> list[dict[str, Any]]:
    """District coverage counts grouped by state, scoped. India only (source_country='IN');
    the `districts` gazetteer currently covers TG + AP. Scope = article mentions a scoped
    entity OR district state in the org's regions."""
    clauses = ["a.collected_at > now() - make_interval(hours => :h)", "a.source_country = 'IN'"]
    params: dict[str, Any] = {"h": window_hours}
    if not all_entities:
        scope_or: list[str] = []
        if entity_ids:
            scope_or.append("""EXISTS (SELECT 1 FROM article_entity_mentions aem
                                 WHERE aem.article_id = a.id
                                   AND aem.entity_id = ANY(CAST(:eids AS uuid[])))""")
            params["eids"] = entity_ids
        if state_codes:
            scope_or.append("d.state_code = ANY(:scodes)")
            params["scodes"] = list(state_codes)
        if not scope_or:
            return []
        clauses.append("(" + " OR ".join(scope_or) + ")")
    where = " AND ".join(clauses)
    rows = (await db.execute(text(f"""
        SELECT d.state_code AS state_code, d.id AS district_id, d.name AS district,
               count(DISTINCT a.id) AS n
          FROM districts d
          JOIN article_districts ad ON ad.district_id = d.id AND ad.confidence >= 0.4
          JOIN articles a ON a.id = ad.article_id
         WHERE {where}
         GROUP BY d.state_code, d.id, d.name
         ORDER BY d.state_code, n DESC
    """), params)).fetchall()
    states: dict[str, dict[str, Any]] = {}
    for r in rows:
        st = states.setdefault(r.state_code, {"state_code": r.state_code, "articles": 0, "districts": []})
        st["districts"].append({"id": r.district_id, "name": r.district, "articles": int(r.n)})
        st["articles"] += int(r.n)
    return list(states.values())


async def geo_district(db, slug: str, window_hours: int, limit: int) -> dict[str, Any] | None:
    """One district's coverage: metadata + article count + stance split + recent items.
    None if the district slug is unknown."""
    meta = (await db.execute(text(
        "SELECT id::text AS id, name, state_code, hq_city FROM districts WHERE lower(id) = lower(:d)"
    ), {"d": slug})).fetchone()
    if meta is None:
        return None
    did = meta.id  # canonical id (slug lookup is case-insensitive)
    # Per-article stance (v2, strongest by confidence) — one row per article, so the
    # split can never exceed the article count (the old article_stances LEFT JOIN
    # multiplied rows and summed to >100%).
    stats = (await db.execute(text("""
        SELECT count(*) AS n,
               count(*) FILTER (WHERE sent.stance = 'positive') AS sup,
               count(*) FILTER (WHERE sent.stance = 'negative') AS crit,
               count(*) FILTER (WHERE sent.stance = 'neutral')  AS neu
          FROM article_districts ad
          JOIN articles a ON a.id = ad.article_id
          LEFT JOIN LATERAL (
              SELECT e.stance FROM analytics.article_entity_sentiment e
               WHERE e.article_id = a.id ORDER BY e.impact_confidence DESC NULLS LAST LIMIT 1
          ) sent ON true
         WHERE ad.district_id = :d
           AND ad.confidence >= 0.4
           AND a.collected_at > now() - make_interval(hours => :h)
           AND NOT COALESCE(a.is_duplicate, false)
    """), {"d": did, "h": window_hours})).fetchone()
    recent = (await db.execute(text("""
        SELECT a.id::text AS id, a.title AS headline, s.name AS source, a.url,
               a.language_detected AS language, a.published_at
          FROM article_districts ad
          JOIN articles a ON a.id = ad.article_id
          JOIN sources s ON s.id = a.source_id
         WHERE ad.district_id = :d
           AND ad.confidence >= 0.4
           AND a.collected_at > now() - make_interval(hours => :h)
           AND NOT COALESCE(a.is_duplicate, false)
         ORDER BY a.collected_at DESC LIMIT :lim
    """), {"d": did, "h": window_hours, "lim": limit})).fetchall()
    return {
        "id": meta.id, "name": meta.name, "state_code": meta.state_code, "hq_city": meta.hq_city,
        "articles": int(stats.n) if stats else 0,
        "stance": {
            "supportive": int(stats.sup or 0) if stats else 0,
            "neutral": int(stats.neu or 0) if stats else 0,
            "critical": int(stats.crit or 0) if stats else 0,
        },
        "recent": [
            {"id": r.id, "headline": r.headline, "source": r.source, "url": r.url,
             "language": r.language,
             "published_at": r.published_at.isoformat() if r.published_at is not None else None}
            for r in recent
        ],
    }


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


async def articles_full_by_ids(db, ids: list[str]) -> dict[str, dict[str, Any]]:
    """Full serialize_article-shape rows for a set of article ids, keyed by id.

    Every drill-down (story timeline / district recent / entity coverage) enriches
    its article items through this so they carry the SAME 16 fields as the main
    /articles feed — no reduced stubs. v2 stance = strongest by impact_confidence.
    Cheap: one batch query, not N+1.
    """
    if not ids:
        return {}
    rows = (await db.execute(text(f"""
        SELECT a.id::text AS id, a.title AS headline,
               {_SUMMARY_SQL} AS summary,
               COALESCE(NULLIF(a.full_text_translated, ''), NULLIF(a.full_text_scraped, '')) AS full_text,
               NULLIF(a.lead_text_original, '') AS summary_original,
               NULLIF(a.full_text_scraped, '') AS full_text_original,
               s.name AS source, a.url, a.language_detected AS language,
               a.thread_id::text AS story_id, sent.stance AS stance, sent.intensity AS intensity,
               s.political_lean AS political_lean,
               EXISTS (SELECT 1 FROM analytics.low_credibility_sources lc WHERE lc.source_id = a.source_id) AS low_credibility,
               (a.substrate_status='ok' AND NOT COALESCE(a.is_duplicate,false)
                AND a.title IS NOT NULL AND a.topic_category IS NOT NULL AND a.topic_category<>'OTHER'
                AND a.labse_embedding_v4 IS NOT NULL
                AND jsonb_typeof(a.entities_extracted)='array' AND jsonb_array_length(a.entities_extracted)>0) AS api_ready,
               a.published_at, a.updated_at AS last_updated, a.geo_primary
          FROM articles a
          JOIN sources s ON s.id = a.source_id
          LEFT JOIN LATERAL (
              SELECT e.stance, e.impact_confidence AS intensity FROM analytics.article_entity_sentiment e
               WHERE e.article_id = a.id
               ORDER BY e.impact_confidence DESC NULLS LAST LIMIT 1
          ) sent ON true
         WHERE a.id = ANY(CAST(:ids AS uuid[]))
    """), {"ids": ids})).fetchall()
    return {r._mapping["id"]: dict(r._mapping) for r in rows}


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


# ── YouTube transcript (strict on-demand) + newspaper full text ─────────────

async def record_clip_grants(org_id: str, clip_ids: list[str]) -> None:
    """Best-effort: record that `org_id` was shown these clip ids by a keyword/entity
    query, refreshing surfaced_at. This grant is the ONLY thing that later authorises
    GET /v1/clips/{id} to serve that clip's full transcript — strict on-demand, so a
    client can only read the transcript of a clip its own query surfaced recently.
    Opens its own short-lived write connection so it never disturbs the read path."""
    ids = [str(c) for c in (clip_ids or []) if c is not None and str(c).strip()]
    if not ids:
        return
    from db import get_db  # local import: keeps this the only get_db user in queries.py
    try:
        async with get_db() as db:
            await db.execute(text("""
                INSERT INTO analytics.api_clip_grants (org_id, clip_id, surfaced_at)
                SELECT CAST(:o AS uuid), x, now() FROM unnest(CAST(:ids AS text[])) AS x
                ON CONFLICT (org_id, clip_id) DO UPDATE SET surfaced_at = now()
            """), {"o": org_id, "ids": ids})
            await db.commit()
    except Exception:  # noqa: BLE001 — grant bookkeeping must never break a response
        pass


async def clip_grant_fresh(db, org_id: str, clip_id: str, window_hours: int) -> bool:
    """True iff `org_id` surfaced `clip_id` within the window — the on-demand gate."""
    row = (await db.execute(text("""
        SELECT 1 FROM analytics.api_clip_grants
         WHERE org_id = CAST(:o AS uuid) AND clip_id = :cid
           AND surfaced_at > now() - make_interval(hours => :h)
         LIMIT 1
    """), {"o": org_id, "cid": str(clip_id), "h": window_hours})).first()
    return row is not None


async def clip_transcript_by_id(db, clip_id: str) -> dict[str, Any] | None:
    """Assemble one video's FULL transcript from its per-segment rows.

    youtube_clips_v2 stores one row per transcript SEGMENT, so the full transcript is
    the video's segments concatenated in play order (clip_start_seconds), de-duplicated.
    Returns None if the clip id is malformed or unknown.
    """
    try:
        cid = int(str(clip_id).strip())
    except (TypeError, ValueError):
        return None
    head = (await db.execute(text("""
        SELECT id::text AS id, video_id, video_title, channel_name, video_url,
               video_published_at, transcript_language, transcript_source, transcript_segment
          FROM youtube_clips_v2 WHERE id = :cid LIMIT 1
    """), {"cid": cid})).first()
    if head is None:
        return None
    transcript = head.transcript_segment
    seg_count = 1
    if head.video_id:
        seg = (await db.execute(text("""
            SELECT string_agg(seg, E'\n' ORDER BY ord NULLS LAST, seg) AS transcript,
                   count(*) AS n
              FROM (
                SELECT DISTINCT ON (clip_start_seconds, transcript_segment)
                       transcript_segment AS seg, clip_start_seconds AS ord
                  FROM youtube_clips_v2
                 WHERE video_id = :vid
                   AND transcript_segment IS NOT NULL AND transcript_segment <> ''
                 ORDER BY clip_start_seconds, transcript_segment
              ) s
        """), {"vid": head.video_id})).first()
        if seg and seg.transcript:
            transcript = seg.transcript
            seg_count = seg.n
    return {
        "id": head.id, "video_id": head.video_id, "video_title": head.video_title,
        "channel_name": head.channel_name, "video_url": head.video_url,
        "video_published_at": head.video_published_at,
        "transcript_language": head.transcript_language,
        "transcript_source": head.transcript_source,
        "transcript": transcript, "segment_count": seg_count,
    }


_CUTTING_COLS = """
    cl.id::text AS id,
    COALESCE(cl.headline_translated, cl.headline) AS headline,
    NULLIF(cl.headline, '') AS headline_original,
    NULLIF(cl.subheadline, '') AS subheadline,
    COALESCE(NULLIF(cl.body_text_translated, ''), NULLIF(cl.body_text, '')) AS full_text,
    NULLIF(cl.body_text, '') AS full_text_original,
    ns.name AS source, cl.section AS section,
    COALESCE(cl.detected_language, cl.language) AS language,
    cl.edition_date AS edition_date, cl.geo_primary AS geo,
    cl.page_number AS page_number, cl.collected_at AS collected_at
"""


async def cutting_full_by_id(db, cutting_id: str, entity_ids: list[str],
                             all_entities: bool, regions: list[str] = ()) -> dict[str, Any] | None:
    """One newspaper cutting with FULL text (native + English), scope-gated by the
    caller's provisioned entities OR regions — the SAME rule as the feed, so any item
    visible in /cuttings is fetchable here. None if unknown/out-of-scope (caller -> 404)."""
    params: dict[str, Any] = {"cid": cutting_id}
    scope_clause = ""
    if not all_entities:
        preds: list[str] = []
        if entity_ids:
            preds.append("EXISTS (SELECT 1 FROM clipping_entity_mentions m "
                         "WHERE m.clipping_id = cl.id AND m.entity_id = ANY(CAST(:eids AS uuid[])))")
            params["eids"] = list(entity_ids)
        for i, rg in enumerate(regions or ()):
            preds.append(f"(cl.geo_primary ILIKE :rg{i} OR cl.geo_district ILIKE :rg{i})")
            params[f"rg{i}"] = f"%{rg}%"
        if not preds:
            return None
        scope_clause = "AND (" + " OR ".join(preds) + ")"
    row = (await db.execute(text(f"""
        SELECT {_CUTTING_COLS}
          FROM clippings cl
          LEFT JOIN newspaper_sources ns ON ns.id = cl.newspaper_source_id
         WHERE cl.id = CAST(:cid AS uuid)
           AND NOT COALESCE(cl.is_duplicate, false)
           {scope_clause}
         LIMIT 1
    """), params)).first()
    return dict(row._mapping) if row else None


async def list_scoped_cuttings(db, *, entity_ids: list[str], all_entities: bool,
                               regions: list[str], window_hours: int,
                               language: str | None, limit: int,
                               before: datetime | None = None) -> list[dict[str, Any]]:
    """Recent newspaper cuttings (full text) within the caller's scope. Scope =
    provisioned entities OR a region substring match on the cutting's geo, mirroring
    the article feed. Paginates on collected_at via the optional `before` cursor."""
    preds = ["NOT COALESCE(cl.is_duplicate, false)",
             "cl.collected_at > now() - make_interval(hours => :h)"]
    params: dict[str, Any] = {"h": window_hours, "lim": limit}
    if language:
        preds.append("COALESCE(cl.detected_language, cl.language) = :lang")
        params["lang"] = language
    if before is not None:
        preds.append("cl.collected_at < :before")
        params["before"] = before
    if not all_entities:
        scope_preds: list[str] = []
        if entity_ids:
            scope_preds.append("EXISTS (SELECT 1 FROM clipping_entity_mentions m "
                               "WHERE m.clipping_id = cl.id AND m.entity_id = ANY(CAST(:eids AS uuid[])))")
            params["eids"] = list(entity_ids)
        for i, rg in enumerate(regions or []):
            scope_preds.append(f"(cl.geo_primary ILIKE :rg{i} OR cl.geo_district ILIKE :rg{i})")
            params[f"rg{i}"] = f"%{rg}%"
        if not scope_preds:
            return []
        preds.append("(" + " OR ".join(scope_preds) + ")")
    where = " AND ".join(preds)
    rows = (await db.execute(text(f"""
        SELECT {_CUTTING_COLS}
          FROM clippings cl
          LEFT JOIN newspaper_sources ns ON ns.id = cl.newspaper_source_id
         WHERE {where}
         ORDER BY cl.collected_at DESC
         LIMIT :lim
    """), params)).fetchall()
    return [dict(r._mapping) for r in rows]
