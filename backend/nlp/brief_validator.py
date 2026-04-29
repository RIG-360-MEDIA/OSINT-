"""
Brief citation validator and section-quality helpers.

Two responsibilities:

1. ``validate_citations`` — parse a generated section's markdown for every
   citation marker and verify each refers to an item that was actually
   passed to the LLM as evidence. Hallucinated IDs are reported.

2. ``count_words`` — small utility used by the section-length-minimum
   check in :mod:`backend.nlp.brief_generator`.

Citation formats produced by the brief prompts (see CITATION_GUIDANCE):

  * ``[N]``                            — article index (1-based)
  * ``(Doc: <title-prefix>...)``       — government document
  * ``(Paper: <newspaper> <date>...)`` — newspaper clipping
  * ``(Social: <platform> @ <date>)``  — social post
  * ``(Video: <channel> @ <mm:ss>)``   — youtube clip

The validator does not require an exact string match for the four
prose-style cites — those are free-form labels the LLM constructs from
the evidence headers. We only enforce that *the referenced thing exists*
in the evidence (e.g. for ``[12]`` we check ``len(articles) >= 12``).

The validator is conservative — when in doubt, it accepts. Its purpose
is to catch obvious hallucinations like ``[99]`` when only 30 articles
were supplied, not to police every prose detail.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable


# ── Regexes ──────────────────────────────────────────────────────────────────
# ``[N]`` where N is 1-3 digits. Excludes things like [Doc 1] or [Paper 2]
# by requiring the whole bracketed content to be digits.
_ARTICLE_CITE_RE = re.compile(r"\[(\d{1,3})\]")
_DOC_CITE_RE = re.compile(r"\(Doc:\s*[^)]+?\)", re.IGNORECASE)
_PAPER_CITE_RE = re.compile(r"\(Paper:\s*[^)]+?\)", re.IGNORECASE)
_SOCIAL_CITE_RE = re.compile(r"\(Social:\s*[^)]+?\)", re.IGNORECASE)
_VIDEO_CITE_RE = re.compile(r"\(Video:\s*[^)]+?\)", re.IGNORECASE)


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of running ``validate_citations`` over one piece of text."""

    section_name: str
    article_indexes_seen: tuple[int, ...]
    invalid_article_indexes: tuple[int, ...]
    doc_cite_count: int
    paper_cite_count: int
    social_cite_count: int
    video_cite_count: int
    issues: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_valid(self) -> bool:
        """True when no clearly-hallucinated cites were found."""
        return not self.invalid_article_indexes and not self.issues

    @property
    def total_cites(self) -> int:
        return (
            len(self.article_indexes_seen)
            + self.doc_cite_count
            + self.paper_cite_count
            + self.social_cite_count
            + self.video_cite_count
        )


def validate_citations(
    section_name: str,
    text: str,
    *,
    article_count: int,
    govt_doc_count: int,
    newspaper_count: int,
    social_count: int,
    video_count: int,
) -> ValidationResult:
    """Validate every citation marker in ``text`` against the supplied evidence.

    Parameters
    ----------
    section_name:
        Human-readable section label (used in issue messages).
    text:
        The generated section markdown.
    article_count, govt_doc_count, newspaper_count, social_count, video_count:
        Number of items the LLM had access to in each pillar. Index-style
        cites (``[N]``) must be ``<= article_count``. Prose-style cites
        (``Doc:``, ``Paper:``, ``Social:``, ``Video:``) are allowed only
        when the corresponding pillar was non-empty.
    """
    if not text:
        return ValidationResult(
            section_name=section_name,
            article_indexes_seen=(),
            invalid_article_indexes=(),
            doc_cite_count=0,
            paper_cite_count=0,
            social_cite_count=0,
            video_cite_count=0,
            issues=("empty section",),
        )

    article_indexes = tuple(
        sorted({int(m.group(1)) for m in _ARTICLE_CITE_RE.finditer(text)})
    )
    invalid = tuple(i for i in article_indexes if i < 1 or i > article_count)

    doc_count = len(_DOC_CITE_RE.findall(text))
    paper_count = len(_PAPER_CITE_RE.findall(text))
    social_pat_count = len(_SOCIAL_CITE_RE.findall(text))
    video_count_seen = len(_VIDEO_CITE_RE.findall(text))

    issues: list[str] = []
    if doc_count and govt_doc_count == 0:
        issues.append(
            f"{doc_count} (Doc:…) cites but no govt docs in evidence"
        )
    if paper_count and newspaper_count == 0:
        issues.append(
            f"{paper_count} (Paper:…) cites but no newspaper clippings"
        )
    if social_pat_count and social_count == 0:
        issues.append(
            f"{social_pat_count} (Social:…) cites but no social posts"
        )
    if video_count_seen and video_count == 0:
        issues.append(
            f"{video_count_seen} (Video:…) cites but no video clips"
        )
    if invalid:
        issues.append(
            f"hallucinated article indexes: {list(invalid)} (only "
            f"{article_count} articles supplied)"
        )

    return ValidationResult(
        section_name=section_name,
        article_indexes_seen=article_indexes,
        invalid_article_indexes=invalid,
        doc_cite_count=doc_count,
        paper_cite_count=paper_count,
        social_cite_count=social_pat_count,
        video_cite_count=video_count_seen,
        issues=tuple(issues),
    )


def strip_invalid_citations(text: str, *, article_count: int) -> str:
    """Best-effort fix: remove sentences containing hallucinated ``[N]``.

    Used as the second-attempt fallback after a validation failure +
    one regen retry. Sentences are split on ``. ``, ``! ``, ``? ``;
    sentences whose article cites are all valid are kept verbatim.
    Sentences that contain at least one invalid index are dropped.
    """
    if not text:
        return text

    sentence_split = re.split(r"(?<=[.!?])\s+", text)
    kept: list[str] = []
    for sentence in sentence_split:
        bad = [
            int(m.group(1))
            for m in _ARTICLE_CITE_RE.finditer(sentence)
            if int(m.group(1)) < 1 or int(m.group(1)) > article_count
        ]
        if not bad:
            kept.append(sentence)
    return " ".join(kept).strip()


def count_words(text: str) -> int:
    """Cheap word counter used by the section-length-minimum check."""
    if not text:
        return 0
    return len(re.findall(r"\b\w+\b", text))


def build_id_allowlist(
    *,
    article_count: int,
    govt_doc_count: int,
    newspaper_count: int,
    social_count: int,
    video_count: int,
) -> str:
    """Return a short, prompt-ready string telling the LLM the allowed IDs.

    Inserted into each section prompt by :mod:`backend.nlp.brief_generator`
    so the model has an explicit list to honour. This is the prompt-side
    half of the citation validator — we *tell* the model what's allowed,
    then we *check* that it complied.
    """
    article_range = (
        f"[1]–[{article_count}]" if article_count else "(no articles)"
    )
    return (
        "ALLOWED CITATION IDS — only cite items that exist in the evidence:\n"
        f"  Article indexes: {article_range}\n"
        f"  Govt docs in evidence: {govt_doc_count}\n"
        f"  Newspaper clippings: {newspaper_count}\n"
        f"  Social posts: {social_count}\n"
        f"  Video clips: {video_count}\n"
        "Before answering, verify every bracketed [N] is in range and "
        "every (Doc:…) / (Paper:…) / (Social:…) / (Video:…) cite refers "
        "to an item present above. If unsure, omit the cite rather than "
        "invent one.\n"
    )


__all__ = [
    "ValidationResult",
    "validate_citations",
    "strip_invalid_citations",
    "count_words",
    "build_id_allowlist",
]
