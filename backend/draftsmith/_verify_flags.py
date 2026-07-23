"""backend.draftsmith._verify_flags — VerifyReport -> Flag[] projection.

Pure function shared by worker.py (after every verify/repair pass) and
api/routes_draft.py (after an editor-triggered re-verify). Kept out of both
call sites so the "how do violations become flags" rule lives in exactly one
place. Not part of the frozen contract in models.py — just a small shared
helper, same spirit as _db_serialize.py.
"""
from __future__ import annotations

from backend.draftsmith.models import Flag, VerifyReport


def flags_from_report(report: VerifyReport) -> list[Flag]:
    """Flatten every beat's violations into draft Flag objects.

    `id` is left blank and `status` left at its default ('open') — db.create_flags
    only reads beat_index/span/severity/reason/source_ids off each Flag; the DB
    assigns the real id and status on INSERT.
    """
    flags: list[Flag] = []
    for beat in report.beats:
        for violation in beat.violations:
            flags.append(
                Flag(
                    id="",
                    beat_index=beat.index,
                    span=violation.span,
                    severity=violation.severity,
                    reason=violation.why,
                    source_ids=tuple(violation.expected_source_ids),
                )
            )
    return flags
