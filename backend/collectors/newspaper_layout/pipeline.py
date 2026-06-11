"""
Newspaper extraction pipeline — PP-Structure edition.

Tier 1  PaddleOCR PP-Structure: layout detection + OCR on rendered page images
        Primary path for all CareersWave PDFs (scanned newspaper images).

Tier 2  Groq Vision fallback: used when PP-Structure is unavailable (ImportError)
        or when it returns 0 articles (e.g. very low-quality scan).

Tier 3  Groq text-LLM normalization: always runs after successful extraction to
        clean OCR noise, detect language, and identify section.
"""
from __future__ import annotations

import logging

from .ocr import extract_regions
from .assembler import assemble_articles
from .normalizer import normalize_articles

logger = logging.getLogger(__name__)


async def extract_articles_from_pdf(
    pdf_path: str,
    paper_id: str | None = None,
    language: str = "en",
    max_pages: int = 24,
    skip_normalization: bool = False,
) -> list[dict]:
    """
    Extract articles from a scanned (or digital-born) newspaper PDF.

    Returns [{headline, text, bounding_box, page_number, section,
              detected_language, continuation_page}]

    Parameters
    ----------
    pdf_path          Local path to the PDF file.
    paper_id          Informational slug used in log messages.
    language          ISO 639-1 language hint passed to PP-Structure OCR engine
                      ('en', 'te', 'hi', …).
    max_pages         Cap on the number of pages to process.
    skip_normalization  Skip the Groq text-LLM pass. Faster; useful for tests.
    """
    # ── Tier 1: PP-Structure layout + OCR ────────────────────────────────
    try:
        pages_regions = extract_regions(pdf_path, lang=language, max_pages=max_pages)
        total = sum(len(p) for p in pages_regions)
        logger.info(
            "PP-Structure: %d regions across %d pages (paper=%s)",
            total, len(pages_regions), paper_id,
        )

        if total > 0:
            raw = assemble_articles(pages_regions)
            logger.info("Assembly: %d articles from %s", len(raw), pdf_path)

            if raw:
                if skip_normalization:
                    return raw
                return await normalize_articles(raw, language)

            logger.info("Assembly yielded 0 articles — falling back to Groq Vision")

    except ImportError as exc:
        logger.warning("PP-Structure not installed (%s) — falling back to Groq Vision", exc)
    except Exception as exc:
        logger.warning("PP-Structure failed for %s: %s — falling back to Groq Vision", pdf_path, exc)

    # ── Tier 2: Groq Vision fallback ─────────────────────────────────────
    return await _groq_vision_fallback(pdf_path, max_pages)


async def _groq_vision_fallback(pdf_path: str, max_pages: int) -> list[dict]:
    try:
        from backend.collectors.newspaper_collector import _extract_via_groq_vision
        articles = await _extract_via_groq_vision(pdf_path, max_pages=max_pages)
        logger.info("Groq Vision fallback: %d articles from %s", len(articles), pdf_path)
        return articles
    except Exception as exc:
        logger.warning("Groq Vision fallback also failed: %s", exc)
        return []
