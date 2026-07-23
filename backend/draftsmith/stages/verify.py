"""draftsmith.stages.verify — Stage 5: fact-faithfulness check + spot-check.

verify(brief, draft) runs the Door B per-beat verifier (VERIFY_B_SYSTEM) at
config.VERIFY_TEMP and tolerantly parses its JSON into models.VerifyReport. The
verifier gets a raised token budget (worldwide_gen_v2's fix for the
token-starved verifier that used to emit verdict=None).

spot_check(brief, draft, base_report) is the adversarial second pass: it samples
up to _SPOT_SAMPLE beats that the base report marked GREEN and re-verifies each
against a perturbed BRIEF — one of the beat's cited sources withheld and the
evidence order shuffled. A beat whose verdict FLIPS off green under that
perturbation had fragile support, so it is downgraded to amber "fragile
support". Amber never fails a report; it surfaces as an editor flag.

merge_spot_check(base, overlay) folds those amber downgrades back into the base
report immutably (green -> amber only; never a downgrade of a worse verdict).
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
from typing import Any, Optional

from backend.draftsmith import config
from backend.draftsmith._db_serialize import to_json
from backend.draftsmith.llm import LLMError, cerebras_json
from backend.draftsmith.models import (
    BeatVerdictReport,
    Draft,
    VerifyReport,
    Violation,
)
from backend.draftsmith.prompts import build_verify_prompt

logger = logging.getLogger(__name__)

# Verifier token budget — worldwide_gen_v2 raised the verify call to 8000 so the
# checker never runs out of room to emit its JSON (a token-starved verifier
# silently returned verdict=None and everything shipped unchecked).
_VERIFY_MAX_TOKENS = 8000

# Adversarial pass: how many green cited beats to probe, and the fragile marker.
_SPOT_SAMPLE = 5
_FRAGILE_REASON = (
    "fragile support: verdict flips off green when a cited source is withheld "
    "and the evidence order is shuffled"
)

_VERDICTS = ("green", "amber", "red")
_VERDICT_RANK = {"green": 0, "amber": 1, "red": 2}
# Leading "[<id>]" citation handle on a BRIEF evidence line.
_LINE_ID_RE = re.compile(r"^\s*\[([^\]\s]+)\]")


# --- coercion helpers (never trust model output) ----------------------------
def _as_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _as_str_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(s for s in (_as_str(v) for v in value) if s)


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _as_int(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_severity(value: Any) -> str:
    s = _as_str(value).lower()
    return s if s in ("red", "amber") else "amber"


def _to_violation(raw: Any) -> Optional[Violation]:
    if not isinstance(raw, dict):
        return None
    span = _as_str(raw.get("span"))
    why = _as_str(raw.get("why"))
    if not span and not why:
        return None
    return Violation(
        span=span,
        why=why,
        severity=_as_severity(raw.get("severity")),  # type: ignore[arg-type]
        expected_source_ids=_as_str_tuple(raw.get("expected_source_ids")),
    )


def _worst(a: str, b: str) -> str:
    return a if _VERDICT_RANK[a] >= _VERDICT_RANK[b] else b


def _to_beat_report(raw: Any, fallback_index: int) -> BeatVerdictReport:
    d = raw if isinstance(raw, dict) else {}
    violations = tuple(
        v for v in (_to_violation(x) for x in _as_list(d.get("violations"))) if v
    )
    verdict = _as_str(d.get("verdict")).lower()
    if verdict not in _VERDICTS:
        verdict = "green"
    # Keep the verdict consistent with its own violations: a beat can never be
    # greener than its worst flagged span.
    for viol in violations:
        verdict = _worst(verdict, viol.severity)
    return BeatVerdictReport(
        index=_as_int(d.get("index"), fallback_index),
        verdict=verdict,  # type: ignore[arg-type]
        violations=violations,
    )


def to_verify_report(data: dict[str, Any]) -> VerifyReport:
    """Tolerantly assemble a VerifyReport from a raw verifier payload.

    Pure and deterministic. The overall verdict is RECOMPUTED from the beats
    (fail iff any beat is red) rather than trusting the model's top-level field,
    so VerifyReport.has_red and .verdict can never disagree. A flat
    {"violations": [...]} payload (the legacy VERIFY shape) is wrapped as a
    single beat so an off-schema completion still yields a report.
    """
    if not isinstance(data, dict):
        raise ValueError(
            "to_verify_report: expected a JSON object, got %r" % type(data)
        )
    raw_beats = _as_list(data.get("beats"))
    if not raw_beats and _as_list(data.get("violations")):
        raw_beats = [{"index": 0, "verdict": "red", "violations": data["violations"]}]
    beats = tuple(
        _to_beat_report(b, i) for i, b in enumerate(raw_beats)
    )
    verdict = "fail" if any(b.verdict == "red" for b in beats) else "pass"
    return VerifyReport(verdict=verdict, beats=beats)


async def verify(brief: str, draft: Draft) -> VerifyReport:
    """Stage 5 — check every beat's reported facts against the BRIEF.

    Runs at config.VERIFY_TEMP with the raised verifier token budget. Raises
    ValueError on empty input; LLM failures propagate from cerebras_json (never
    silently swallowed).
    """
    if not brief or not brief.strip():
        raise ValueError("verify: brief is empty")
    if draft is None:
        raise ValueError("verify: draft is required")

    system, user = build_verify_prompt(brief, to_json(draft))
    data = await cerebras_json(
        system, user,
        temperature=config.VERIFY_TEMP,
        max_tokens=_VERIFY_MAX_TOKENS,
    )
    if not isinstance(data, dict):
        raise ValueError(
            "verify: verifier returned a non-object JSON payload (%r)" % type(data)
        )
    return to_verify_report(data)


# --- adversarial spot-check --------------------------------------------------
def _perturb_brief(brief: str, withhold_id: str, rng: random.Random) -> str:
    """Return a BRIEF copy with `withhold_id`'s evidence line(s) dropped and the
    remaining evidence lines shuffled. Non-evidence lines (headers, blanks) keep
    their relative order and lead the block. Pure w.r.t. the passed rng."""
    evidence: list[str] = []
    scaffold: list[str] = []
    for line in brief.splitlines():
        match = _LINE_ID_RE.match(line)
        if match is None:
            scaffold.append(line)
            continue
        if match.group(1) == withhold_id:
            continue  # withheld source
        evidence.append(line)
    shuffled = list(evidence)
    rng.shuffle(shuffled)
    return "\n".join(scaffold + [""] + shuffled)


def _green_cited_beats(
    draft: Draft, base_report: VerifyReport,
) -> list[tuple[int, Any]]:
    """Beats the base report marked green AND that carry cited source_ids —
    the only beats whose support is worth stress-testing."""
    green = {
        b.index for b in base_report.beats if b.verdict == "green"
    }
    out: list[tuple[int, Any]] = []
    for idx, beat in enumerate(draft.beats):
        if idx in green and beat.source_ids:
            out.append((idx, beat))
    return out


async def _probe_beat(
    brief: str, draft: Draft, index: int, beat: Any,
) -> Optional[BeatVerdictReport]:
    """Re-verify one beat against a perturbed BRIEF. Returns an amber
    'fragile support' report if its verdict flips off green, else None. Never
    raises — a probe failure is logged and treated as 'not proven fragile'."""
    # Deterministic per-beat rng so a given (draft, beat) always probes the same
    # withheld source + shuffle — reproducible across eval sweeps.
    seed = f"{draft.headline} {index} {'|'.join(beat.source_ids)}"
    rng = random.Random(seed)
    withhold_id = rng.choice(list(beat.source_ids))
    perturbed = _perturb_brief(brief, withhold_id, rng)
    mini = Draft(headline=draft.headline, dek=draft.dek, beats=(beat,))
    try:
        report = await verify(perturbed, mini)
    except (LLMError, ValueError) as exc:
        logger.warning(
            "spot_check probe failed for beat %d (withheld %s): %s",
            index, withhold_id, exc,
        )
        return None
    probed = report.beats[0].verdict if report.beats else "green"
    if probed == "green":
        return None  # support held under perturbation
    span = beat.subhead or (beat.text or "")[:80]
    return BeatVerdictReport(
        index=index,
        verdict="amber",
        violations=(
            Violation(
                span=span,
                why=_FRAGILE_REASON,
                severity="amber",
                expected_source_ids=tuple(beat.source_ids),
            ),
        ),
    )


async def spot_check(
    brief: str, draft: Draft, base_report: Optional[VerifyReport] = None,
) -> VerifyReport:
    """Adversarial second-verify over up to _SPOT_SAMPLE green cited beats.

    `base_report` identifies which beats were green (recomputed via verify() when
    omitted). Returns a VerifyReport whose beats are ONLY the fragile downgrades
    (amber); merge it into the base report with merge_spot_check. verdict is
    always "pass" — a fragile-support finding is an amber, never a fail.
    """
    if not brief or not brief.strip():
        raise ValueError("spot_check: brief is empty")
    if draft is None:
        raise ValueError("spot_check: draft is required")

    report = base_report if base_report is not None else await verify(brief, draft)
    candidates = _green_cited_beats(draft, report)
    if not candidates:
        return VerifyReport(verdict="pass", beats=())

    rng = random.Random(f"spot::{draft.headline}::{len(candidates)}")
    sampled = candidates if len(candidates) <= _SPOT_SAMPLE else rng.sample(
        candidates, _SPOT_SAMPLE,
    )
    probes = await asyncio.gather(
        *(_probe_beat(brief, draft, idx, beat) for idx, beat in sampled)
    )
    fragile = tuple(p for p in probes if p is not None)
    return VerifyReport(verdict="pass", beats=fragile)


def merge_spot_check(base: VerifyReport, overlay: VerifyReport) -> VerifyReport:
    """Fold spot-check amber downgrades into `base`, immutably.

    A base beat marked green is upgraded to amber (with the overlay's fragile
    violations appended) when the overlay flags the same index; a beat that is
    already amber/red is left untouched (never downgraded). Returns a NEW
    VerifyReport; neither input is mutated. Overall verdict is recomputed.
    """
    overlay_by_index = {b.index: b for b in overlay.beats if b.verdict == "amber"}
    merged: list[BeatVerdictReport] = []
    for beat in base.beats:
        frag = overlay_by_index.get(beat.index)
        if frag is not None and beat.verdict == "green":
            merged.append(
                BeatVerdictReport(
                    index=beat.index,
                    verdict="amber",
                    violations=tuple(beat.violations) + tuple(frag.violations),
                )
            )
        else:
            merged.append(beat)
    verdict = "fail" if any(b.verdict == "red" for b in merged) else "pass"
    return VerifyReport(verdict=verdict, beats=tuple(merged))
