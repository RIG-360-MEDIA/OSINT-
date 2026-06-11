"""GET /api/brief/sources — the "show me the articles" receipts endpoint.

Every qualitative read elsewhere in the Night Desk (a sentiment number, a threat
cable, an outlet-lean bar, an entity standing) is built from real coverage. This
endpoint hands back THAT coverage so any claim is one click from its evidence.

It reuses posture.py's vetted idioms verbatim so the rows shown here are exactly
the rows the metrics were computed from:
  * POL            — the 18-label stance → polarity map.
  * _BODY_PRESENT  — the anti-hallucination guard (the entity's canonical name or
                     a registered/curated alias must appear in the article body),
                     so a NER mis-tag can never surface as a "source".
  * principal_of   — resolves the signed-in persona's primary subject.

KEY DATA FACT: ``article_stances.actor_entity_id`` is mislabelled — it holds the
stance TARGET (who the stance is ABOUT), not the speaker. So "stories that
criticise/support entity X" is ``article_stances st WHERE st.actor_entity_id = X
AND (POL) < 0 / > 0``. We use it as the *directed* stance toward a target entity.

Auth + prefs lookup follow routers/home.py exactly (get_optional_user → load_prefs
→ principal_of). Unauthenticated / no-prefs / no-principal degrade to an empty
list rather than erroring.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from auth.middleware import get_optional_user
from brief_prefs import load_prefs
from db import get_db
from posture import POL, _BODY_PRESENT, principal_of
import i18n as _i18n

router = APIRouter(prefix="/api/brief", tags=["brief"])

# Newest-first hard cap — keeps the panel snappy and the response bounded.
_CAP = 200
# Default lookback. Matches the product's "recent coverage" horizon (21 days),
# the same window the War Room / Analytics universes are built over.
_WINDOW_HOURS = 504

_KINDS = {"negative", "supportive", "neutral", "outlet", "topic", "entity"}

# Directed stance toward :tid summed over an article — the SAME expression
# build_six_feeds uses for its criticism/support feeds. Only stances whose
# target is :tid count, so "Congress criticised" in a story about a Congress
# principal reads as pressure on the principal, not support.
_POL_SUM = (
    f"(SELECT COALESCE(sum(({POL}) * st.intensity), 0) "
    f"FROM article_stances st WHERE st.article_id = a.id "
    f"AND st.actor_entity_id = CAST(:tid AS uuid))"
)


def _tone(lean: float | None) -> str:
    """Directed lean → tone bucket. >= +0.1 supportive, <= -0.1 hostile, else neutral."""
    if lean is None:
        return "neutral"
    if lean >= 0.1:
        return "supportive"
    if lean <= -0.1:
        return "hostile"
    return "neutral"


async def _query_sources(
    db, tid: str, *, extra_join: str = "", extra_where: str = "",
    params: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Newest-first articles where target :tid is a body-present mention, with the
    directed lean toward :tid attached as ``tone``.

    `extra_join` / `extra_where` let each kind narrow the same base universe
    (e.g. a source filter, a topic filter, or a directed-stance sign filter)
    without duplicating the mention + body-presence scaffolding.
    """
    sql = text(f"""
        SELECT a.id::text AS id,
               COALESCE(NULLIF(a.title, ''), a.lead_text_translated, '') AS title,
               s.name AS outlet,
               a.url AS url,
               a.collected_at AS when_ts,
               {_POL_SUM} AS lean
          FROM article_entity_mentions m
          JOIN articles a ON a.id = m.article_id
          JOIN sources s ON s.id = a.source_id
          {extra_join}
         WHERE m.entity_id = CAST(:tid AS uuid)
           AND a.collected_at >= analytics.now_sim() - make_interval(hours => :wh)
           AND a.collected_at <= analytics.now_sim()
           AND {_BODY_PRESENT}
           {extra_where}
         ORDER BY a.collected_at DESC
         LIMIT :cap
    """)
    binds = {"tid": tid, "wh": _WINDOW_HOURS, "cap": _CAP, **(params or {})}
    rows = (await db.execute(sql, binds)).fetchall()

    items: list[dict[str, Any]] = []
    for r in rows:
        title = (r.title or "").strip()
        if not title:
            continue
        lean = float(r.lean) if r.lean is not None else None
        items.append({
            "id": r.id,
            "title": title,
            "title_en": None,
            "outlet": r.outlet or "",
            "url": r.url or "",
            "when": r.when_ts.strftime("%Y-%m-%dT%H:%M:%SZ") if r.when_ts else "",
            "tone": _tone(lean),
        })

    # Bilingual rule: attach an English gloss to non-English headlines, in one
    # batched pass. attach_en writes "title_en" only where it differs from title.
    await _i18n.attach_en(db, items, "title")
    for it in items:
        if it.get("title_en") and it["title_en"].strip() == it["title"].strip():
            it["title_en"] = None
    return items


# Directed-stance sign filter per stance bucket toward the target entity. Uses
# the SAME _POL_SUM expression the Standing card is built from, so the rows here
# match the supportive / critical / neutral counts shown in the dossier.
_BUCKET_WHERE = {
    "supportive": f"AND {_POL_SUM} > 0",
    "critical": f"AND {_POL_SUM} < 0",
    "neutral": f"AND {_POL_SUM} = 0",
}


@router.get("/sources")
async def get_sources(
    kind: str = Query(..., description="negative|supportive|neutral|outlet|topic|entity"),
    value: str | None = Query(None, description="outlet name / topic_category / entity_id"),
    bucket: str | None = Query(None, description="supportive|critical|neutral (kind=entity only)"),
    user: dict[str, str] | None = Depends(get_optional_user),
) -> dict[str, Any]:
    """Show-me-the-articles for a given read.

    For kinds negative/supportive/neutral/outlet/topic the directed-stance TARGET
    is the signed-in persona's principal. For kind=entity the target is `value`
    (an entity_id) and the rows are that entity's recent coverage, toned by the
    directed lean toward it. An optional `bucket` (supportive|critical|neutral)
    narrows kind=entity to the directed stance of that sign toward the entity;
    when absent the full coverage record is returned (unchanged behaviour).
    Returns ``{count, articles[]}`` newest-first.
    """
    empty: dict[str, Any] = {"count": 0, "articles": []}
    if kind not in _KINDS:
        return empty
    if not user:
        return empty

    async with get_db() as db:
        prefs = await load_prefs(db, user["id"])
        if not prefs:
            return empty

        if kind == "entity":
            # Target is the requested entity itself; no principal needed.
            if not value:
                return empty
            # Optional directed-stance bucket toward this entity. Unknown buckets
            # degrade to the full record rather than erroring.
            items = await _query_sources(
                db, value, extra_where=_BUCKET_WHERE.get(bucket, ""))
        else:
            pid, _ = principal_of(prefs)
            if not pid:
                return empty
            if kind == "negative":
                items = await _query_sources(
                    db, pid, extra_where=f"AND {_POL_SUM} < 0")
            elif kind == "supportive":
                items = await _query_sources(
                    db, pid, extra_where=f"AND {_POL_SUM} > 0")
            elif kind == "neutral":
                items = await _query_sources(
                    db, pid, extra_where=f"AND {_POL_SUM} = 0")
            elif kind == "outlet":
                if not value:
                    return empty
                items = await _query_sources(
                    db, pid, extra_where="AND s.name = :outlet",
                    params={"outlet": value})
            elif kind == "topic":
                # Topic drill-down surfaces the directed-NEGATIVE coverage on that
                # topic — the "why is my sentiment here low on X" receipts.
                if not value:
                    return empty
                items = await _query_sources(
                    db, pid,
                    extra_where=f"AND a.topic_category = :topic AND {_POL_SUM} < 0",
                    params={"topic": value})
            else:  # pragma: no cover — guarded by _KINDS above
                return empty

    return {"count": len(items), "articles": items}
