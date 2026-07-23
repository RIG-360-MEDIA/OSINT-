"""draftsmith.prompts.verify_b — Door B fact-faithfulness verifier prompt.

Adapts worldwide_gen_v2 VERIFY into a PER-BEAT checker whose output matches
models.VerifyReport: an overall pass|fail plus, per beat, a green|amber|red
verdict with span-level violations. Keeps VERIFY's discipline verbatim — a
reported fact/date must be in the BRIEF, computed dates are violations,
misattributed quotes fail — and adds the Tier-3-sole-support check.

`VERIFY_B_SYSTEM` is the system string; `build_verify_prompt(brief, draft)`
assembles the (system, user) pair.
"""

from __future__ import annotations

VERIFY_B_SYSTEM = (
    "You are a fact-faithfulness checker for Rig Wire explainer articles. You "
    "receive the BRIEF (the ONLY permitted source of facts; its evidence lines "
    "carry [id] handles and T<tier> trust tiers) and a DRAFT structured as an "
    "array of beats. Check EACH beat independently.\n\n"

    "A REPORTED fact — any number, date, quote, name, place, org, market/company, "
    "or specific event — MUST be supported by a BRIEF line. Flag any that is not, "
    "and flag any date the brief does not state (including a date computed by "
    "adding a duration to a start date). General background or explanation is "
    "allowed UNLESS it smuggles in an un-brief'd specific. Also flag a fact whose "
    "ONLY support is a Tier-3 source (reddit/tiktok/telegram/instagram/wechat/"
    "unverified twitter) unless the draft attributes it in-text as unverified — "
    "Tier-3 may not be the sole support for a stated fact.\n\n"

    "Per beat assign a verdict: green = every reported fact is supported at an "
    "adequate tier; amber = a soft issue (a stated fact resting only on Tier-3 "
    "without in-text attribution, a weak or off-tier citation, or an imprecise "
    "date that still stays within the brief's ordering); red = a hard violation "
    "(a fact or date NOT in the brief, or a misattributed quote). For each problem "
    "emit a violation naming the offending span, why it fails, its severity "
    "(red|amber), and expected_source_ids — the BRIEF handles that SHOULD support "
    "the span if any exist.\n\n"

    "The overall verdict is \"fail\" if ANY beat is red, otherwise \"pass\". "
    "OUTPUT strict JSON only: "
    '{"verdict":"pass"|"fail","beats":[{"index":0,"verdict":"green"|"amber"|"red",'
    '"violations":[{"span":"","why":"","severity":"red"|"amber",'
    '"expected_source_ids":[]}]}]}. '
    "Only FAIL a beat (red) on a real fact/date not in the brief, or a "
    "misattributed quote."
)


def build_verify_prompt(brief: str, draft_json: str) -> tuple[str, str]:
    """Build (system, user) for the verifier.

    `draft_json` is the draft serialised as JSON (headline/dek/beats/…); the
    verifier reads the beats array and checks each beat against the BRIEF.
    """
    user = (
        "BRIEF:\n"
        + (brief or "")
        + "\n\nDRAFT (beats JSON):\n"
        + (draft_json or "")
    )
    return VERIFY_B_SYSTEM, user
