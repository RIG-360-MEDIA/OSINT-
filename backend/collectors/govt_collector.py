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
from urllib.parse import urljoin

import httpx

logger = logging.getLogger(__name__)


_HTTP_HEADERS = {
    "User-Agent": "RIGSurveillance/1.0 (+https://rig-surveillance.local)"
}


# ── Portal scrapers ─────────────────────────────────────────────────────────


async def fetch_document_urls(
    portal_url: str,
    document_type: str,
    since_days: int = 2,
) -> list[dict]:
    """
    Scrape a government portal for new document URLs.

    Returns list of dicts: {url, title, published_at, type}.
    """
    if "pib.gov.in" in portal_url:
        return await _scrape_pib(since_days)

    if "tggovernment" in portal_url or "tshc.gov.in" in portal_url:
        return await _scrape_tg_goms(since_days)

    return await _scrape_generic_pdfs(portal_url, since_days)


async def _scrape_pib(since_days: int) -> list[dict]:
    """Scrape PIB press releases page for document links."""
    docs: list[dict] = []
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
                    title = link.get_text(strip=True)
                    if title and len(title) > 10:
                        full_url = (
                            href
                            if href.startswith("http")
                            else urljoin("https://pib.gov.in/", href)
                        )
                        docs.append(
                            {
                                "url": full_url,
                                "title": title,
                                "published_at": None,
                                "type": "press_release",
                            }
                        )
    except Exception as exc:
        logger.warning("PIB scrape failed: %s", exc)

    return docs[:20]


async def _scrape_tg_goms(since_days: int) -> list[dict]:
    """Scrape Telangana GO.Ms portal for PDF links."""
    docs: list[dict] = []
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
                    docs.append(
                        {
                            "url": full_url,
                            "title": link.get_text(strip=True) or "GO.Ms",
                            "published_at": None,
                            "type": "government_order",
                        }
                    )
    except Exception as exc:
        logger.warning("Telangana GO.Ms scrape failed: %s", exc)

    return docs[:10]


async def _scrape_generic_pdfs(
    portal_url: str,
    since_days: int,
) -> list[dict]:
    """Fall-back scraper: collect any .pdf link from a portal page."""
    docs: list[dict] = []
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
                    docs.append(
                        {
                            "url": full_url,
                            "title": link.get_text(strip=True) or full_url,
                            "published_at": None,
                            "type": "document",
                        }
                    )
    except Exception as exc:
        logger.warning("Generic scrape failed for %s: %s", portal_url, exc)

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
            kwargs = {
                "input_path": [pdf_path],
                "output_dir": output_dir,
                "format": "markdown",
            }
            if is_scanned:
                kwargs["hybrid"] = "docling-fast"

            opendataloader_pdf.convert(**kwargs)

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
