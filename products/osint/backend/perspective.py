"""Perspective Lens — framing divergence by language/origin for a keyword.

The moat feature: the SAME keyword framed differently across the languages/regions
that cover it. Coverage volume per language + directed stance-lean per language →
who is talking about this, and how differently they frame it. Divergence = the
spread between the most-supportive and most-critical language lens.

Verified: modi → en +66 / te +67 / bn +80 lean (Bengali coverage more supportive).
Read-only (analytics_user).
"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text


def _word_pattern(q: str) -> str:
    return r"\y" + re.escape(q.strip()) + r"\y"


async def build_perspective(db, q: str, days: int = 7) -> dict[str, Any]:
    """Framing divergence for keyword `q` across the languages that cover it."""
    q = (q or "").strip()
    if not q:
        return {"query": q, "framing_by_language": [], "divergence": None}
    pat = _word_pattern(q)
    d = int(days)

    coverage = {r.lang: int(r.c) for r in (await db.execute(text("""
        SELECT coalesce(language_iso, '?') AS lang, count(*) AS c
          FROM articles
         WHERE collected_at > now() - make_interval(days => :d) AND title ~* :pat
         GROUP BY 1 ORDER BY 2 DESC LIMIT 12
    """), {"d": d, "pat": pat})).fetchall()}

    lenses = [{
        "lang": r.lang, "articles": int(r.arts),
        "lean": int(r.lean) if r.lean is not None else None,
    } for r in (await db.execute(text("""
        SELECT coalesce(a.language_iso, '?') AS lang, count(DISTINCT a.id) AS arts,
               round(100.0 * (count(*) FILTER (WHERE s.stance IN ('supportive','sympathetic'))
                            - count(*) FILTER (WHERE s.stance IN ('critical','hostile','mocking')))
                     / nullif(count(*), 0)) AS lean
          FROM articles a JOIN article_stances s ON s.article_id = a.id
         WHERE a.collected_at > now() - make_interval(days => :d)
           AND a.title ~* :pat AND s.actor ~* :pat
         GROUP BY 1 HAVING count(DISTINCT a.id) >= 3
         ORDER BY 2 DESC LIMIT 10
    """), {"d": d, "pat": pat})).fetchall()]

    leans = [l["lean"] for l in lenses if l["lean"] is not None]
    divergence = (max(leans) - min(leans)) if len(leans) >= 2 else None
    return {
        "query": q, "days": days,
        "coverage_by_language": coverage,
        "framing_by_language": lenses,
        "divergence": divergence,
        "note": "lean −100 (critical) … +100 (supportive) per language; "
                "divergence = spread between most-supportive and most-critical lens",
    }
