"""draftsmith.stages — the pipeline stages.

Each stage is a pure-ish async step over the frozen models contract:
  plan → gather → rank → brief → draft → verify/repair → images.
Stages join this package as their waves land.
"""

from __future__ import annotations

from backend.draftsmith.stages.brief import BriefResult, BriefStats, build_brief
from backend.draftsmith.stages.draft import draft, to_draft
from backend.draftsmith.stages.images import gather_images
from backend.draftsmith.stages.plan import plan, to_query_plan
from backend.draftsmith.stages.rank import estimate_tokens, rank
from backend.draftsmith.stages.repair import repair, run_repair_loop
from backend.draftsmith.stages.verify import (
    merge_spot_check,
    spot_check,
    to_verify_report,
    verify,
)

__all__ = [
    "plan",
    "to_query_plan",
    "rank",
    "estimate_tokens",
    "build_brief",
    "BriefResult",
    "BriefStats",
    "gather_images",
    "draft",
    "to_draft",
    "verify",
    "to_verify_report",
    "spot_check",
    "merge_spot_check",
    "repair",
    "run_repair_loop",
]
