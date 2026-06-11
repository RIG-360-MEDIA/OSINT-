"""GET /api/brief/emerging — top-N surging entities.

Ported from backend/observability/brief_emerging.py. Same stopword filter +
NEW-today boost + surge ratio scoring.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from sqlalchemy import text

from db import get_db

router = APIRouter(prefix="/api/brief", tags=["brief"])


ICON_MAP: list[tuple[list[str], str, str]] = [
    (["protest", "agitation", "rally", "march"],    "megaphone", "rose"),
    (["minister", "cabinet", "modi", "shah"],       "building", "cyan"),
    (["farmer", "agriculture", "crop", "loan"],     "target", "green"),
    (["price", "tariff", "fuel", "inflation"],      "trendUp", "amber"),
    (["court", "judge", "verdict", "law"],          "scale", "violet"),
    (["police", "crime", "arrest", "violence"],     "shield", "rose"),
    (["election", "vote", "poll", "campaign"],      "vote", "amber"),
]
DEFAULT_ICON, DEFAULT_TONE = "chat", "amber"


def _classify(entity: str) -> tuple[str, str]:
    lower = entity.lower()
    for keywords, icon, tone in ICON_MAP:
        if any(k in lower for k in keywords):
            return icon, tone
    return DEFAULT_ICON, DEFAULT_TONE


EXCLUDED_WATCHED = ["naidu", "rahul", "akhilesh", "owaisi", "asaduddin", "chandrababu"]

STOPWORDS = {
    "police", "government", "officials", "president", "minister",
    "court", "party", "india", "united states", "china", "russia",
    "people", "country", "state", "nation", "public", "media",
    "the government", "supreme court", "the court", "the police",
    "men", "women", "students", "voters", "citizens", "leaders",
    "spokesperson", "official", "authorities", "ministry",
    "company", "team", "group", "members",
}


@router.get("/emerging")
async def get_emerging(limit: int = 5) -> dict[str, Any]:
    async with get_db() as db:
        rows = (await db.execute(text("""
            WITH today AS (
              SELECT entity_text, SUM(n_mentions_total) AS today_n
                FROM entity_mention_daily
               WHERE date = analytics.now_sim_date()
               GROUP BY entity_text
            ),
            yesterday AS (
              SELECT entity_text, SUM(n_mentions_total) AS yest_n
                FROM entity_mention_daily
               WHERE date = analytics.now_sim_date() - 1
               GROUP BY entity_text
            )
            SELECT t.entity_text,
                   t.today_n,
                   COALESCE(y.yest_n, 0) AS yest_n,
                   CASE WHEN COALESCE(y.yest_n, 0) > 0
                        THEN ROUND((t.today_n::numeric / y.yest_n::numeric), 2)
                        ELSE NULL END AS surge,
                   (COALESCE(y.yest_n, 0) = 0) AS is_new_today
              FROM today t
              LEFT JOIN yesterday y USING (entity_text)
             WHERE LENGTH(t.entity_text) BETWEEN 4 AND 50
               AND t.entity_text !~* '^(the |a |an )'
               AND t.today_n >= 3
             ORDER BY t.today_n DESC
             LIMIT 200
        """))).fetchall()

    candidates: list[dict[str, Any]] = []
    for r in rows:
        e_lower = r.entity_text.lower()
        if e_lower in STOPWORDS or any(s in e_lower for s in STOPWORDS):
            continue
        if any(p in e_lower for p in EXCLUDED_WATCHED):
            continue

        is_new = r.is_new_today and r.today_n >= 5
        surge = float(r.surge) if r.surge else None
        score = (
            (1000 if is_new else 0) +
            (500 * surge if surge and surge >= 2.0 else 0) +
            r.today_n
        )

        if is_new:
            sub = f"NEW · {r.today_n} mentions today"
        elif surge and surge >= 2.0:
            sub = f"↑ {int((surge - 1) * 100)}% vs yesterday"
        elif surge:
            sub = f"{r.today_n} today · {int(r.yest_n)} yesterday"
        else:
            sub = f"{r.today_n} mentions today"

        icon, tone = _classify(r.entity_text)
        candidates.append({
            "icon": icon, "tone": tone,
            "title": r.entity_text.title()[:32],
            "sub": sub,
            "_score": score,
        })

    candidates.sort(key=lambda x: x["_score"], reverse=True)
    items = [{k: v for k, v in c.items() if k != "_score"} for c in candidates[:limit]]
    return {"signals": items}
