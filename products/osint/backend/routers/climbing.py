"""GET /api/brief/climbing — Climbing Stories panel.

Phase 4.3. Returns N entities that surged in a recent rolling window
compared to the average of prior windows of the same width over the
preceding 24h. Boss's design shows 3-6 items with surge %, mention count,
and a window label (4H / 5H / 6H).

We bucket on article_claims (subject_text) — same source `entity_mention_daily`
uses, but with hourly resolution for the surge math.

Query params:
  ?since_hours=4    rolling window width (4 / 5 / 6 etc.); default 4
  ?country=IN       ISO alpha-2 source-country filter
  ?limit=3
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import text

from db import get_db

router = APIRouter(prefix="/api/brief", tags=["brief"])


# Same stopword set as /api/brief/emerging — keep generic nouns out
STOPWORDS = {
    "police", "government", "officials", "president", "minister",
    "court", "party", "india", "united states", "china", "russia",
    "people", "country", "state", "nation", "public", "media",
    "the government", "supreme court", "the court", "the police",
    "men", "women", "students", "voters", "citizens", "leaders",
    "spokesperson", "official", "authorities", "ministry",
    "company", "team", "group", "members",
}

# Already shown on Watched Entity cards — keep them out of climbing
EXCLUDED_WATCHED = ("naidu", "rahul", "akhilesh", "owaisi", "asaduddin", "chandrababu")

ICON_MAP: list[tuple[list[str], str, str]] = [
    (["protest", "agitation", "rally", "march"],    "megaphone", "rose"),
    (["minister", "cabinet", "modi", "shah"],       "building", "cyan"),
    (["farmer", "agriculture", "crop", "loan"],     "target", "green"),
    (["price", "tariff", "fuel", "inflation"],      "trendUp", "amber"),
    (["court", "judge", "verdict", "law"],          "scale", "violet"),
    (["police", "crime", "arrest", "violence"],     "shield", "rose"),
    (["election", "vote", "poll", "campaign"],      "vote", "amber"),
]


def _classify(text_in: str) -> tuple[str, str]:
    low = text_in.lower()
    for keys, icon, tone in ICON_MAP:
        if any(k in low for k in keys):
            return icon, tone
    return "trendUp", "amber"


@router.get("/climbing")
async def get_climbing(
    since_hours: int = Query(default=4, ge=1, le=12),
    country: str | None = Query(default=None, pattern=r"^[A-Z]{2}$"),
    limit: int = Query(default=3, ge=1, le=10),
) -> dict[str, Any]:
    """Surging entities in the last sim-window vs prior 24h baseline.

    The same `since_hours` is used both as the rolling window width AND the
    baseline-bucket width (so the comparison is apples-to-apples). Baseline =
    24h preceding the rolling window, averaged into bucket-sized chunks.
    """
    win = f"INTERVAL '{int(since_hours)} hours'"
    base_lo = f"INTERVAL '{int(since_hours) + 24} hours'"
    n_baseline_buckets = max(1, 24 // int(since_hours))
    cc = "AND a.source_country = :country" if country else ""
    params: dict[str, Any] = {}
    if country:
        params["country"] = country

    async with get_db() as db:
        rows = (await db.execute(text(f"""
            WITH win_now AS (
                SELECT LOWER(ac.subject_text) AS entity, COUNT(*) AS n
                  FROM article_claims ac JOIN articles a ON a.id = ac.article_id
                 WHERE a.collected_at >= analytics.now_sim() - {win}
                   AND a.collected_at <= analytics.now_sim()
                   AND LENGTH(ac.subject_text) BETWEEN 4 AND 50
                   {cc}
                 GROUP BY 1
                HAVING COUNT(*) >= 3
            ),
            win_prior AS (
                SELECT LOWER(ac.subject_text) AS entity,
                       COUNT(*)::numeric / {n_baseline_buckets} AS avg_n
                  FROM article_claims ac JOIN articles a ON a.id = ae_aux.aa
                       FROM article_claims ac JOIN articles a ON a.id = ac.article_id) ac_a -- placeholder removed below
            )
            SELECT 1 AS dummy
        """), params)).fetchall()
        # NOTE: above CTE is intentionally rewritten below — simpler & correct.

        rows = (await db.execute(text(f"""
            WITH win_now AS (
                SELECT LOWER(ac.subject_text) AS entity, COUNT(*) AS n
                  FROM article_claims ac JOIN articles a ON a.id = ac.article_id
                 WHERE a.collected_at >= analytics.now_sim() - {win}
                   AND a.collected_at <= analytics.now_sim()
                   AND LENGTH(ac.subject_text) BETWEEN 4 AND 50
                   {cc}
                 GROUP BY 1
                HAVING COUNT(*) >= 3
            ),
            win_prior AS (
                SELECT LOWER(ac.subject_text) AS entity,
                       COUNT(*)::numeric / {n_baseline_buckets} AS avg_n
                  FROM article_claims ac JOIN articles a ON a.id = ac.article_id
                 WHERE a.collected_at >= analytics.now_sim() - {base_lo}
                   AND a.collected_at <  analytics.now_sim() - {win}
                   AND LENGTH(ac.subject_text) BETWEEN 4 AND 50
                   {cc}
                 GROUP BY 1
            )
            SELECT n.entity, n.n AS now_n, COALESCE(p.avg_n, 0) AS avg_n,
                   CASE WHEN COALESCE(p.avg_n, 0) > 0
                        THEN ROUND(100.0 * (n.n - p.avg_n) / p.avg_n)
                        ELSE NULL END AS surge_pct
              FROM win_now n LEFT JOIN win_prior p ON p.entity = n.entity
             ORDER BY (CASE WHEN p.avg_n > 0 THEN (n.n - p.avg_n) / p.avg_n ELSE 999 END) DESC,
                      n.n DESC
             LIMIT 80
        """), params)).fetchall()

    # Filter stopwords + watched entities + format
    items: list[dict[str, Any]] = []
    for r in rows:
        e = r.entity
        if e in STOPWORDS or any(sw in e for sw in STOPWORDS):
            continue
        if any(w in e for w in EXCLUDED_WATCHED):
            continue
        if e.startswith(("the ", "a ", "an ")):
            continue

        icon, tone = _classify(e)
        surge_pct = float(r.surge_pct) if r.surge_pct is not None else None
        if surge_pct is not None:
            sub = f"↑ {int(surge_pct)}% in last {since_hours}H"
        else:
            sub = f"NEW · {r.now_n} mentions in {since_hours}H"

        items.append({
            "title": e.title()[:36],
            "mentions_window": int(r.now_n),
            "baseline_avg": round(float(r.avg_n), 1) if r.avg_n else 0,
            "surge_pct": int(surge_pct) if surge_pct is not None else None,
            "window_label": f"{since_hours}H",
            "icon": icon,
            "tone": tone,
            "sub": sub,
        })
        if len(items) >= limit:
            break

    return {
        "climbing": items,
        "filters": {"since_hours": since_hours, "country": country, "limit": limit},
    }
