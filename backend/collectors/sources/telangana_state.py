"""
Telangana state portal adapters — Phase 3 source coverage.

Registered via @register_source decorators; auto-loaded by registry.lookup().

Covers:
  - TS Government Orders (GOIR)        government_order
  - TS Gazette                          gazette
  - TGERC tariff orders                 tariff_order
  - TS-iPASS clearances                 clearance
  - TSPSC notifications                 notification
  - GHMC tenders                        tender
  - HMDA approvals                      notification
  - eProcurement Telangana              tender

All scrapers share signature
    async def scrape_X(portal_url, document_type, since_days=2) -> list[dict]
and return a list of {url, title, published_at: None, type: <doc_type>} dicts,
capped at 15. Failures are logged and swallowed (return whatever was gathered).
"""
from __future__ import annotations

import logging
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from backend.collectors.govt_collector import _HTTP_HEADERS, _is_junk_title
from backend.collectors.sources._dateparse import parse_listing_date
from backend.config.govt_config import (
    HTTP_TIMEOUT_SECONDS as _REQUEST_TIMEOUT,
    PER_PORTAL_CAP as _MAX_CANDIDATES,
)
from backend.collectors.sources.registry import register_source

logger = logging.getLogger(__name__)




# ── Helpers ────────────────────────────────────────────────────────────────


def _absolutize(href: str, base: str) -> str:
    """Return absolute URL, preserving href if already absolute."""
    if href.startswith("http://") or href.startswith("https://"):
        return href
    return urljoin(base, href)


def _append_doc(
    docs: list[dict],
    url: str,
    title: str,
    document_type: str,
    *,
    date_hint: str = "",
    anchor=None,
) -> None:
    """Append a candidate to docs (immutable-style helper) if not junk.

    If ``anchor`` is a BeautifulSoup tag, the surrounding row text
    (parent ``<tr>`` / ``<li>`` / ``<div>`` / ``<p>``) is harvested as
    a date hint when ``date_hint`` is empty. Lifts date-parser hit-rate
    significantly because most listing pages render the publish date in
    a sibling cell, not the title."""
    safe_title = (title or url.rsplit("/", 1)[-1]).strip()
    if _is_junk_title(safe_title, url):
        from backend.collectors.sources.registry import record_junk_dropped
        record_junk_dropped()
        return
    if anchor is not None and not date_hint:
        row = anchor.find_parent(["tr", "li", "div", "p"])
        if row is not None:
            date_hint = row.get_text(" ", strip=True)
    pub = (
        parse_listing_date(date_hint)
        or parse_listing_date(safe_title)
        or parse_listing_date(url)
    )
    docs.append(
        {
            "url": url,
            "title": safe_title[:500],
            "published_at": pub,
            "type": document_type,
        }
    )


async def _fetch_html(client: httpx.AsyncClient, url: str) -> str | None:
    """GET a URL; return text on 2xx else None. Never raises."""
    try:
        r = await client.get(url)
        if r.status_code >= 400:
            logger.warning("Fetch %s returned HTTP %s", url, r.status_code)
            return None
        return r.text
    except Exception as exc:  # noqa: BLE001
        logger.warning("Fetch %s raised: %s", url, exc)
        return None


# ── Scrapers ───────────────────────────────────────────────────────────────


@register_source("goir.telangana.gov.in")
async def scrape_ts_goir(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """TS Government Orders (GOIR) — generic .pdf scrape from landing page.

    The portal is form-based; landing page exposes a few "Recent" PDFs and
    template links. We harvest .pdf hrefs and rely on _is_junk_title to drop
    RTI / template noise.
    """
    docs: list[dict] = []
    try:
        async with httpx.AsyncClient(
            timeout=_REQUEST_TIMEOUT,
            follow_redirects=True,
            headers=_HTTP_HEADERS,
        ) as client:
            html = await _fetch_html(client, portal_url)
            if not html:
                return docs
            soup = BeautifulSoup(html, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if ".pdf" not in href.lower():
                    continue
                full_url = _absolutize(href, portal_url)
                title = a.get_text(strip=True)
                _append_doc(docs, full_url, title, document_type, anchor=a)
                if len(docs) >= _MAX_CANDIDATES:
                    break
    except Exception as exc:  # noqa: BLE001
        logger.warning("TS GOIR scrape failed: %s", exc)
    logger.info("TS GOIR: discovered %d candidates", len(docs))
    return docs[:_MAX_CANDIDATES]


@register_source("gad.telangana.gov.in")
async def scrape_ts_gazette(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """TS Gazette — list of dated PDF gazettes on GAD portal."""
    docs: list[dict] = []
    try:
        async with httpx.AsyncClient(
            timeout=_REQUEST_TIMEOUT,
            follow_redirects=True,
            headers=_HTTP_HEADERS,
        ) as client:
            html = await _fetch_html(client, portal_url)
            if not html:
                return docs
            soup = BeautifulSoup(html, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                lower = href.lower()
                if ".pdf" not in lower and "gazette" not in lower:
                    continue
                if ".pdf" not in lower:
                    continue
                full_url = _absolutize(href, portal_url)
                title = a.get_text(strip=True) or "TS Gazette"
                _append_doc(docs, full_url, title, document_type, anchor=a)
                if len(docs) >= _MAX_CANDIDATES:
                    break
    except Exception as exc:  # noqa: BLE001
        logger.warning("TS Gazette scrape failed: %s", exc)
    logger.info("TS Gazette: discovered %d candidates", len(docs))
    return docs[:_MAX_CANDIDATES]


@register_source("tserc.gov.in")
async def scrape_tserc_tariff(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """TGERC tariff orders — static directory listing of PDFs.

    Apache mod_autoindex pages render every file as <a href="filename.pdf">.
    """
    docs: list[dict] = []
    try:
        async with httpx.AsyncClient(
            timeout=_REQUEST_TIMEOUT,
            follow_redirects=True,
            headers=_HTTP_HEADERS,
        ) as client:
            html = await _fetch_html(client, portal_url)
            if not html:
                return docs
            soup = BeautifulSoup(html, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if not href.lower().endswith(".pdf"):
                    continue
                full_url = _absolutize(href, portal_url)
                # Apache index anchor text is the filename — that's fine
                title = a.get_text(strip=True) or href.rsplit("/", 1)[-1]
                _append_doc(docs, full_url, title, document_type, anchor=a)
                if len(docs) >= _MAX_CANDIDATES:
                    break
    except Exception as exc:  # noqa: BLE001
        logger.warning("TGERC tariff scrape failed: %s", exc)
    logger.info("TGERC tariff: discovered %d candidates", len(docs))
    return docs[:_MAX_CANDIDATES]


@register_source("ipass.telangana.gov.in")
async def scrape_ts_ipass(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """TS-iPASS investment-clearance portal.

    Landing page is mostly an investor-application UI — public document list
    is sparse. We attempt PDF + 'order/clearance/notification' link harvest.
    """
    docs: list[dict] = []
    keywords = ("order", "clearance", "notification", "approval", "circular")
    try:
        async with httpx.AsyncClient(
            timeout=_REQUEST_TIMEOUT,
            follow_redirects=True,
            headers=_HTTP_HEADERS,
        ) as client:
            html = await _fetch_html(client, portal_url)
            if not html:
                return docs
            soup = BeautifulSoup(html, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                lower_href = href.lower()
                text = a.get_text(strip=True)
                lower_text = text.lower()
                is_pdf = lower_href.endswith(".pdf")
                has_kw = any(k in lower_href or k in lower_text for k in keywords)
                if not (is_pdf or has_kw):
                    continue
                full_url = _absolutize(href, portal_url)
                # F1 — PDF-only: drop navigation/category links that aren't actual PDFs.
                if ".pdf" not in full_url.lower():
                    continue
                _append_doc(docs, full_url, text, document_type, anchor=a)
                if len(docs) >= _MAX_CANDIDATES:
                    break
    except Exception as exc:  # noqa: BLE001
        logger.warning("TS-iPASS scrape failed: %s", exc)
    logger.info("TS-iPASS: discovered %d candidates", len(docs))
    return docs[:_MAX_CANDIDATES]


@register_source("tspsc.gov.in")
async def scrape_tspsc(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """TSPSC notifications — list of recent recruitment / exam notifications.

    Note: many entries are 'recruitment' which our junk filter normally drops,
    but the document_type is 'notification' and TSPSC's whole purpose is
    recruitment notices; we override by inspecting the file extension.
    """
    docs: list[dict] = []
    try:
        async with httpx.AsyncClient(
            timeout=_REQUEST_TIMEOUT,
            follow_redirects=True,
            headers=_HTTP_HEADERS,
        ) as client:
            html = await _fetch_html(client, portal_url)
            if not html:
                return docs
            soup = BeautifulSoup(html, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if ".pdf" not in href.lower():
                    continue
                full_url = _absolutize(href, portal_url)
                title = a.get_text(strip=True) or href.rsplit("/", 1)[-1]
                # Bypass junk-title filter for TSPSC: 'recruitment'/'vacancy'
                # IS the news here. Still drop empty/very-short titles.
                if not title or len(title) < 4:
                    continue
                docs.append(
                    {
                        "url": full_url,
                        "title": title[:500],
                        "published_at": (
                            parse_listing_date(title)
                            or parse_listing_date(full_url)
                        ),
                        "type": document_type,
                    }
                )
                if len(docs) >= _MAX_CANDIDATES:
                    break
    except Exception as exc:  # noqa: BLE001
        logger.warning("TSPSC scrape failed: %s", exc)
    logger.info("TSPSC: discovered %d candidates", len(docs))
    return docs[:_MAX_CANDIDATES]


@register_source("ghmc.gov.in")
async def scrape_ghmc_tenders(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """GHMC tender notices.

    The page is an ASP.NET grid; we harvest both .pdf links and any anchor
    whose text/href mentions 'tender'/'NIT'.
    """
    docs: list[dict] = []
    keywords = ("tender", "nit", "notice", "rfp", "rfq", "eoi")
    try:
        async with httpx.AsyncClient(
            timeout=_REQUEST_TIMEOUT,
            follow_redirects=True,
            headers=_HTTP_HEADERS,
        ) as client:
            html = await _fetch_html(client, portal_url)
            if not html:
                return docs
            soup = BeautifulSoup(html, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                text = a.get_text(strip=True)
                lower_href = href.lower()
                lower_text = text.lower()
                is_pdf = ".pdf" in lower_href
                has_kw = any(k in lower_href or k in lower_text for k in keywords)
                if not (is_pdf or has_kw):
                    continue
                # Skip bare # anchors / javascript
                if href.startswith("#") or href.lower().startswith("javascript"):
                    continue
                full_url = _absolutize(href, portal_url)
                # F1 — PDF-only: drop navigation/category links that aren't actual PDFs.
                if ".pdf" not in full_url.lower():
                    continue
                _append_doc(docs, full_url, text or "GHMC Tender", document_type, anchor=a)
                if len(docs) >= _MAX_CANDIDATES:
                    break
    except Exception as exc:  # noqa: BLE001
        logger.warning("GHMC tenders scrape failed: %s", exc)
    logger.info("GHMC tenders: discovered %d candidates", len(docs))
    return docs[:_MAX_CANDIDATES]


@register_source("hmda.gov.in")
async def scrape_hmda(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """HMDA circulars and notifications page."""
    docs: list[dict] = []
    try:
        async with httpx.AsyncClient(
            timeout=_REQUEST_TIMEOUT,
            follow_redirects=True,
            headers=_HTTP_HEADERS,
        ) as client:
            html = await _fetch_html(client, portal_url)
            if not html:
                return docs
            soup = BeautifulSoup(html, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if ".pdf" not in href.lower():
                    continue
                full_url = _absolutize(href, portal_url)
                title = a.get_text(strip=True) or href.rsplit("/", 1)[-1]
                _append_doc(docs, full_url, title, document_type, anchor=a)
                if len(docs) >= _MAX_CANDIDATES:
                    break
    except Exception as exc:  # noqa: BLE001
        logger.warning("HMDA scrape failed: %s", exc)
    logger.info("HMDA: discovered %d candidates", len(docs))
    return docs[:_MAX_CANDIDATES]


@register_source("tender.telangana.gov.in")
async def scrape_eproc_ts(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """eProcurement Telangana — landing page harvest.

    The full search uses POST forms with date filters which we don't replay.
    We pull what we can from the public landing page (recent tender summary
    table / news ticker). May return 0 — that's expected; the audit log
    will flag it for follow-up.
    """
    docs: list[dict] = []
    keywords = ("tender", "nit", "bid", "rfp", "rfq", "eoi", "auction")
    try:
        async with httpx.AsyncClient(
            timeout=_REQUEST_TIMEOUT,
            follow_redirects=True,
            headers=_HTTP_HEADERS,
        ) as client:
            html = await _fetch_html(client, portal_url)
            if not html:
                return docs
            soup = BeautifulSoup(html, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                text = a.get_text(strip=True)
                lower_href = href.lower()
                lower_text = text.lower()
                is_pdf = ".pdf" in lower_href
                has_kw = any(k in lower_href or k in lower_text for k in keywords)
                if not (is_pdf or has_kw):
                    continue
                if href.startswith("#") or href.lower().startswith("javascript"):
                    continue
                full_url = _absolutize(href, portal_url)
                # F1 — PDF-only: drop navigation/category links that aren't actual PDFs.
                if ".pdf" not in full_url.lower():
                    continue
                _append_doc(docs, full_url, text or "eProc Tender", document_type, anchor=a)
                if len(docs) >= _MAX_CANDIDATES:
                    break
    except Exception as exc:  # noqa: BLE001
        logger.warning("eProcurement TS scrape failed: %s", exc)
    logger.info("eProcurement TS: discovered %d candidates", len(docs))
    return docs[:_MAX_CANDIDATES]