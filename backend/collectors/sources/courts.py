"""
Courts and Tribunals portal adapters — Phase 3 source coverage (Agent C3).

Registered via @register_source decorators; auto-loaded by registry.lookup().

Covers:
  - Supreme Court of India (sci.gov.in)              judgment
  - Telangana High Court (tshc.gov.in)               court_order
  - NCLT  (nclt.gov.in)                              nclt_order
  - NCLAT (nclat.nic.in)                             nclat_order
  - NGT   (greentribunal.gov.in)                     ngt_order
  - eCourts (services.ecourts.gov.in)                ecourts   [STUB — needs per-case query]

All scrapers share signature
    async def scrape_X(portal_url, document_type, since_days=2) -> list[dict]
and return a list of {url, title, published_at: None, type: <doc_type>} dicts,
capped at 15. Failures are logged and swallowed (return whatever was gathered).

For court PDF anchors, the visible text is often just a case number
(e.g. "C.A. 1234/2024"). We keep that as-is; the downstream intel extractor
infers the real subject from the PDF body text.
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


_MIN_TITLE_LEN = 3  # case numbers can be short — relax the floor


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
    bypass_junk: bool = False,
    date_hint: str = "",
    anchor=None,
) -> None:
    """Append a candidate. Court case numbers may trip junk filter — allow opt-out.

    ``published_at`` is parsed from ``date_hint`` (typically the surrounding
    row text), then ``title``, then ``url``. Many court listings embed dates
    in the title (e.g. ``Order dated 12.03.2024``).
    """
    safe_title = (title or url.rsplit("/", 1)[-1]).strip()
    if not safe_title or len(safe_title) < _MIN_TITLE_LEN:
        return
    if not bypass_junk and _is_junk_title(safe_title, url):
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


def _is_skip_href(href: str) -> bool:
    """Skip pure anchors and javascript pseudo-links."""
    if not href:
        return True
    if href.startswith("#"):
        return True
    if href.lower().startswith(("javascript", "mailto:", "tel:")):
        return True
    return False


# ── Scrapers ───────────────────────────────────────────────────────────────


@register_source("sci.gov.in")
async def scrape_sci_judgments(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """Supreme Court of India — daily judgments page (Playwright; table loads via JS)."""
    from backend.collectors.playwright_helper import render_html

    docs: list[dict] = []
    try:
        html = await render_html(
            portal_url,
            wait_for_selector="table a[href]",
            timeout_ms=30000,
        )
        if not html:
            return docs
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if _is_skip_href(href):
                continue
            if ".pdf" not in href.lower():
                continue
            full_url = _absolutize(href, portal_url)
            title = a.get_text(strip=True) or href.rsplit("/", 1)[-1]
            _append_doc(docs, full_url, title, document_type, bypass_junk=True, anchor=a)
            if len(docs) >= _MAX_CANDIDATES:
                break
    except Exception as exc:  # noqa: BLE001
        logger.warning("SCI judgments scrape failed: %s", exc)
    logger.info("SCI judgments (playwright): discovered %d candidates", len(docs))
    return docs[:_MAX_CANDIDATES]


@register_source("tshc.gov.in")
async def scrape_tshc(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """Telangana High Court — recent orders.

    Strategy:
      1. If the input URL doesn't already point at a recent-orders endpoint,
         try `<base>/recent_orders` first; fall back to the given URL.
      2. Harvest .pdf anchors, bypass junk filter (case numbers are short).
    """
    docs: list[dict] = []
    candidates_tried: list[str] = []
    try:
        async with httpx.AsyncClient(
            timeout=_REQUEST_TIMEOUT,
            follow_redirects=True,
            headers=_HTTP_HEADERS,
            verify=False,
        ) as client:
            urls_to_try: list[str] = []
            lower = portal_url.lower()
            if "recent_orders" not in lower and "order" not in lower:
                urls_to_try.append(urljoin(portal_url.rstrip("/") + "/", "recent_orders"))
            urls_to_try.append(portal_url)

            html: str | None = None
            for u in urls_to_try:
                candidates_tried.append(u)
                html = await _fetch_html(client, u)
                if html:
                    break
            if not html:
                return docs

            soup = BeautifulSoup(html, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if _is_skip_href(href):
                    continue
                if ".pdf" not in href.lower():
                    continue
                full_url = _absolutize(href, portal_url)
                title = a.get_text(strip=True) or href.rsplit("/", 1)[-1]
                _append_doc(docs, full_url, title, document_type, bypass_junk=True, anchor=a)
                if len(docs) >= _MAX_CANDIDATES:
                    break
    except Exception as exc:  # noqa: BLE001
        logger.warning("TS High Court scrape failed (tried %s): %s", candidates_tried, exc)
    logger.info("TS High Court: discovered %d candidates", len(docs))
    return docs[:_MAX_CANDIDATES]


@register_source("nclt.gov.in")
async def scrape_nclt(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """NCLT — order/judgement date-wise listing.

    The page uses a date filter form; the default landing renders the most
    recent batch. We harvest every .pdf link.
    """
    docs: list[dict] = []
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
            soup = BeautifulSoup(html, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if _is_skip_href(href):
                    continue
                if ".pdf" not in href.lower():
                    continue
                full_url = _absolutize(href, portal_url)
                title = a.get_text(strip=True) or href.rsplit("/", 1)[-1]
                _append_doc(docs, full_url, title, document_type, bypass_junk=True, anchor=a)
                if len(docs) >= _MAX_CANDIDATES:
                    break
    except Exception as exc:  # noqa: BLE001
        logger.warning("NCLT scrape failed: %s", exc)
    logger.info("NCLT: discovered %d candidates", len(docs))
    return docs[:_MAX_CANDIDATES]


@register_source("nclat.nic.in")
async def scrape_nclat(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """NCLAT — appellate tribunal orders (page_id=10).

    WordPress-style page; orders are rendered as PDF anchors in the body.
    """
    docs: list[dict] = []
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
            soup = BeautifulSoup(html, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if _is_skip_href(href):
                    continue
                if ".pdf" not in href.lower():
                    continue
                full_url = _absolutize(href, portal_url)
                title = a.get_text(strip=True) or href.rsplit("/", 1)[-1]
                _append_doc(docs, full_url, title, document_type, bypass_junk=True, anchor=a)
                if len(docs) >= _MAX_CANDIDATES:
                    break
    except Exception as exc:  # noqa: BLE001
        logger.warning("NCLAT scrape failed: %s", exc)
    logger.info("NCLAT: discovered %d candidates", len(docs))
    return docs[:_MAX_CANDIDATES]


@register_source("greentribunal.gov.in")
async def scrape_ngt(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """National Green Tribunal — orders & judgements (Playwright)."""
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
            if _is_skip_href(href):
                continue
            if ".pdf" not in href.lower():
                continue
            full_url = _absolutize(href, portal_url)
            title = a.get_text(strip=True) or href.rsplit("/", 1)[-1]
            _append_doc(docs, full_url, title, document_type, bypass_junk=True, anchor=a)
            if len(docs) >= _MAX_CANDIDATES:
                break
    except Exception as exc:  # noqa: BLE001
        logger.warning("NGT scrape failed: %s", exc)
    logger.info("NGT (playwright): discovered %d candidates", len(docs))
    return docs[:_MAX_CANDIDATES]


async def _scrape_state_hc_orders(
    portal_url: str,
    document_type: str,
    *,
    selector_keywords: tuple[str, ...] = (),
    label: str = "state HC",
) -> list[dict]:
    """Shared workhorse for state High Court orders/judgments pages.

    Each state HC publishes a recent-orders / daily-cause-list page that
    links to PDFs (with case numbers and dates in anchor text — perfect
    for the date parser). Selectors vary slightly per court; the calling
    adapter passes its own keywords and we keep them as additive filters.
    """
    docs: list[dict] = []
    try:
        async with httpx.AsyncClient(
            timeout=30,
            follow_redirects=True,
            headers=_HTTP_HEADERS,
            verify=False,  # State HC sites frequently ship bad cert chains.
        ) as client:
            html = await _fetch_html(client, portal_url)
            if not html:
                return docs
            soup = BeautifulSoup(html, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if _is_skip_href(href):
                    continue
                lower = href.lower()
                anchor_text = a.get_text(" ", strip=True)
                if not (
                    ".pdf" in lower
                    or any(
                        k in lower or k in anchor_text.lower()
                        for k in selector_keywords
                    )
                ):
                    continue
                full_url = _absolutize(href, portal_url)
                if ".pdf" not in full_url.lower():
                    continue
                row = a.find_parent(["tr", "li", "div", "p"])
                date_hint = (
                    row.get_text(" ", strip=True) if row is not None else ""
                )
                _append_doc(
                    docs, full_url, anchor_text or "court order",
                    document_type or "court_order",
                    bypass_junk=True, date_hint=date_hint,
                )
                if len(docs) >= _MAX_CANDIDATES:
                    break
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s scrape failed: %s", label, exc)
    logger.info("%s: discovered %d candidates", label, len(docs))
    return docs[:_MAX_CANDIDATES]


@register_source("bombayhighcourt.nic.in")
async def scrape_bombay_hc(
    portal_url: str, document_type: str, since_days: int = 2,
) -> list[dict]:
    """Bombay High Court — orders & judgments listings (httpx-direct)."""
    return await _scrape_state_hc_orders(
        portal_url, document_type,
        selector_keywords=("orders", "judgement", "judgment", "causelist"),
        label="Bombay HC",
    )


@register_source("delhihighcourt.nic.in")
async def scrape_delhi_hc(
    portal_url: str, document_type: str, since_days: int = 2,
) -> list[dict]:
    """Delhi High Court — orders & judgments listings."""
    return await _scrape_state_hc_orders(
        portal_url, document_type,
        selector_keywords=("dhc_case", "dhc_doc", "judgement", "judgment"),
        label="Delhi HC",
    )


@register_source("hcmadras.tn.gov.in")
async def scrape_madras_hc(
    portal_url: str, document_type: str, since_days: int = 2,
) -> list[dict]:
    """Madras High Court — orders & judgments listings."""
    return await _scrape_state_hc_orders(
        portal_url, document_type,
        selector_keywords=("orders", "judgement", "judgment", "causelist"),
        label="Madras HC",
    )


@register_source("karnatakajudiciary.kar.nic.in")
async def scrape_karnataka_hc(
    portal_url: str, document_type: str, since_days: int = 2,
) -> list[dict]:
    """Karnataka High Court — orders & judgments listings."""
    return await _scrape_state_hc_orders(
        portal_url, document_type,
        selector_keywords=("orders", "judgement", "judgment", "case_status"),
        label="Karnataka HC",
    )


@register_source("ecourts.gov.in")
async def scrape_ecourts_stub(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """eCourts — STUB.

    The eCourts portal exposes case status only via per-case search forms
    (CNR / case-number / party-name lookups behind CAPTCHA + state/district
    cascades). It is not crawlable as a flat document list. Wired up here so
    the registry lookup matches and we don't accidentally fall through to the
    generic scraper, but always returns [].
    """
    logger.info(
        "ecourts requires per-case query — not implemented in v1 (url=%s)",
        portal_url,
    )
    return []