"""Stage 2A — multi-source triangulation (Mode A).

Given a cluster of articles (Stage 0 output), find SPO claims that
multiple sources agree on, and surface conflicts where the same
subject+predicate has different object values across sources.

NO LLM CALLS. Pure SQL + Python over the populated `article_claims` table.
Activates as soon as D1 lands and SPO columns start filling.

Output classes:
  - agreed       — same (subject, predicate, object) across ≥2 articles
  - disputed     — same (subject, predicate) but different object
                   across ≥2 articles (e.g., GDP "rose 4.2%" vs "rose 5.1%")
  - solo         — only one source supports this triple
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import text

from backend.database import get_db

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TriangulatedClaim:
    subject: str
    predicate: str
    agreed_object: str | None       # consensus object if `class` == 'agreed'
    supporting_article_ids: tuple[str, ...]
    competing_objects: tuple[str, ...]  # non-empty only if `class` == 'disputed'
    classification: str             # "agreed" | "disputed" | "solo"
    support_count: int


def _normalize(s: str | None) -> str:
    if not s:
        return ""
    return " ".join(s.strip().lower().split())


async def _fetch_claims(article_ids: list[str]) -> list[dict]:
    if not article_ids:
        return []
    async with get_db() as db:
        rows = (await db.execute(text("""
            SELECT article_id::text AS aid,
                   subject_text, predicate, object_text, claim_text, confidence
              FROM article_claims
             WHERE article_id::text = ANY(:ids)
               AND subject_text IS NOT NULL
               AND predicate    IS NOT NULL
               AND object_text  IS NOT NULL
        """), {"ids": article_ids})).mappings().all()
    return [dict(r) for r in rows]


def triangulate(claims: list[dict]) -> list[TriangulatedClaim]:
    """Group by (subject, predicate), then bucket by object to find
    agreement / dispute. `claims` rows from `article_claims`."""
    if not claims:
        return []
    # Group: (subj, pred) -> { obj -> set(article_ids) }
    groups: dict[tuple[str, str], dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    raw_objects: dict[tuple[str, str], dict[str, str]] = defaultdict(dict)
    for c in claims:
        sk = _normalize(c["subject_text"])
        pk = _normalize(c["predicate"])
        ok = _normalize(c["object_text"])
        if not sk or not pk or not ok:
            continue
        groups[(sk, pk)][ok].add(str(c["aid"]))
        # remember the un-normalised object_text for the most-supported variant
        raw_objects[(sk, pk)].setdefault(ok, c["object_text"])
    out: list[TriangulatedClaim] = []
    for (sk, pk), buckets in groups.items():
        # Pick the canonical raw subject/predicate from the first hit
        raw_subj = next(
            (c["subject_text"] for c in claims if _normalize(c["subject_text"]) == sk),
            sk,
        )
        raw_pred = next(
            (c["predicate"] for c in claims if _normalize(c["predicate"]) == pk),
            pk,
        )
        # Order objects by support count descending
        ranked_objs = sorted(buckets.items(), key=lambda x: -len(x[1]))
        top_obj_key, top_supporters = ranked_objs[0]
        total_articles = set().union(*buckets.values())
        if len(buckets) == 1:
            # Single object across all sources
            if len(top_supporters) >= 2:
                cls = "agreed"
            else:
                cls = "solo"
            competing: tuple[str, ...] = ()
            agreed = raw_objects[(sk, pk)][top_obj_key]
        else:
            # Multiple distinct objects — dispute
            cls = "disputed"
            competing = tuple(raw_objects[(sk, pk)][k] for k, _ in ranked_objs[1:5])
            agreed = raw_objects[(sk, pk)][top_obj_key] if len(top_supporters) >= 2 else None
        out.append(TriangulatedClaim(
            subject=raw_subj,
            predicate=raw_pred,
            agreed_object=agreed,
            supporting_article_ids=tuple(sorted(total_articles)),
            competing_objects=competing,
            classification=cls,
            support_count=len(total_articles),
        ))
    # Surface agreed claims first (best signal), then disputed (story-worthy), then solo
    rank = {"agreed": 0, "disputed": 1, "solo": 2}
    out.sort(key=lambda c: (rank[c.classification], -c.support_count))
    return out


async def triangulate_cluster(article_ids: list[str]) -> list[TriangulatedClaim]:
    """End-to-end Stage 2A entry point for one cluster."""
    claims = await _fetch_claims(article_ids)
    result = triangulate(claims)
    logger.info(
        "stage2a: %d articles, %d raw claims, %d triangulated triples "
        "(agreed=%d disputed=%d solo=%d)",
        len(article_ids), len(claims), len(result),
        sum(1 for r in result if r.classification == "agreed"),
        sum(1 for r in result if r.classification == "disputed"),
        sum(1 for r in result if r.classification == "solo"),
    )
    return result
