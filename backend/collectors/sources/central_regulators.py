"""
Central regulator portal scrapers (Phase 3, agent C2).

Each scraper here is registered against a URL substring via
``@register_source(...)``. ``backend.collectors.govt_collector.fetch_document_urls``
consults that registry first and dispatches to the matching adapter.

Conventions (per Phase-3 spec):
    async def scrape_<name>(
        portal_url: str,
        document_type: str,
        since_days: int = 2,
    ) -> list[dict]
returning items shaped ``{url, title, published_at: None, type: <doc_type>}``.

All scrapers:
    * cap output at 15 items per portal,
    * catch every exception, log a warning, and return ``[]`` on failure
      (NEVER raise — failures must not break the daily ingest sweep),
    * skip junk titles via the shared ``_is_junk_title`` helper,
    * reuse ``_HTTP_HEADERS`` so target portals see a real-browser UA.

Portals covered:
    * RBI Circulars              — rbi.org.in (RSS-first, HTML fallback)
    * RBI Press Releases         — rbi.org.in (RSS-first, HTML fallback)
    * SEBI Orders                — sebi.gov.in
    * CCI Orders                 — cci.gov.in
    * IRDAI Circulars            — irdai.gov.in
    * TRAI Press Releases/Orders — trai.gov.in
    * CERC Orders                — cercind.gov.in
    * PNGRB Notifications        — pngrb.gov.in
"""
from __future__ import annotations

import logging
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from backend.collectors.govt_collector import _HTTP_HEADERS, _is_junk_title
from backend.collectors.sources._dateparse import parse_listing_date
from backend.collectors.sources.registry import register_source

logger = logging.getLogger(__name__)


_PER_PORTAL_CAP = 15
_HTTP_TIMEOUT = 30


# ── Internal helpers ────────────────────────────────────────────────────────


def _absolutise(href: str, base: str) -> str:
    """Resolve a possibly relative href against the portal base URL."""
    if href.startswith(("http://", "https://")):
        return href
    return urljoin(base, href)


def _looks_like_document(href: str) -> bool:
    """True for hrefs that point at a downloadable document or detail page."""
    lower = href.lower()
    if any(lower.endswith(ext) for ext in (".pdf", ".doc", ".docx")):
        return True
    if ".pdf?" in lower or ".pdf#" in lower:
        return True
    # Many regulator portals use detail-page anchors that 302 to a PDF.
    return any(
        token in lower
        for token in (
            "/notification",
            "/circular",
            "/order",
            "/press",
            "/press-release",
            "displaynotification",
            "showrss",
            "rssitemview",
            "id=",
        )
    )


async def _fetch(client: httpx.AsyncClient, url: str) -> str | None:
    """GET ``url`` and return body text, or None on any error."""
    try:
        r = await client.get(url)
        r.raise_for_status()
        return r.text
    except Exception as exc:  # noqa: BLE001
        logger.warning("Fetch failed for %s: %s", url, exc)
        return None


def _normalise_title(raw: str | None, fallback_url: str) -> str:
    """Trim/strip a candidate title; fall back to URL basename if empty/short."""
    title = (raw or "").strip()
    if not title or len(title) < 6:
        title = fallback_url.rstrip("/").rsplit("/", 1)[-1] or fallback_url
    return title[:500]


def _collect_links(
    html: str,
    base_url: str,
    document_type: str,
    *,
    href_filter=None,
) -> tuple[list[dict], int]:
    """Parse ``html`` for anchor tags and emit candidate doc dicts.

    Returns (docs, dropped_junk).
    """
    soup = BeautifulSoup(html, "html.parser")
    docs: list[dict] = []
    dropped_junk = 0
    seen: set[str] = set()

    for link in soup.find_all("a", href=True):
        href = link.get("href", "").strip()
        if not href or href.startswith(("javascript:", "mailto:", "#")):
            continue

        if href_filter is not None:
            if not href_filter(href):
                continue
        elif not _looks_like_document(href):
            continue

        full_url = _absolutise(href, base_url)
        if full_url in seen:
            continue
        seen.add(full_url)

        title = _normalise_title(link.get_text(strip=True), full_url)
        if _is_junk_title(title, full_url):
            dropped_junk += 1
            from backend.collectors.sources.registry import record_junk_dropped
            record_junk_dropped()
            continue

        # F1 — PDF-only: drop navigation/category links that aren't actual PDFs.
        if ".pdf" not in full_url.lower():
            continue

        # Parse a date out of the surrounding row text first, then the
        # title, then the URL. RBI/SEBI/CCI etc. typically place the date
        # in a sibling <td> within the same <tr>.
        row_text = ""
        row = link.find_parent(["tr", "li", "p", "div"])
        if row is not None:
            row_text = row.get_text(" ", strip=True)
        published_at = (
            parse_listing_date(row_text)
            or parse_listing_date(title)
            or parse_listing_date(full_url)
        )

        docs.append(
            {
                "url": full_url,
                "title": title,
                "published_at": published_at,
                "type": document_type,
            }
        )

        if len(docs) >= _PER_PORTAL_CAP:
            break

    return docs, dropped_junk


def _parse_rss_items(
    xml_text: str,
    document_type: str,
    *,
    base_url: str,
) -> list[dict]:
    """Parse an RSS/Atom feed into the canonical doc-dict shape."""
    soup = BeautifulSoup(xml_text, features="xml")
    docs: list[dict] = []
    seen: set[str] = set()

    items = soup.find_all("item") or soup.find_all("entry")
    for item in items:
        link_el = item.find("link")
        if link_el is None:
            continue
        href = (link_el.get_text(strip=True) or link_el.get("href") or "").strip()
        if not href:
            continue
        full_url = _absolutise(href, base_url)
        if full_url in seen:
            continue
        seen.add(full_url)

        title_el = item.find("title")
        raw_title = title_el.get_text(strip=True) if title_el is not None else ""
        title = _normalise_title(raw_title, full_url)
        if _is_junk_title(title, full_url):
            continue

        # F1 — PDF-only: RBI RSS items are detail pages; only direct PDFs survive.
        if ".pdf" not in full_url.lower():
            continue

        docs.append(
            {
                "url": full_url,
                "title": title,
                "published_at": (
                    parse_listing_date(title) or parse_listing_date(full_url)
                ),
                "type": document_type,
            }
        )
        if len(docs) >= _PER_PORTAL_CAP:
            break

    return docs


# ── RBI ─────────────────────────────────────────────────────────────────────


_RBI_RSS_FEEDS = (
    # NotificationsIssued covers circulars; PressReleases covers press releases.
    "https://www.rbi.org.in/Scripts/RSS.aspx?action=NotificationsIssued",
    "https://www.rbi.org.in/Scripts/RSS.aspx?action=PressReleases",
)


@register_source("rbi.org.in")
async def scrape_rbi(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """Scrape RBI circulars / press releases.

    Strategy:
        1. Try the RBI RSS endpoints (XML, lightweight).
        2. Fallback to scraping the portal HTML for ``NotificationUser.aspx``
           or ``BS_PressReleaseDisplay.aspx`` style links.
    """
    docs: list[dict] = []
    try:
        async with httpx.AsyncClient(
            timeout=_HTTP_TIMEOUT,
            follow_redirects=True,
            headers=_HTTP_HEADERS,
        ) as client:
            # RSS attempts
            for feed_url in _RBI_RSS_FEEDS:
                xml = await _fetch(client, feed_url)
                if not xml:
                    continue
                rss_docs = _parse_rss_items(
                    xml, document_type, base_url="https://www.rbi.org.in/"
                )
                for d in rss_docs:
                    if d["url"] not in {x["url"] for x in docs}:
                        docs.append(d)
                if len(docs) >= _PER_PORTAL_CAP:
                    return docs[:_PER_PORTAL_CAP]

            # HTML fallback
            if not docs:
                html = await _fetch(client, portal_url)
                if html:
                    html_docs, dropped = _collect_links(
                        html,
                        portal_url,
                        document_type,
                        href_filter=lambda h: (
                            "NotificationUser" in h
                            or "BS_PressReleaseDisplay" in h
                            or h.lower().endswith(".pdf")
                        ),
                    )
                    docs.extend(html_docs)
                    logger.info(
                        "RBI HTML fallback: %d candidates, dropped %d junk",
                        len(html_docs),
                        dropped,
                    )
    except Exception as exc:  # noqa: BLE001
        logger.warning("RBI scrape failed for %s: %s", portal_url, exc)
        return []

    logger.info("RBI: returning %d docs from %s", len(docs), portal_url)
    return docs[:_PER_PORTAL_CAP]


# ── SEBI ────────────────────────────────────────────────────────────────────


@register_source("sebi.gov.in")
async def scrape_sebi(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """Scrape SEBI listing pages via Playwright (SPA / JS-rendered)."""
    from backend.collectors.playwright_helper import render_html

    docs: list[dict] = []
    try:
        html = await render_html(
            portal_url,
            wait_for_selector="a[href*='.pdf']",
            timeout_ms=30000,
        )
        if not html:
            return docs
        docs, dropped = _collect_links(
            html,
            portal_url,
            document_type,
            href_filter=lambda h: (
                h.lower().endswith(".pdf")
                or ".pdf?" in h.lower()
                or "AttachLive" in h
                or "AttachDoc" in h
                or "showAttachmentDoc" in h
                or "/sebi_data/" in h.lower()
                or "/cms/sebi_data/" in h.lower()
                or "yyyy=" in h.lower()
                or "intmid=" in h.lower()
            ),
        )
        logger.info(
            "SEBI (playwright): %d candidates, dropped %d junk",
            len(docs),
            dropped,
        )
        return docs
    except Exception as exc:  # noqa: BLE001
        logger.warning("SEBI scrape failed for %s: %s", portal_url, exc)
        return []


# ── CCI ─────────────────────────────────────────────────────────────────────


@register_source("cci.gov.in")
async def scrape_cci(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """Scrape Competition Commission of India order index pages."""
    try:
        async with httpx.AsyncClient(
            timeout=_HTTP_TIMEOUT,
            follow_redirects=True,
            headers=_HTTP_HEADERS,
            verify=False,  # CCI portal ships an incomplete cert chain.
        ) as client:
            html = await _fetch(client, portal_url)
            if not html:
                return []

            docs, dropped = _collect_links(
                html,
                portal_url,
                document_type,
                href_filter=lambda h: (
                    h.lower().endswith(".pdf")
                    or "/sites/default/files" in h.lower()
                    or "/antitrust/orders" in h.lower()
                ),
            )
            logger.info(
                "CCI: %d candidates, dropped %d junk", len(docs), dropped
            )
            return docs
    except Exception as exc:  # noqa: BLE001
        logger.warning("CCI scrape failed for %s: %s", portal_url, exc)
        return []


# ── IRDAI ───────────────────────────────────────────────────────────────────


@register_source("irdai.gov.in")
async def scrape_irdai(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """Scrape IRDAI circulars listings (Drupal-style portal)."""
    try:
        async with httpx.AsyncClient(
            timeout=_HTTP_TIMEOUT,
            follow_redirects=True,
            headers=_HTTP_HEADERS,
        ) as client:
            html = await _fetch(client, portal_url)
            if not html:
                return []

            docs, dropped = _collect_links(
                html,
                portal_url,
                document_type,
                href_filter=lambda h: (
                    h.lower().endswith(".pdf")
                    or "/document-detail" in h.lower()
                    or "/web/guest/" in h.lower()
                ),
            )
            logger.info(
                "IRDAI: %d candidates, dropped %d junk", len(docs), dropped
            )
            return docs
    except Exception as exc:  # noqa: BLE001
        logger.warning("IRDAI scrape failed for %s: %s", portal_url, exc)
        return []


# ── TRAI ────────────────────────────────────────────────────────────────────


@register_source("trai.gov.in")
async def scrape_trai(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """Scrape TRAI press releases / notifications page."""
    try:
        async with httpx.AsyncClient(
            timeout=_HTTP_TIMEOUT,
            follow_redirects=True,
            headers=_HTTP_HEADERS,
        ) as client:
            html = await _fetch(client, portal_url)
            if not html:
                return []

            docs, dropped = _collect_links(
                html,
                portal_url,
                document_type,
                href_filter=lambda h: (
                    h.lower().endswith(".pdf")
                    or "/notifications/" in h.lower()
                    or "/release/" in h.lower()
                    or "/sites/default/files" in h.lower()
                ),
            )
            logger.info(
                "TRAI: %d candidates, dropped %d junk", len(docs), dropped
            )
            return docs
    except Exception as exc:  # noqa: BLE001
        logger.warning("TRAI scrape failed for %s: %s", portal_url, exc)
        return []


# ── CERC ────────────────────────────────────────────────────────────────────


@register_source("cercind.gov.in")
async def scrape_cerc(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """Scrape Central Electricity Regulatory Commission current orders page (Playwright)."""
    from backend.collectors.playwright_helper import render_html

    docs: list[dict] = []
    try:
        html = await render_html(
            portal_url,
            wait_for_selector="a[href*='.pdf']",
            timeout_ms=30000,
        )
        if not html:
            return docs
        docs, dropped = _collect_links(
            html,
            portal_url,
            document_type,
            href_filter=lambda h: (
                h.lower().endswith(".pdf")
                or "/orders/" in h.lower()
                or "ord_" in h.lower()
            ),
        )
        logger.info(
            "CERC (playwright): %d candidates, dropped %d junk",
            len(docs),
            dropped,
        )
        return docs
    except Exception as exc:  # noqa: BLE001
        logger.warning("CERC scrape failed for %s: %s", portal_url, exc)
        return []


# ── PNGRB ───────────────────────────────────────────────────────────────────


@register_source("pngrb.gov.in")
async def scrape_pngrb(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """Scrape Petroleum & Natural Gas Regulatory Board regulations page (Playwright)."""
    from backend.collectors.playwright_helper import render_html

    docs: list[dict] = []
    try:
        html = await render_html(
            portal_url,
            wait_for_selector="a[href*='.pdf']",
            timeout_ms=30000,
        )
        if not html:
            return docs
        docs, dropped = _collect_links(
            html,
            portal_url,
            document_type,
            href_filter=lambda h: (
                h.lower().endswith(".pdf")
                or "/writereaddata" in h.lower()
                or "/eng/" in h.lower()
                or "regulation" in h.lower()
                or "notification" in h.lower()
            ),
        )
        logger.info(
            "PNGRB (playwright): %d candidates, dropped %d junk",
            len(docs),
            dropped,
        )
        return docs
    except Exception as exc:  # noqa: BLE001
        logger.warning("PNGRB scrape failed for %s: %s", portal_url, exc)
        return []
