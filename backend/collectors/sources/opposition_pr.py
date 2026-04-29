"""
Opposition party press-release collector for the CM Page.

Reads verified handles from `cm_political_handles` (platform IN
('press_rss','press_html')) and routes them through the existing
collector path for that platform — RSS via `tasks.collect_rss_direct`,
HTML via `tasks.collect_html`.

There is intentionally NO hard-coded handle list in this file. Every
opposition feed must be inserted into cm_political_handles with a
verified_url so a future audit can trace where each row came from.
See migration 029 + scripts/seeds/political_handles_*.sql.

Lookup helper exposed for other collectors / Celery tasks. Adding a new
verified handle is a single SQL insert; no code change needed.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import text

from backend.database import get_db

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OppositionFeed:
    state: str
    party: str
    person_name: str | None
    person_role: str | None
    platform: str
    handle: str
    url: str
    cadence_minutes: int


async def list_active_feeds(
    *,
    state: str | None = None,
    platform: str | None = None,
) -> list[OppositionFeed]:
    """Return verified, active rows from cm_political_handles, optionally
    filtered by state / platform. The collector pipelines call this — no
    in-process cache so a SQL update takes effect immediately."""
    sql = """
        SELECT state, party, person_name, person_role, platform, handle, url, cadence_minutes
        FROM cm_political_handles
        WHERE active = TRUE
          AND coalition = 'opposition'
          AND (:state::text IS NULL OR state = :state)
          AND (:platform::text IS NULL OR platform = :platform)
        ORDER BY state, party, person_role NULLS LAST
    """
    out: list[OppositionFeed] = []
    async with get_db() as db:
        try:
            rows = (
                await db.execute(text(sql), {"state": state, "platform": platform})
            ).all()
        except Exception as exc:  # noqa: BLE001
            logger.info("opposition_pr.list_active_feeds skipped: %s", exc)
            return []
    for r in rows:
        out.append(
            OppositionFeed(
                state=r.state,
                party=r.party,
                person_name=r.person_name,
                person_role=r.person_role,
                platform=r.platform,
                handle=r.handle,
                url=r.url,
                cadence_minutes=int(r.cadence_minutes or 60),
            )
        )
    return out


async def list_active_twitter_handles(state: str | None = None) -> list[str]:
    """Twitter handles only, returned as @handle strings ready for
    backend.collectors.social_collector.collect_twitter_user_tweets()."""
    feeds = await list_active_feeds(state=state, platform="twitter")
    return [f.handle if f.handle.startswith("@") else f"@{f.handle}" for f in feeds]


async def list_active_youtube_channel_ids(state: str | None = None) -> list[str]:
    """YouTube channel IDs (UC... format expected in handle column) for
    use by the existing youtube collector path."""
    feeds = await list_active_feeds(state=state, platform="youtube")
    return [f.handle for f in feeds]


async def list_active_press_rss_urls(state: str | None = None) -> list[tuple[str, str]]:
    """RSS feed URLs as (party, url). Hand to tasks.collect_rss_direct."""
    feeds = await list_active_feeds(state=state, platform="press_rss")
    return [(f.party, f.url) for f in feeds]
