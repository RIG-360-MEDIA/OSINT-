"""
backend/collectors/telugu_scraper.py
====================================

Playwright-based scraper for Telugu newspapers that killed public RSS:
**Eenadu**, **Sakshi**, **Andhra Jyothy**.

Why this exists
---------------
RSS probe (2026-05-06) confirmed the three biggest Telugu dailies no
longer expose working feeds — they return HTTP 200 but zero ``<item>``
elements (HTML pages, not RSS). Yet these papers are where most district
political news in Telangana actually lives. Without them /brief is blind
to ~70% of state-level political reporting outside Hyderabad.

Strategy
--------
For each (paper × district) tuple:

1. Open the district edition page in headless Chromium
   (``--no-sandbox`` per existing container conventions).
2. Wait for ``domcontentloaded`` then extract article anchor URLs that
   match a per-paper URL pattern.
3. For each unique URL not already in the ``articles`` table, open it,
   extract title + lead paragraphs + published timestamp, and persist
   via ``backend.collectors.persistence`` so it joins the same NLP /
   relevance pipeline as RSS-collected articles.

We deliberately don't re-implement deduplication or NLP here. The
existing article-insert helper handles ``url`` uniqueness and queues
NLP processing.

Beat cadence
------------
Every 30 min via ``celery_app.beat_schedule['scrape-telugu-dailies-…']``.
One paper × all districts per tick is ~33 page loads × 1.5s each
(~50s wall-clock). Three papers ≈ 150s, comfortably within a 30-min
window even on a single-concurrency ``collectors`` worker.

Future work
-----------
Sakshi and Andhra Jyothy have aggressive bot detection. The Eenadu
adapter is ready; the other two are config stubs and will need cookie
warmup / fingerprint randomisation (similar to the YouTube-cookies fix
already shipped). Add when the Eenadu signal is confirmed flowing.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import urljoin, urlparse

from backend.celery_app import app

logger = logging.getLogger(__name__)


# Eenadu URL inspection (2026-05-07) — verified shapes:
#
#   /telangana                  →  88 stories, mix of /telugu-news/telangana/...
#                                  and /telugu-news/districts/...
#   /telangana/districts        →  29 stories, all /telugu-news/districts/...
#                                  with district name embedded in slug.
#
# Per-district URLs like /telangana/karimnagar return the homepage —
# they are not real routes. So we don't iterate per-district; we hit the
# two state landing pages and let the URL slug carry district info
# (e.g. "/districts/medak-three-youths-drown..." → district = medak).

# Map URL slug fragment → canonical Telangana district name.
# Built by reading Eenadu story slugs over a 2-day window.
EENADU_SLUG_TO_DISTRICT: dict[str, str] = {
    "hyderabad":  "Hyderabad",
    "ranga":      "Rangareddy",
    "medchal":    "Medchal-Malkajgiri",
    "sangareddy": "Sangareddy",
    "vikarabad":  "Vikarabad",
    "karimnagar": "Karimnagar",
    "peddapalli": "Peddapalli",
    "jagtial":    "Jagtial",
    "rajanna":    "Rajanna Sircilla",
    "sircilla":   "Rajanna Sircilla",
    "warangal":   "Warangal",
    "hanumakonda":"Hanumakonda",
    "mahabubabad":"Mahabubabad",
    "mulugu":     "Mulugu",
    "bhupalpally":"Jayashankar Bhupalpally",
    "jangaon":    "Jangaon",
    "khammam":    "Khammam",
    "kothagudem": "Bhadradri Kothagudem",
    "bhadradri":  "Bhadradri Kothagudem",
    "adilabad":   "Adilabad",
    "mancherial": "Mancherial",
    "nirmal":     "Nirmal",
    "asifabad":   "Kumram Bheem Asifabad",
    "kumram":     "Kumram Bheem Asifabad",
    "nizamabad":  "Nizamabad",
    "kamareddy":  "Kamareddy",
    "medak":      "Medak",
    "siddipet":   "Siddipet",
    "yadadri":    "Yadadri Bhuvanagiri",
    "bhongir":    "Yadadri Bhuvanagiri",
    "nalgonda":   "Nalgonda",
    "suryapet":   "Suryapet",
    "mahbubnagar":"Mahbubnagar",
    "mahabubnagar":"Mahbubnagar",
    "wanaparthy": "Wanaparthy",
    "narayanpet": "Narayanpet",
    "nagarkurnool":"Nagarkurnool",
    "gadwal":     "Jogulamba Gadwal",
    "jogulamba":  "Jogulamba Gadwal",
}


@dataclass(frozen=True)
class PaperConfig:
    """Per-paper scraping config. Selectors targeted at HTML circa 2026-05."""

    paper_id: str
    paper_name: str
    list_urls: tuple[str, ...]      # one or more index pages to scrape
    article_link_pattern: str       # regex; URLs matching are scraped
    title_selectors: tuple[str, ...]
    body_selectors: tuple[str, ...]
    date_selectors: tuple[str, ...]
    enabled: bool = True


PAPERS: tuple[PaperConfig, ...] = (
    PaperConfig(
        paper_id="eenadu",
        paper_name="Eenadu",
        list_urls=(
            "https://www.eenadu.net/telangana",
            "https://www.eenadu.net/telangana/districts",
        ),
        # Real article shape: /telugu-news/(telangana|districts)/<slug>/<sec>/<id>
        article_link_pattern=r"^https://www\.eenadu\.net/telugu-news/(?:telangana|districts)/[^/?#]+/\d+/\d+/?$",
        title_selectors=("h1.eng-heading", "h1.story-headline", "h1"),
        body_selectors=("div.fullstory", "div.story-content", "article"),
        date_selectors=("time", "span.publish-date", "div.publish-info time"),
        enabled=True,
    ),
    # Sakshi and Andhra Jyothy: stubs. They have aggressive bot detection
    # (Sakshi 405 on direct fetch; AJ 404 across all RSS paths). Wire them
    # when we have bandwidth for cookie-warmup / fingerprint randomisation.
    PaperConfig(
        paper_id="sakshi",
        paper_name="Sakshi",
        list_urls=("https://www.sakshi.com/news/telangana",),
        article_link_pattern=r"^https://www\.sakshi\.com/news/.+",
        title_selectors=("h1.title", "h1"),
        body_selectors=("div.field-name-body", "article"),
        date_selectors=("time", "span.created"),
        enabled=False,
    ),
    PaperConfig(
        paper_id="andhrajyothy",
        paper_name="Andhra Jyothy",
        list_urls=("https://www.andhrajyothy.com/telangana",),
        article_link_pattern=r"^https://www\.andhrajyothy\.com/.+",
        title_selectors=("h1", "h1.article-title"),
        body_selectors=("div.article-body", "div.story-detail"),
        date_selectors=("time", "span.date"),
        enabled=False,
    ),
)


def _district_from_url(url: str) -> str | None:
    """Look at the slug fragment to infer Telangana district. None on miss."""
    # /telugu-news/districts/<slug>/<sec>/<id>  → slug like "medak-three-youths..."
    m = re.search(r"/(?:districts|telangana)/([a-z\-]+)/", url)
    if not m:
        return None
    slug = m.group(1)
    for token in slug.split("-"):
        if token in EENADU_SLUG_TO_DISTRICT:
            return EENADU_SLUG_TO_DISTRICT[token]
    return None


# ── Scraping primitives ─────────────────────────────────────────────────────


_NAV_TIMEOUT_MS = 15_000
_SCROLL_PAUSE_MS = 400
_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


async def _extract_article_links(
    page, list_url: str, link_pattern: re.Pattern[str]
) -> list[str]:
    """Visit a district list page; return unique article URLs matching pattern."""
    try:
        await page.goto(list_url, timeout=_NAV_TIMEOUT_MS, wait_until="domcontentloaded")
    except Exception:
        logger.info("telugu/list-failed url=%s", list_url, exc_info=True)
        return []

    # Eenadu lazy-loads — small scroll triggers the rest of the cards.
    try:
        await page.evaluate("window.scrollBy(0, 1500)")
        await page.wait_for_timeout(_SCROLL_PAUSE_MS)
    except Exception:
        pass

    try:
        anchors = await page.eval_on_selector_all(
            "a[href]", "els => els.map(e => e.href)"
        )
    except Exception:
        return []

    out: list[str] = []
    seen: set[str] = set()
    for href in anchors:
        if not href or href in seen:
            continue
        if link_pattern.match(href):
            seen.add(href)
            out.append(href)

    return out


async def _extract_article(page, url: str, cfg: PaperConfig) -> dict | None:
    """Visit one article URL; return dict suitable for persistence, or None."""
    try:
        await page.goto(url, timeout=_NAV_TIMEOUT_MS, wait_until="domcontentloaded")
    except Exception:
        return None

    title = await _first_text(page, cfg.title_selectors)
    body = await _first_text(page, cfg.body_selectors, max_chars=2000)
    if not title or not body:
        return None

    published_at = await _first_attr_or_text(
        page, cfg.date_selectors, attr="datetime", fallback_text=True
    )

    return {
        "url": url,
        "title": title.strip(),
        "lead_text_original": body.strip(),
        "published_at": _parse_iso_or_none(published_at) or datetime.now(timezone.utc),
        "language": "te",  # Eenadu is Telugu — NLP pipeline auto-translates
    }


async def _first_text(page, selectors: Iterable[str], max_chars: int = 400) -> str | None:
    for sel in selectors:
        try:
            el = await page.query_selector(sel)
            if not el:
                continue
            text = (await el.inner_text()) or ""
            if text:
                return text[:max_chars]
        except Exception:
            continue
    return None


async def _first_attr_or_text(
    page, selectors: Iterable[str], attr: str, fallback_text: bool = False
) -> str | None:
    for sel in selectors:
        try:
            el = await page.query_selector(sel)
            if not el:
                continue
            v = await el.get_attribute(attr)
            if v:
                return v
            if fallback_text:
                t = await el.inner_text()
                if t:
                    return t
        except Exception:
            continue
    return None


def _parse_iso_or_none(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        # ISO 8601 with optional Z suffix
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


# ── Persistence: re-use existing article-insert helper ─────────────────────


async def _persist_article(db, paper_cfg: PaperConfig, district_slug: str, art: dict) -> bool:
    """
    Insert if URL is new. Returns True if inserted, False if duplicate.

    Source row resolution is bound to the canonical paper domain
    (eenadu.net / sakshi.com / andhrajyothy.com). NLP and relevance
    scoring fire automatically via existing pipelines.
    """
    from sqlalchemy import text

    src_row = (
        await db.execute(
            text("SELECT id FROM sources WHERE domain = :d LIMIT 1"),
            {"d": _domain_for(paper_cfg.paper_id)},
        )
    ).fetchone()
    if not src_row:
        logger.warning("telugu/persist no source row for %s", paper_cfg.paper_id)
        return False

    import hashlib
    url_hash = hashlib.md5(art["url"].encode("utf-8")).hexdigest()

    inserted = (
        await db.execute(
            text(
                """
                INSERT INTO articles (
                    source_id, url, url_hash, title,
                    lead_text_original, published_at, collected_at,
                    language_detected, geo_primary
                ) VALUES (
                    :source_id, :url, :url_hash, :title,
                    :lead, :published_at, NOW(),
                    :language, :geo
                )
                ON CONFLICT (url_hash) DO NOTHING
                RETURNING id
                """
            ),
            {
                "source_id": src_row.id,
                "url": art["url"],
                "url_hash": url_hash,
                "title": art["title"],
                "lead": art["lead_text_original"],
                "published_at": art["published_at"],
                "language": art["language"],
                "geo": art.get("geo_primary") or "Telangana",
            },
        )
    ).fetchone()
    return inserted is not None


def _domain_for(paper_id: str) -> str:
    return {
        "eenadu":       "eenadu.net",
        "sakshi":       "sakshi.com",
        "andhrajyothy": "andhrajyothy.com",
    }.get(paper_id, paper_id)


# ── Celery task ─────────────────────────────────────────────────────────────


@app.task(name="tasks.scrape_telugu_dailies", queue="collectors")
def scrape_telugu_dailies(paper_id: str | None = None, max_districts: int | None = None) -> dict:
    """Scrape one or all enabled Telugu dailies × all (or capped) districts."""
    return asyncio.run(_run(paper_id=paper_id, max_districts=max_districts))


async def _run(paper_id: str | None, max_districts: int | None) -> dict:
    """
    Per-paper:
      1. Visit each list page in `cfg.list_urls`.
      2. Collect URLs matching `cfg.article_link_pattern`.
      3. Scrape each, persist, infer district from URL slug.

    `max_districts` is honoured as a hard cap on articles per paper —
    keeps smoke tests bounded.
    """
    from playwright.async_api import async_playwright

    from backend.database import get_db

    target_papers = [
        p for p in PAPERS
        if p.enabled and (paper_id is None or p.paper_id == paper_id)
    ]
    if not target_papers:
        return {"papers": 0, "inserted": 0, "scanned": 0}

    inserted_total = 0
    scanned_total = 0

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage",
                  "--disable-blink-features=AutomationControlled"],
        )
        try:
            for cfg in target_papers:
                pat = re.compile(cfg.article_link_pattern)
                inserted_for_paper = 0

                # Aggregate URLs across all list pages, dedupe.
                seen: set[str] = set()
                urls: list[str] = []
                context = await browser.new_context(
                    user_agent=_USER_AGENT,
                    viewport={"width": 1280, "height": 900},
                    ignore_https_errors=True,
                )
                try:
                    page = await context.new_page()
                    for list_url in cfg.list_urls:
                        for u in await _extract_article_links(page, list_url, pat):
                            if u not in seen:
                                seen.add(u); urls.append(u)
                    scanned_total += len(urls)
                    if max_districts is not None:
                        urls = urls[: max_districts * 5]  # rough cap

                    async with get_db() as db:
                        for url in urls:
                            art = await _extract_article(page, url, cfg)
                            if not art:
                                continue
                            district = _district_from_url(url)
                            art["geo_primary"] = district or "Telangana"
                            if await _persist_article(db, cfg, district or "telangana", art):
                                inserted_for_paper += 1
                        await db.commit()
                except Exception:
                    logger.exception("telugu/list failed paper=%s", cfg.paper_id)
                finally:
                    await context.close()

                logger.info(
                    "telugu/done paper=%s scanned=%d inserted=%d",
                    cfg.paper_id, len(urls), inserted_for_paper,
                )
                inserted_total += inserted_for_paper
        finally:
            await browser.close()

    return {
        "papers": len(target_papers),
        "scanned": scanned_total,
        "inserted": inserted_total,
    }
