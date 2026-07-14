"""Keyword Dossier builder — one keyword → unified cross-source intelligence.

The flagship "type anything, get the picture" feature. Given a free-text keyword
(person / org / event / phrase / niche topic), aggregate over the store-everything
news corpus + the live social feed and return: volume + trend, sentiment
distribution, top articles, cross-platform social, and related (co-mentioned)
entities.

Search uses trigram-accelerated word-boundary matching (migration 120 indexes)
so `~*` stays fast on 910k rows — naive ILIKE matched "Modi" inside "Modified".

Read-only (analytics_user). Pure builder so it can be driven by the request path
or a cache/precompute later.
"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text

# ── search pattern ────────────────────────────────────────────────────────────

def _word_pattern(q: str) -> str:
    """POSIX word-boundary regex for a keyword, metacharacters escaped.

    `\\y` is Postgres' word boundary; escaping stops user input like "C++" or
    "a.b" from being interpreted as regex. Powered by the gin_trgm_ops indexes.
    """
    return r"\y" + re.escape(q.strip()) + r"\y"


def _stance_label(avg: float | None) -> str:
    if avg is None:
        return "no data"
    if avg >= 0.15:
        return "positive"
    if avg <= -0.15:
        return "negative"
    return "mixed"


# ── the builder ───────────────────────────────────────────────────────────────

async def build_keyword_dossier(db, q: str, days: int = 7) -> dict[str, Any]:
    """Assemble the cross-source dossier for keyword `q` over the last `days`."""
    q = (q or "").strip()
    if not q:
        return {"query": q, "error": "empty query"}
    pat = _word_pattern(q)
    d = int(days)
    d2 = d * 2

    # 1. Volume: total in window + prior window (velocity) + daily series.
    vol = (await db.execute(text("""
        SELECT
          count(*) FILTER (WHERE collected_at > now() - make_interval(days => :days)) AS cur,
          count(*) FILTER (WHERE collected_at > now() - make_interval(days => :days2)
                             AND collected_at <= now() - make_interval(days => :days)) AS prev
        FROM articles
        WHERE collected_at > now() - make_interval(days => :days2) AND title ~* :pat
    """), {"days": d, "days2": d2, "pat": pat})).first()
    cur_n = int(vol.cur or 0) if vol else 0
    prev_n = int(vol.prev or 0) if vol else 0
    velocity = round((cur_n - prev_n) / prev_n * 100.0, 1) if prev_n else None

    series = [
        {"date": r.d.isoformat(), "count": int(r.c)}
        for r in (await db.execute(text("""
            SELECT collected_at::date AS d, count(*) AS c
              FROM articles
             WHERE collected_at > now() - make_interval(days => :days) AND title ~* :pat
             GROUP BY 1 ORDER BY 1
        """), {"days": d, "pat": pat})).fetchall()
    ]

    # 2. Sentiment distribution (directed stances where the keyword is the target).
    dist_rows = (await db.execute(text("""
        SELECT stance, count(*) AS c, avg(intensity) AS ai
          FROM article_stances
         WHERE actor ~* :pat AND intensity IS NOT NULL
         GROUP BY stance ORDER BY 2 DESC
    """), {"pat": pat})).fetchall()
    distribution = {r.stance: int(r.c) for r in dist_rows}
    total_st = sum(distribution.values())
    avg_int = (await db.execute(text("""
        SELECT avg(intensity) AS ai FROM article_stances
         WHERE actor ~* :pat AND intensity IS NOT NULL
    """), {"pat": pat})).scalar()
    avg_int = float(avg_int) if avg_int is not None else None
    # directed intensity is 0..1 magnitude; derive a signed lean from stance mix.
    pos = distribution.get("supportive", 0) + distribution.get("sympathetic", 0)
    neg = (distribution.get("critical", 0) + distribution.get("hostile", 0)
           + distribution.get("mocking", 0))
    lean = ((pos - neg) / total_st) if total_st else None

    # 3. Top recent articles (with tone from their stances).
    arts = (await db.execute(text("""
        SELECT a.id::text AS id, a.title, a.url, a.source_id,
               EXTRACT(EPOCH FROM (now() - a.collected_at))/3600.0 AS age_h,
               (SELECT avg(s.intensity) FROM article_stances s WHERE s.article_id = a.id) AS ai
          FROM articles a
         WHERE a.collected_at > now() - make_interval(days => :days) AND a.title ~* :pat
         ORDER BY a.collected_at DESC LIMIT 10
    """), {"days": d, "pat": pat})).fetchall()
    top_articles = [{
        "id": r.id, "headline": r.title, "url": r.url,
        "age_hours": round(float(r.age_h), 1) if r.age_h is not None else None,
        "tone": ("supportive" if (r.ai or 0) >= 0.10
                 else "hostile" if (r.ai or 0) <= -0.10 else "neutral"),
    } for r in arts]

    # 4. Cross-platform social (count by platform + a few samples).
    soc_rows = (await db.execute(text("""
        SELECT platform, count(*) AS c
          FROM social_posts
         WHERE collected_at > now() - make_interval(days => :days) AND post_text ~* :pat
         GROUP BY platform ORDER BY 2 DESC
    """), {"days": d, "pat": pat})).fetchall()
    by_platform = {r.platform: int(r.c) for r in soc_rows}
    soc_samples = [{
        "platform": r.platform, "text": (r.post_text or "")[:200], "url": r.post_url,
    } for r in (await db.execute(text("""
        SELECT platform, post_text, post_url FROM social_posts
         WHERE collected_at > now() - make_interval(days => :days) AND post_text ~* :pat
         ORDER BY collected_at DESC LIMIT 6
    """), {"days": d, "pat": pat})).fetchall()]

    # 5. Related (co-mentioned) entities — the "things around this keyword".
    related = [{"name": r.nm, "count": int(r.c)} for r in (await db.execute(text("""
        SELECT e->>'name' AS nm, count(*) AS c
          FROM articles a, jsonb_array_elements(a.entities_extracted) e
         WHERE a.collected_at > now() - make_interval(days => :days) AND a.title ~* :pat
           AND e->>'name' !~* :pat AND length(e->>'name') > 2
         GROUP BY 1 ORDER BY 2 DESC LIMIT 12
    """), {"days": d, "pat": pat})).fetchall()]

    # 6. Top accounts driving the keyword (per platform, by volume + engagement).
    top_accounts = [{
        "platform": r.platform, "username": r.username,
        "posts": int(r.c), "engagement": int(r.eng or 0),
    } for r in (await db.execute(text("""
        SELECT sp.platform AS platform, sp.author_username AS username, count(*) AS c,
               sum(coalesce(sp.upvotes,0)+coalesce(sp.likes,0)
                   +coalesce(sp.comments_count,0)) AS eng
          FROM social_posts sp
         WHERE sp.collected_at > now() - make_interval(days => :days)
           AND sp.post_text ~* :pat AND sp.author_username IS NOT NULL
         GROUP BY sp.platform, sp.author_username ORDER BY c DESC LIMIT 10
    """), {"days": d, "pat": pat})).fetchall()]

    # 7. Harmful accounts — toxic / weaponized / coordinated posts about the keyword.
    # Signals are precomputed on social_posts (toxicity, weaponization_signals,
    # coordination_cluster_id); coverage is sparse until on-demand enrichment lands,
    # so this returns what exists honestly (may be empty for low-signal keywords).
    harmful_accounts = [{
        "platform": r.platform, "username": r.username,
        "toxic_posts": int(r.toxic or 0), "max_toxicity": round(float(r.mx or 0), 2),
        "coordinated_posts": int(r.coord or 0),
    } for r in (await db.execute(text("""
        SELECT sp.platform AS platform, sp.author_username AS username,
               count(*) FILTER (WHERE sp.toxicity > 0.5) AS toxic,
               max(sp.toxicity) AS mx,
               count(*) FILTER (WHERE sp.coordination_cluster_id IS NOT NULL) AS coord
          FROM social_posts sp
         WHERE sp.collected_at > now() - make_interval(days => :days)
           AND sp.post_text ~* :pat AND sp.author_username IS NOT NULL
           AND (sp.toxicity > 0.5 OR sp.coordination_cluster_id IS NOT NULL
                OR (sp.weaponization_signals IS NOT NULL
                    AND sp.weaponization_signals::text NOT IN ('null','{}','[]')))
         GROUP BY sp.platform, sp.author_username
         ORDER BY toxic DESC, mx DESC NULLS LAST LIMIT 10
    """), {"days": d, "pat": pat})).fetchall()]

    return {
        "query": q,
        "days": days,
        "volume": {"total": cur_n, "prev": prev_n, "velocity_pct": velocity,
                   "series": series},
        "top_accounts": top_accounts,
        "harmful_accounts": harmful_accounts,
        "sentiment": {"distribution": distribution, "avg_intensity": avg_int,
                      "lean": round(lean, 3) if lean is not None else None,
                      "label": _stance_label(lean), "n": total_st},
        "top_articles": top_articles,
        "social": {"total": sum(by_platform.values()), "by_platform": by_platform,
                   "samples": soc_samples},
        "related_entities": related,
    }
