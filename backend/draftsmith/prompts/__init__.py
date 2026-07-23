"""draftsmith.prompts — the Door B prompt builders.

The frozen prompt strings and their (system, user) builders, adapted from the
live worldwide_gen_v2 recipe (PROMPT_D / VERIFY / REPAIR) with their
FACTS-ARE-FROZEN and DATE-DISCIPLINE language preserved verbatim.

Public interface consumed by the stages:
  build_planner_prompt(input_text) -> (system, user)
  build_draft_prompt(brief, dials) -> (system, user)
  VERIFY_B_SYSTEM   (str)     ;  build_verify_prompt(brief, draft_json)
  REPAIR_B_SYSTEM   (str)     ;  build_repair_prompt(brief, draft, violations)
"""

from __future__ import annotations

from backend.draftsmith.prompts.planner import (
    BRIEF_LINE_THRESHOLD,
    PLANNER_SYSTEM,
    build_planner_prompt,
)
from backend.draftsmith.prompts.prompt_d_b import (
    PROMPT_D_B_BASE,
    build_draft_prompt,
)
from backend.draftsmith.prompts.verify_b import (
    VERIFY_B_SYSTEM,
    build_verify_prompt,
)
from backend.draftsmith.prompts.repair_b import (
    REPAIR_B_SYSTEM,
    build_repair_prompt,
)

__all__ = [
    "BRIEF_LINE_THRESHOLD",
    "PLANNER_SYSTEM",
    "build_planner_prompt",
    "PROMPT_D_B_BASE",
    "build_draft_prompt",
    "VERIFY_B_SYSTEM",
    "build_verify_prompt",
    "REPAIR_B_SYSTEM",
    "build_repair_prompt",
]
