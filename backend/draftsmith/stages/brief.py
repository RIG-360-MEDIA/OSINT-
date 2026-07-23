"""draftsmith.stages.brief — Stage 4: ranked evidence -> the writer's BRIEF.

    build_brief(selected_items, plan) -> BriefResult(text, stats)

Assembles the human/LLM-readable BRIEF the writer prompt (prompts.prompt_d_b,
its CITATION_RULES) expects: evidence grouped into "=== SECTION ===" blocks
of "[id] T<tier> <SOURCE_TYPE> <date> <outlet>: <text>" lines, plus a
"=== BINDING DIRECTIVES ===" block carrying the editor's angle/must-include/
must-avoid/tone straight from plan.directives.

Then, best-effort: try Headroom (pip headroom-ai) to further compress that
assembled text below what rank.py's pre-Headroom BUNDLE_TOKEN_CEILING already
enforces (see config.BUNDLE_TOKEN_CEILING's own comment — that ceiling is
explicitly "pre-Headroom"). The citation spine — every selected item's
source_id + trust_tier + published_at, together on one line — MUST survive
compression intact; if Headroom is not installed, raises, or drops any part
of the spine, the uncompressed BRIEF ships instead and the reason is recorded
in the returned stats. Compression is a token-budget nicety; it may never be
allowed to silently corrupt what the writer can cite.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from backend.draftsmith.models import Directives, EvidenceItem, QueryPlan
from backend.draftsmith.stages.rank import estimate_tokens

logger = logging.getLogger(__name__)

__all__ = ["build_brief", "BriefResult", "BriefStats"]

# Section order: highest-trust/most-structured families first, social last —
# gives the writer the load-bearing facts before the colour/lead material.
_SECTION_ORDER: tuple[str, ...] = (
    "story_fact",
    "corpus_article",
    "youtube_clip",
    "wikipedia",
    "web",
    "twitter",
    "reddit",
    "tiktok",
    "telegram",
    "instagram",
    "wechat",
)
_SECTION_LABELS: Mapping[str, str] = {
    "story_fact": "STORY FACTS",
    "corpus_article": "CORPUS ARTICLES",
    "youtube_clip": "YOUTUBE CLIPS",
    "wikipedia": "WIKIPEDIA",
    "web": "WEB",
    "twitter": "TWITTER",
    "reddit": "REDDIT",
    "tiktok": "TIKTOK",
    "telegram": "TELEGRAM",
    "instagram": "INSTAGRAM",
    "wechat": "WECHAT",
}


@dataclass(frozen=True)
class BriefStats:
    """Before/after token estimates + whether/why Headroom compression was
    used. Local to this stage — not part of the frozen models.py contract."""

    tokens_before: int
    tokens_after: int
    compressed: bool
    compression_reason: Optional[str]
    item_count: int
    directives_included: bool


@dataclass(frozen=True)
class BriefResult:
    text: str
    stats: BriefStats


# --- assembly ----------------------------------------------------------------


def _format_line(item: EvidenceItem) -> str:
    date_str = item.published_at.date().isoformat() if item.published_at else "n/d"
    header_parts = [f"[{item.source_id}]", f"T{item.trust_tier}", item.source_type.upper(), date_str]
    if item.outlet:
        header_parts.append(item.outlet)
    return " ".join(header_parts) + f": {item.text}"


def _anchor_block(plan: QueryPlan) -> str:
    lines = ["=== STORY ANCHOR ===", f"Topic: {plan.topic_summary}"]
    if plan.entities:
        lines.append("Key entities: " + ", ".join(e.name for e in plan.entities))
    if plan.geo_hints:
        lines.append("Geo: " + ", ".join(plan.geo_hints))
    if plan.time_window.rationale:
        lines.append(f"Window: {plan.time_window.rationale}")
    return "\n".join(lines)


def _directives_block(directives: Directives) -> str:
    if directives.is_empty:
        return ""
    lines = ["=== BINDING DIRECTIVES ==="]
    if directives.angle:
        lines.append(f"Angle: {directives.angle}")
    if directives.must_include:
        lines.append("Must include: " + "; ".join(directives.must_include))
    if directives.must_avoid:
        lines.append("Must avoid: " + "; ".join(directives.must_avoid))
    if directives.tone_notes:
        lines.append(f"Tone: {directives.tone_notes}")
    if directives.length_hint:
        lines.append(f"Length hint: ~{directives.length_hint} words")
    if directives.other_constraints:
        lines.append("Other constraints: " + "; ".join(directives.other_constraints))
    return "\n".join(lines)


def _assemble_text(items: Sequence[EvidenceItem], plan: QueryPlan) -> str:
    sections: list[str] = [_anchor_block(plan)]

    by_type: dict[str, list[EvidenceItem]] = {}
    for item in items:
        by_type.setdefault(item.source_type, []).append(item)

    for source_type in _SECTION_ORDER:
        group = by_type.get(source_type)
        if not group:
            continue
        ranked = sorted(group, key=lambda i: i.relevance, reverse=True)
        lines = [f"=== {_SECTION_LABELS[source_type]} ==="]
        lines.extend(_format_line(i) for i in ranked)
        sections.append("\n".join(lines))

    directives_block = _directives_block(plan.directives)
    if directives_block:
        sections.append(directives_block)

    return "\n\n".join(sections)


# --- Headroom compression (best-effort, never load-bearing) ----------------


def _headroom_compress(bundle_text: str) -> tuple[Optional[str], Optional[str]]:
    """Attempt Headroom compression of the assembled BRIEF text.

    Returns (compressed_text, None) on a usable result, or (None, reason)
    for every path that must fall back to the uncompressed bundle: package
    not installed, the call itself raising (Headroom's failure surface isn't
    documented anywhere in this codebase, so any exception is caught), or a
    response with no text we can extract. Citation-spine verification is the
    CALLER's job (_citation_spine_intact) — this function only reports
    whether Headroom produced *something*.
    """
    try:
        from headroom import compress  # type: ignore  # pip: headroom-ai
    except ImportError as exc:
        return None, f"headroom not installed: {exc}"

    try:
        result: Any = compress(json.dumps({"brief": bundle_text}, ensure_ascii=False))
    except Exception as exc:  # noqa: BLE001 — unknown 3rd-party failure surface; must never break the pipeline
        return None, f"headroom compression raised: {str(exc)[:200]}"

    candidate: Optional[str] = None
    if isinstance(result, Mapping):
        raw = result.get("brief") or result.get("text") or result.get("compressed")
        candidate = str(raw) if raw is not None else None
    elif isinstance(result, str):
        candidate = result
        try:
            parsed = json.loads(result)
            if isinstance(parsed, Mapping) and parsed.get("brief"):
                candidate = str(parsed["brief"])
        except (json.JSONDecodeError, TypeError):
            pass  # not JSON-wrapped; use the raw string as-is

    if not candidate:
        return None, "headroom returned no usable compressed text"
    return candidate, None


def _citation_spine_intact(candidate: str, items: Sequence[EvidenceItem]) -> bool:
    """True only if EVERY selected item's source_id, trust_tier, and (when
    present) published_at date all still appear together on one line of
    `candidate` — i.e. Headroom compressed prose without severing a
    citation handle from the tier/date that qualifies it."""
    lines = candidate.splitlines()
    for item in items:
        marker = f"[{item.source_id}]"
        matches = [ln for ln in lines if marker in ln]
        if not matches:
            return False
        line = matches[0]
        if f"T{item.trust_tier}" not in line:
            return False
        if item.published_at is not None:
            date_str = item.published_at.date().isoformat()
            if date_str not in line:
                return False
    return True


# --- entry point -------------------------------------------------------------


def build_brief(selected_items: Sequence[EvidenceItem], plan: QueryPlan) -> BriefResult:
    """Stage 4 — the rank stage's selection -> the frozen BRIEF string the
    writer prompt is built around, plus token/compression stats.

    Never raises on a Headroom failure (see _headroom_compress /
    _citation_spine_intact docstrings) — only a missing `plan` is a
    programming error worth raising over.
    """
    if plan is None:
        raise ValueError("build_brief: plan is required")

    items = list(selected_items)
    assembled = _assemble_text(items, plan)
    tokens_before = estimate_tokens(assembled)

    compressed, reason = _headroom_compress(assembled)
    if compressed is not None and _citation_spine_intact(compressed, items):
        final_text = compressed
        used_compression = True
        compression_reason: Optional[str] = None
    else:
        final_text = assembled
        used_compression = False
        compression_reason = reason or "compressed bundle lost the citation spine"
        if compressed is not None:
            logger.warning(
                "brief: discarding Headroom output — %s", compression_reason
            )

    stats = BriefStats(
        tokens_before=tokens_before,
        tokens_after=estimate_tokens(final_text),
        compressed=used_compression,
        compression_reason=compression_reason,
        item_count=len(items),
        directives_included=not plan.directives.is_empty,
    )
    return BriefResult(text=final_text, stats=stats)
