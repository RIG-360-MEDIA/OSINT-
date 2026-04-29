"""
Brief Beat tasks — daily auto-generation fan-out.

Closes D-BRIEF-2 (the no-op stub) by giving the daily ``00:30 UTC`` Beat
fire something to do:

* :func:`generate_all_briefs` — Beat-fired aggregator. Iterates every
  user with ``user_page_access(page_slug='brief')`` and enqueues a
  per-user task. Errors are logged, never raised — one bad user does
  not block the cohort.
* :func:`generate_brief_for_user` — runs the per-user generation flow.
  Same code path the router uses (via :mod:`backend.nlp.brief_runner`)
  so any router fix lands here automatically.

The Beat schedule entry already exists in
:mod:`backend.celery_app` (``generate-briefs-daily``); we simply
replace the previous stub at ``backend.tasks.collector_tasks
.generate_all_briefs`` with this implementation. Celery task names are
preserved so the Beat schedule keeps working.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import text

from backend.celery_app import app
from backend.database import get_db
from backend.nlp.brief_runner import BriefError, run_for_user

logger = logging.getLogger(__name__)


async def _list_brief_users() -> list[dict[str, str]]:
    """Return ``[{user_id, email}, …]`` for every user with brief access."""
    async with get_db() as db:
        result = await db.execute(
            text(
                """
                SELECT u.id::text AS user_id, COALESCE(u.email, '') AS email
                FROM user_page_access upa
                JOIN users u ON u.id = upa.user_id
                WHERE upa.page_slug = 'brief'
                ORDER BY u.created_at NULLS LAST
                """
            )
        )
        return [
            {"user_id": r._mapping["user_id"], "email": r._mapping["email"]}
            for r in result.fetchall()
        ]


async def _run_for_user_async(user_id: str, email: str) -> dict[str, Any]:
    """Async wrapper used by the Celery sync task body."""
    async with get_db() as db:
        result = await run_for_user(db, user_id=user_id, user_email=email)
        return {
            "user_id": user_id,
            "brief_date": result.brief_date.isoformat(),
            "articles_used": result.articles_used,
            "cached": result.cached,
            "section_failures": list(result.section_failures),
        }


@app.task(name="tasks.generate_brief_for_user", bind=True, max_retries=0)
def generate_brief_for_user(self, user_id: str, email: str = "") -> dict:  # type: ignore[no-untyped-def]
    """Per-user brief generation. Routed to the ``brief`` queue."""
    try:
        return asyncio.run(_run_for_user_async(user_id, email))
    except BriefError as exc:
        logger.warning(
            "Brief skipped for user %s: %s (%d)",
            user_id, exc.detail, exc.status_code,
        )
        return {
            "user_id": user_id,
            "skipped": True,
            "status_code": exc.status_code,
            "detail": exc.detail,
        }
    except Exception as exc:  # noqa: BLE001 — never bubble up to Celery
        logger.exception(
            "Brief generation failed for user %s: %s", user_id, exc
        )
        return {"user_id": user_id, "error": str(exc)}


@app.task(name="tasks.generate_all_briefs", bind=True, max_retries=0)
def generate_all_briefs(self) -> dict:  # type: ignore[no-untyped-def]
    """Daily Beat fan-out. Replaces the legacy P10 stub.

    Iterates every user with brief page-access and enqueues a per-user
    ``generate_brief_for_user`` task on the ``brief`` queue. The
    aggregator returns immediately — no per-user work is done in this
    task body, so a single bad user cannot starve the others.
    """
    users = asyncio.run(_list_brief_users())
    if not users:
        logger.info("generate_all_briefs: no users with brief access")
        return {"users": 0, "enqueued": 0}

    enqueued = 0
    for u in users:
        try:
            generate_brief_for_user.apply_async(
                args=[u["user_id"], u["email"]],
                queue="brief",
            )
            enqueued += 1
        except Exception as exc:  # noqa: BLE001 — log + continue
            logger.exception(
                "generate_all_briefs: enqueue failed for %s: %s",
                u["user_id"], exc,
            )

    logger.info(
        "generate_all_briefs: enqueued %d/%d per-user tasks",
        enqueued, len(users),
    )
    return {"users": len(users), "enqueued": enqueued}


__all__ = ["generate_all_briefs", "generate_brief_for_user"]
