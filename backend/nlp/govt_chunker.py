"""
Whole-document section-aware chunker for govt PDFs.

OpenDataLoader produces markdown with #/##/### headings. We split on heading
boundaries first, then within long sections by sentence boundaries with target
~800 chars and 150-char overlap. Each chunk gets section_heading, start_char,
end_char metadata for citation precision.

Cap: 300 chunks per document. For monsters (CAG audit reports can be 500 pages
producing >1000 chunks), we summarize trailing sections into a single chunk.
"""
from __future__ import annotations

import re

# Heading regex — markdown # at start of line, 1-6 hashes, then space, then text
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
# Sentence-ish boundaries — period/?/! followed by whitespace + capital, OR newline+newline
_SENT_BOUNDARY_RE = re.compile(
    r"(?<=[.!?])\s+(?=[A-Z\u0900-\u097F\u0C00-\u0C7F])|\n\n+"
)

DEFAULT_TARGET = 800
DEFAULT_OVERLAP = 150
MAX_CHUNKS = 300
TAIL_CHUNK_CAP_CHARS = 8000


def _split_sections(text: str) -> list[tuple[str, str, int]]:
    """Split markdown text on heading boundaries.

    Returns list of (heading, section_body, start_char_offset_in_doc).
    """
    if not text:
        return []
    headings = list(_HEADING_RE.finditer(text))
    if not headings:
        return [("", text, 0)]
    sections: list[tuple[str, str, int]] = []
    # Preamble before first heading
    if headings[0].start() > 0:
        preamble = text[: headings[0].start()].strip()
        if preamble:
            sections.append(("", preamble, 0))
    for i, m in enumerate(headings):
        heading = m.group(2).strip()[:200]
        body_start = m.end()
        body_end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        body = text[body_start:body_end].strip()
        if body:
            sections.append((heading, body, body_start))
    return sections


def _chunk_section(
    heading: str,
    body: str,
    body_offset: int,
    target: int = DEFAULT_TARGET,
    overlap: int = DEFAULT_OVERLAP,
) -> list[dict]:
    """Sentence-boundary chunking within a single section."""
    if len(body) <= target:
        return [{
            "heading": heading,
            "text": body,
            "start_char": body_offset,
            "end_char": body_offset + len(body),
        }]
    chunks: list[dict] = []
    pos = 0
    while pos < len(body):
        end = min(pos + target, len(body))
        # Snap end to nearest sentence boundary if close
        if end < len(body):
            window = body[pos:min(end + 200, len(body))]
            boundaries = [m.end() for m in _SENT_BOUNDARY_RE.finditer(window)]
            ideal = target
            best = (
                min(boundaries, key=lambda b: abs(b - ideal))
                if boundaries else None
            )
            if best is not None and abs(best - ideal) <= 200:
                end = pos + best
        snippet = body[pos:end].strip()
        if snippet:
            chunks.append({
                "heading": heading,
                "text": snippet,
                "start_char": body_offset + pos,
                "end_char": body_offset + end,
            })
        if end >= len(body):
            break
        pos = max(pos + 1, end - overlap)
    return chunks


def chunk_document_smart(
    text: str,
    *,
    target: int = DEFAULT_TARGET,
    overlap: int = DEFAULT_OVERLAP,
) -> list[dict]:
    """Whole-doc section-aware chunker.

    Returns list of dicts: {index, text, section_heading, start_char, end_char}.
    Capped at MAX_CHUNKS (300). For oversized docs, the last chunk concatenates
    trailing sections so coverage isn't lost entirely.
    """
    if not text:
        return []
    sections = _split_sections(text)
    raw_chunks: list[dict] = []
    for heading, body, offset in sections:
        raw_chunks.extend(_chunk_section(heading, body, offset, target, overlap))
        if len(raw_chunks) > MAX_CHUNKS * 2:
            # safety: don't allocate millions
            break
    if not raw_chunks:
        return []
    if len(raw_chunks) > MAX_CHUNKS:
        head = raw_chunks[: MAX_CHUNKS - 1]
        tail = raw_chunks[MAX_CHUNKS - 1:]
        tail_text = "\n\n".join(c["text"] for c in tail)
        raw_chunks = head + [{
            "heading": "(remainder)",
            "text": tail_text[:TAIL_CHUNK_CAP_CHARS],
            "start_char": tail[0]["start_char"],
            "end_char": tail[-1]["end_char"],
        }]
    # Reindex + rename heading → section_heading
    for i, c in enumerate(raw_chunks):
        c["index"] = i
        c["section_heading"] = c.pop("heading", None) or None
    return raw_chunks
