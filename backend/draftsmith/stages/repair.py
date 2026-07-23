"""draftsmith.stages.repair — Stage 5b: the verify -> repair -> re-verify loop.

Mirrors the worldwide_gen_v2 repair-or-hold gate, adapted to the Door B beats
schema. run_repair_loop verifies the draft, and while the report still carries a
RED beat (a hard fact/date violation) and rounds remain, it calls the repairer
(REPAIR_B_SYSTEM) to rewrite ONLY the flagged spans, then re-verifies. When
dials.spot_check is set it runs the adversarial spot-check on the settled draft
and folds any "fragile support" ambers into the final report.

Whatever violations survive become editor flags. Per the contract, RED flags do
NOT block the job reaching 'ready' — an editor resolves them before finalize —
so run_repair_loop always returns its best draft, its final report, and the
leftover flags rather than raising on a still-red result.

    run_repair_loop(brief, draft, dials) -> (Draft, VerifyReport, list[Flag])
"""

from __future__ import annotations

import json
import logging
from typing import Any

from backend.draftsmith import config
from backend.draftsmith._db_serialize import to_json
from backend.draftsmith.models import Dials, Draft, Flag, VerifyReport
from backend.draftsmith.prompts import build_repair_prompt
from backend.draftsmith.llm import cerebras_json
from backend.draftsmith.stages.draft import to_draft
from backend.draftsmith.stages.verify import merge_spot_check, spot_check, verify

logger = logging.getLogger(__name__)


def _violations_payload(report: VerifyReport) -> str:
    """Flatten every beat's violations into the JSON the repairer consumes:
    one object per violation, tagged with its beat_index so the model can locate
    the span to rewrite."""
    items = [
        {
            "beat_index": beat.index,
            "span": viol.span,
            "why": viol.why,
            "severity": viol.severity,
            "expected_source_ids": list(viol.expected_source_ids),
        }
        for beat in report.beats
        for viol in beat.violations
    ]
    return json.dumps(items, ensure_ascii=False)


def _flags_from_report(report: VerifyReport) -> list[Flag]:
    """Convert every leftover violation (red AND amber) into an editor Flag.

    `id` is left empty — db.create_flags assigns the real id on INSERT (it reads
    only beat_index/span/severity/reason/source_ids). Status defaults to 'open'.
    """
    return [
        Flag(
            id="",
            beat_index=beat.index,
            span=viol.span,
            severity=viol.severity,
            reason=viol.why,
            source_ids=tuple(viol.expected_source_ids),
        )
        for beat in report.beats
        for viol in beat.violations
    ]


async def repair(brief: str, draft: Draft, report: VerifyReport) -> Draft:
    """One repair pass: rewrite the flagged spans, preserving beat structure.

    Reuses the draft stage's tolerant to_draft coercion so a repaired completion
    is parsed exactly like an original one. Raises ValueError on empty input;
    LLM failures propagate from cerebras_json.
    """
    if not brief or not brief.strip():
        raise ValueError("repair: brief is empty")
    if draft is None:
        raise ValueError("repair: draft is required")
    if report is None:
        raise ValueError("repair: report is required")

    system, user = build_repair_prompt(
        brief, to_json(draft), _violations_payload(report),
    )
    data = await cerebras_json(system, user, temperature=config.REPAIR_TEMP)
    if not isinstance(data, dict):
        raise ValueError(
            "repair: repairer returned a non-object JSON payload (%r)" % type(data)
        )
    return to_draft(data)


async def run_repair_loop(
    brief: str, draft: Draft, dials: Dials,
) -> tuple[Draft, VerifyReport, list[Flag]]:
    """Verify, then repair-and-re-verify while red beats remain (bounded by
    config.MAX_REPAIR_ROUNDS), then optionally spot-check.

    Returns the best draft reached, its final report, and the leftover
    violations as flags. Never raises on a still-red result — red flags block
    finalize, not 'ready'.
    """
    if not brief or not brief.strip():
        raise ValueError("run_repair_loop: brief is empty")
    if draft is None:
        raise ValueError("run_repair_loop: draft is required")
    if dials is None:
        raise ValueError("run_repair_loop: dials is required")

    current: Draft = draft
    report: VerifyReport = await verify(brief, current)

    rounds = 0
    while report.has_red and rounds < config.MAX_REPAIR_ROUNDS:
        rounds += 1
        logger.info(
            "repair round %d/%d — %d red beat(s) remaining",
            rounds, config.MAX_REPAIR_ROUNDS,
            sum(1 for b in report.beats if b.verdict == "red"),
        )
        current = await repair(brief, current, report)
        report = await verify(brief, current)

    if report.has_red:
        logger.warning(
            "repair loop exhausted %d round(s) with red beats still present; "
            "surfacing them as flags (blocks finalize, not 'ready')",
            config.MAX_REPAIR_ROUNDS,
        )

    if dials.clamp().spot_check:
        overlay = await spot_check(brief, current, report)
        report = merge_spot_check(report, overlay)

    flags = _flags_from_report(report)
    return current, report, flags
