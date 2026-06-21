"""Intelligence layer (Bucket 1) — analytical views over data we already extract.

Read-only SELECTs over article_stances (504k), article_quotes (322k, translated),
article_entity_mentions (1.33M), article_districts (49k). No corpus changes.

Pure scoring functions (balance_from_stances) are unit-tested; the async helpers
fetch from the corpus.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

# Stance vocabulary → polarity (from the live distribution).
SUPPORTIVE = frozenset({"supportive", "sympathetic", "admiration", "promotional", "defensive"})
CRITICAL = frozenset({"critical", "mocking", "concerned"})
# everything else (neutral, analytical) counts as neutral
#
# NOTE: deliberately NO story/cluster dependency in this module — clustering
# (story_clusters_*) is not production-ready yet, so features that would need it
# (framing contrast, coverage-gap) are intentionally not built here.


def balance_from_stances(rows: Sequence[dict]) -> dict:
    """Pure: turn stance rows into a -1..+1 balance score (intensity-weighted).

    +1 = uniformly supportive, -1 = uniformly critical, ~0 = balanced.
    """
    sup = sum(float(r["intensity"]) for r in rows if r["stance"] in SUPPORTIVE)
    crit = sum(float(r["intensity"]) for r in rows if r["stance"] in CRITICAL)
    neutral = sum(1 for r in rows if r["stance"] not in SUPPORTIVE and r["stance"] not in CRITICAL)
    denom = sup + crit
    score = (sup - crit) / denom if denom else 0.0
    if abs(score) < 0.2:
        label = "balanced"
    elif score > 0:
        label = "leans supportive"
    else:
        label = "leans critical"
    return {
        "balance_score": round(score, 3),
        "label": label,
        "supportive_weight": round(sup, 2),
        "critical_weight": round(crit, 2),
        "neutral_count": neutral,
        "n_stances": len(rows),
    }


_STANCES_FOR_ARTICLES_SQL = """
SELECT stance, intensity, actor, actor_entity_id::text AS actor_entity_id
FROM article_stances
WHERE article_id = ANY(CAST(:ids AS uuid[]))
"""


async def stances_for_articles(conn: AsyncConnection, article_ids: Iterable[str]) -> list[dict]:
    ids = list(article_ids)
    if not ids:
        return []
    rows = (await conn.execute(text(_STANCES_FOR_ARTICLES_SQL), {"ids": ids})).mappings().all()
    return [dict(r) for r in rows]


_ENTITY_STANCE_SQL = """
SELECT stance, count(*) AS n, round(avg(intensity)::numeric, 3) AS avg_intensity
FROM article_stances
WHERE actor_entity_id = CAST(:eid AS uuid)
GROUP BY stance ORDER BY n DESC
"""

_ENTITY_STANCE_RAW_SQL = """
SELECT stance, intensity FROM article_stances WHERE actor_entity_id = CAST(:eid AS uuid)
"""


async def entity_stance_profile(conn: AsyncConnection, entity_id: str) -> dict:
    """How is an entity portrayed? Distribution of stances toward it + balance."""
    dist = (await conn.execute(text(_ENTITY_STANCE_SQL), {"eid": entity_id})).mappings().all()
    raw = (await conn.execute(text(_ENTITY_STANCE_RAW_SQL), {"eid": entity_id})).mappings().all()
    return {
        "distribution": [dict(r) for r in dist],
        "balance": balance_from_stances([dict(r) for r in raw]),
    }


_QUOTES_BY_SPEAKER_SQL = """
SELECT coalesce(q.quote_text_en, q.quote_text) AS quote,
       coalesce(q.speaker_name_en, q.speaker_name) AS speaker,
       q.is_direct, a.url, a.published_at, a.language_detected AS language, a.title,
       a.id::text AS article_id
FROM article_quotes q JOIN articles a ON a.id = q.article_id
WHERE q.speaker_entity_id = CAST(:eid AS uuid)
  AND a.substrate_status = 'ok' AND NOT a.is_duplicate
  AND coalesce(q.quote_text_en, q.quote_text) IS NOT NULL{topic}
ORDER BY a.published_at DESC NULLS LAST
LIMIT :k
"""


async def who_said(
    conn: AsyncConnection, speaker_entity_id: str, topic: str | None = None, k: int = 20
) -> list[dict]:
    """Verbatim (translated) quotes by a speaker, optionally about a topic."""
    topic_clause = " AND coalesce(q.quote_text_en, q.quote_text) ILIKE :topic" if topic else ""
    params: dict = {"eid": speaker_entity_id, "k": k}
    if topic:
        params["topic"] = f"%{topic}%"
    rows = (await conn.execute(text(_QUOTES_BY_SPEAKER_SQL.format(topic=topic_clause)), params)).mappings().all()
    return [dict(r) for r in rows]


_CONNECT_SQL = """
SELECT a.id::text AS id, a.title, a.url, a.published_at, a.language_detected AS language
FROM article_entity_mentions m1
JOIN article_entity_mentions m2 ON m1.article_id = m2.article_id
JOIN articles a ON a.id = m1.article_id
WHERE m1.entity_id = CAST(:a AS uuid) AND m2.entity_id = CAST(:b AS uuid)
  AND a.substrate_status = 'ok' AND NOT a.is_duplicate
ORDER BY a.published_at DESC NULLS LAST
LIMIT :k
"""

_BRIDGES_SQL = """
SELECT d.canonical_name, d.entity_type, count(*) AS co_mentions
FROM article_entity_mentions m1
JOIN article_entity_mentions m2 ON m1.article_id = m2.article_id
JOIN article_entity_mentions mid ON mid.article_id = m1.article_id
JOIN entity_dictionary d ON d.id = mid.entity_id
WHERE m1.entity_id = CAST(:a AS uuid) AND m2.entity_id = CAST(:b AS uuid)
  AND mid.entity_id <> CAST(:a AS uuid) AND mid.entity_id <> CAST(:b AS uuid)
GROUP BY d.canonical_name, d.entity_type
ORDER BY co_mentions DESC LIMIT :bridges
"""


async def connect_entities(
    conn: AsyncConnection, entity_a: str, entity_b: str, k: int = 10, bridges: int = 8
) -> dict:
    """Shared coverage of two entities + the entities that bridge them."""
    shared = (await conn.execute(text(_CONNECT_SQL), {"a": entity_a, "b": entity_b, "k": k})).mappings().all()
    bridge_rows = (
        await conn.execute(text(_BRIDGES_SQL), {"a": entity_a, "b": entity_b, "bridges": bridges})
    ).mappings().all()
    return {
        "shared_articles": [dict(r) for r in shared],
        "bridge_entities": [dict(r) for r in bridge_rows],
    }


_DISTRICT_SENTIMENT_SQL = """
SELECT d.district_id,
       count(*) AS n,
       sum(CASE WHEN s.stance = ANY(:sup) THEN s.intensity ELSE 0 END) AS sup,
       sum(CASE WHEN s.stance = ANY(:crit) THEN s.intensity ELSE 0 END) AS crit
FROM article_stances s
JOIN article_districts d ON d.article_id = s.article_id
{where}
GROUP BY d.district_id
HAVING count(*) >= :min_n
ORDER BY n DESC
LIMIT :k
"""


async def district_sentiment(
    conn: AsyncConnection, entity_id: str | None = None, k: int = 40, min_n: int = 3
) -> list[dict]:
    """Per-district supportive-vs-critical balance (optionally toward one entity)."""
    where = "WHERE s.actor_entity_id = CAST(:eid AS uuid)" if entity_id else ""
    params: dict = {"sup": list(SUPPORTIVE), "crit": list(CRITICAL), "k": k, "min_n": min_n}
    if entity_id:
        params["eid"] = entity_id
    rows = (await conn.execute(text(_DISTRICT_SENTIMENT_SQL.format(where=where)), params)).mappings().all()
    out: list[dict] = []
    for r in rows:
        sup, crit = float(r["sup"]), float(r["crit"])
        denom = sup + crit
        out.append({
            "district": r["district_id"],
            "n_stances": r["n"],
            "balance_score": round((sup - crit) / denom, 3) if denom else 0.0,
        })
    return out


def _examples(rows: list[dict], k: int = 3) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for r in rows:
        if r["article_id"] in seen:
            continue
        seen.add(r["article_id"])
        out.append({"title": r.get("title"), "url": r.get("url"), "language": r.get("language")})
        if len(out) >= k:
            break
    return out


def find_contested(rows: Sequence[dict], min_each: int = 1) -> list[dict]:
    """Pure: from stance rows, find TARGETS that get BOTH supportive and critical
    coverage in the same result set — i.e. where sources disagree about them."""
    by_actor: dict[str, dict] = {}
    for r in rows:
        eid = r.get("actor_entity_id")
        if not eid:
            continue
        g = by_actor.setdefault(eid, {"actor": r.get("actor"), "supportive": [], "critical": []})
        if r["stance"] in SUPPORTIVE:
            g["supportive"].append(r)
        elif r["stance"] in CRITICAL:
            g["critical"].append(r)
    out: list[dict] = []
    for eid, g in by_actor.items():
        sup, crit = len(g["supportive"]), len(g["critical"])
        if sup >= min_each and crit >= min_each:
            total = sup + crit
            out.append({
                "actor": g["actor"],
                "actor_entity_id": eid,
                "supportive_count": sup,
                "critical_count": crit,
                "contested_score": round((min(sup, crit) / total) * 2, 3),  # 1.0 = even split
                "supportive_examples": _examples(g["supportive"]),
                "critical_examples": _examples(g["critical"]),
            })
    out.sort(key=lambda x: x["supportive_count"] + x["critical_count"], reverse=True)
    return out


_DISAGREE_SQL = """
SELECT s.actor, s.actor_entity_id::text AS actor_entity_id, s.stance, s.intensity,
       a.id::text AS article_id, a.title, a.url, a.language_detected AS language,
       a.source_id::text AS source_id
FROM article_stances s JOIN articles a ON a.id = s.article_id
WHERE s.article_id = ANY(CAST(:ids AS uuid[])) AND s.actor_entity_id IS NOT NULL
"""


async def disagreements(conn: AsyncConnection, article_ids: Iterable[str]) -> list[dict]:
    ids = list(article_ids)
    if not ids:
        return []
    rows = (await conn.execute(text(_DISAGREE_SQL), {"ids": ids})).mappings().all()
    return find_contested([dict(r) for r in rows])
