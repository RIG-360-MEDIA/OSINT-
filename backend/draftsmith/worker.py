"""backend.draftsmith.worker — the Door B job state machine.

    queued -> planning -> gathering -> ranking -> drafting -> verifying
            -> [repairing -> verifying]* -> images -> ready
                                                     -> failed (any stage, attempts exhausted)

`run_job(job_id)` drives one job through every stage, persisting progress via
backend.draftsmith.db at each transition so a crashed worker's state is always
recoverable from the row (never held only in memory). Every stage call is
wrapped in asyncio.wait_for(...); a timeout or exception is treated
identically — recorded on the job, and either left for a retry (lease
expiry) or turned into a terminal 'failed' once config.MAX_ATTEMPTS is spent.

STAGE CONTRACT (as actually authored in backend.draftsmith.stages — verified
by reading each module directly, not assumed):

    stages.plan(input_text, dials) -> QueryPlan
    stages.gather.gather_all(query_plan, job_id) -> GatherResult
        -- ALREADY persists every item via db.save_evidence internally.
           GatherResult.proceed encodes the config.GATHER_MIN_FAMILIES gate
           (>= N families, >= 1 tier-1) — this module trusts it rather than
           re-deriving the same check.
    stages.rank(items, query_plan) -> list[EvidenceItem]
        -- the KEPT items (relevance-scored, capped, char-truncated,
           budget-trimmed); no `dials` argument. This module marks them
           selected=true via db.select_evidence(..., mark_selected=True) —
           rank() itself does not touch the DB.
    stages.build_brief(selected_items, query_plan) -> BriefResult(text, stats)
        -- SYNCHRONOUS (no `await`). `.text` is the BRIEF for
           prompts.build_draft_prompt / build_verify_prompt.
    stages.draft(brief, dials) -> Draft
    stages.run_repair_loop(brief, draft, dials) -> (Draft, VerifyReport, list[Flag])
        -- ONE call spanning: initial verify, up to config.MAX_REPAIR_ROUNDS
           repair+re-verify cycles, and (if dials.spot_check) an adversarial
           spot-check pass folded into the final report. Flags are ready for
           db.create_flags as-is. Because this is opaque from the outside,
           this module cannot observe or surface a live 'repairing' state
           mid-loop — see the KNOWN LIMITATION note below.
    stages.gather_images(job_id, query_plan, selected_items) -> list[ImageCandidate]
        -- ALREADY persists via db.save_images internally and returns
           exactly what was persisted (real DB ids).

IMPORTANT — a Python import-shadowing gotcha that bit this module during
authoring: `backend/draftsmith/stages/__init__.py` does
`from backend.draftsmith.stages.plan import plan, to_query_plan` (and the
equivalent for rank/verify/draft/...). That re-export REPLACES the `plan`
(etc.) attribute on the `stages` package with the FUNCTION, shadowing the
submodule. So `from backend.draftsmith.stages import plan as x; x(...)` is
correct; `from backend.draftsmith.stages import plan as x; x.plan(...)` is
NOT — `x` is already the callable, not a module with a `.plan` attribute.
Every stage call in this file uses the plain-callable form. `gather_all` is
the one exception: it is NOT re-exported by stages/__init__.py at all, so it
is imported directly from `backend.draftsmith.stages.gather`.

KNOWN LIMITATION: because run_repair_loop is a single opaque coroutine, an
operator polling job state during a live run will see 'verifying' persist
through every internal repair round — this module never observes a
mid-loop transition to fire an honest 'repairing' update. stage_progress's
"verify_repair" entry records whether a repair actually happened
(`final_draft != draft_obj`) after the fact instead. Making 'repairing'
live would require stages.run_repair_loop to expose a progress callback or
per-round generator — a stage-layer change, out of scope here.

Two run modes, pick ONE per deploy (never both — see CLAUDE.md's "two beat
schedulers" foot-gun, same failure mode applies to two claimers):
  * Celery task `run_job_task` on queue 'draftsmith', dispatched directly by
    the API's POST /jobs with a specific job_id (see api/routes_jobs.py).
  * Standalone asyncio poll loop (`python -m backend.draftsmith.worker`),
    5s interval, claiming via db.claim_next_job's FOR UPDATE SKIP LOCKED.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional

from backend.draftsmith import config, db
from backend.draftsmith.db._common import DraftJob
from backend.draftsmith.models import DraftVersion, JobState, QueryPlan
from backend.draftsmith.stages import build_brief, draft as run_draft, gather_images
from backend.draftsmith.stages import plan as run_plan
from backend.draftsmith.stages import rank as run_rank
from backend.draftsmith.stages import run_repair_loop
from backend.draftsmith.stages.gather import gather_all

logger = logging.getLogger(__name__)

_TERMINAL_STATES: frozenset[JobState] = frozenset({"ready", "failed", "cancelled", "published"})
_POLL_INTERVAL_SECONDS = 5.0


class WorkerStageError(RuntimeError):
    """Raised for any stage failure (timeout or exception) so run_job has
    one uniform thing to catch, tagged with which stage failed."""

    def __init__(self, stage: str, message: str) -> None:
        super().__init__(f"{stage}: {message}")
        self.stage = stage


def _lease() -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=config.LEASE_SECONDS)


def _lease_active(job: DraftJob) -> bool:
    return job.lease_until is not None and job.lease_until > datetime.now(timezone.utc)


def _repair_loop_timeout() -> float:
    """stages.run_repair_loop spans an initial verify, up to
    config.MAX_REPAIR_ROUNDS repair+re-verify cycles, and (if dials.spot_check)
    one spot-check pass whose per-beat probes run concurrently (asyncio.gather
    inside spot_check) — so it costs roughly one more verify call's wall time,
    not config.MAX_REPAIR_ROUNDS+1 of them serially. No single config.TIMEOUTS
    entry covers this composite shape, so it's derived here instead."""
    return (
        config.TIMEOUTS["verify"] * (config.MAX_REPAIR_ROUNDS + 2)
        + config.TIMEOUTS["repair"] * config.MAX_REPAIR_ROUNDS
    )


async def _begin_attempt(job: DraftJob) -> Optional[DraftJob]:
    """Ensure this job is leased and its attempt counted before stages run.

    - If db.claim_next_job already did this (poll-loop path: state != 'queued'
      and the lease is still live), reuse it as-is — claiming again here would
      double-count the attempt.
    - Otherwise (Celery direct-dispatch path: a freshly created job, state
      'queued', no lease yet) claim it ourselves, honouring MAX_ATTEMPTS.
    Returns None (having already marked the job 'failed') when attempts are
    exhausted before this run could even start.
    """
    if job.state != "queued" and _lease_active(job):
        return job
    if job.attempt >= config.MAX_ATTEMPTS:
        await db.update_job_state(
            job.id,
            "failed",
            error=f"max attempts ({config.MAX_ATTEMPTS}) reached before this run could start",
        )
        return None
    return await db.update_job_state(
        job.id, "planning", attempt=job.attempt + 1, lease_until=_lease(), error=None,
    )


async def _timed(stage_key: str, timeout_s: float, coro: Any) -> tuple[Any, dict[str, Any]]:
    """Run `coro` under a timeout, returning (result, timing_record). Any
    failure (timeout or exception) is normalised into WorkerStageError so
    run_job never has to special-case asyncio.TimeoutError separately."""
    started = time.monotonic()
    try:
        result = await asyncio.wait_for(coro, timeout=timeout_s)
    except asyncio.TimeoutError as exc:
        raise WorkerStageError(stage_key, f"timed out after {timeout_s}s") from exc
    except WorkerStageError:
        raise
    except Exception as exc:  # noqa: BLE001 — stage failures must surface, never be swallowed
        raise WorkerStageError(stage_key, str(exc)) from exc
    elapsed = round(time.monotonic() - started, 3)
    return result, {"ok": True, "elapsed_s": elapsed}


async def _fail(job: DraftJob, stage: str, exc: Exception, progress: Mapping[str, Any]) -> None:
    """Record the failure. If this was the job's last permitted attempt,
    transition to the terminal 'failed' state; otherwise leave the state
    where it is with the error recorded — the lease will expire and either
    the poll loop's claim_next_job or an operator-triggered redispatch picks
    it up for the next attempt."""
    message = f"{stage} stage failed: {exc}"[:2000]
    logger.error("run_job %s: %s", job.id, message)
    current = await db.get_job(job.id)
    attempt = current.attempt if current is not None else job.attempt
    state_now = current.state if current is not None else job.state
    target_state: JobState = "failed" if attempt >= config.MAX_ATTEMPTS else state_now
    await db.update_job_state(
        job.id, target_state, error=message, stage_progress=dict(progress),
    )


async def run_job(job_id: str) -> None:
    """Drive one job through every stage, start to finish (or to 'failed')."""
    job = await db.get_job(job_id)
    if job is None:
        logger.error("run_job: no draft_jobs row for id=%s", job_id)
        return
    if job.state in _TERMINAL_STATES:
        logger.info("run_job: job %s already terminal (%s); nothing to do", job_id, job.state)
        return

    claimed = await _begin_attempt(job)
    if claimed is None:
        return
    job = claimed
    progress: dict[str, Any] = dict(job.stage_progress or {})

    try:
        query_plan: Optional[QueryPlan] = job.query_plan
        if query_plan is None:
            query_plan, timing = await _timed(
                "plan", config.TIMEOUTS["plan"], run_plan(job.input_text, job.dials),
            )
            progress = {**progress, "plan": timing}
            await db.save_query_plan(job.id, query_plan)

        await db.update_job_state(
            job.id, "gathering", stage_progress=progress, lease_until=_lease(), error=None,
        )
        gather_result, timing = await _timed(
            "gather", config.TIMEOUTS["gather_global"], gather_all(query_plan, job.id),
        )
        progress = {
            **progress,
            "gather": {
                **timing,
                "families_ok": list(gather_result.families_ok),
                "tier1_families_ok": list(gather_result.tier1_families_ok),
                "item_count": len(gather_result.items),
            },
        }
        if not gather_result.proceed:
            raise WorkerStageError(
                "gather",
                f"insufficient corroboration: families_ok={list(gather_result.families_ok)!r}, "
                f"tier1_families_ok={list(gather_result.tier1_families_ok)!r}; need >= "
                f"{config.GATHER_MIN_FAMILIES} families including >= 1 tier-1",
            )
        # gather_all already persisted every item via db.save_evidence.
        evidence = list(gather_result.items)

        await db.update_job_state(
            job.id, "ranking", stage_progress=progress, lease_until=_lease(),
        )
        kept, timing = await _timed("rank", config.TIMEOUTS["rank"], run_rank(evidence, query_plan))
        progress = {**progress, "rank": {**timing, "kept_count": len(kept)}}
        if not kept:
            raise WorkerStageError("rank", "ranking produced zero selected evidence items")
        selected_ids = [item.source_id for item in kept]
        # Persists the selected=true flag; rank()'s own `kept` items (already
        # relevance-scored and char-capped) are what feed the brief/images
        # stages below, not a re-fetch of this call's return value.
        await db.select_evidence(job.id, selected_ids, mark_selected=True)

        brief_started = time.monotonic()
        try:
            brief_result = build_brief(kept, query_plan)  # sync, no await
        except Exception as exc:  # noqa: BLE001
            raise WorkerStageError("brief", str(exc)) from exc
        progress = {
            **progress,
            "brief": {
                "ok": True,
                "elapsed_s": round(time.monotonic() - brief_started, 3),
                "tokens_before": brief_result.stats.tokens_before,
                "tokens_after": brief_result.stats.tokens_after,
                "compressed": brief_result.stats.compressed,
            },
        }
        brief = brief_result.text

        await db.update_job_state(
            job.id, "drafting", stage_progress=progress, lease_until=_lease(),
        )
        draft_obj, timing = await _timed("draft", config.TIMEOUTS["draft"], run_draft(brief, job.dials))
        progress = {**progress, "draft": timing}

        await db.update_job_state(
            job.id, "verifying", stage_progress=progress, lease_until=_lease(),
        )
        (final_draft, final_report, flags), timing = await _timed(
            "repair", _repair_loop_timeout(), run_repair_loop(brief, draft_obj, job.dials),
        )
        repaired = final_draft != draft_obj
        progress = {
            **progress,
            "verify_repair": {
                **timing,
                "final_verdict": final_report.verdict,
                "repaired": repaired,
                "flag_count": len(flags),
            },
        }
        stored = await db.save_version(
            job.id,
            DraftVersion(
                version=1, kind=("repair" if repaired else "model"), draft=final_draft,
                verify_report=final_report, created_by="model",
            ),
        )
        if flags:
            await db.create_flags(job.id, stored.id, flags)

        await db.update_job_state(
            job.id, "images", stage_progress=progress, lease_until=_lease(),
        )
        _, timing = await _timed(
            "images", config.TIMEOUTS["images"], gather_images(job.id, query_plan, kept),
        )
        progress = {**progress, "images": timing}
        # gather_images already persisted via db.save_images.

        await db.update_job_state(
            job.id, "ready", stage_progress=progress, lease_until=None, error=None,
        )

    except WorkerStageError as exc:
        progress = {**progress, exc.stage: {"ok": False, "error": str(exc)[:500]}}
        await _fail(job, exc.stage, exc, progress)
    except Exception as exc:  # noqa: BLE001 — never silently swallow a stage failure
        progress = {**progress, "unknown": {"ok": False, "error": str(exc)[:500]}}
        await _fail(job, "unknown", exc, progress)


# ── Celery task entry (production) ───────────────────────────────────────────
# Reuses the app's existing Celery app/broker if importable, so draftsmith
# rides the same worker infra as every other pillar (see CLAUDE.md's queue
# table). The app object in backend/celery_app.py is named `app`, not
# `celery_app` — imported under an alias here so this module's own public
# name stays `run_job_task` regardless. Guarded: an environment without
# backend.celery_app configured (e.g. a unit-test sandbox) still imports this
# module cleanly.
#
# OPERATIONAL GAP (flagged, not fixed here — celery_app.py is out of scope
# for this file): celery_app.py's `Celery(..., include=[...])` list does NOT
# contain "backend.draftsmith.worker", and no queue table in CLAUDE.md/start.sh
# lists a "draftsmith" consumer. Decorating this task with @_celery_app.task
# registers it in-process (fine for the API process that imports this module
# directly), but a SEPARATE `celery -A backend.celery_app worker` process will
# never load this module — and so never execute the task — until:
#   1. "backend.draftsmith.worker" is added to celery_app.py's include=[...], and
#   2. a worker-draftsmith consumer process is added to start.sh (or an
#      existing low-traffic queue's worker adds -Q ...,draftsmith).
# Until both land, prefer the standalone poll loop below for a working deploy.
try:
    from backend.celery_app import app as _celery_app  # type: ignore[import-not-found]
except Exception:  # noqa: BLE001 — any import-time failure just disables the Celery path
    _celery_app = None

run_job_task: Any = None
if _celery_app is not None:

    @_celery_app.task(
        name="draftsmith.run_job",
        bind=True,
        soft_time_limit=config.SOFT_TIME_LIMIT,
    )
    def _run_job_task(self: Any, job_id: str) -> None:  # noqa: ANN001 - Celery bound-task signature
        asyncio.run(run_job(job_id))

    run_job_task = _run_job_task
    # Deploy note: launch a consumer for this queue with
    #   celery -A backend.celery_app worker -Q draftsmith --concurrency={config.CONCURRENCY}
    # CONCURRENCY is RAM-bound (max 2) — see config.py's comment on the box budget.
    # Callers MUST dispatch with an explicit queue (see api/routes_jobs.py's
    # _dispatch: `.apply_async(args=[job_id], queue="draftsmith")`) — a bare
    # `queue=` kwarg on @app.task is not reliably honoured as a routing
    # default without a matching task_routes entry, so don't rely on `.delay()`.


# ── Standalone poll-loop entry (dev / no-Celery deploy) ──────────────────────

async def _poll_loop() -> None:
    logger.info(
        "draftsmith worker: standalone poll loop starting "
        "(interval=%.0fs, concurrency=%d)",
        _POLL_INTERVAL_SECONDS, config.CONCURRENCY,
    )
    while True:
        try:
            job = await db.claim_next_job()
            if job is not None:
                await run_job(job.id)
                continue  # look for more work immediately, no need to sleep
        except Exception:  # noqa: BLE001 — the poll loop must never die
            logger.exception("draftsmith poll loop: unexpected error claiming/running a job")
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(_poll_loop())
