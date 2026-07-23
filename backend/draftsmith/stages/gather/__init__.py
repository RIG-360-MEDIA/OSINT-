"""backend.draftsmith.stages.gather — Stage 2: QueryPlan -> snapshotted evidence.

    result = await gather_all(plan, job_id)

Fans every adapter out concurrently (asyncio.gather), isolates each one in
its own try/except + timeout so a single dead source never aborts the
stage, snapshots every item gathered into rigwire.draft_evidence (the
frozen citation set the writer may quote), and reports whether enough
corroborating source families came back to proceed to ranking
(config.GATHER_MIN_FAMILIES, including >= 1 tier-1 family).

Adapters, three owned by this module and three authored in parallel:
  - gather_warehouse          (warehouse.py)   -> corpus_article
  - gather_facts              (facts.py)       -> story_fact
  - gather_youtube_warehouse  (youtube.py)     -> youtube_clip (warehouse)
  - gather_social             (social.py)      -> twitter/reddit/tiktok/telegram/instagram/wechat/youtube_clip
  - gather_web                (web.py)         -> web
  - gather_wiki               (wiki.py)        -> wikipedia

None of these ever write to the warehouse; rigwire.draft_evidence (via
backend.draftsmith.db.save_evidence) is the ONLY write this stage performs.
"""
from __future__ import annotations

import asyncio
import functools
import logging
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional, Sequence

from backend.draftsmith import config, db
from backend.draftsmith.embed import EmbeddingError, embed_text
from backend.draftsmith.models import EvidenceItem, QueryPlan
from backend.draftsmith.stages.gather.facts import gather_facts
from backend.draftsmith.stages.gather.social import gather_social
from backend.draftsmith.stages.gather.warehouse import gather_warehouse
from backend.draftsmith.stages.gather.web import gather_web
from backend.draftsmith.stages.gather.wiki import gather_wiki
from backend.draftsmith.stages.gather.youtube import gather_youtube_warehouse

logger = logging.getLogger(__name__)

_Adapter = Callable[[QueryPlan], Awaitable[Sequence[EvidenceItem]]]

# name -> (adapter, per-adapter timeout seconds). The three DB-only adapters
# here are each a couple of short indexed SELECTs, so the fine-grained
# per-source budget (config.TIMEOUTS['gather_source']) is the right cap.
# social/web/wiki each fan out over MULTIPLE network calls internally and
# already isolate + bound every individual call at that same per-source
# constant (see their own modules) — re-applying it as a single outer cap
# here would prematurely truncate an adapter mid-loop before its own
# per-item isolation gets a chance to work, so those three get the whole
# stage's budget (config.TIMEOUTS['gather_global']) as their individual
# ceiling instead; the outer wait_for below still enforces gather_global as
# the hard total-stage bound regardless.
_ADAPTERS: tuple[tuple[str, _Adapter, str], ...] = (
    ("warehouse", gather_warehouse, "gather_source"),
    ("facts", gather_facts, "gather_source"),
    ("youtube_warehouse", gather_youtube_warehouse, "gather_source"),
    ("social", gather_social, "gather_global"),
    ("web", gather_web, "gather_global"),
    ("wiki", gather_wiki, "gather_global"),
)

# Adapters that run a LaBSE cosine-ANN query over a stored embedding column
# and therefore need the SHARED seed vector (embedded exactly once per job by
# gather_all). Every other adapter is embedding-free.
_SEED_VEC_ADAPTERS: frozenset[str] = frozenset({"warehouse", "youtube_warehouse"})


@dataclass(frozen=True)
class SourceOutcome:
    """Per-adapter result for one gather_all run — the "per-source ok/fail"
    the job's stage_progress wants. LOCAL to this stage, not part of the
    frozen models.py contract (nothing downstream of gather consumes it as
    a citable shape)."""

    source: str
    ok: bool
    count: int
    elapsed_seconds: float
    error: Optional[str] = None


@dataclass(frozen=True)
class GatherResult:
    """Stage 2's full outcome: the merged, already-snapshotted evidence plus
    enough bookkeeping for the caller (job orchestrator) to decide whether
    to advance to ranking or fail the job."""

    items: Sequence[EvidenceItem] = field(default_factory=tuple)
    source_outcomes: Sequence[SourceOutcome] = field(default_factory=tuple)
    families_ok: Sequence[str] = field(default_factory=tuple)
    tier1_families_ok: Sequence[str] = field(default_factory=tuple)
    proceed: bool = False
    elapsed_seconds: float = 0.0


async def _embed_seed_once(plan: QueryPlan) -> Optional[list[float]]:
    """Embed the shared warehouse vector seed EXACTLY ONCE per gather run.

    The remote LaBSE server is slow (~30-40s per call), so every vector-search
    adapter reuses this single embedding rather than re-embedding the same seed
    per source (which timed out the whole stage). Bounded by its own
    config.TIMEOUTS['gather_seed_embed'] budget and fully isolated: an empty/
    too-short seed, an EmbeddingError, or the budget elapsing all degrade to
    None — FTS still runs and the stage continues, never aborts.
    """
    seed = (plan.queries.warehouse_vector_seed or "").strip()
    if not seed:
        return None
    try:
        return await asyncio.wait_for(
            embed_text(seed), timeout=config.TIMEOUTS["gather_seed_embed"],
        )
    except (EmbeddingError, asyncio.TimeoutError) as exc:
        logger.warning(
            "gather_all: seed embedding failed/timed out (%s); vector search "
            "disabled for this run, FTS-only",
            exc,
        )
        return None


def _bind_seed_vec(
    name: str, adapter: _Adapter, seed_vec: Optional[list[float]],
) -> _Adapter:
    """Pass the shared seed vector into the two vector adapters that need it,
    leaving every other adapter's `adapter(plan)` call signature untouched."""
    if name in _SEED_VEC_ADAPTERS:
        return functools.partial(adapter, seed_vec=seed_vec)
    return adapter


async def gather_all(plan: QueryPlan, job_id: str) -> GatherResult:
    """Stage 2 — fan every adapter out, snapshot everything gathered, and
    report whether the corroboration floor (config.GATHER_MIN_FAMILIES,
    including >= 1 tier-1 family) was met.

    Never raises on an individual adapter's failure (network error, bad
    query, timeout) — each is caught, logged, and recorded as
    ok=False in the returned SourceOutcome. Only a bad `plan`/`job_id`
    argument or a failure in the draft_evidence snapshot write itself
    propagates.
    """
    if plan is None:
        raise ValueError("gather_all: plan is required")
    if not job_id or not job_id.strip():
        raise ValueError("gather_all: job_id is required")

    started = time.monotonic()
    seed_vec = await _embed_seed_once(plan)
    tasks = {
        name: asyncio.create_task(
            _run_one(
                name, _bind_seed_vec(name, adapter, seed_vec), plan,
                config.TIMEOUTS[timeout_key],
            )
        )
        for name, adapter, timeout_key in _ADAPTERS
    }

    try:
        await asyncio.wait_for(asyncio.gather(*tasks.values()), timeout=config.TIMEOUTS["gather_global"])
    except asyncio.TimeoutError:
        logger.warning(
            "gather_all: stage exceeded gather_global=%ss for job %s; "
            "salvaging whichever adapters already finished",
            config.TIMEOUTS["gather_global"], job_id,
        )

    outcomes: list[SourceOutcome] = []
    all_items: list[EvidenceItem] = []
    for name, task in tasks.items():
        if task.done() and not task.cancelled():
            outcome, items = task.result()
        else:
            task.cancel()
            outcome, items = SourceOutcome(
                source=name, ok=False, count=0,
                elapsed_seconds=time.monotonic() - started,
                error=f"gather_all: stage-level gather_global timeout ({config.TIMEOUTS['gather_global']}s)",
            ), []
        outcomes.append(outcome)
        all_items.extend(items)

    if all_items:
        await db.save_evidence(job_id, all_items)

    families_ok = sorted({item.source_type for item in all_items})
    tier1_families_ok = sorted({item.source_type for item in all_items if item.trust_tier == 1})
    proceed = len(families_ok) >= config.GATHER_MIN_FAMILIES and bool(tier1_families_ok)

    return GatherResult(
        items=tuple(all_items),
        source_outcomes=tuple(outcomes),
        families_ok=tuple(families_ok),
        tier1_families_ok=tuple(tier1_families_ok),
        proceed=proceed,
        elapsed_seconds=time.monotonic() - started,
    )


async def _run_one(
    name: str, adapter: _Adapter, plan: QueryPlan, timeout_seconds: float,
) -> tuple[SourceOutcome, list[EvidenceItem]]:
    """Run one adapter under its own timeout, never letting it raise past
    this point — a dead source degrades the bundle, it never fails the
    job."""
    start = time.monotonic()
    try:
        items = list(await asyncio.wait_for(adapter(plan), timeout=timeout_seconds))
    except asyncio.TimeoutError:
        elapsed = time.monotonic() - start
        logger.warning("gather_all: %s timed out after %ss", name, timeout_seconds)
        return SourceOutcome(source=name, ok=False, count=0, elapsed_seconds=elapsed, error="timeout"), []
    except Exception as exc:  # noqa: BLE001 — isolate one bad source, never abort the fan-out
        elapsed = time.monotonic() - start
        logger.exception("gather_all: %s raised", name)
        return SourceOutcome(source=name, ok=False, count=0, elapsed_seconds=elapsed, error=str(exc)), []

    elapsed = time.monotonic() - start
    return SourceOutcome(source=name, ok=True, count=len(items), elapsed_seconds=elapsed), items


__all__ = ["GatherResult", "SourceOutcome", "gather_all"]
