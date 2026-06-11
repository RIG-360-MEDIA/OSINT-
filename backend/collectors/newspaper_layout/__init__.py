"""
Newspaper layout extraction pipeline (PP-Structure edition).

Primary path:   PaddleOCR PP-Structure → article assembly → LLM normalization
Fallback path:  Groq Vision (scanned PDFs where PP-Structure fails)

Public API
----------
extract_articles_from_pdf(pdf_path, paper_id, language, max_pages) -> list[dict]
"""
from .pipeline import extract_articles_from_pdf
from .ocr import extract_regions, OCRRegion
from .assembler import assemble_articles

__all__ = [
    "extract_articles_from_pdf",
    "extract_regions",
    "OCRRegion",
    "assemble_articles",
]
