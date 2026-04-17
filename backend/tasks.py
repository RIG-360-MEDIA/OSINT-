"""
Celery task definitions.

P03: collector tasks only.
NLP tasks added in P06.
Brief tasks added in P10.
"""
from __future__ import annotations

import asyncio
import logging

from backend.celery_app import app
from backend.collectors.html_collector import HTMLCollector
from backend.collectors.rss_collector import RSSCollector

logger = logging.getLogger(__name__)


@app.task(name="tasks.collect_rss", bind=True, max_retries=3)
def collect_rss(self):  # type: ignore[no-untyped-def]
    """
    Collect articles from all active RSS sources via FreshRSS GReader API.
    Runs every 15 minutes.
    """
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


@app.task(name="tasks.collect_html", bind=True, max_retries=2)
def collect_html(self):  # type: ignore[no-untyped-def]
    """
    Collect articles from scrape-type sources. Runs every 6 hours.
    """
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


# ---------------------------------------------------------------------------
# Placeholder tasks — implemented in later prompts
# ---------------------------------------------------------------------------

@app.task(name="tasks.process_nlp_batch", bind=True)
def process_nlp_batch(self):  # type: ignore[no-untyped-def]
    """NLP entity extraction batch — implemented in P06."""
    logger.debug("process_nlp_batch called (not yet implemented)")
    return {"status": "not_implemented", "prompt": "P06"}


@app.task(name="tasks.score_relevance_batch", bind=True)
def score_relevance_batch(self):  # type: ignore[no-untyped-def]
    """Relevance scoring batch — implemented in a later prompt."""
    logger.debug("score_relevance_batch called (not yet implemented)")
    return {"status": "not_implemented"}


@app.task(name="tasks.generate_all_briefs", bind=True)
def generate_all_briefs(self):  # type: ignore[no-untyped-def]
    """Daily brief generation — implemented in P10."""
    logger.debug("generate_all_briefs called (not yet implemented)")
    return {"status": "not_implemented", "prompt": "P10"}
