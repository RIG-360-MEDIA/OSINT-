"""GET /api/brief/entities — 4 Watched Entity cards.

Ported from backend/observability/brief_entities.py (parallel session).
Same hybrid FK-then-ILIKE matching strategy. Same 4 hardcoded entities.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter
from sqlalchemy import text

from db import get_db

router = APIRouter(prefix="/api/brief", tags=["brief"])


ENTITIES_CONFIG: list[dict[str, Any]] = [
    {
        "rank": "01", "tone": "rose", "classification": "High Influence",
        "name": "N. Chandrababu Naidu", "init": "CN",
        "image": "images/entity-naidu.png",
        "party": "TDP", "region": "Andhra Pradesh",
        "regional_label": "South India", "region_key": "south",
        "tag": "Opposition Leader",
        "entity_uuid": "ca35f636-000e-40f5-8a16-69d3f0b14621",
        "patterns": ["%chandrababu%naidu%", "%n. chandrababu%", "chandrababu naidu"],
    },
    {
        "rank": "02", "tone": "cyan", "classification": "High Influence",
        "name": "Rahul Gandhi", "init": "RG",
        "image": "images/entity-rahul-gandhi.png",
        "party": "INC", "region": "National",
        "regional_label": "North & West India", "region_key": "north",
        "tag": "National Figure",
        "entity_uuid": "13676001-3789-495e-9b7a-a6ffa2d7d0bc",
        "patterns": ["%rahul gandhi%", "%rahul%gandhi%"],
    },
    {
        "rank": "03", "tone": "amber", "classification": "Rising",
        "name": "Akhilesh Yadav", "init": "AY",
        "image": "images/entity-akhilesh-yadav.png",
        "party": "SP", "region": "Uttar Pradesh",
        "regional_label": "Uttar Pradesh", "region_key": "up",
        "tag": "Regional Leader",
        "entity_uuid": "8b49e04c-65aa-4b8e-8d90-e7b250c98df7",
        "patterns": ["%akhilesh%yadav%", "akhilesh yadav"],
    },
    {
        "rank": "04", "tone": "violet", "classification": "High Influence",
        "name": "Asaduddin Owaisi", "init": "AO",
        "image": "images/entity-owaisi.png",
        "party": "AIMIM", "region": "Telangana",
        "regional_label": "Telangana", "region_key": "telangana",
        "tag": "Regional Voice",
        "entity_uuid": "92a84982-18e1-4fcd-ac69-e2965794f789",
        "patterns": ["%asaduddin%owaisi%", "%asaduddin%", "asad owaisi"],
    },
]


def _classify_velocity(change_pct: float | None) -> tuple[str, str]:
    if change_pct is None:
        return ("Stable", "Neutral")
    if change_pct >= 100:
        return ("Very High", "")
    if change_pct >= 30:
        return ("High", "")
    if change_pct >= 5:
        return ("Rising", "")
    if change_pct <= -20:
        return ("Cooling", "")
    return ("Stable", "")


def _sentiment_label(value: float | None) -> str:
    if value is None:
        return "Neutral"
    if value >= 0.15:
        return "Positive"
    if value <= -0.15:
        return "Negative"
    return "Neutral"


async def _one_entity(db, cfg: dict[str, Any]) -> dict[str, Any]:
    patterns = cfg["patterns"]
    uuid = cfg.get("entity_uuid")
    ilike_claims  = " OR ".join([f"LOWER(ac.subject_text) LIKE :p{i}" for i, _ in enumerate(patterns)])
    ilike_quotes  = " OR ".join([f"LOWER(aq.speaker_name) LIKE :p{i}" for i, _ in enumerate(patterns)])
    ilike_stances = " OR ".join([f"LOWER(asn.actor) LIKE :p{i}"        for i, _ in enumerate(patterns)])
    if uuid:
        or_claims  = f"ac.subject_entity_id = CAST(:euid AS uuid) OR (ac.subject_entity_id IS NULL AND ({ilike_claims}))"
        or_quotes  = f"aq.speaker_entity_id = CAST(:euid AS uuid) OR (aq.speaker_entity_id IS NULL AND ({ilike_quotes}))"
        or_stances = f"asn.actor_entity_id  = CAST(:euid AS uuid) OR (asn.actor_entity_id  IS NULL AND ({ilike_stances}))"
    else:
        or_claims, or_quotes, or_stances = ilike_claims, ilike_quotes, ilike_stances
    params: dict[str, Any] = {f"p{i}": p for i, p in enumerate(patterns)}
    if uuid:
        params["euid"] = uuid

    metrics = (await db.execute(text(f"""
        WITH today_claims AS (
          SELECT COUNT(*) AS n FROM article_claims ac
            JOIN articles a ON a.id = ac.article_id
           WHERE a.collected_at >= NOW() - INTERVAL '24 hours'
             AND ({or_claims})
        ),
        today_quotes AS (
          SELECT COUNT(*) AS n FROM article_quotes aq
            JOIN articles a ON a.id = aq.article_id
           WHERE a.collected_at >= NOW() - INTERVAL '24 hours'
             AND ({or_quotes})
        ),
        baseline AS (
          SELECT COALESCE(SUM(n_mentions_total)::float /
                          NULLIF(COUNT(DISTINCT date), 0), 0) AS avg_n
            FROM entity_mention_daily
           WHERE date BETWEEN CURRENT_DATE - 8 AND CURRENT_DATE - 1
             AND ({" OR ".join([f"entity_text LIKE :p{i}" for i, _ in enumerate(patterns)])})
        ),
        sentiment_today AS (
          SELECT AVG(intensity) AS s FROM article_stances asn
            JOIN articles a ON a.id = asn.article_id
           WHERE a.collected_at >= NOW() - INTERVAL '24 hours'
             AND asn.intensity IS NOT NULL
             AND ({or_stances})
        )
        SELECT (SELECT n FROM today_claims) + (SELECT n FROM today_quotes) AS today_n,
               (SELECT avg_n FROM baseline) AS baseline_avg,
               (SELECT s FROM sentiment_today) AS sentiment
    """), params)).fetchone()

    today_n = int(metrics.today_n or 0)
    baseline = float(metrics.baseline_avg or 0)
    change_pct = ((today_n - baseline) / baseline * 100) if baseline > 0 else None

    quote_row = (await db.execute(text(f"""
        SELECT aq.quote_text, a.collected_at, s.name AS source
          FROM article_quotes aq
          JOIN articles a ON a.id = aq.article_id
          JOIN sources s ON s.id = a.source_id
         WHERE ({or_quotes})
           AND LENGTH(aq.quote_text) >= 30
           AND aq.quote_text !~ '^[A-Z][a-z]+,\s+[A-Z][a-z]+\s*$'
           AND a.collected_at >= NOW() - INTERVAL '7 days'
         ORDER BY LEAST(LENGTH(aq.quote_text), 240) DESC,
                  a.collected_at DESC
         LIMIT 1
    """), params)).fetchone()

    sparkrows = (await db.execute(text(f"""
        SELECT date_trunc('hour', a.collected_at) AS hour, COUNT(*) AS n
          FROM article_claims ac
          JOIN articles a ON a.id = ac.article_id
         WHERE a.collected_at >= NOW() - INTERVAL '15 hours'
           AND ({or_claims})
         GROUP BY 1 ORDER BY 1
    """), params)).fetchall()
    velocity_bars = [int(r.n) for r in sparkrows]
    while len(velocity_bars) < 15:
        velocity_bars.insert(0, 0)
    velocity_bars = velocity_bars[-15:]

    sentiment_val = float(metrics.sentiment) if metrics.sentiment is not None else None
    velocity_label, _ = _classify_velocity(change_pct)
    sentiment_label = _sentiment_label(sentiment_val)
    influence = min(100, max(0, today_n * 2))
    change_str = (f"{'+' if change_pct >= 0 else ''}{change_pct:.0f}%"
                  if change_pct is not None else "—")

    return {
        "rank": cfg["rank"],
        "tone": cfg["tone"],
        "classification": cfg["classification"],
        "name": cfg["name"],
        "init": cfg["init"],
        "image": cfg["image"],
        "party": cfg["party"],
        "region": cfg["region"],
        "influence": int(influence),
        "change": change_str,
        "spark": "articles",
        "sentiment": {
            "label": sentiment_label,
            "value": (f"{'+' if (sentiment_val or 0) >= 0 else ''}"
                      f"{sentiment_val:.2f}" if sentiment_val is not None else "0.00"),
            "spark": "sentiment",
        },
        "velocity": velocity_label,
        "velocityBars": velocity_bars,
        "regionalLabel": cfg["regional_label"],
        "regionKey": cfg["region_key"],
        "quote": (quote_row.quote_text[:280] if quote_row and quote_row.quote_text
                  else f"No recent quote captured for {cfg['name']}."),
        "quoteCtx": ((quote_row.source + " · "
                      + quote_row.collected_at.strftime("%d %b · %H:%M IST"))
                     if quote_row else "—"),
        "tag": cfg["tag"],
        "mentions_today": today_n,
    }


@router.get("/entities")
async def get_entities() -> dict[str, Any]:
    async with get_db() as db:
        items = [await _one_entity(db, cfg) for cfg in ENTITIES_CONFIG]
    return {
        "entities": items,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
