"""Pipeline orchestrator — stitches Stages 0 → 6.

Two entry points:
  - run_for_cluster(cluster) — drive a single Stage-0 cluster through the
    rest of the pipeline (Mode A for ≥2 articles, Mode B for singletons).
  - run_recent(lookback_hours) — full sweep: Stage 0 then process every
    cluster.

This module composes the per-stage primitives without hiding which model
or temperature each step uses — keeping the stages as simple, testable
pure-ish functions.

Stage 1 (frame router) and Stage 2A (triangulation) are NOT yet
implemented — they require D5 (`articles.narrative_frame`) and the D1
SPO data respectively. The orchestrator gracefully skips them when the
data isn't there.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import text

from backend.database import get_db
from backend.tasks.narrative.stage0_clusters import AssembledCluster, run_stage0
from backend.tasks.narrative.stage2b_interrogation import interrogate_article
from backend.tasks.narrative.stage3_lede import build_lede
from backend.tasks.narrative.stage4_body import compose_body
from backend.tasks.narrative.stage5_critic import needs_revision, run_critic_panel
from backend.tasks.narrative.stage6_revision import revise_draft

logger = logging.getLogger(__name__)

MAX_REVISION_PASSES = 2
CRITIC_FLOOR = 0.6


@dataclass(frozen=True)
class PipelineDraft:
    cluster_id: str | None
    headline: str
    lede: str
    body: str
    word_count: int
    critic_scores: dict[str, float]
    revisions: int
    mode: str  # "A" or "B"


async def _claims_for_articles(article_ids: list[str], limit: int = 25) -> list[dict]:
    if not article_ids:
        return []
    async with get_db() as db:
        rows = (await db.execute(text("""
            SELECT subject_text, predicate, object_text, claim_text, confidence
              FROM article_claims
             WHERE article_id::text = ANY(:ids)
               AND subject_text IS NOT NULL
               AND predicate    IS NOT NULL
               AND object_text  IS NOT NULL
             ORDER BY confidence DESC NULLS LAST
             LIMIT :lim
        """), {"ids": article_ids, "lim": limit})).mappings().all()
    return [
        {
            "subject":   r["subject_text"],
            "predicate": r["predicate"],
            "object":    r["object_text"],
            "text":      r["claim_text"],
            "confidence": float(r["confidence"] or 0.5),
        }
        for r in rows
    ]


async def run_for_cluster(cluster: AssembledCluster) -> PipelineDraft | None:
    """Run a single cluster through stages 2B→3→4→5→6 (Stage 2A not yet built)."""
    mode = "A" if len(cluster.article_ids) >= 2 else "B"
    claims = await _claims_for_articles(list(cluster.article_ids))
    if not claims:
        logger.info("pipeline: cluster %s has no SPO claims, skipping", cluster.seed_id)
        return None
    primary = claims[0]
    supporting = claims[1:6]
    lede = await build_lede(primary_claim=primary, supporting_claims=supporting)
    if not lede:
        logger.warning("pipeline: lede generation failed for cluster %s", cluster.seed_id)
        return None
    body = await compose_body(lede=lede.lede, claims_ranked=claims)
    if not body:
        logger.warning("pipeline: body composition failed for cluster %s", cluster.seed_id)
        return None
    headline = lede.headline
    lede_text = lede.lede
    body_text = body.body
    panel = await run_critic_panel(
        f"HEADLINE: {headline}\n\nLEDE: {lede_text}\n\nBODY:\n{body_text}"
    )
    revisions = 0
    while needs_revision(panel, floor=CRITIC_FLOOR) and revisions < MAX_REVISION_PASSES:
        revised = await revise_draft(headline, lede_text, body_text, panel)
        if not revised:
            break
        headline, lede_text, body_text = revised.headline, revised.lede, revised.body
        panel = await run_critic_panel(
            f"HEADLINE: {headline}\n\nLEDE: {lede_text}\n\nBODY:\n{body_text}"
        )
        revisions += 1
    return PipelineDraft(
        cluster_id=None,  # set by persistence layer (Stage 0 migration)
        headline=headline,
        lede=lede_text,
        body=body_text,
        word_count=len(body_text.split()),
        critic_scores={k: v.score for k, v in panel.items()},
        revisions=revisions,
        mode=mode,
    )


async def run_recent(lookback_hours: int = 24) -> list[PipelineDraft]:
    """Full sweep — Stage 0 + per-cluster pipeline. Returns produced drafts."""
    clusters = await run_stage0(lookback_hours=lookback_hours)
    out: list[PipelineDraft] = []
    for c in clusters:
        try:
            d = await run_for_cluster(c)
            if d:
                out.append(d)
        except Exception as e:  # noqa: BLE001
            logger.warning("pipeline: cluster %s failed: %s", c.seed_id, e)
    return out
