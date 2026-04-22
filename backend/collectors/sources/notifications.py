"""
Central-government gazettes & notification-feed adapters — Phase 3 source coverage.

Registered via @register_source decorators; auto-loaded by registry.lookup().

Covers:
  - Gazette of India (e-Gazette)        gazette         (captcha-gated; v1 noop)
  - MoF Notifications                   mof_notification
  - MEA Press Releases                  mea_release
  - MoD Press Releases                  mod_release
  - MHA Notifications                   mha_notification
  - NITI Aayog Reports                  niti_report
  - GeM Circulars                       gem_circular

All scrapers share signature
    async def scrape_X(portal_url, document_type, since_days=2) -> list[dict]
returning a list of {url, title, published_at: None, type: <doc_type>} dicts,
capped at 15. Failures are logged and swallowed (return whatever was gathered).
"""
from __future__ import annotations

import logging
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from backend.collectors.govt_collector import _HTTP_HEADERS, _is_junk_title
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
) -> None:
    """Append a candidate to docs (immutable-style helper) if not junk."""
    safe_title = (title or url.rsplit("/", 1)[-1]).strip()
    if _is_junk_title(safe_title, url):
        return
    docs.append(
        {
            "url": url,
            "title": safe_title[:500],
            "published_at": None,
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


def _harvest_links(
    html: str,
    portal_url: str,
    document_type: str,
    *,
    require_pdf: bool = False,
    keywords: tuple[str, ...] = (),
    skip_javascript: bool = True,
) -> list[dict]:
    """Parse HTML and harvest candidate links.

    A link is kept if either:
      - require_pdf=True and href ends with/contains .pdf, OR
      - keywords supplied and any keyword matches href or anchor text, OR
      - require_pdf=False and no keywords (everything passes the URL filter).

    Always drops # / javascript: hrefs (when skip_javascript=True) and titles
    that fail _is_junk_title. Returns at most _MAX_CANDIDATES dicts.
    """
    docs: list[dict] = []
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if skip_javascript and (
            href.startswith("#") or href.lower().startswith("javascript")
        ):
            continue
        text = a.get_text(strip=True)
        lower_href = href.lower()
        lower_text = text.lower()
        is_pdf = ".pdf" in lower_href
        if require_pdf and not is_pdf:
            continue
        if keywords and not (
            is_pdf or any(k in lower_href or k in lower_text for k in keywords)
        ):
            continue
        full_url = _absolutize(href, portal_url)
        _append_doc(docs, full_url, text, document_type)
        if len(docs) >= _MAX_CANDIDATES:
            break
    return docs


# ── Scrapers ───────────────────────────────────────────────────────────────


@register_source("egazette.gov.in")
async def scrape_egazette(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """Gazette of India — e-Gazette portal.

    The site is protected by ASP.NET viewstate + captcha and rejects unsigned
    requests. We attempt a probe GET; if it fails or returns a captcha page we
    log a warning and return []. v1 ships with the source seed marked
    is_active=FALSE so the scheduler won't poll it.
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
                logger.warning(
                    "egazette requires session — not implemented in v1"
                )
                return docs
            lowered = html.lower()
            if "captcha" in lowered or "verification" in lowered:
                logger.warning(
                    "egazette requires session — not implemented in v1"
                )
                return docs
            # Best-effort PDF harvest if the static index actually rendered.
            docs = _harvest_links(
                html, portal_url, document_type, require_pdf=True
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("egazette scrape failed: %s", exc)
    logger.info("egazette: discovered %d candidates", len(docs))
    return docs[:_MAX_CANDIDATES]


@register_source("finmin.nic.in")
async def scrape_mof_notifications(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """Ministry of Finance — notifications & circulars index page.

    Page lists notifications via anchor links to PDFs and detail pages. We
    harvest .pdf links plus anchors mentioning notification/circular keywords.
    """
    docs: list[dict] = []
    keywords = ("notification", "circular", "office-memorandum", "om", "order")
    try:
        async with httpx.AsyncClient(
            timeout=_REQUEST_TIMEOUT,
            follow_redirects=True,
            headers=_HTTP_HEADERS,
        ) as client:
            html = await _fetch_html(client, portal_url)
            if not html:
                return docs
            docs = _harvest_links(
                html, portal_url, document_type, keywords=keywords
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("MoF notifications scrape failed: %s", exc)
    logger.info("MoF notifications: discovered %d candidates", len(docs))
    return docs[:_MAX_CANDIDATES]


@register_source("mea.gov.in")
async def scrape_mea_press(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """Ministry of External Affairs — press-releases index.

    Each press release is an anchor to /press-releases.htm?dtl/<id>/<slug> —
    we keep anchors whose href contains 'press' or 'dtl' (the MEA detail
    permalink token).
    """
    docs: list[dict] = []
    keywords = ("press", "dtl", "release", "statement", "briefing")
    try:
        async with httpx.AsyncClient(
            timeout=_REQUEST_TIMEOUT,
            follow_redirects=True,
            headers=_HTTP_HEADERS,
        ) as client:
            html = await _fetch_html(client, portal_url)
            if not html:
                return docs
            docs = _harvest_links(
                html, portal_url, document_type, keywords=keywords
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("MEA press scrape failed: %s", exc)
    logger.info("MEA press: discovered %d candidates", len(docs))
    return docs[:_MAX_CANDIDATES]


@register_source("mod.gov.in")
async def scrape_mod_press(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """Ministry of Defence — What's New / press notifications page.

    The Drupal page lists news items as anchors to /dod/<slug> with a few PDFs
    inline. We harvest .pdf and any /dod/ permalink that isn't a nav stub.
    """
    docs: list[dict] = []
    keywords = ("/dod/", "press", "release", "news", "notification", "what")
    try:
        async with httpx.AsyncClient(
            timeout=_REQUEST_TIMEOUT,
            follow_redirects=True,
            headers=_HTTP_HEADERS,
        ) as client:
            html = await _fetch_html(client, portal_url)
            if not html:
                return docs
            docs = _harvest_links(
                html, portal_url, document_type, keywords=keywords
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("MoD press scrape failed: %s", exc)
    logger.info("MoD press: discovered %d candidates", len(docs))
    return docs[:_MAX_CANDIDATES]


@register_source("mha.gov.in")
async def scrape_mha_notifications(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """Ministry of Home Affairs — notifications listing page.

    Notifications surface as PDF links and as /en/divisionofmha-page-type
    permalinks. Harvest both via keyword match.
    """
    docs: list[dict] = []
    keywords = ("notification", "circular", "advisory", "order", "guidelines")
    try:
        async with httpx.AsyncClient(
            timeout=_REQUEST_TIMEOUT,
            follow_redirects=True,
            headers=_HTTP_HEADERS,
        ) as client:
            html = await _fetch_html(client, portal_url)
            if not html:
                return docs
            docs = _harvest_links(
                html, portal_url, document_type, keywords=keywords
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("MHA notifications scrape failed: %s", exc)
    logger.info("MHA notifications: discovered %d candidates", len(docs))
    return docs[:_MAX_CANDIDATES]


@register_source("niti.gov.in")
async def scrape_niti_reports(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """NITI Aayog — reports & publications page.

    Each report is a PDF anchor (sometimes wrapped through /sites/default/
    files/ or /document/). PDF-only harvest is sufficient.
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
            docs = _harvest_links(
                html, portal_url, document_type, require_pdf=True
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("NITI reports scrape failed: %s", exc)
    logger.info("NITI reports: discovered %d candidates", len(docs))
    return docs[:_MAX_CANDIDATES]


@register_source("gem.gov.in")
async def scrape_gem_circulars(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """Government e-Marketplace — News & Events / circulars page.

    GeM exposes circulars as PDF downloads and as /resources/<slug> news
    permalinks. Harvest .pdf plus circular/news keyword matches.
    """
    docs: list[dict] = []
    keywords = ("circular", "notice", "news", "event", "advisory", "office-memorandum")
    try:
        async with httpx.AsyncClient(
            timeout=_REQUEST_TIMEOUT,
            follow_redirects=True,
            headers=_HTTP_HEADERS,
        ) as client:
            html = await _fetch_html(client, portal_url)
            if not html:
                return docs
            docs = _harvest_links(
                html, portal_url, document_type, keywords=keywords
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("GeM circulars scrape failed: %s", exc)
    logger.info("GeM circulars: discovered %d candidates", len(docs))
    return docs[:_MAX_CANDIDATES]
