"""
Government document collector.

Scrapes portals (PIB, Telangana GO.Ms, CAG, ministry sites) for new PDF
documents, downloads them, and extracts text via OpenDataLoader PDF
(Apache 2.0). Falls back to PyMuPDF for simple digital PDFs when
OpenDataLoader is unavailable.

Long documents are split into 1000-char overlapping chunks for embedding.
"""
from __future__ import annotations

import logging
import os
import re
from urllib.parse import urljoin

import httpx

logger = logging.getLogger(__name__)


_HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
}


# Drop any candidate whose title (or URL filename when title is empty)
# matches one of these patterns. Curated from real PIB/CAG/Telangana junk.
_JUNK_TITLE_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in (
        # — Generic boilerplate that slips past content filters —
        r"^\s*user[\s\-]*guide\s*$",
        r"^\s*disclaimer\s*$",
        r"^\s*terms\s+(of\s+)?(use|service)\s*$",
        r"^\s*privacy\s+policy\s*$",
        r"^\s*cookie\s+policy\s*$",
        r"^\s*help(\s+(center|page))?\s*$",
        r"^\s*site[\s\-]*map\s*$",
        r"^\s*home\s*$",
        r"^\s*contact[\s\-]*us\s*$",
        r"^\s*about[\s\-]*us\s*$",
        r"^\s*feedback\s*$",
        # — Opaque ID-only filenames (e.g. "PR1417BAA07FE288C4...PDF") —
        # Any title that's just a long alphanumeric token + extension is
        # an upload-system filename, not a real document title.
        r"^[A-Z0-9_\-]{16,}\.(pdf|doc|docx)\s*$",
        # — Existing patterns —
        r"\bcitizen[\s\-]*charter\b",
        r"\brti\b.*\b(act|manual|compliance|response template)\b",
        r"\binformation\s+manual\b",
        r"\bfact[\s\-]*check\b",
        r"\bessay\s+(writing\s+)?competition\b",
        r"\brecruitment\b",
        r"\b(vacancy|vacancies)\b",
        r"\btelephone\s+directory\b",
        r"\bholiday\s+list\b",
        r"\bnews[\s\-]*letter\b",
        r"\bphoto\s+gallery\b",
        r"\b(annual|monthly)\s+report\b.*\bcover\b",  # cover pages of reports
        r"\bfraudulent\s+websites?\b",
        r"\bgeneral\s+knowledge\b",
        r"\bshikayat\b",  # Hindi (Latin): complaint/grievance — generic admin
        r"\bsuchana\s+adhikar\b",  # Hindi (Latin): RTI
        r"\bnagrik\s+charter\b",  # Hindi (Latin): citizen charter
        r"\binternal\s+complaints?\s+committee\b",
        r"\bgrievance\s+(officer|redressal)\b",
        r"\b(work|business)\s+allocation\b",
        r"\bdelegation\s+of\s+(financial|administrative)\s+powers\b",
        r"\bappointment\s+of\b.*\b(officer|inquiry|associate)\b",
        r"\bre[\s\-]*designation\b",
        r"\bgazetted\s+holiday\b",
        r"\btransparency\s+audit\b",
        r"\bpension\s+adalat\b",
        r"\bcpio\b",
        # Devanagari (Hindi) literal patterns — actual page text, not Latin.
        r"नागरिक\s*(चार्टर|अधिकार)",  # citizen charter / citizen rights
        r"शिकायत",  # complaint / grievance
        r"सूचना\s*अधिकार",  # right to information
        r"तथ्य\S*\s*(की\s*)?(जाँच|जांच)",  # fact check (incl. plural तथ्यों)
        r"धोखाधड़ी",  # fraud / fraudulent
        r"सूचना\s*पुस्तिका",  # information manual / handbook
        r"शी\s*बॉक्स",  # SHe-Box (women's grievance portal — admin, not news)
        r"आन्?तरिक\s*शिकायत",  # internal complaints
        r"कार्य\s*आबंटन",  # work allocation
        r"वित्तीय\s*(और\s*प्रशासनिक\s*)?शक्तियों\s*का\s*प्रत्यायोजन",  # delegation of powers
        r"नियुक्ति",  # appointment
        r"निबंध\s*(लेखन\s*)?प्रतियोगिता",  # essay (writing) competition
        r"पारदर्शिता\s*लेखा\s*परीक्षा",  # transparency audit
        r"पेंशन\s*अदालत",  # pension adalat
        r"भर्ती",  # recruitment
        r"रिक्ति",  # vacancy
        r"अवकाश\s*सूची",  # holiday list
        # Telugu literal patterns
        r"స\.\s*హ\.\s*సెక్షన్",  # RTI section header in Telugu
        r"సమాచార\s*హక్కు",  # right to information (Telugu)
        # English RTI section markers (4(1)(b) etc.)
        r"\brti\s+u/s\s+4\(1\)",
    )
]


# PIB site-footer / about-us areas that are never news-worthy.
_PIB_URL_DENY = (
    "/aboutus/",
    "/RTI/",
    "/Annual_Reports/",
    "/Holiday/",
    "/CitizenCharter/",
)


def _is_junk_title(title: str | None, url: str = "") -> bool:
    """True if the title or URL filename matches a junk pattern."""
    candidate = (title or "").strip()
    if not candidate or len(candidate) < 4:
        # Fall back to URL basename
        candidate = url.rsplit("/", 1)[-1]
    for pat in _JUNK_TITLE_PATTERNS:
        if pat.search(candidate):
            return True
    return False


async def _try_sitemap(portal_url: str) -> list[dict] | None:
    """Try /sitemap.xml first. Returns None if unavailable.

    Currently a stub returning None — Phase 3 will implement per-portal logic.
    """
    return None


# ── Portal scrapers ─────────────────────────────────────────────────────────


def _apply_since_days_filter(
    docs: list[dict],
    *,
    since_days: int,
    portal_url: str,
) -> list[dict]:
    """Drop rows whose ``published_at`` is older than ``since_days``.

    Rows with ``published_at is None`` are kept (the date parser couldn't
    extract a date — losing them would create silent black holes; the
    parse-time WARNING already surfaces the gap). Rows with a parsed date
    older than the cutoff are dropped — this is the gate that turns the
    daily run into a real delta instead of a re-scrape (defect D-23).
    """
    from datetime import datetime, timedelta, timezone

    cutoff = datetime.now(timezone.utc) - timedelta(days=since_days)
    kept: list[dict] = []
    dropped_old = 0
    no_date = 0
    for d in docs:
        pub = d.get("published_at")
        if pub is None:
            no_date += 1
            kept.append(d)
            continue
        if isinstance(pub, str):
            try:
                pub = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            except ValueError:
                kept.append(d)
                continue
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=timezone.utc)
        if pub >= cutoff:
            kept.append(d)
        else:
            dropped_old += 1

    if dropped_old or no_date:
        logger.info(
            "since_days filter [%s]: kept %d, dropped %d as too old, "
            "%d had no parseable date",
            portal_url, len(kept), dropped_old, no_date,
        )
    return kept


async def fetch_document_urls(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """
    Scrape a government portal for new document URLs.

    Resolution order:
      1. Phase-3 source-adapter registry (per-portal scrapers in
         backend/collectors/sources/*.py with @register_source decorators)
      2. Built-in PIB scraper
      3. Built-in Telangana GO.Ms / TS High Court scraper
      4. Generic PDF-link scraper (any portal)

    Returns list of dicts: {url, title, published_at, type}. Rows older
    than ``since_days`` are filtered out by the shared gate; this is the
    single point of date enforcement so per-adapter implementations
    don't have to repeat it.
    """
    from backend.collectors.sources.registry import lookup

    adapter = lookup(portal_url)
    raw: list[dict]
    if adapter is not None:
        try:
            raw = await adapter(portal_url, document_type, since_days)
        except Exception as exc:
            logger.warning(
                "Source adapter for %s failed: %s — falling back to built-ins",
                portal_url,
                exc,
            )
            raw = await _legacy_fallback(portal_url, since_days)
    else:
        raw = await _legacy_fallback(portal_url, since_days)

    return _apply_since_days_filter(
        raw, since_days=since_days, portal_url=portal_url
    )


async def _legacy_fallback(portal_url: str, since_days: int) -> list[dict]:
    """Built-in scrapers for portals without a registered adapter."""
    if "pib.gov.in" in portal_url:
        return await _scrape_pib(since_days)
    if "tggovernment" in portal_url or "tshc.gov.in" in portal_url:
        return await _scrape_tg_goms(since_days)
    return await _scrape_generic_pdfs(portal_url, since_days)


async def _scrape_pib(since_days: int) -> list[dict]:
    """Scrape PIB press releases page for document links."""
    docs: list[dict] = []
    dropped_junk = 0
    try:
        async with httpx.AsyncClient(
            timeout=30,
            follow_redirects=True,
            headers=_HTTP_HEADERS,
        ) as client:
            r = await client.get("https://pib.gov.in/allRel.aspx")
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(r.text, "html.parser")
            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                if "prid=" in href or ".pdf" in href.lower():
                    # Skip PIB site-footer / about-us URL areas outright.
                    if any(d in href for d in _PIB_URL_DENY):
                        dropped_junk += 1
                        continue

                    title = link.get_text(strip=True)
                    full_url = (
                        href
                        if href.startswith("http")
                        else urljoin("https://pib.gov.in/", href)
                    )
                    # Fall back to URL basename when anchor text is short —
                    # many PIB PDF links are icon-only or single-word anchors.
                    if not title or len(title) < 10:
                        title = full_url.rstrip("/").rsplit("/", 1)[-1] or full_url

                    if _is_junk_title(title, full_url):
                        dropped_junk += 1
                        from backend.collectors.sources.registry import (
                            record_junk_dropped,
                        )
                        record_junk_dropped()
                        continue

                    from backend.collectors.sources._dateparse import (
                        parse_listing_date,
                    )
                    docs.append(
                        {
                            "url": full_url,
                            "title": title[:500],
                            "published_at": (
                                parse_listing_date(title)
                                or parse_listing_date(full_url)
                            ),
                            "type": "press_release",
                        }
                    )
    except Exception as exc:
        logger.warning("PIB scrape failed: %s", exc)

    logger.info(
        "PIB: discovered %d candidates, dropped %d junk",
        len(docs),
        dropped_junk,
    )
    return docs[:20]


async def _scrape_tg_goms(since_days: int) -> list[dict]:
    """Scrape Telangana GO.Ms portal for PDF links."""
    docs: list[dict] = []
    dropped_junk = 0
    try:
        async with httpx.AsyncClient(
            timeout=30,
            follow_redirects=True,
            headers=_HTTP_HEADERS,
        ) as client:
            r = await client.get("https://goir.telangana.gov.in/")
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(r.text, "html.parser")
            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                if ".pdf" in href.lower():
                    full_url = (
                        href
                        if href.startswith("http")
                        else urljoin("https://goir.telangana.gov.in/", href)
                    )
                    title = link.get_text(strip=True) or "GO.Ms"

                    if _is_junk_title(title, full_url):
                        dropped_junk += 1
                        from backend.collectors.sources.registry import (
                            record_junk_dropped,
                        )
                        record_junk_dropped()
                        continue

                    from backend.collectors.sources._dateparse import (
                        parse_listing_date,
                    )
                    docs.append(
                        {
                            "url": full_url,
                            "title": title,
                            "published_at": (
                                parse_listing_date(title)
                                or parse_listing_date(full_url)
                            ),
                            "type": "government_order",
                        }
                    )
    except Exception as exc:
        logger.warning("Telangana GO.Ms scrape failed: %s", exc)

    logger.info(
        "TG GO.Ms: discovered %d candidates, dropped %d junk",
        len(docs),
        dropped_junk,
    )
    return docs[:10]


async def _scrape_generic_pdfs(
    portal_url: str,
    since_days: int,
) -> list[dict]:
    """Fall-back scraper: collect any .pdf link from a portal page."""
    docs: list[dict] = []
    dropped_junk = 0
    try:
        async with httpx.AsyncClient(
            timeout=30,
            follow_redirects=True,
            headers=_HTTP_HEADERS,
        ) as client:
            r = await client.get(portal_url)
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(r.text, "html.parser")
            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                if ".pdf" in href.lower():
                    full_url = (
                        href
                        if href.startswith("http")
                        else urljoin(portal_url + "/", href)
                    )
                    title = link.get_text(strip=True) or full_url

                    if _is_junk_title(title, full_url):
                        dropped_junk += 1
                        from backend.collectors.sources.registry import (
                            record_junk_dropped,
                        )
                        record_junk_dropped()
                        continue

                    from backend.collectors.sources._dateparse import (
                        parse_listing_date,
                    )
                    docs.append(
                        {
                            "url": full_url,
                            "title": title,
                            "published_at": (
                                parse_listing_date(title)
                                or parse_listing_date(full_url)
                            ),
                            "type": "document",
                        }
                    )
    except Exception as exc:
        logger.warning("Generic scrape failed for %s: %s", portal_url, exc)

    logger.info(
        "Generic[%s]: discovered %d candidates, dropped %d junk",
        portal_url,
        len(docs),
        dropped_junk,
    )
    return docs[:15]


# ── PDF download + text extraction ──────────────────────────────────────────


async def download_pdf(url: str, tmpdir: str) -> str | None:
    """
    Download a PDF to a temp directory.
    Returns local file path or None if the URL is not a PDF / fails.
    """
    try:
        async with httpx.AsyncClient(
            timeout=60,
            follow_redirects=True,
            headers=_HTTP_HEADERS,
        ) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return None

            content_type = r.headers.get("content-type", "")
            if "pdf" not in content_type and not url.lower().endswith(".pdf"):
                return None

            pdf_path = os.path.join(tmpdir, f"doc_{abs(hash(url))}.pdf")
            with open(pdf_path, "wb") as f:
                f.write(r.content)
            return pdf_path

    except Exception as exc:
        logger.warning("PDF download failed for %s: %s", url, exc)
        return None


async def extract_text_from_pdf(
    pdf_path: str,
    is_scanned: bool = False,
) -> str | None:
    """
    Extract text from PDF.

    Strategy:
      1. OpenDataLoader PDF (Apache 2.0) — preferred, handles XY-Cut++ for
         multi-column layouts; uses hybrid mode for scanned docs.
      2. PyMuPDF — fallback for simple digital PDFs when OpenDataLoader is
         not installed.
    """
    import tempfile

    try:
        import opendataloader_pdf  # type: ignore[import-not-found]
    except ImportError:
        opendataloader_pdf = None

    if opendataloader_pdf is not None:
        try:
            output_dir = tempfile.mkdtemp()
            opendataloader_pdf.run(
                input_path=pdf_path,
                output_folder=output_dir,
                generate_markdown=True,
                debug=False,
            )
            for fname in os.listdir(output_dir):
                if fname.endswith(".md"):
                    with open(os.path.join(output_dir, fname)) as mf:
                        text = mf.read()
                    if text.strip():
                        return text
        except Exception as exc:
            logger.warning(
                "OpenDataLoader extraction failed (%s) — falling back to PyMuPDF",
                exc,
            )

    try:
        import fitz  # type: ignore[import-not-found]

        doc = fitz.open(pdf_path)
        text = "".join(page.get_text() for page in doc)
        doc.close()
        return text if text.strip() else None
    except Exception as exc:
        logger.warning("PyMuPDF extraction failed: %s", exc)
        return None


# ── Chunking for RAG ────────────────────────────────────────────────────────


def chunk_document(
    text: str,
    chunk_size: int = 1000,
    overlap: int = 100,
) -> list[dict]:
    """
    Split text into overlapping chunks for embedding.
    Each chunk dict: {index, text}.
    """
    if not text:
        return []

    if overlap >= chunk_size:
        overlap = chunk_size // 2

    chunks: list[dict] = []
    start = 0
    chunk_index = 0
    n = len(text)

    while start < n:
        end = min(start + chunk_size, n)
        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append({"index": chunk_index, "text": chunk_text})
            chunk_index += 1

        if end >= n:
            break
        start = end - overlap

    return chunks


if __name__ == "__main__":
    """Dry-run: list candidates from each seeded portal without downloading."""
    import asyncio

    async def main():
        portals = [
            ("https://pib.gov.in", "press_release"),
            ("https://goir.telangana.gov.in", "government_order"),
            ("https://cag.gov.in", "audit_report"),
        ]
        for url, dtype in portals:
            print(f"\n=== {url} ({dtype}) ===")
            docs = await fetch_document_urls(url, dtype, since_days=2)
            for d in docs[:10]:
                print(f"  · {d['title'][:80]}")
            print(f"  TOTAL: {len(docs)}")

    asyncio.run(main())
