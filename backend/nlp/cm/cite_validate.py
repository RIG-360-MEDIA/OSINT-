"""
Cite-ID validator for CM Page v2 LLM auto-publish.

Every LLM-synthesised text on the CM Page (Lead headline, Analysis
column, Action item) must include a list of ``cite_ids`` — UUIDs of
real ``articles`` rows that ground the assertion. Per the project
memory note: "every seed row must be source-verified; no fabricated
handles/pledges/quotes; LLM outputs need cite-ID guardrails." This
module is the guardrail.

Public surface:

    async def validate_cite_ids(db, ids: Sequence[UUID|str]) -> ValidationResult

    @dataclass
    class ValidationResult:
        valid_ids:    list[UUID]    # IDs that resolve to real rows
        invalid_ids:  list[str]     # IDs that didn't resolve
        ratio:        float         # len(valid) / len(input)

If even one cite_id fails to resolve, the LLM output is considered
unsafe and gets persisted with ``rejected=TRUE`` instead of being
shown. The audit trail (``cm_lead_headlines.rejection_reason``,
``cm_analysis_drafts.status='rejected'``) supports daily metrics so
we can watch the rejection rate per model.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Sequence
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ValidationResult:
    """Result of a cite-ID validation pass."""

    valid_ids: list[UUID] = field(default_factory=list)
    invalid_ids: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.valid_ids) + len(self.invalid_ids)

    @property
    def ratio(self) -> float:
        return len(self.valid_ids) / self.total if self.total else 0.0

    @property
    def all_valid(self) -> bool:
        return self.total > 0 and not self.invalid_ids


def _coerce(ids: Sequence[UUID | str]) -> tuple[list[UUID], list[str]]:
    """Return (parsed UUIDs, originals that couldn't be parsed)."""
    parsed: list[UUID] = []
    bad: list[str] = []
    for raw in ids:
        if isinstance(raw, UUID):
            parsed.append(raw)
            continue
        if not isinstance(raw, str) or not raw.strip():
            bad.append(str(raw))
            continue
        try:
            parsed.append(UUID(raw.strip()))
        except (ValueError, TypeError):
            bad.append(raw)
    return parsed, bad


async def validate_cite_ids(
    db: AsyncSession,
    ids: Sequence[UUID | str],
) -> ValidationResult:
    """Verify each cite ID resolves to a real ``articles`` row.

    Order is preserved on the input list — callers that need a stable
    "first valid" pick can rely on the first element of ``valid_ids``
    matching the LLM's preferred citation.

    Cheap: one ``SELECT id WHERE id = ANY(:ids)`` regardless of the
    input length. Empty input returns an empty result with
    ``ratio = 0.0`` (treated as a fail at the caller — an LLM output
    without any cite_ids is by definition not grounded).
    """
    parsed, malformed = _coerce(ids)
    if not parsed:
        return ValidationResult(valid_ids=[], invalid_ids=malformed)

    rows = await db.execute(
        text(
            "SELECT id FROM articles WHERE id = ANY(CAST(:ids AS uuid[]))"
        ),
        {"ids": [str(u) for u in parsed]},
    )
    found: set[UUID] = {row.id if isinstance(row.id, UUID) else UUID(str(row.id)) for row in rows.all()}

    valid: list[UUID] = []
    invalid: list[str] = list(malformed)
    for u in parsed:
        if u in found:
            valid.append(u)
        else:
            invalid.append(str(u))

    if invalid:
        logger.info(
            "cite-ID validation: %d valid, %d invalid (%.0f%% pass)",
            len(valid),
            len(invalid),
            100 * len(valid) / max(1, len(parsed)),
        )
    return ValidationResult(valid_ids=valid, invalid_ids=invalid)


__all__ = ["ValidationResult", "validate_cite_ids"]
