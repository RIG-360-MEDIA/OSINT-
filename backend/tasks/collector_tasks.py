"""
Collector and maintenance Celery tasks.

Moved from backend/tasks.py (P03/P04 flat module) into the tasks package.
"""
from __future__ import annotations

import asyncio
import logging

from backend.celery_app import app
from backend.collectors.direct_rss_collector import DirectRSSCollector
from backend.collectors.html_collector import HTMLCollector
from backend.collectors.rss_collector import RSSCollector
from backend.nlp.groq_client import groq_manager

logger = logging.getLogger(__name__)


@app.task(name="tasks.collect_rss", bind=True, max_retries=3)
def collect_rss(self):  # type: ignore[no-untyped-def]
    """Collect articles from all active RSS sources via FreshRSS GReader API."""
    try:
        collector = RSSCollector()
        result = asyncio.run(collector.collect())
        logger.info(
            "RSS collection complete: %d articles inserted",
            result["articles_inserted"],
        )
        return result
    except Exception as exc:
        logger.error("RSS collection failed: %s", exc)
        raise self.retry(exc=exc, countdown=60)


@app.task(name="tasks.collect_rss_direct", bind=True, max_retries=2)
def collect_rss_direct(self):  # type: ignore[no-untyped-def]
    """Direct-fetch RSS feeds that FreshRSS refuses to subscribe.

    Targets DB sources whose rss_url is not present in FreshRSS subscriptions
    and pulls them with browser-grade headers + TieredFetcher body extraction.
    Runs every 30 minutes; auto-disables sources after 10 consecutive failures.
    """
    try:
        collector = DirectRSSCollector()
        result = asyncio.run(collector.collect())
        logger.info(
            "DirectRSS complete: %d articles inserted from %d/%d feeds",
            result["articles_inserted"],
            result["feeds_succeeded"],
            result["feeds_targeted"],
        )
        return result
    except Exception as exc:
        logger.error("DirectRSS collection failed: %s", exc)
        raise self.retry(exc=exc, countdown=120)


@app.task(name="tasks.collect_html", bind=True, max_retries=2)
def collect_html(self):  # type: ignore[no-untyped-def]
    """Collect articles from scrape-type sources. Runs every 6 hours."""
    try:
        collector = HTMLCollector()
        result = asyncio.run(collector.collect_all())
        logger.info(
            "HTML collection complete: %d articles inserted",
            result["articles_inserted"],
        )
        return result
    except Exception as exc:
        logger.error("HTML collection failed: %s", exc)
        raise self.retry(exc=exc, countdown=300)


@app.task(name="tasks.reset_groq_keys")
def reset_groq_keys() -> dict:  # type: ignore[no-untyped-def]
    """Reset exhausted Groq API keys. Runs daily at 00:05 UTC via Celery Beat."""
    groq_manager.reset_exhausted()
    status = groq_manager.status
    logger.info("Groq key pool reset complete: %s", status)
    return status


@app.task(name="tasks.generate_all_briefs", bind=True)
def generate_all_briefs(self):  # type: ignore[no-untyped-def]
    """Daily brief generation — implemented in P10."""
    logger.debug("generate_all_briefs called (not yet implemented)")
    return {"status": "not_implemented", "prompt": "P10"}
