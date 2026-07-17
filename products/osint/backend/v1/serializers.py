"""Public response shaping — the outward field whitelist.

Belt-and-braces with queries.py: even though the SQL already selects only
safe columns, every value a client sees is assembled here by explicit key, so
adding a column to a query can never accidentally leak it to a client. Only
the documented fields are emitted; internal helpers (collected_at, raw geo)
are dropped or normalised.
"""
from __future__ import annotations

from typing import Any

# Ceiling on `summary` / `summary_original`, matched to LEAD_TEXT_MAX_CHARS
# (2000) in the collectors -- i.e. the API never truncates a summary below what
# ingest actually stores. The API reference states no length limit, so this is
# ours to choose.
#
# Raised from 400 on 2026-07-17. At 400 the API was clipping 58% of summaries
# (p50 length 513) -- and once `summary` prefers the LLM-written English
# summary_executive (see queries._SUMMARY_SQL), whose median runs well past
# 400, a 400-char ceiling would have cut most English summaries mid-sentence.
# At 2000 only ~3.9% are clipped, and those keep the ellipsis below.
_SUMMARY_MAX = 2000


def _iso(dt: Any) -> str | None:
    return dt.isoformat() if dt is not None and hasattr(dt, "isoformat") else None


def _clip(text_val: Any, n: int = _SUMMARY_MAX) -> str | None:
    if not text_val:
        return None
    s = str(text_val).strip()
    return (s[: n - 1] + "…") if len(s) > n else s


# Raw stance value -> client label. positive->supportive, negative->critical
# (locked vocab, kept in sync with queries._STANCE_SETS).
_STANCE_LABEL = {
    "supportive": "supportive", "positive": "supportive",
    "critical": "critical", "negative": "critical",
    "neutral": "neutral",
}


def _stance_label(raw: Any) -> str | None:
    return _STANCE_LABEL.get(str(raw).strip().lower()) if raw else None


def _as_float(v: Any) -> float | None:
    try:
        return round(float(v), 3) if v is not None else None
    except (TypeError, ValueError):
        return None


def _source_flags(row: dict[str, Any]) -> dict[str, Any]:
    """Source-transparency signals — NOT a truth verdict. `political_lean` shown only
    when classified; `low_credibility` = outlet is on our curated low-cred list
    (absence is not an endorsement). `coordinated_coverage` is a planned follow-up."""
    flags: dict[str, Any] = {"low_credibility": bool(row.get("low_credibility"))}
    # Only surface a real political lean — reject garbage values like 'state'/'unknown'.
    lean = str(row.get("political_lean") or "").strip().lower()
    if lean in ("left", "lean-left", "left-center", "center", "centre",
                "right-center", "lean-right", "right"):
        flags["political_lean"] = lean
    return flags


def serialize_entity(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "type": row.get("type"),
    }


def serialize_article(row: dict[str, Any], entities: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": row.get("id"),
        "headline": row.get("headline"),
        # summary/full_text are English (translated-preferred); *_original are the native
        # language; `language` is the source-language tag — so analysts read English and
        # clients can render the original Telugu/Urdu/Hindi.
        "summary": _clip(row.get("summary")),
        "full_text": row.get("full_text") or None,
        "summary_original": _clip(row.get("summary_original")) or None,
        "full_text_original": row.get("full_text_original") or None,
        "source": row.get("source"),
        "language": row.get("language"),
        "url": row.get("url"),
        "geo": row.get("geo_primary") or None,
        "story_id": row.get("story_id") or None,
        "sentiment": (
            {"label": _stance_label(row.get("stance")), "intensity": _as_float(row.get("intensity"))}
            if _stance_label(row.get("stance")) else None
        ),
        "source_flags": _source_flags(row),
        "api_ready": bool(row.get("api_ready")),
        "published_at": _iso(row.get("published_at")),
        "last_updated": _iso(row.get("last_updated")),
    }
    if entities is not None:
        out["entities"] = [serialize_entity(e) for e in entities]
    return out


def serialize_story(row: dict[str, Any]) -> dict[str, Any]:
    """A surfaceable grouped story. `outlets` is the deduped independent-outlet count;
    `top_outlets` the heaviest 3 by article volume. Per-story sentiment is not carried
    here (keeper column is sparse) — it's assembled on the /stories/{id} detail."""
    langs = row.get("languages")
    return {
        "id": row.get("id"),
        "title": row.get("title"),
        "topic": row.get("topic"),
        "subject_country": row.get("subject_country"),
        "subject_region": row.get("subject_region"),
        "event_type": row.get("event_type") or None,
        "article_count": row.get("article_count"),
        "outlets": row.get("outlets"),
        "top_outlets": list(row.get("top_outlets") or []),
        "languages": langs if isinstance(langs, dict) else None,
        "importance": _as_float(row.get("importance_score")),
        "representative_article_id": row.get("representative_article_id"),
        "first_seen": _iso(row.get("first_seen_at")),
        "last_updated": _iso(row.get("last_seen_at")),
    }


def serialize_story_detail(data: dict[str, Any]) -> dict[str, Any]:
    """Full story: the list card + a chronological member timeline + full outlet breakdown."""
    out = serialize_story(data.get("story") or {})
    out["outlets_breakdown"] = [
        {"name": o.get("name"), "count": o.get("count")} for o in (data.get("outlets") or [])
    ]
    # Full 16-field parity with /articles (enriched upstream), plus the timeline flag.
    out["timeline"] = [
        {**serialize_article(t), "is_representative": bool(t.get("is_representative"))}
        for t in (data.get("timeline") or [])
    ]
    return out


def serialize_clip_transcript(row: dict[str, Any]) -> dict[str, Any]:
    """A YouTube clip's FULL transcript (assembled from its segments). Served only
    on-demand for a clip the caller surfaced via a keyword/entity query."""
    return {
        "type": "clip",
        "id": row.get("id"),
        "video_id": row.get("video_id"),
        "title": row.get("video_title"),
        "channel": row.get("channel_name"),
        "url": row.get("video_url"),
        "published_at": _iso(row.get("video_published_at")),
        "language": row.get("transcript_language"),
        "transcript_source": row.get("transcript_source"),
        "segment_count": row.get("segment_count"),
        "transcript": row.get("transcript"),
    }


def serialize_cutting(row: dict[str, Any]) -> dict[str, Any]:
    """A newspaper cutting with full text — native + English, mirroring the article
    shape so newspapers read as a first-class pillar."""
    ed = row.get("edition_date")
    return {
        "type": "cutting",
        "id": row.get("id"),
        "headline": row.get("headline"),
        "headline_original": row.get("headline_original"),
        "subheadline": row.get("subheadline"),
        "full_text": row.get("full_text"),
        "full_text_original": row.get("full_text_original"),
        "source": row.get("source"),
        "section": row.get("section"),
        "language": row.get("language"),
        "geo": row.get("geo") or None,
        "page_number": row.get("page_number"),
        "edition_date": ed.isoformat() if ed is not None and hasattr(ed, "isoformat") else None,
        "published_at": ed.isoformat() if ed is not None and hasattr(ed, "isoformat") else None,
    }


def serialize_coverage_item(row: dict[str, Any]) -> dict[str, Any]:
    """A single item in the unified cross-pillar feed (article | clip | cutting)."""
    return {
        "type": row.get("type"),
        "id": row.get("id"),
        "headline": row.get("headline"),
        "source": row.get("source"),
        "language": row.get("language"),
        "url": row.get("url"),
        "published_at": _iso(row.get("published_at")),
    }


def serialize_outlets(subject: str, outlets: list[dict[str, Any]], window_days: int) -> dict[str, Any]:
    return {
        "subject": subject,
        "window_days": window_days,
        "outlets": [
            {"name": o.get("name"), "count": o.get("count"), "net_lean": o.get("net_lean")}
            for o in outlets
        ],
        "basis": (
            "Per-outlet volume (articles mentioning the subject) + net_lean "
            "(supportive−critical) from classified, entity-linked stances — a sample."
        ),
    }


def _shape_split(s: dict[str, Any]) -> dict[str, Any]:
    """One two-field sentiment block: tone split + net_lean + the impact dimension.
    Carries clip_ids through when present (the on-demand YouTube pillar's drill-down)."""
    out: dict[str, Any] = {
        "total": s.get("total", 0),
        "split": {
            "supportive": s.get("supportive", 0),
            "neutral": s.get("neutral", 0),
            "critical": s.get("critical", 0),
        },
        "net_lean": s.get("net_lean", 0.0),
        "impact": s.get("impact"),
    }
    if s.get("clip_ids") is not None:
        out["clip_ids"] = s["clip_ids"]
    return out


def serialize_sentiment(
    split: dict[str, Any], subject: str, window_days: int,
    daily: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "subject": subject,
        "window_days": window_days,
        **_shape_split(split),  # combined headline: total / split / net_lean / impact
        "by_pillar": {k: _shape_split(v) for k, v in (split.get("by_pillar") or {}).items()},
        "daily": daily or [],
        "basis": (
            "Two-field sentiment (stance=tone, impact=good/bad-for-subject) from the "
            "gold-tuned engine, split by pillar (news articles vs newspaper cuttings). "
            "A classified, entity-linked sample — not an exhaustive census."
        ),
    }
