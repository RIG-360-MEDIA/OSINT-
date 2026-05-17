"""
Tiered article text fetcher with four-tier fallback strategy.

Tier 1 — Trafilatura (fast, precision mode, normal sites)
Tier 2 — Googlebot User-Agent spoof (soft-paywall sites)
Tier 3 — Crawl4AI headless Chromium (JS-rendered sites, think tanks)
Tier 4 — Archive.ph (hard-paywall sites that have been archived)

Usage:
    async with TieredFetcher() as fetcher:
        text, tier_used = await fetcher.fetch(url, domain, rss_summary)

tier_used values:
    0  — RSS summary used as last resort
    1  — Trafilatura succeeded
    2  — Googlebot spoof succeeded
    3  — Crawl4AI succeeded
    4  — Archive.ph succeeded
    -1 — all tiers failed, no text recovered
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx
import trafilatura

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Domain classification lists
# ---------------------------------------------------------------------------

# Soft-paywall sites: show full content to Googlebot for indexing compliance
SOFT_PAYWALL_DOMAINS: list[str] = [
    "thehindu.com",
    "thehindubusinessline.com",
    "livemint.com",
    "hindustantimes.com",
    "ndtv.com",
]

# JS-rendered sites: require a real browser to render content
JS_RENDERED_DOMAINS: list[str] = [
    "tv9telugu.com",
    "ntvtelugu.com",
    "telanganatoday.com",
    "siasat.com",
    "gadgets360.com",
    "espncricinfo.com",
    "zeenews.india.com",
    "ndtvprofit.com",
    "inc42.com",
    "firstpost.com",
    "sportskeeda.com",
    "bhaskar.com",
    "prabhatkhabar.com",
    "prajavani.net",
    "aspistrategist.org.au",
    "warontherocks.com",
    "idsa.in",
    "stimson.org",
    "fpri.org",
    "mwi.westpoint.edu",
    "smallwarsjournal.com",
    "pacforum.org",
]

# Hard-paywall sites: no programmatic bypass — try archive.ph only
HARD_PAYWALL_DOMAINS: list[str] = [
    "bloomberg.com",
    "straitstimes.com",
    "japantimes.co.jp",
    "independent.co.uk",
    "forbesindia.com",
    "moneycontrol.com",
    "worldpoliticsreview.com",
    "ft.com",
    "wsj.com",
    "economist.com",
]

# ---------------------------------------------------------------------------
# Headers
# ---------------------------------------------------------------------------

GOOGLEBOT_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; "
        "Googlebot/2.1; "
        "+http://www.google.com/bot.html)"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

BROWSER_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; "
        "Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}

MIN_TEXT_LENGTH = 100
LEAD_TEXT_MAX_CHARS = 2000


# ---------------------------------------------------------------------------
# TieredFetcher
# ---------------------------------------------------------------------------


class TieredFetcher:
    """
    Fetches article full text using a 4-tier fallback strategy.

    Must be used as an async context manager so the shared Crawl4AI browser
    instance is properly initialised and torn down:

        async with TieredFetcher() as fetcher:
            text, tier = await fetcher.fetch(url, domain, rss_summary)
    """

    def __init__(self) -> None:
        self._crawler: object | None = None
        self._crawl4ai_available: bool = False

    async def __aenter__(self) -> "TieredFetcher":
        try:
            from crawl4ai import AsyncWebCrawler, BrowserConfig  # type: ignore[import]

            browser_config = BrowserConfig(
                headless=True,
                verbose=False,
                browser_type="chromium",
            )
            # 0.4.248 defaults chrome_channel="chromium" which is the correct Playwright
            # channel for the bundled Chromium. Explicitly clear it so _build_browser_args
            # omits the channel arg entirely — works across 0.4.x versions regardless of
            # whether the default is "chrome" (0.4.21) or "chromium" (0.4.248+).
            browser_config.chrome_channel = ""
            self._crawler = AsyncWebCrawler(config=browser_config)
            await self._crawler.__aenter__()  # type: ignore[union-attr]
            self._crawl4ai_available = True
            logger.info("TieredFetcher: Crawl4AI browser ready")
        except Exception as exc:
            logger.warning(
                "TieredFetcher: Crawl4AI unavailable (%s). Tier 3 will be skipped.", exc
            )
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._crawler is not None:
            try:
                await self._crawler.__aexit__(*args)  # type: ignore[union-attr]
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _detect_tier(self, domain: str) -> str:
        """
        Returns the recommended starting tier for a domain.

        'js'     → skip to Crawl4AI (JS-rendered)
        'soft'   → try Trafilatura first, then Googlebot
        'hard'   → try archive.ph only
        'normal' → try Trafilatura, fall back to Crawl4AI
        """
        domain_lower = domain.lower()
        for d in JS_RENDERED_DOMAINS:
            if d in domain_lower:
                return "js"
        for d in SOFT_PAYWALL_DOMAINS:
            if d in domain_lower:
                return "soft"
        for d in HARD_PAYWALL_DOMAINS:
            if d in domain_lower:
                return "hard"
        return "normal"

    async def fetch(
        self,
        url: str,
        domain: str,
        rss_summary: str | None = None,
    ) -> tuple[str | None, int]:
        """
        Fetch article text using tiered fallback.

        Returns (text, tier_used). See module docstring for tier values.
        """
        domain_type = self._detect_tier(domain)

        if domain_type == "hard":
            text = await self._tier4_archive(url)
            if text and len(text) >= MIN_TEXT_LENGTH:
                return text[:LEAD_TEXT_MAX_CHARS], 4
            if rss_summary and len(rss_summary) > 50:
                return rss_summary[:LEAD_TEXT_MAX_CHARS], 0
            return None, -1

        # Try Tier 1 (trafilatura) first for ALL non-hard domains, including
        # JS-rendered ones. Empirical audit (2026-05-10) showed trafilatura
        # cleanly extracts content from 12/15 previously-broken JS-tagged
        # sources. Falling through to Tier 3 only when trafilatura returns
        # nothing keeps the JS escape hatch for genuine SPA cases.
        text = await self._tier1_trafilatura(url)
        if text and len(text) >= MIN_TEXT_LENGTH:
            return text[:LEAD_TEXT_MAX_CHARS], 1

        if domain_type == "js":
            text = await self._tier3_crawl4ai(url)
            if text and len(text) >= MIN_TEXT_LENGTH:
                return text[:LEAD_TEXT_MAX_CHARS], 3
            if rss_summary and len(rss_summary) > 50:
                return rss_summary[:LEAD_TEXT_MAX_CHARS], 0
            return None, -1

        # Tier 2 — Googlebot spoof (soft-paywall sites only)
        if domain_type == "soft":
            text = await self._tier2_googlebot(url)
            if text and len(text) >= MIN_TEXT_LENGTH:
                return text[:LEAD_TEXT_MAX_CHARS], 2

        # Tier 3 — Crawl4AI (only if browser initialised successfully)
        if self._crawl4ai_available:
            text = await self._tier3_crawl4ai(url)
            if text and len(text) >= MIN_TEXT_LENGTH:
                return text[:LEAD_TEXT_MAX_CHARS], 3

        # Tier 4 — Archive.ph
        text = await self._tier4_archive(url)
        if text and len(text) >= MIN_TEXT_LENGTH:
            return text[:LEAD_TEXT_MAX_CHARS], 4

        # Last resort: RSS summary
        if rss_summary and len(rss_summary) > 50:
            return rss_summary[:LEAD_TEXT_MAX_CHARS], 0

        return None, -1

    # ------------------------------------------------------------------
    # Tier implementations
    # ------------------------------------------------------------------

    async def _tier1_trafilatura(self, url: str) -> str | None:
        """Tier 1: plain httpx GET + Trafilatura precision extraction."""
        try:
            async with httpx.AsyncClient(
                timeout=30,
                headers=BROWSER_HEADERS,
                follow_redirects=True,
            ) as client:
                response = await client.get(url)
                if response.status_code != 200:
                    return None
                return trafilatura.extract(
                    response.text,
                    favor_precision=True,
                    include_tables=False,
                    include_comments=False,
                    include_links=False,
                    no_fallback=True,
                )
        except Exception as exc:
            logger.debug("Tier 1 failed for %s: %s", url, exc)
            return None

    async def _tier2_googlebot(self, url: str) -> str | None:
        """
        Tier 2: Googlebot User-Agent spoof.

        Soft-paywall sites (The Hindu, Livemint) serve full content to
        Googlebot to comply with Google's crawler-access indexing policy,
        but gate content behind a paywall for regular browser UAs.
        """
        try:
            async with httpx.AsyncClient(
                timeout=30,
                headers=GOOGLEBOT_HEADERS,
                follow_redirects=True,
            ) as client:
                response = await client.get(url)
                if response.status_code != 200:
                    return None
                return trafilatura.extract(
                    response.text,
                    favor_precision=True,
                    include_tables=False,
                    include_comments=False,
                    include_links=False,
                    no_fallback=True,
                )
        except Exception as exc:
            logger.debug("Tier 2 failed for %s: %s", url, exc)
            return None

    async def _tier3_crawl4ai(self, url: str) -> str | None:
        """
        Tier 3: Crawl4AI headless Chromium.

        Renders JavaScript before extracting content. Uses the shared
        browser instance — do NOT create a new browser per call.
        """
        if not self._crawl4ai_available or self._crawler is None:
            return None
        try:
            from crawl4ai import CrawlerRunConfig  # type: ignore[import]
            from crawl4ai.content_filter_strategy import (  # type: ignore[import]
                PruningContentFilter,
            )
            from crawl4ai.markdown_generation_strategy import (  # type: ignore[import]
                DefaultMarkdownGenerator,
            )

            run_config = CrawlerRunConfig(
                markdown_generator=DefaultMarkdownGenerator(
                    content_filter=PruningContentFilter(
                        threshold=0.48,
                        threshold_type="fixed",
                    )
                ),
                wait_until="networkidle",
                page_timeout=30000,
                verbose=False,
            )
            result = await self._crawler.arun(url=url, config=run_config)  # type: ignore[union-attr]

            if result.success and result.markdown:
                md = result.markdown
                # fit_markdown is the filtered/pruned version (preferred)
                if hasattr(md, "fit_markdown") and md.fit_markdown:
                    return md.fit_markdown
                if hasattr(md, "raw_markdown") and md.raw_markdown:
                    return md.raw_markdown
                # Fallback: markdown may be a plain string in some versions
                text = str(md)
                return text if text else None
            return None
        except Exception as exc:
            logger.debug("Tier 3 failed for %s: %s", url, exc)
            return None

    async def _tier4_archive(self, url: str) -> str | None:
        """
        Tier 4: Archive.ph fallback.

        Fetches the most recent archived snapshot of a URL.
        Used for hard-paywall articles that have been publicly archived.
        """
        try:
            archive_url = f"https://archive.ph/newest/{url}"
            async with httpx.AsyncClient(
                timeout=20,
                headers=BROWSER_HEADERS,
                follow_redirects=True,
            ) as client:
                response = await client.get(archive_url)
                if response.status_code != 200:
                    return None
                return trafilatura.extract(
                    response.text,
                    favor_precision=True,
                    include_tables=False,
                    include_comments=False,
                    include_links=False,
                    no_fallback=True,
                )
        except Exception as exc:
            logger.debug("Tier 4 failed for %s: %s", url, exc)
            return None
