"""backend.draftsmith._db_serialize — jsonb (de)serialisation helpers for db.py.

Split out of db.py to keep that module under the file-size budget. Pure
functions only: no I/O, no SQL. Every function here either turns a frozen
models.py dataclass into a JSON-safe structure for a jsonb column, or turns
a jsonb value (already-parsed dict/list OR a raw JSON string, depending on
driver behaviour) back into the matching frozen dataclass.

Never trust the shape of a jsonb value coming back from the database: this
module always validates via `load_maybe_json` before touching keys.
"""
from __future__ import annotations

import dataclasses
import json
from datetime import datetime
from typing import Any, Mapping, Optional, Sequence

from backend.draftsmith.models import (
    BeatVerdictReport,
    Dials,
    Directives,
    Draft,
    DraftBeat,
    DraftVersion,
    EvidenceItem,
    Flag,
    ImageCandidate,
    KeyFact,
    PlanEntity,
    PullQuote,
    QueryPlan,
    SourceQueries,
    TimeWindow,
    VerifyReport,
    Violation,
)


def _json_default(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"{type(obj).__name__} is not JSON serialisable")


def to_json(dc: Any) -> str:
    """Serialise a frozen dataclass (or plain value) to a JSON string, ready
    to CAST(:param AS jsonb) in a parameterised query."""
    payload = dataclasses.asdict(dc) if dataclasses.is_dataclass(dc) else dc
    return json.dumps(payload, default=_json_default)


def load_maybe_json(value: Any) -> Any:
    """Normalise a jsonb column value to a parsed dict/list/None.

    Depending on driver/session configuration, a jsonb column fetched via a
    raw SQLAlchemy `text()` query can come back either already-parsed
    (dict/list) or as the raw JSON string. Handle both so callers never have
    to care which."""
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        if not value.strip():
            return None
        return json.loads(value)
    raise TypeError(f"Unexpected jsonb value type: {type(value).__name__}")


# --- Dials --------------------------------------------------------------

def dials_from_row(value: Optional[Mapping[str, Any]]) -> Dials:
    return Dials.from_json(value)


# --- QueryPlan (and its nested shapes) -----------------------------------

def _plan_entity_from_dict(d: Mapping[str, Any]) -> PlanEntity:
    return PlanEntity(
        name=d["name"],
        type=d["type"],
        disambiguation=d.get("disambiguation", ""),
        aliases=tuple(d.get("aliases") or ()),
        alternates=tuple(d.get("alternates") or ()),
    )


def _directives_from_dict(d: Mapping[str, Any]) -> Directives:
    return Directives(
        angle=d.get("angle"),
        must_include=tuple(d.get("must_include") or ()),
        must_avoid=tuple(d.get("must_avoid") or ()),
        tone_notes=d.get("tone_notes"),
        length_hint=d.get("length_hint"),
        other_constraints=tuple(d.get("other_constraints") or ()),
    )


def _time_window_from_dict(d: Mapping[str, Any]) -> TimeWindow:
    return TimeWindow(
        from_days_ago=d.get("from_days_ago", 0),
        to_days_ago=d.get("to_days_ago"),
        rationale=d.get("rationale", ""),
    )


def _source_queries_from_dict(d: Mapping[str, Any]) -> SourceQueries:
    return SourceQueries(
        warehouse_fts=tuple(d.get("warehouse_fts") or ()),
        warehouse_vector_seed=d.get("warehouse_vector_seed", ""),
        facts_cluster_hint=d.get("facts_cluster_hint", ""),
        web=tuple(d.get("web") or ()),
        youtube=tuple(d.get("youtube") or ()),
        twitter=tuple(d.get("twitter") or ()),
        reddit=tuple(d.get("reddit") or ()),
        tiktok=tuple(d.get("tiktok") or ()),
        telegram=tuple(d.get("telegram") or ()),
        instagram=tuple(d.get("instagram") or ()),
        wechat=tuple(d.get("wechat") or ()),
        wikipedia_titles=tuple(d.get("wikipedia_titles") or ()),
    )


def query_plan_from_json(value: Optional[Mapping[str, Any]]) -> Optional[QueryPlan]:
    if not value:
        return None
    return QueryPlan(
        topic_summary=value.get("topic_summary", ""),
        entities=tuple(_plan_entity_from_dict(e) for e in value.get("entities") or ()),
        directives=_directives_from_dict(value.get("directives") or {}),
        time_window=_time_window_from_dict(value.get("time_window") or {}),
        queries=_source_queries_from_dict(value.get("queries") or {}),
        geo_hints=tuple(value.get("geo_hints") or ()),
        language_hints=tuple(value.get("language_hints") or ()),
    )


# --- EvidenceItem ---------------------------------------------------------

def evidence_item_from_row(row: Mapping[str, Any]) -> EvidenceItem:
    return EvidenceItem(
        source_id=row["source_id"],
        source_type=row["source_type"],
        trust_tier=row["trust_tier"],
        text=row["text_snapshot"],
        title=row.get("title"),
        url=row.get("url"),
        outlet=row.get("outlet"),
        author=row.get("author"),
        published_at=row.get("published_at"),
        relevance=row.get("relevance") if row.get("relevance") is not None else 0.0,
        extra=load_maybe_json(row.get("raw")) or {},
    )


# --- Draft / DraftVersion -------------------------------------------------

def _draft_beat_from_dict(d: Mapping[str, Any]) -> DraftBeat:
    return DraftBeat(
        subhead=d["subhead"], text=d["text"],
        source_ids=tuple(d.get("source_ids") or ()),
    )


def _key_fact_from_dict(d: Mapping[str, Any]) -> KeyFact:
    return KeyFact(fact=d["fact"], source_ids=tuple(d.get("source_ids") or ()))


def _pull_quote_from_dict(d: Optional[Mapping[str, Any]]) -> Optional[PullQuote]:
    if not d:
        return None
    return PullQuote(
        text=d.get("text", ""), speaker=d.get("speaker", ""),
        source_id=d.get("source_id", ""),
    )


def _violation_from_dict(d: Mapping[str, Any]) -> Violation:
    return Violation(
        span=d["span"], why=d["why"], severity=d["severity"],
        expected_source_ids=tuple(d.get("expected_source_ids") or ()),
    )


def _beat_verdict_report_from_dict(d: Mapping[str, Any]) -> BeatVerdictReport:
    return BeatVerdictReport(
        index=d["index"], verdict=d["verdict"],
        violations=tuple(_violation_from_dict(v) for v in d.get("violations") or ()),
    )


def verify_report_from_json(value: Optional[Mapping[str, Any]]) -> Optional[VerifyReport]:
    if not value:
        return None
    return VerifyReport(
        verdict=value["verdict"],
        beats=tuple(_beat_verdict_report_from_dict(b) for b in value.get("beats") or ()),
    )


def _draft_from_row(row: Mapping[str, Any]) -> Draft:
    beats = tuple(_draft_beat_from_dict(b) for b in load_maybe_json(row["beats"]) or ())
    key_facts = tuple(_key_fact_from_dict(k) for k in load_maybe_json(row.get("key_facts")) or ())
    pull_quote = _pull_quote_from_dict(load_maybe_json(row.get("pull_quote")))
    unsourced_gaps = tuple(load_maybe_json(row.get("unsourced_gaps")) or ())
    return Draft(
        headline=row["headline"], dek=row.get("dek") or "", beats=beats,
        key_facts=key_facts, pull_quote=pull_quote, unsourced_gaps=unsourced_gaps,
    )


def draft_version_from_row(row: Mapping[str, Any]) -> DraftVersion:
    return DraftVersion(
        version=row["version"], kind=row["kind"], draft=_draft_from_row(row),
        verify_report=verify_report_from_json(load_maybe_json(row.get("verify_report"))),
        created_by=row["created_by"], created_at=row.get("created_at"),
    )


# --- Flag ------------------------------------------------------------------

def flag_from_row(row: Mapping[str, Any]) -> Flag:
    return Flag(
        id=str(row["id"]), beat_index=row["beat_index"], span=row["span"],
        severity=row["severity"], reason=row["reason"],
        source_ids=tuple(row.get("source_ids") or ()),
        status=row["status"], resolved_by=row.get("resolved_by"),
        resolution_note=row.get("resolution_note"),
    )


# --- ImageCandidate ----------------------------------------------------------

def image_candidate_from_row(row: Mapping[str, Any]) -> ImageCandidate:
    return ImageCandidate(
        id=str(row["id"]), slot=row["slot"], origin=row["origin"], url=row["url"],
        thumb_url=row.get("thumb_url"), license=row.get("license"),
        license_url=row.get("license_url"), attribution=row.get("attribution"),
        needs_license_review=bool(row.get("needs_license_review", False)),
        selected=bool(row.get("selected", False)),
    )
