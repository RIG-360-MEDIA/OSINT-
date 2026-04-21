"""
Newspaper clipping collector (P16 — Cutting Room).

Flow:
    1. Visit the CareersWave.in page for each configured newspaper.
    2. Extract today's PDF download URL from the page markup.
    3. Download the PDF.
    4. Use OpenDataLoader PDF (hybrid mode) to extract article
       regions with bounding boxes — PyMuPDF fallback if unavailable.
    5. Render each article region as a cropped PNG via PyMuPDF.
    6. Score each article for relevance to the user.
    7. Caller stores relevant articles as clippings with coordinates.
"""

import base64
import json
import logging
import os
import tempfile
from datetime import date

import httpx

logger = logging.getLogger(__name__)


async def get_pdf_url_from_careerswave(careerswave_url: str) -> str | None:
    """
    Scrape a CareersWave newspaper page and return today's PDF URL.

    CareersWave pages expose the actual newspaper PDF as an anchor tag
    pointing to the newspaper's own CDN. Prefer links whose href contains
    today's date in any of several common formats; fall back to the first
    PDF-looking anchor.
    """
    try:
        async with httpx.AsyncClient(
            timeout=30,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64) "
                    "Chrome/120.0.0.0"
                ),
            },
        ) as client:
            r = await client.get(careerswave_url)
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(r.text, "html.parser")

            today = date.today()
            date_str = today.strftime("%Y-%m-%d")
            date_str2 = today.strftime("%d-%m-%Y")
            date_str3 = today.strftime("%B-%d-%Y").lower()

            pdf_links: list[str] = []
            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                if ".pdf" in href.lower():
                    if (
                        date_str in href
                        or date_str2 in href
                        or date_str3 in href
                    ):
                        return href
                    pdf_links.append(href)

            if pdf_links:
                return pdf_links[0]

            # Fallback: explicit download button
            for btn in soup.find_all(
                ["button", "a"],
                string=lambda s: s and "download" in s.lower(),
            ):
                href = btn.get("href", "")
                if href and ".pdf" in href.lower():
                    return href

    except Exception as e:
        logger.warning(
            f"CareersWave scrape failed for {careerswave_url}: {e}"
        )
    return None


async def extract_articles_from_pdf(
    pdf_path: str,
    language: str = "en",
) -> list[dict]:
    """
    Extract individual articles from a newspaper PDF.

    Returns a list of dicts with keys:
        headline, text, bounding_box [l, b, r, t], page_number
    """
    articles: list[dict] = []

    try:
        import opendataloader_pdf

        output_dir = tempfile.mkdtemp()

        opendataloader_pdf.convert(
            input_path=[pdf_path],
            output_dir=output_dir,
            format="json",
            hybrid="docling-fast" if language != "en" else None,
        )

        for fname in os.listdir(output_dir):
            if not fname.endswith(".json"):
                continue
            with open(os.path.join(output_dir, fname)) as f:
                data = json.load(f)

            current: dict | None = None

            for element in data:
                elem_type = element.get("type", "")
                content = element.get("content", "")
                bbox = element.get("bounding box", [])
                page = element.get("page number", 1)

                if elem_type == "heading" and len(content) > 10:
                    if current:
                        articles.append(current)
                    current = {
                        "headline": content,
                        "text": "",
                        "bounding_box": bbox,
                        "page_number": page,
                    }
                elif current and elem_type in ("paragraph", "text"):
                    current["text"] += " " + content
                    if bbox and current["bounding_box"]:
                        cb = current["bounding_box"]
                        current["bounding_box"] = [
                            min(cb[0], bbox[0]),
                            min(cb[1], bbox[1]),
                            max(cb[2], bbox[2]),
                            max(cb[3], bbox[3]),
                        ]

            if current:
                articles.append(current)

    except ImportError:
        logger.info(
            "OpenDataLoader not available — using PyMuPDF fallback"
        )
        articles = _extract_with_pymupdf(pdf_path)

    except Exception as e:
        logger.warning(f"PDF article extraction failed: {e}")

    return articles


def _extract_with_pymupdf(pdf_path: str) -> list[dict]:
    """PyMuPDF fallback: treat each long text block as one article."""
    articles: list[dict] = []
    try:
        import fitz

        doc = fitz.open(pdf_path)

        for page_num, page in enumerate(doc, 1):
            blocks = page.get_text("blocks")
            for block in blocks:
                if block[6] != 0:  # skip image blocks
                    continue
                text = block[4].strip()
                if len(text) <= 100:
                    continue
                lines = text.split("\n")
                headline = lines[0]
                body = " ".join(lines[1:])
                articles.append(
                    {
                        "headline": headline[:200],
                        "text": body,
                        "bounding_box": list(block[:4]),
                        "page_number": page_num,
                    }
                )
        doc.close()
    except Exception as e:
        logger.warning(f"PyMuPDF fallback failed: {e}")
    return articles


def render_article_clipping(
    pdf_path: str,
    page_number: int,
    bbox: list[float],
    scale: float = 2.0,
) -> str | None:
    """
    Render a single article region as a base64-encoded PNG.

    bbox is [left, bottom, right, top] in PDF points (PyMuPDF uses
    top-down y, so we flip using page height).
    """
    try:
        import fitz

        doc = fitz.open(pdf_path)
        page = doc[page_number - 1]

        page_height = page.rect.height
        rect = fitz.Rect(
            bbox[0],
            page_height - bbox[3],
            bbox[2],
            page_height - bbox[1],
        )
        # Small padding around the article
        rect = rect + fitz.Rect(-5, -5, 5, 5)

        mat = fitz.Matrix(scale, scale)
        clip = page.get_pixmap(matrix=mat, clip=rect)

        doc.close()

        img_bytes = clip.tobytes("png")
        return base64.b64encode(img_bytes).decode("utf-8")

    except Exception as e:
        logger.warning(f"Clipping render failed: {e}")
        return None


async def is_relevant_to_user(
    headline: str,
    text: str,
    user_entities: list[str],
    user_geo: str,
) -> tuple[bool, float, str]:
    """
    Newsprint-specific relevance scorer.

    Lighter than `relevance_scorer.compute_stage1_score` because we
    don't have a full user_profile row or source_geo_states for
    newspapers — entity + geo + political-term match is enough to
    gate clipping storage.

    Returns (is_relevant, score, reason).
    """
    combined = (headline or "") + " " + (text or "")
    combined_lower = combined.lower()

    score = 0.0
    reasons: list[str] = []

    for entity in user_entities:
        if entity and entity.lower() in combined_lower:
            score += 0.4
            reasons.append(f"{entity} mentioned")
            break

    if user_geo and user_geo.lower() in combined_lower:
        score += 0.3
        reasons.append(f"Covers {user_geo}")

    political_terms = (
        "government", "minister", "cm", "chief minister", "assembly",
        "cabinet", "policy", "scheme", "budget", "court", "order",
        "telangana", "hyderabad", "revanth", "kcr", "brs",
        "congress", "bjp",
    )
    for term in political_terms:
        if term in combined_lower:
            score += 0.1
            break

    reason_text = ". ".join(reasons) if reasons else "Matched geography coverage"
    return score >= 0.3, score, reason_text
