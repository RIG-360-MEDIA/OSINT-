"""
tasks.refresh_coverage_summaries

Daily Celery beat task that regenerates the 2-3 line summary shown beneath
each panel on the /coverage hub. Pulls the last ~30 items from each
pillar's source table, hands the title list to llama-3.1-8b-instant, and
upserts the result into ``coverage_panel_summaries``.

Beat-fired at 04:15 UTC (slots between brief generation at 00:30/01:00 and
the newspaper run at 04:30). One task per fire; iterates the five slugs
sequentially. Each Groq call is small and cheap (FAST_MODEL, ~150 tokens
out), so the whole job completes in well under 30 seconds even on warm
keys.

Failure mode: if Groq is exhausted or any single slug fails, that slug's
existing summary row is left untouched — the page never goes blank
because the seed rows from migration 038 remain in place.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Final

from sqlalchemy import text

from backend.celery_app import app
from backend.database import get_db
from backend.nlp.groq_client import FAST_MODEL, GroqQuotaExhausted, call_groq

logger = logging.getLogger(__name__)


# ── Per-slug ingest config ─────────────────────────────────────────────────
# Each slug pulls ~30 most-recent titles. The title columns differ per
# table; this map is the single source of truth.

_SLUG_CONFIG: Final[dict[str, dict[str, str]]] = {
    "articles": {
        "table":     "articles",
        "title_col": "title",
        "where":     "is_duplicate IS NOT TRUE",
        "label":     "Articles (RSS + scraped news)",
    },
    "newspaper": {
        "table":     "newspaper_clippings",
        "title_col": "headline",
        "where":     "headline IS NOT NULL",
        "label":     "Newspaper clippings (print + e-paper editions)",
    },
    "tv": {
        "table":     "youtube_clips",
        "title_col": "video_title",
        "where":     "TRUE",
        "label":     "TV / video clips (YouTube + broadcasts)",
    },
    "social": {
        "table":     "social_posts",
        "title_col": "LEFT(post_text, 180)",
        "where":     "TRUE",
        "label":     "Social signals (Reddit + Telegram)",
    },
    "govt": {
        "table":     "govt_documents",
        "title_col": "title",
        "where":     "TRUE",
        "label":     "Government documents (orders + circulars + gazettes)",
    },
}

_SAMPLE_SIZE: Final[int] = 30
_TIME_WINDOW_HOURS: Final[int] = 24


_SYSTEM_PROMPT: Final[str] = (
    "You are an editorial copywriter for an intelligence platform. "
    "You write the short flap-copy that sits under each section header on "
    "a coverage hub page — two or three sentences, declarative, "
    "newsroom-style. No marketing language. No first person. No 'we'. "
    "No bullet points. No quotes. No emoji. "
    "Describe what the section IS as a stream and what's currently active "
    "in it, drawing on the recent items provided. Be specific where you "
    "can — name a topic, a region, an entity — but stay concise."
)


def _build_user_prompt(label: str, titles: list[str]) -> str:
    if not titles:
        bullet_block = "(no items in the last 24 hours)"
    else:
        bullet_block = "\n".join(f"- {t}" for t in titles[:_SAMPLE_SIZE])
    return (
        f"Section: {label}\n\n"
        f"Recent items in this stream:\n{bullet_block}\n\n"
        "Write a 2–3 sentence editorial summary describing what this "
        "section is and what is currently active in it. Maximum 60 "
        "words. Plain prose only — no list formatting."
    )


async def _fetch_recent_titles(slug: str) -> list[str]:
    """Pull the last `_SAMPLE_SIZE` non-null titles from a pillar table."""
    cfg = _SLUG_CONFIG[slug]
    q = text(f"""
        SELECT {cfg['title_col']} AS title
        FROM {cfg['table']}
        WHERE {cfg['where']}
          AND collected_at > NOW() - INTERVAL '{_TIME_WINDOW_HOURS} hours'
        ORDER BY collected_at DESC
        LIMIT :limit
    """)
    async with get_db() as db:
        result = await db.execute(q, {"limit": _SAMPLE_SIZE})
        rows = result.fetchall()
    return [r.title for r in rows if r.title]


async def _generate_summary(slug: str, titles: list[str]) -> str | None:
    """Run one Groq call. Returns None if quota exhausted or empty."""
    cfg = _SLUG_CONFIG[slug]
    user_prompt = _build_user_prompt(cfg["label"], titles)
    try:
        text_out = await call_groq(
            system=_SYSTEM_PROMPT,
            user=user_prompt,
            model=FAST_MODEL,
            task_type="classification",  # cheap path through the router
            max_tokens=180,
            temperature=0.4,
        )
    except GroqQuotaExhausted:
        logger.warning("Groq quota exhausted refreshing %s summary", slug)
        return None
    except Exception as exc:  # noqa: BLE001 — network/etc, never crash the task
        logger.warning("Groq call failed for %s: %s", slug, exc)
        return None

    cleaned = (text_out or "").strip()
    # Cap defensively — any rogue LLM expansion gets clipped here.
    if len(cleaned) > 480:
        cleaned = cleaned[:480].rsplit(" ", 1)[0] + "…"
    return cleaned or None


async def _upsert_summary(slug: str, summary: str, sample_size: int) -> None:
    """Write the new summary to coverage_panel_summaries (UPSERT)."""
    async with get_db() as db:
        await db.execute(
            text("""
                INSERT INTO coverage_panel_summaries (
                    slug, summary, generated_at,
                    generated_by_model, source_sample_size
                )
                VALUES (
                    :slug, :summary, NOW(),
                    :model, :sample_size
                )
                ON CONFLICT (slug) DO UPDATE SET
                    summary             = EXCLUDED.summary,
                    generated_at        = EXCLUDED.generated_at,
                    generated_by_model  = EXCLUDED.generated_by_model,
                    source_sample_size  = EXCLUDED.source_sample_size
            """),
            {
                "slug":         slug,
                "summary":      summary,
                "model":        FAST_MODEL,
                "sample_size":  sample_size,
            },
        )
        await db.commit()


async def _refresh_all() -> dict[str, str]:
    """Refresh all five slugs sequentially. Returns per-slug status."""
    results: dict[str, str] = {}
    for slug in _SLUG_CONFIG:
        try:
            titles = await _fetch_recent_titles(slug)
            summary = await _generate_summary(slug, titles)
            if summary is None:
                results[slug] = "skipped"
                continue
            await _upsert_summary(slug, summary, len(titles))
            results[slug] = "ok"
            logger.info(
                "Coverage summary refreshed: slug=%s sample=%d",
                slug, len(titles),
            )
        except Exception as exc:  # noqa: BLE001 — isolate slug failures
            logger.exception("Coverage summary failed for %s: %s", slug, exc)
            results[slug] = f"error: {type(exc).__name__}"
    return results


@app.task(
    name="tasks.refresh_coverage_summaries",
    bind=True,
    max_retries=0,
)
def refresh_coverage_summaries(self) -> dict:  # type: ignore[no-untyped-def]
    """
    Celery entrypoint. Beat-fired at 04:15 UTC.

    Routed to the ``nlp`` queue (LLM work, idempotent, isolated from
    collectors). Returns a per-slug status dict purely for observability
    — Beat ignores the return value.
    """
    return {"results": asyncio.run(_refresh_all())}
