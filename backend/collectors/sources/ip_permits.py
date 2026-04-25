"""
IP / regulatory permit portal adapters — Phase 3 source coverage (Agent C5).

Registered via @register_source decorators; auto-loaded by registry.lookup().

Covers:
  - IP India Patents (recently granted)        patent
  - IP India Trademarks (journal PDFs)         trademark
  - IP India GI Tags (recent news GI)          gi_tag
  - MCA Notifications                          mca_notification
  - FSSAI Standards / Notifications            fssai_notification
  - CDSCO Drug Approvals / Notices             cdsco_notification

All scrapers share signature
    async def scrape_X(portal_url, document_type, since_days=2) -> list[dict]
and return a list of {url, title, published_at: None, type: <doc_type>} dicts,
capped at 15. Failures are logged and swallowed (return whatever was gathered).

Note on IP India trademark journals: the weekly journal PDF can be multiple GB
(occasionally ~10 GB). We only emit the URL here — the download stage in
backend.collectors.govt_collector.download_pdf has a 60s timeout and skips
oversized responses, so discovery never blocks on these payloads.
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


_MAX_CANDIDATES = 15
_REQUEST_TIMEOUT = 30


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
) -> None:
    """Append a candidate to docs (immutable-style helper) if not junk."""
    safe_title = (title or url.rsplit("/", 1)[-1]).strip()
    if _is_junk_title(safe_title, url):
        from backend.collectors.sources.registry import record_junk_dropped
        record_junk_dropped()
        return
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


def _harvest_pdf_links(
    html: str,
    portal_url: str,
    document_type: str,
    extra_keywords: tuple[str, ...] = (),
) -> list[dict]:
    """Generic harvester — pulls .pdf links plus anchors matching keywords.

    Pure function (returns a fresh list); no in-place mutation of inputs.
    """
    docs: list[dict] = []
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("#") or href.lower().startswith("javascript"):
            continue
        text = a.get_text(strip=True)
        lower_href = href.lower()
        lower_text = text.lower()
        is_pdf = ".pdf" in lower_href
        has_kw = bool(extra_keywords) and any(
            k in lower_href or k in lower_text for k in extra_keywords
        )
        if not (is_pdf or has_kw):
            continue
        full_url = _absolutize(href, portal_url)
        # F1 — PDF-only: drop FSSAI /standards/, MCA category, CDSCO sub-folder
        # navigation links that match keywords but aren't actual PDFs.
        if ".pdf" not in full_url.lower():
            continue
        _append_doc(docs, full_url, text, document_type)
        if len(docs) >= _MAX_CANDIDATES:
            break
    return docs


# ── IP India ───────────────────────────────────────────────────────────────


@register_source("ipindia.gov.in/recently-granted-patents")
async def scrape_ip_india_patents(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """IP India recently-granted patents.

    Page lists weekly grant PDFs. Harvest .pdf hrefs.
    """
    docs: list[dict] = []
    try:
        async with httpx.AsyncClient(
            timeout=_REQUEST_TIMEOUT,
            follow_redirects=True,
            headers=_HTTP_HEADERS,
            verify=False,  # ipindia.gov.in occasionally serves stale chain
        ) as client:
            html = await _fetch_html(client, portal_url)
            if not html:
                return docs
            docs = _harvest_pdf_links(html, portal_url, document_type)
    except Exception as exc:  # noqa: BLE001
        logger.warning("IP India patents scrape failed: %s", exc)
    logger.info("IP India patents: discovered %d candidates", len(docs))
    return docs[:_MAX_CANDIDATES]


@register_source("ipindia.gov.in/journal-tm")
async def scrape_ip_india_trademarks(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """IP India trademark journal — weekly PDFs (can be multi-GB).

    We only emit URLs; the download stage handles size limits.
    """
    docs: list[dict] = []
    keywords = ("journal", "trademark", "tm")
    try:
        async with httpx.AsyncClient(
            timeout=_REQUEST_TIMEOUT,
            follow_redirects=True,
            headers=_HTTP_HEADERS,
            verify=False,
        ) as client:
            html = await _fetch_html(client, portal_url)
            if not html:
                return docs
            docs = _harvest_pdf_links(
                html, portal_url, document_type, extra_keywords=keywords
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("IP India trademarks scrape failed: %s", exc)
    logger.info("IP India trademarks: discovered %d candidates", len(docs))
    return docs[:_MAX_CANDIDATES]


@register_source("ipindia.gov.in/recent-news-gi")
async def scrape_ip_india_gi(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """IP India Geographical Indications recent news — PDF + GI keyword harvest."""
    docs: list[dict] = []
    keywords = ("gi", "geographical", "indication", "registration")
    try:
        async with httpx.AsyncClient(
            timeout=_REQUEST_TIMEOUT,
            follow_redirects=True,
            headers=_HTTP_HEADERS,
            verify=False,
        ) as client:
            html = await _fetch_html(client, portal_url)
            if not html:
                return docs
            docs = _harvest_pdf_links(
                html, portal_url, document_type, extra_keywords=keywords
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("IP India GI scrape failed: %s", exc)
    logger.info("IP India GI: discovered %d candidates", len(docs))
    return docs[:_MAX_CANDIDATES]


# ── MCA ────────────────────────────────────────────────────────────────────


@register_source("mca.gov.in")
async def scrape_mca_notifications(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """Ministry of Corporate Affairs notifications (Playwright; ASP.NET grid hydrates via JS)."""
    from backend.collectors.playwright_helper import render_html

    docs: list[dict] = []
    keywords = (
        "notification",
        "circular",
        "order",
        "rules",
        "amendment",
        "act",
    )
    try:
        html = await render_html(
            portal_url,
            wait_for_selector="a[href*='.pdf']",
            timeout_ms=30000,
        )
        if not html:
            return docs
        docs = _harvest_pdf_links(
            html, portal_url, document_type, extra_keywords=keywords
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("MCA notifications scrape failed: %s", exc)
    logger.info("MCA notifications (playwright): discovered %d candidates", len(docs))
    return docs[:_MAX_CANDIDATES]


# ── FSSAI ──────────────────────────────────────────────────────────────────


@register_source("fssai.gov.in")
async def scrape_fssai_notifications(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """FSSAI standards / notifications page."""
    docs: list[dict] = []
    keywords = (
        "notification",
        "standard",
        "regulation",
        "order",
        "circular",
        "amendment",
        "gazette",
    )
    try:
        async with httpx.AsyncClient(
            timeout=_REQUEST_TIMEOUT,
            follow_redirects=True,
            headers=_HTTP_HEADERS,
        ) as client:
            html = await _fetch_html(client, portal_url)
            if not html:
                return docs
            docs = _harvest_pdf_links(
                html, portal_url, document_type, extra_keywords=keywords
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("FSSAI notifications scrape failed: %s", exc)
    logger.info("FSSAI notifications: discovered %d candidates", len(docs))
    return docs[:_MAX_CANDIDATES]


# ── CDSCO ──────────────────────────────────────────────────────────────────


@register_source("cdsco.gov.in")
async def scrape_cdsco_notifications(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """CDSCO (drug regulator) notices / approvals page.

    OpenCMS index — anchors are typically .pdf or sub-folder index pages.
    We scrape one level deep on the listing page.
    """
    docs: list[dict] = []
    keywords = (
        "notice",
        "notification",
        "approval",
        "circular",
        "order",
        "draft",
        "guideline",
    )
    try:
        async with httpx.AsyncClient(
            timeout=_REQUEST_TIMEOUT,
            follow_redirects=True,
            headers=_HTTP_HEADERS,
        ) as client:
            html = await _fetch_html(client, portal_url)
            if not html:
                return docs
            docs = _harvest_pdf_links(
                html, portal_url, document_type, extra_keywords=keywords
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("CDSCO notifications scrape failed: %s", exc)
    logger.info("CDSCO notifications: discovered %d candidates", len(docs))
    return docs[:_MAX_CANDIDATES]
