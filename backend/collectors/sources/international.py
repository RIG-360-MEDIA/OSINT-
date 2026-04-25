"""
International body adapters — Phase 3 source coverage (India-relevant).

Registered via @register_source decorators; auto-loaded by registry.lookup().

Covers:
  - World Bank India research            wb_india_report
  - Asian Development Bank (ADB) India   adb_india_report
  - IMF India Article IV / CR            imf_country_report
  - UN India publications                un_india_publication
  - ILO India publications               ilo_india_publication
  - WTO India filings                    wto_india_filing
  - BIS Annual Report                    bis_publication

All scrapers share signature
    async def scrape_X(portal_url, document_type, since_days=2) -> list[dict]
returning list[{url, title, published_at: None, type: <doc_type>}], capped
at 15. Failures are logged and swallowed.

India relevance is enforced downstream by the per-user relevance scorer via
the geography_affected field — discovery does not pre-filter for India.
"""
from __future__ import annotations

import logging
from urllib.parse import urljoin, urlparse

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


def _is_pdf_or_doc_href(href: str) -> bool:
    """Detect downloadable document URLs (.pdf, .doc, .docx)."""
    lower = href.lower()
    return any(ext in lower for ext in (".pdf", ".docx", ".doc"))


# ── Scrapers ───────────────────────────────────────────────────────────────


@register_source("worldbank.org")
async def scrape_worldbank_india(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """World Bank India — research listing.

    The /research/all page is server-rendered with anchor links to project
    documents and report landing pages. We harvest both PDF download links
    and HTML report pages whose href contains 'india'/'publication'/'document'.
    """
    docs: list[dict] = []
    keywords = ("publication", "document", "report", "india", "research")
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
                if href.startswith("#") or lower_href.startswith("javascript"):
                    continue
                is_pdf = _is_pdf_or_doc_href(lower_href)
                has_kw = any(k in lower_href for k in keywords)
                if not (is_pdf or has_kw):
                    continue
                full_url = _absolutize(href, portal_url)
                # Stay within worldbank.org domain
                if "worldbank.org" not in urlparse(full_url).netloc:
                    continue
                # F1 — PDF-only: drop /publication/ category landing pages.
                if ".pdf" not in full_url.lower():
                    continue
                _append_doc(docs, full_url, text, document_type)
                if len(docs) >= _MAX_CANDIDATES:
                    break
    except Exception as exc:  # noqa: BLE001
        logger.warning("World Bank India scrape failed: %s", exc)
    logger.info("World Bank India: discovered %d candidates", len(docs))
    return docs[:_MAX_CANDIDATES]


@register_source("adb.org")
async def scrape_adb_india(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """Asian Development Bank India publications (Playwright; bot-blocked otherwise)."""
    from backend.collectors.playwright_helper import render_html

    docs: list[dict] = []
    try:
        html = await render_html(
            portal_url,
            wait_for_selector="a.list__item__title, a[href*='.pdf']",
            timeout_ms=30000,
        )
        if not html:
            return docs
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            lower_href = href.lower()
            text = a.get_text(strip=True)
            if href.startswith("#") or lower_href.startswith("javascript"):
                continue
            is_pdf = _is_pdf_or_doc_href(lower_href)
            is_pub = "/publications/" in lower_href
            if not (is_pdf or is_pub):
                continue
            full_url = _absolutize(href, portal_url)
            if "adb.org" not in urlparse(full_url).netloc:
                continue
            if ".pdf" not in full_url.lower():
                continue
            _append_doc(docs, full_url, text, document_type)
            if len(docs) >= _MAX_CANDIDATES:
                break
    except Exception as exc:  # noqa: BLE001
        logger.warning("ADB India scrape failed: %s", exc)
    logger.info("ADB India (playwright): discovered %d candidates", len(docs))
    return docs[:_MAX_CANDIDATES]


@register_source("imf.org")
async def scrape_imf_india(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """IMF India country reports (Playwright; bot-blocked / JS-rendered)."""
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
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            lower_href = href.lower()
            text = a.get_text(strip=True)
            if href.startswith("#") or lower_href.startswith("javascript"):
                continue
            is_pdf = _is_pdf_or_doc_href(lower_href)
            is_issue = "/publications/cr/issues/" in lower_href or "/issues/" in lower_href
            if not (is_pdf or is_issue):
                continue
            full_url = _absolutize(href, portal_url)
            if "imf.org" not in urlparse(full_url).netloc:
                continue
            if ".pdf" not in full_url.lower():
                continue
            _append_doc(docs, full_url, text, document_type)
            if len(docs) >= _MAX_CANDIDATES:
                break
    except Exception as exc:  # noqa: BLE001
        logger.warning("IMF India scrape failed: %s", exc)
    logger.info("IMF India (playwright): discovered %d candidates", len(docs))
    return docs[:_MAX_CANDIDATES]


@register_source("india.un.org")
async def scrape_un_india(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """UN India office publications (Playwright; Drupal cards hydrate via JS)."""
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
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            lower_href = href.lower()
            text = a.get_text(strip=True)
            if href.startswith("#") or lower_href.startswith("javascript"):
                continue
            is_pdf = _is_pdf_or_doc_href(lower_href)
            is_pub = (
                "/sites/default/files/" in lower_href
                or "/publications/" in lower_href
                or "/resources/" in lower_href
            )
            if not (is_pdf or is_pub):
                continue
            full_url = _absolutize(href, portal_url)
            if "un.org" not in urlparse(full_url).netloc:
                continue
            if ".pdf" not in full_url.lower():
                continue
            _append_doc(docs, full_url, text, document_type)
            if len(docs) >= _MAX_CANDIDATES:
                break
    except Exception as exc:  # noqa: BLE001
        logger.warning("UN India scrape failed: %s", exc)
    logger.info("UN India (playwright): discovered %d candidates", len(docs))
    return docs[:_MAX_CANDIDATES]


@register_source("ilo.org")
async def scrape_ilo_india(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """ILO India publications.

    The /asia/countries/india/publications/lang--en/index.htm page renders
    each publication as <a href="/wcmsp5/groups/.../wcms_*.pdf"> or a
    /global/publications/ link.
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
                lower_href = href.lower()
                text = a.get_text(strip=True)
                if href.startswith("#") or lower_href.startswith("javascript"):
                    continue
                is_pdf = _is_pdf_or_doc_href(lower_href)
                is_pub = (
                    "/publications/" in lower_href
                    or "/wcmsp5/" in lower_href
                    or "wcms_" in lower_href
                )
                if not (is_pdf or is_pub):
                    continue
                full_url = _absolutize(href, portal_url)
                if "ilo.org" not in urlparse(full_url).netloc:
                    continue
                # F1 — PDF-only: drop /publications/ category landing pages.
                if ".pdf" not in full_url.lower():
                    continue
                _append_doc(docs, full_url, text, document_type)
                if len(docs) >= _MAX_CANDIDATES:
                    break
    except Exception as exc:  # noqa: BLE001
        logger.warning("ILO India scrape failed: %s", exc)
    logger.info("ILO India: discovered %d candidates", len(docs))
    return docs[:_MAX_CANDIDATES]


@register_source("docs.wto.org")
async def scrape_wto_india(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """WTO India filings — direct-doc adapter.

    The portal_url points at a single .docx download (India's WTO/AG/N notif).
    Single-doc adapters return one row.
    """
    # F1 EXCEPTION: single-doc adapter — portal_url IS the document (.docx),
    # not a listing page. Strict .pdf filter would drop a legitimate doc.
    docs: list[dict] = []
    try:
        # Derive a sensible title from the URL filename
        path = urlparse(portal_url).path
        filename = path.rsplit("/", 1)[-1] or "WTO India filing"
        title = f"WTO India filing — {filename}"
        docs.append(
            {
                "url": portal_url,
                "title": title[:500],
                "published_at": (
                    parse_listing_date(title)
                    or parse_listing_date(portal_url)
                ),
                "type": document_type,
            }
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("WTO India scrape failed: %s", exc)
    logger.info("WTO India: discovered %d candidates", len(docs))
    return docs[:_MAX_CANDIDATES]


@register_source("bis.org")
async def scrape_bis(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """BIS Annual Report — direct PDF adapter.

    The portal_url is the canonical /publ/arpdf/ar<year>e.pdf. We return a
    single candidate; the doc-intel pipeline will fetch & parse the PDF.
    """
    # F1 EXCEPTION: single-doc adapter — portal_url IS the .pdf already.
    docs: list[dict] = []
    try:
        path = urlparse(portal_url).path
        filename = path.rsplit("/", 1)[-1] or "BIS Annual Report"
        title = f"BIS Annual Report — {filename}"
        docs.append(
            {
                "url": portal_url,
                "title": title[:500],
                "published_at": (
                    parse_listing_date(title)
                    or parse_listing_date(portal_url)
                ),
                "type": document_type,
            }
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("BIS scrape failed: %s", exc)
    logger.info("BIS: discovered %d candidates", len(docs))
    return docs[:_MAX_CANDIDATES]
