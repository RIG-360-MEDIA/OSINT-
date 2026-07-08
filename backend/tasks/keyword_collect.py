"""On-demand keyword collection — Phase 2 trigger (social queue).

When a user searches a keyword, run the cheap_stack keyword collectors across
platforms and persist the results into `social_posts` (via land.py). This is the
Meltwater/on-demand model: collect what's searched, history builds from use.

Runs on the existing `social` queue — NO new worker, NO second Beat. Fire it
fire-and-forget from an internal endpoint:

    from backend.tasks.keyword_collect import collect_keyword
    collect_keyword.delay("PLA Navy")                    # all platforms
    collect_keyword.delay("Tridel", ["tiktok", "youtube"])  # subset

The task is a thin wrapper over `run_keyword_collection()`, which is a plain sync
function so it can be called directly (tests / manual runs) without Celery.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from backend.celery_app import app
from backend.collectors.cheap_stack.land import collect_and_land

logger = logging.getLogger(__name__)

# Cookie-free platforms always work; cookie-gated ones (reddit/twitter/instagram)
# only when their creds are present in the container env (Phase-2 6b).
DEFAULT_PLATFORMS = [
    "reddit", "tiktok", "youtube", "twitter", "telegram", "instagram", "wechat",
]


def run_keyword_collection(
    keyword: str,
    platforms: Optional[list[str]] = None,
    limit: int = 25,
    client: str = "on_demand",
) -> dict[str, int]:
    """Collect `keyword` across `platforms` and land results into social_posts.
    Returns {platform: n_landed}. Plain sync — callable without Celery."""
    platforms = platforms or DEFAULT_PLATFORMS
    landed = asyncio.run(
        collect_and_land(keyword, platforms, limit=limit, client=client)
    )
    logger.info("keyword_collect kw=%r landed=%s", keyword, landed)
    return landed


@app.task(name="tasks.social.collect_keyword", queue="social")
def collect_keyword(
    keyword: str,
    platforms: Optional[list[str]] = None,
    limit: int = 25,
    client: str = "on_demand",
) -> dict[str, int]:
    """On-demand: collect a keyword across platforms and persist to social_posts."""
    return run_keyword_collection(keyword, platforms, limit, client)
