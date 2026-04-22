"""
Parliament-of-India portal adapters — Phase 3 source coverage (Agent C4).

Registered via @register_source decorators; auto-loaded by registry.lookup().

Covers:
  - Lok Sabha Q&A                       lok_sabha_question
  - Lok Sabha Bills (introduced)        bill
  - Rajya Sabha Bills (pending)         bill
  - Rajya Sabha Debates (synopsis)      rs_debate
  - Parliamentary Committee Reports     committee_report
  - PRS Legislative Research bills      bill   (third-party)

All scrapers share signature
    async def scrape_X(portal_url, document_type, since_days=2) -> list[dict]
and return a list of {url, title, published_at: None, type: <doc_type>} dicts,
capped at 15. Failures are logged and swallowed (return whatever was gathered).

NOTE: the new sansad.in portal is JS-heavy (Angular SPA). When the main URL
returns a near-empty shell we fall back to the legacy NIC document mirrors
(``eparlib.nic.in`` and ``loksabhadocs.nic.in``) which still serve plain HTML
directory listings of recent PDFs.
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
# Heuristic: if a sansad.in landing page yields fewer than this many useful
# anchors we attempt a NIC legacy fallback URL.
_SPA_SHELL_THRESHOLD = 3


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


def _harvest_pdf_anchors(
    html: str,
    base: str,
    document_type: str,
    extra_keywords: tuple[str, ...] = (),
) -> list[dict]:
    """Parse HTML and harvest .pdf or keyword-matching anchors.

    Pure function — returns a fresh list (immutable style).
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
        full_url = _absolutize(href, base)
        # F1 — PDF-only: drop navigation/category links that aren't actual PDFs.
        # sansad.in SPA shells expose accessibility/lang nav links matching keywords;
        # legacy NIC fallbacks are real .pdf directories.
        if ".pdf" not in full_url.lower():
            continue
        _append_doc(docs, full_url, text, document_type)
        if len(docs) >= _MAX_CANDIDATES:
            break
    return docs


async def _scrape_with_fallback(
    portal_url: str,
    document_type: str,
    fallback_urls: tuple[str, ...],
    extra_keywords: tuple[str, ...] = (),
    label: str = "parliament",
) -> list[dict]:
    """Try portal_url first; fall back to NIC mirrors if SPA shell detected."""
    docs: list[dict] = []
    try:
        async with httpx.AsyncClient(
            timeout=_REQUEST_TIMEOUT,
            follow_redirects=True,
            headers=_HTTP_HEADERS,
        ) as client:
            html = await _fetch_html(client, portal_url)
            if html:
                docs = _harvest_pdf_anchors(
                    html, portal_url, document_type, extra_keywords
                )
            if len(docs) < _SPA_SHELL_THRESHOLD:
                for fb in fallback_urls:
                    fb_html = await _fetch_html(client, fb)
                    if not fb_html:
                        continue
                    fb_docs = _harvest_pdf_anchors(
                        fb_html, fb, document_type, extra_keywords
                    )
                    # Merge dedup on URL
                    seen = {d["url"] for d in docs}
                    for d in fb_docs:
                        if d["url"] not in seen:
                            docs.append(d)
                            seen.add(d["url"])
                        if len(docs) >= _MAX_CANDIDATES:
                            break
                    if len(docs) >= _MAX_CANDIDATES:
                        break
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s scrape failed: %s", label, exc)
    logger.info("%s: discovered %d candidates", label, len(docs))
    return docs[:_MAX_CANDIDATES]


# ── Scrapers ───────────────────────────────────────────────────────────────


@register_source("sansad.in/ls/questions")
async def scrape_ls_questions(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """Lok Sabha Questions & Answers — daily starred/unstarred lists.

    sansad.in is an Angular SPA; HTML shell rarely contains data anchors.
    Falls back to the legacy ``loksabhadocs.nic.in`` PDF directory which
    publishes daily question lists (e.g. ``/Questions/QResult.aspx``).
    """
    return await _scrape_with_fallback(
        portal_url=portal_url,
        document_type=document_type,
        fallback_urls=(
            "https://loksabhadocs.nic.in/qsearch/QResult.aspx",
            "https://eparlib.nic.in/handle/123456789/787",
        ),
        extra_keywords=("question", "starred", "unstarred", "qresult"),
        label="LS Questions",
    )


@register_source("sansad.in/ls/legislation")
async def scrape_ls_bills(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """Lok Sabha Bills — introduced and pending.

    Fallback: ``loksabhadocs.nic.in/Bills`` directory of bill-as-introduced
    PDFs (legacy mirror).
    """
    return await _scrape_with_fallback(
        portal_url=portal_url,
        document_type=document_type,
        fallback_urls=(
            "https://loksabhadocs.nic.in/Bills/BillsAsIntroduced.aspx",
            "https://eparlib.nic.in/handle/123456789/2",
        ),
        extra_keywords=("bill", "amendment", "act"),
        label="LS Bills",
    )


@register_source("sansad.in/rs/legislation")
async def scrape_rs_bills(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """Rajya Sabha Bills — pending list.

    Fallback: ``rajyasabha.nic.in/legislation`` legacy listing.
    """
    return await _scrape_with_fallback(
        portal_url=portal_url,
        document_type=document_type,
        fallback_urls=(
            "https://rajyasabha.nic.in/Legislation/PendingBills",
            "https://rsdebate.nic.in/handle/123456789/2",
        ),
        extra_keywords=("bill", "amendment", "pending"),
        label="RS Bills",
    )


@register_source("sansad.in/rs/proceedings")
async def scrape_rs_debates(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """Rajya Sabha debate synopses — daily proceedings summary.

    Fallback: ``rsdebate.nic.in`` (Rajya Sabha digital library) which serves
    plain HTML browse pages of synopsis PDFs.
    """
    return await _scrape_with_fallback(
        portal_url=portal_url,
        document_type=document_type,
        fallback_urls=(
            "https://rsdebate.nic.in/simple-search?query=synopsis",
            "https://rajyasabha.nic.in/Debates/Synopsis",
        ),
        extra_keywords=("synopsis", "debate", "proceedings"),
        label="RS Debates",
    )


@register_source("sansad.in/ls/committees")
async def scrape_committee_reports(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """Parliamentary Standing Committee reports.

    Fallback: ``eparlib.nic.in`` committee reports collection — a substantive
    archive of departmental standing committee analyses.
    """
    return await _scrape_with_fallback(
        portal_url=portal_url,
        document_type=document_type,
        fallback_urls=(
            "https://eparlib.nic.in/handle/123456789/64158",
            "https://loksabhadocs.nic.in/Committee/CommitteeReports.aspx",
        ),
        extra_keywords=("committee", "report", "standing"),
        label="Committee Reports",
    )


@register_source("prsindia.org")
async def scrape_prs_bills(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """PRS Legislative Research — bill tracker with PDF summaries.

    PRS publishes structured PDFs of bill summaries — high quality. Their
    ``/billtrack`` page is server-rendered Drupal HTML, so the primary URL
    typically yields plenty of candidates without needing a fallback.
    """
    docs: list[dict] = []
    keywords = ("bill", "summary", "act", "legislative", "/billtrack")
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
                if href.startswith("#") or href.lower().startswith("javascript"):
                    continue
                text = a.get_text(strip=True)
                lower_href = href.lower()
                lower_text = text.lower()
                is_pdf = ".pdf" in lower_href
                # Bill-tracker rows link to /billtrack/<slug> detail pages too —
                # those are useful targets for the downstream content scraper.
                is_billtrack = "/billtrack/" in lower_href and lower_href != portal_url.lower()
                has_kw = any(k in lower_text for k in keywords if not k.startswith("/"))
                if not (is_pdf or is_billtrack or has_kw):
                    continue
                full_url = _absolutize(href, portal_url)
                # F1 — PDF-only: drop /billtrack/<slug> detail pages and category links.
                if ".pdf" not in full_url.lower():
                    continue
                _append_doc(docs, full_url, text or "PRS Bill", document_type)
                if len(docs) >= _MAX_CANDIDATES:
                    break
    except Exception as exc:  # noqa: BLE001
        logger.warning("PRS Bill Tracker scrape failed: %s", exc)
    logger.info("PRS Bill Tracker: discovered %d candidates", len(docs))
    return docs[:_MAX_CANDIDATES]
