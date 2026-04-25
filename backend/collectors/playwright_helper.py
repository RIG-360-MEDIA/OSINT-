"""
Playwright fetch helper for JS-rendered or bot-blocked govt portals.

Reuses the Chromium browser already installed by `crawl4ai-setup` in the
backend Docker image. Single shared browser instance per process.

Usage:
    from backend.collectors.playwright_helper import render_html

    html = await render_html(
        "https://www.sebi.gov.in/sebiweb/...",
        wait_for_selector="a.search-result",  # optional
        timeout_ms=30000,
    )
    soup = BeautifulSoup(html, "html.parser")
    # ... harvest <a href="*.pdf"> as usual
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

_browser_lock = asyncio.Lock()
_browser: Any = None  # playwright Browser; lazy-init


async def _get_browser():
    global _browser
    if _browser is not None:
        return _browser
    async with _browser_lock:
        if _browser is None:
            from playwright.async_api import async_playwright
            pw = await async_playwright().start()
            _browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
            )
            logger.info("Playwright browser launched")
        return _browser


async def render_html(
    url: str,
    *,
    wait_for_selector: str | None = None,
    timeout_ms: int = 30000,
    user_agent: str | None = None,
) -> str | None:
    """Fetch URL via headless Chromium. Returns HTML or None on failure.

    Always wrap caller in a try/except — never raises.
    """
    browser = await _get_browser()
    context = None
    try:
        context = await browser.new_context(
            user_agent=user_agent or (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()
        try:
            await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            if wait_for_selector:
                try:
                    await page.wait_for_selector(wait_for_selector, timeout=10_000)
                except Exception:
                    pass  # selector may legitimately not appear; return what we have
            html = await page.content()
            return html
        finally:
            await page.close()
    except Exception as exc:
        logger.warning("Playwright render failed for %s: %s", url, str(exc)[:120])
        return None
    finally:
        if context is not None:
            try:
                await context.close()
            except Exception:
                pass


async def shutdown() -> None:
    """Optional teardown (currently process exits without it; call only in tests)."""
    global _browser
    if _browser is not None:
        try:
            await _browser.close()
        except Exception:
            pass
        _browser = None


async def probe() -> tuple[bool, str]:
    """Smoke-test that Chromium can render a page.

    Returns ``(ok, detail)``. ``ok=False`` typically means Chromium isn't
    installed in the worker container — in which case all 9
    Playwright-strict adapters (SEBI, SCI, NGT, MCA, ADB, IMF, UN, CERC,
    PNGRB) silently return ``[]`` on every collection run. Boot calls
    this and refuses to start unless it returns ok.
    """
    try:
        html = await render_html("https://example.com", timeout_ms=10000)
    except Exception as exc:  # noqa: BLE001
        return False, f"probe raised: {exc}"
    if not html:
        return False, "probe returned empty HTML"
    if "Example Domain" not in html:
        return False, "probe HTML did not match expected fixture"
    return True, "ok"


def assert_available_sync() -> None:
    """Synchronous wrapper for use in Celery worker_init signal handlers.

    Logs a CRITICAL warning if Playwright is not usable; does NOT raise,
    because the rest of the worker still has 38 httpx-direct adapters
    that work without it. Operators should treat the warning as a
    deployment bug to fix.
    """
    import asyncio

    try:
        ok, detail = asyncio.run(probe())
    except Exception as exc:  # noqa: BLE001
        logger.critical(
            "Playwright probe could not run (%s). 9 govt adapters will "
            "silently return zero rows until Chromium is installed.",
            exc,
        )
        return
    if not ok:
        logger.critical(
            "Playwright probe failed: %s. 9 govt adapters (SEBI, SCI, "
            "NGT, MCA, ADB, IMF, UN, CERC, PNGRB) will silently return "
            "zero rows until this is fixed.",
            detail,
        )
    else:
        logger.info("Playwright probe ok — JS-rendered adapters enabled.")
