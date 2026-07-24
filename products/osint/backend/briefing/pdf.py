"""Headless-Chromium PDF renderer — the report HTML rendered by a real browser.

Screen == download == print: the same render.py HTML that serves on the site is
handed to Chromium's print pipeline, so the PDF is pixel-identical to the web
view, properly paginated (A4, page-break rules honoured from render.py's
@media print block). Far higher fidelity than WeasyPrint (full CSS grid, exact
type, embedded cutting images, Telugu shaping).

Chromium is installed via Playwright (see infrastructure/Dockerfile.osint).
"""
from __future__ import annotations

import logging

logger = logging.getLogger("briefing.pdf")


async def html_to_pdf(html: str) -> bytes:
    """Render an HTML string to a print-faithful A4 PDF via headless Chromium."""
    import re

    from playwright.async_api import async_playwright

    # Strip the on-screen paged.js loader — Chromium paginates natively here, and
    # running paged.js would double-paginate and drop the running page-footer.
    html = re.sub(r"<script>if\(!window\.__ISPDF__\).*?</script>", "", html, flags=re.S)
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = await browser.new_page()
            await page.set_content(html, wait_until="networkidle")
            pdf = await page.pdf(
                format="A4",
                print_background=True,
                prefer_css_page_size=True,
                margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
            )
            return pdf
        finally:
            await browser.close()


async def render_pdf_for(org_id: str, cover_date) -> bytes:
    from briefing.render import render_for
    html = await render_for(org_id, cover_date)
    return await html_to_pdf(html)
