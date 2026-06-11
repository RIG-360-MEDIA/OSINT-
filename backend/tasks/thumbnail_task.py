"""
backend/tasks/thumbnail_task.py
================================

Backfill og:image thumbnails for articles where the original ingest-time
extraction failed. The original RSS/HTML collector uses ``httpx.get`` for
its quick meta fetch — many news sites' anti-bot systems reject that
from data-center IPs (Hetzner / AWS / GCP), which is why post-deploy
thumbnail coverage dropped from ~57% to ~1%.

We work around that with **Playwright**: a real Chromium browser already
shipped in the backend image (``crawl4ai-setup`` in Dockerfile.backend
installs it). Real browsers defeat almost all anti-bot heuristics that
plain httpx can't.

Single periodic batch task — opens ONE browser per cycle, processes a
capped number of articles, then closes. Avoids spawning a browser per
article.

Earlier prototype used SearXNG image search; reverted because SearXNG's
default engine config returns code-icon SVGs (devicons / lucide) that
pass content-type validation but are useless as thumbnails.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Iterable
from urllib.parse import urljoin, urlparse

import httpx
import psycopg2

from backend.celery_app import app

logger = logging.getLogger(__name__)


DATABASE_URL_SYNC = os.environ.get(
    "DATABASE_URL_SYNC", "postgresql://rig:rigpassword@rig-postgres:5432/rig"
)
HTTP_TIMEOUT_S = 12
NAV_TIMEOUT_MS = 15_000
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Order matters: prefer og:image, then twitter:image, then itemprop, then any
# explicit image relation. Falls back to the first <img> in the page only as
# a last resort.
_META_SELECTORS: tuple[str, ...] = (
    "meta[property='og:image']",
    "meta[name='og:image']",
    "meta[property='og:image:secure_url']",
    "meta[property='og:image:url']",
    "meta[name='twitter:image']",
    "meta[name='twitter:image:src']",
    "meta[property='twitter:image']",
    "meta[itemprop='image']",
    "link[rel='image_src']",
)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _looks_like_image_url(url: str) -> bool:
    if not url:
        return False
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        return False
    if not p.netloc:
        return False
    return True


def _resolve_relative(base_url: str, candidate: str) -> str:
    """og:image is sometimes a relative path; resolve against article URL."""
    if not candidate:
        return ""
    if candidate.startswith("//"):
        # Protocol-relative — pick the article's scheme
        scheme = urlparse(base_url).scheme or "https"
        return f"{scheme}:{candidate}"
    if candidate.startswith(("http://", "https://")):
        return candidate
    return urljoin(base_url, candidate)


def _validate_image_head(client: httpx.Client, url: str) -> bool:
    """HEAD must return 200 and a Content-Type that starts with image/."""
    try:
        r = client.head(url, follow_redirects=True, timeout=HTTP_TIMEOUT_S)
        if r.status_code != 200:
            return False
        ct = (r.headers.get("content-type") or "").lower()
        # Reject SVG explicitly — too easy to be an icon, rarely a real photo.
        if "svg" in ct:
            return False
        return ct.startswith("image/")
    except Exception:
        return False


# ── Playwright extraction ───────────────────────────────────────────────────

async def _extract_og_image_from_url(page, url: str) -> str | None:
    """Visit one article URL with Playwright and return the og:image URL, or None."""
    try:
        await page.goto(url, timeout=NAV_TIMEOUT_MS, wait_until="domcontentloaded")
    except Exception:
        return None

    for selector in _META_SELECTORS:
        try:
            element = await page.query_selector(selector)
            if not element:
                continue
            attr = "href" if selector.startswith("link") else "content"
            value = await element.get_attribute(attr)
            if value:
                return _resolve_relative(url, value.strip())
        except Exception:
            continue

    # Last-ditch fallback: first sufficiently large <img> in the article body.
    try:
        img = await page.query_selector("article img, main img, .article-content img, .post-content img")
        if img:
            src = await img.get_attribute("src")
            if src:
                return _resolve_relative(url, src.strip())
    except Exception:
        pass

    return None


async def _extract_batch(articles: list[tuple[str, str]]) -> list[tuple[str, str | None]]:
    """
    Open one Chromium, iterate the articles, return ``(article_id, og_url_or_None)``.

    Each article gets a fresh BrowserContext (fresh cookies/storage) so a
    cookie banner from site A doesn't leak into site B's request.
    """
    from playwright.async_api import async_playwright

    out: list[tuple[str, str | None]] = []

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            try:
                for article_id, url in articles:
                    if not url:
                        out.append((article_id, None))
                        continue
                    context = None
                    try:
                        context = await browser.new_context(
                            user_agent=USER_AGENT,
                            viewport={"width": 1280, "height": 720},
                            ignore_https_errors=True,
                        )
                        # Block heavy assets to make goto faster — we only need <head>.
                        await context.route(
                            "**/*",
                            lambda route: (
                                route.abort()
                                if route.request.resource_type
                                in ("image", "media", "font", "stylesheet")
                                else route.continue_()
                            ),
                        )
                        page = await context.new_page()
                        og = await _extract_og_image_from_url(page, url)
                        out.append((article_id, og))
                    except Exception:
                        logger.info(
                            "thumbnail/playwright failed for article=%s", article_id,
                            exc_info=True,
                        )
                        out.append((article_id, None))
                    finally:
                        if context is not None:
                            try:
                                await context.close()
                            except Exception:
                                pass
            finally:
                await browser.close()
    except Exception:
        logger.exception("Playwright session crashed; aborting batch")
        # Pad missing entries with None so caller still has 1:1 alignment
        seen = {a for a, _ in out}
        for article_id, _ in articles:
            if article_id not in seen:
                out.append((article_id, None))

    return out


# ── Celery task ─────────────────────────────────────────────────────────────

@app.task(name="tasks.fetch_og_images_batch", queue="collectors")
def fetch_og_images_batch(limit: int = 30, max_age_days: int = 30) -> dict:
    """
    Periodic backfill task.

    Selects up to ``limit`` recent articles missing a thumbnail, opens a
    single Chromium session, fetches og:image for each, HEAD-validates,
    and updates the DB.

    Bounded by ``max_age_days`` so we don't endlessly retry old failures.
    """
    with psycopg2.connect(DATABASE_URL_SYNC) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id::text, url FROM articles "
            "WHERE (thumbnail_url IS NULL OR thumbnail_url = '') "
            "  AND url IS NOT NULL AND url <> '' "
            "  AND collected_at >= now() - (%s || ' days')::interval "
            "ORDER BY collected_at DESC "
            "LIMIT %s",
            (str(max_age_days), int(limit)),
        )
        articles = list(cur.fetchall())

    if not articles:
        return {"checked": 0, "filled": 0}

    results = asyncio.run(_extract_batch(articles))

    filled = 0
    with httpx.Client(
        timeout=HTTP_TIMEOUT_S,
        headers={"User-Agent": USER_AGENT},
    ) as client, psycopg2.connect(DATABASE_URL_SYNC) as conn, conn.cursor() as cur:
        for article_id, og_url in results:
            if not og_url:
                continue
            if not _looks_like_image_url(og_url):
                continue
            if not _validate_image_head(client, og_url):
                logger.info(
                    "thumbnail/head-rejected article=%s url=%s",
                    article_id, og_url[:120],
                )
                continue
            cur.execute(
                "UPDATE articles SET thumbnail_url = %s "
                "WHERE id = %s::uuid "
                "  AND (thumbnail_url IS NULL OR thumbnail_url = '')",
                (og_url, article_id),
            )
            if cur.rowcount > 0:
                filled += 1
                logger.info(
                    "thumbnail/filled article=%s url=%s",
                    article_id, og_url[:120],
                )
        conn.commit()

    return {"checked": len(articles), "filled": filled}
