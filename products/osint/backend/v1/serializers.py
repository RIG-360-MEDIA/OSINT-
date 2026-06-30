"""Public response shaping — the outward field whitelist.

Belt-and-braces with queries.py: even though the SQL already selects only
safe columns, every value a client sees is assembled here by explicit key, so
adding a column to a query can never accidentally leak it to a client. Only
the documented fields are emitted; internal helpers (collected_at, raw geo)
are dropped or normalised.
"""
from __future__ import annotations

from typing import Any

_SUMMARY_MAX = 400


def _iso(dt: Any) -> str | None:
    return dt.isoformat() if dt is not None and hasattr(dt, "isoformat") else None


def _clip(text_val: Any, n: int = _SUMMARY_MAX) -> str | None:
    if not text_val:
        return None
    s = str(text_val).strip()
    return (s[: n - 1] + "…") if len(s) > n else s


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
        "summary": _clip(row.get("summary")),
        "source": row.get("source"),
        "language": row.get("language"),
        "url": row.get("url"),
        "geo": row.get("geo_primary") or None,
        "published_at": _iso(row.get("published_at")),
    }
    if entities is not None:
        out["entities"] = [serialize_entity(e) for e in entities]
    return out


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


def serialize_sentiment(split: dict[str, Any], subject: str, window_days: int) -> dict[str, Any]:
    total = split.get("total", 0)
    return {
        "subject": subject,
        "window_days": window_days,
        "total": total,
        "split": {
            "supportive": split.get("supportive", 0),
            "neutral": split.get("neutral", 0),
            "critical": split.get("critical", 0),
        },
        "net_lean": split.get("net_lean", 0.0),
        "basis": (
            "Sampled estimate from classified, entity-linked coverage — directed "
            "stance toward the subject, not an exhaustive census."
        ),
    }
