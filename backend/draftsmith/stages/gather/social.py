"""backend.draftsmith.stages.gather.social — Stage 2 (social slice): on-demand
keyword search across Reddit / TikTok / YouTube / Twitter / Telegram /
Instagram / WeChat.

    items = await gather_social(plan)

Calls the real `backend.collectors.cheap_stack.keyword_search` collectors —
never re-implements platform plumbing. Only platforms whose plan query list
is non-empty are called at all. Each platform runs in its own
try/except + timeout (config.TIMEOUTS['gather_source']) so one dead cookie,
blocked IP, or upstream hiccup never aborts the others; an honest
KeywordSearchResult(ok=False) is logged and skipped, never raised.

Note: the YouTube branch here is the cheap_stack on-demand `search_youtube`
(innertube keyword search) — a distinct thing from the warehouse
`analytics.youtube_clips_v2` adapter that lives elsewhere in the gather
stage. Both may legitimately produce `source_type == 'youtube_clip'`
evidence for the same job; their source_ids never collide because one is
keyed off a YouTube video id and the other off a warehouse clip id.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Coroutine, Optional, Sequence

from backend.collectors.cheap_stack.keyword_search import (
    KeywordSearchResult,
    search_instagram,
    search_reddit,
    search_telegram,
    search_tiktok,
    search_twitter,
    search_wechat,
    search_youtube,
)
from backend.draftsmith import config
from backend.draftsmith.models import EvidenceItem, QueryPlan, SourceType
from backend.draftsmith.stages.gather._shared import clip_text, make_source_id, parse_iso_datetime

logger = logging.getLogger(__name__)

# plan.queries field name -> (search fn, EvidenceItem.source_type, FETCH_CAPS key)
# tiktok/telegram/instagram/wechat deliberately share config.SOURCE_ID_PREFIX's
# 's' family — see _make_id below for how they stay disambiguated.
_PLATFORMS: dict[str, tuple[Callable[..., Coroutine[Any, Any, KeywordSearchResult]], SourceType, str]] = {
    "reddit": (search_reddit, "reddit", "reddit"),
    "tiktok": (search_tiktok, "tiktok", "tiktok"),
    "youtube": (search_youtube, "youtube_clip", "youtube_clip"),
    "twitter": (search_twitter, "twitter", "twitter"),
    "telegram": (search_telegram, "telegram", "telegram"),
    "instagram": (search_instagram, "instagram", "instagram"),
    "wechat": (search_wechat, "wechat", "wechat"),
}


async def gather_social(plan: QueryPlan) -> list[EvidenceItem]:
    """Stage 2 (social slice): keyword-search every platform the planner
    asked for, normalised to EvidenceItem. Platforms with an empty query
    list in the plan are skipped entirely (never called with a blank
    query)."""
    if plan is None:
        raise ValueError("gather_social: plan is required")

    queries_by_platform = _platform_queries(plan)
    runs = [
        _gather_platform(platform, queries)
        for platform, queries in queries_by_platform.items()
        if queries
    ]
    if not runs:
        return []

    per_platform = await asyncio.gather(*runs)

    seen_ids: set[str] = set()
    items: list[EvidenceItem] = []
    for platform_items in per_platform:
        for item in platform_items:
            if item.source_id in seen_ids:
                continue
            seen_ids.add(item.source_id)
            items.append(item)
    return items


def _platform_queries(plan: QueryPlan) -> dict[str, Sequence[str]]:
    q = plan.queries
    return {
        "reddit": q.reddit,
        "tiktok": q.tiktok,
        "youtube": q.youtube,
        "twitter": q.twitter,
        "telegram": q.telegram,
        "instagram": q.instagram,
        "wechat": q.wechat,
    }


async def _gather_platform(platform: str, queries: Sequence[str]) -> list[EvidenceItem]:
    fn, source_type, cap_key = _PLATFORMS[platform]
    cap = config.FETCH_CAPS[cap_key]
    timeout = config.TIMEOUTS["gather_source"]

    items: list[EvidenceItem] = []
    for query in queries:
        try:
            result = await asyncio.wait_for(fn(query, limit=cap), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(
                "gather_social: %s timed out after %ss (query=%r)",
                platform, timeout, query,
            )
            continue
        except Exception:
            logger.exception(
                "gather_social: %s raised for query=%r", platform, query,
            )
            continue

        if not result.ok:
            logger.info(
                "gather_social: %s ok=False for query=%r: %s",
                platform, query, result.error,
            )
            continue

        for post in result.posts:
            item = _post_to_evidence(platform, source_type, post, query)
            if item is not None:
                items.append(item)

    return items[:cap]


def _tier_for(platform: str, source_type: SourceType, post: dict[str, Any]) -> int:
    if platform == "twitter":
        verified = bool(post.get("verified") or post.get("author_verified"))
        return 2 if verified else 3
    return int(config.BASE_TRUST_TIER.get(source_type, 3))


def _make_id(platform: str, source_type: SourceType, post: dict[str, Any]) -> str:
    prefix = config.SOURCE_ID_PREFIX[source_type]
    post_id = str(post.get("platform_post_id") or "").strip()
    raw = post_id or (post.get("post_url") or "") or (post.get("post_text") or "")
    # tiktok/telegram/instagram/wechat share the 's' prefix family — fold the
    # platform name into the hashed input so their ids never collide.
    if source_type in ("tiktok", "telegram", "instagram", "wechat"):
        raw = f"{platform}:{raw}"
    return make_source_id(prefix, raw)


def _post_to_evidence(
    platform: str, source_type: SourceType, post: dict[str, Any], query: str,
) -> Optional[EvidenceItem]:
    text = (post.get("post_text") or "").strip()
    if platform == "wechat":
        # the full article body is WeChat's differentiator; prefer it over
        # the short title+snippet caption when present.
        content = (post.get("content") or "").strip()
        if content:
            text = content
    if not text:
        return None  # nothing citable — never emit an empty snapshot

    try:
        source_id = _make_id(platform, source_type, post)
    except ValueError:
        logger.warning(
            "gather_social: %s post has no stable id to hash (query=%r), skipping",
            platform, query,
        )
        return None

    author = post.get("author_username") or post.get("account") or None
    published_at = parse_iso_datetime(post.get("posted_at"))

    extra: dict[str, Any] = {
        "platform": platform,
        "matched_keyword": post.get("matched_keyword") or query,
        "upvotes": post.get("upvotes"),
        "comment_count": post.get("comment_count"),
        "views": post.get("views"),
    }
    if platform == "twitter":
        extra["verified"] = bool(post.get("verified") or post.get("author_verified"))
    if platform == "telegram":
        extra["channel"] = post.get("channel")
    if platform == "wechat":
        extra["account"] = post.get("account")

    return EvidenceItem(
        source_id=source_id,
        source_type=source_type,
        trust_tier=_tier_for(platform, source_type, post),  # type: ignore[arg-type]
        text=clip_text(text),
        title=post.get("title") or None,
        url=post.get("post_url") or None,
        outlet=platform,
        author=author,
        published_at=published_at,
        relevance=0.0,
        extra=extra,
    )
