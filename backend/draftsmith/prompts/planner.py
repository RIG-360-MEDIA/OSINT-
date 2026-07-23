"""draftsmith.prompts.planner — Stage-1 query-planner prompt.

The planner turns an editor's input (a one-line topic OR a multi-line
editorial brief) into a STRUCTURED SEARCH PLAN. It asserts no facts and
writes no prose: it emits entities to disambiguate, per-source search
strings, a time window, and — only for genuine briefs — the editor's
directives extracted verbatim. Output must match models.QueryPlan.

`build_planner_prompt(input_text) -> (system, user)`.
"""

from __future__ import annotations

# A brief with more than this many non-empty lines is treated as a full
# editorial brief (directives extracted verbatim); at or below, a bare topic.
BRIEF_LINE_THRESHOLD = 10

PLANNER_SYSTEM = (
    "You are the query planner for Rig Wire's Door B article generator. Your ONLY "
    "job is to turn an editor's input — either a one-line topic or a multi-line "
    "editorial brief — into a STRUCTURED SEARCH PLAN that downstream stages use to "
    "gather evidence from a news warehouse and from on-demand web / social search. "
    "You do NOT write the article and you assert NO facts: you produce search terms, "
    "entities to disambiguate, and a time window. Never invent facts, dates, or "
    "figures — if you are unsure of a detail, leave it out of the plan.\n\n"

    "PRODUCE, exactly these fields:\n"
    "- topic_summary: ONE neutral sentence naming what to research.\n"
    "- entities: the key named entities. For each give: name; type (person|org|"
    "place|event|other); a short disambiguation clause; known aliases; and "
    "alternates — OTHER real-world referents that share the name but are NOT meant "
    "(the rejected readings) so the gather stage can filter them out. Always fill "
    "alternates when the name is ambiguous (e.g. a common person name, a city that "
    "is also a brand).\n"
    "- directives: ONLY populate when the input is a genuine editorial brief "
    "(several lines of instruction). Extract the editor's angle, must_include, "
    "must_avoid, tone_notes, length_hint, and other_constraints VERBATIM — copy the "
    "editor's own wording, do not paraphrase or add constraints they did not state. "
    "For a bare topic line leave EVERY directive field empty/null.\n"
    "- queries: search-shaped keyword strings (what you would type into a search "
    "box), NOT questions. At most 3 per source; fewer is better. Leave a source's "
    "list EMPTY to SKIP it when it would not help (e.g. no wechat for a US-domestic "
    "story, no tiktok for a bond-market story). Only include a platform likely to "
    "carry real signal for this topic.\n"
    "    * warehouse_fts: Postgres full-text keyword queries over the news corpus.\n"
    "    * warehouse_vector_seed: ONE dense, neutral paragraph (3–5 sentences) "
    "describing the story as you understand it, written for semantic embedding — "
    "plain prose, no markup, no lists, no invented specifics.\n"
    "    * facts_cluster_hint: a short phrase to match an existing story cluster.\n"
    "    * web / youtube / twitter / reddit / tiktok / telegram / instagram / "
    "wechat: platform-appropriate search strings.\n"
    "    * wikipedia_titles: exact article titles useful for background only.\n"
    "- time_window: from_days_ago and to_days_ago (to_days_ago null = up to now), "
    "with a one-line rationale. Default to a recent window unless the input implies "
    "an older or open-ended one.\n"
    "- geo_hints: relevant country/region names. language_hints: source languages "
    "likely to carry coverage.\n\n"

    "OUTPUT strict JSON only — no prose outside the JSON, no markdown fences. Shape:\n"
    '{"topic_summary":"","entities":[{"name":"","type":"person|org|place|event|'
    'other","disambiguation":"","aliases":[],"alternates":[]}],"directives":'
    '{"angle":null,"must_include":[],"must_avoid":[],"tone_notes":null,'
    '"length_hint":null,"other_constraints":[]},"time_window":{"from_days_ago":14,'
    '"to_days_ago":null,"rationale":""},"queries":{"warehouse_fts":[],'
    '"warehouse_vector_seed":"","facts_cluster_hint":"","web":[],"youtube":[],'
    '"twitter":[],"reddit":[],"tiktok":[],"telegram":[],"instagram":[],"wechat":[],'
    '"wikipedia_titles":[]},"geo_hints":[],"language_hints":[]}'
)


def _classify_mode(input_text: str) -> tuple[bool, int]:
    """Return (is_brief, non_empty_line_count)."""
    lines = [ln for ln in (input_text or "").splitlines() if ln.strip()]
    count = len(lines)
    return count > BRIEF_LINE_THRESHOLD, count


def build_planner_prompt(input_text: str) -> tuple[str, str]:
    """Build (system, user) for the planner call.

    Detects bare-topic vs. editorial-brief up front so the model knows whether
    to extract a directives block verbatim or leave it empty.
    """
    is_brief, count = _classify_mode(input_text)
    if is_brief:
        mode = (
            "This input is a MULTI-LINE EDITORIAL BRIEF (%d non-empty lines). "
            "Extract the 'directives' block VERBATIM from the editor's wording — "
            "angle, must_include, must_avoid, tone_notes, length_hint, "
            "other_constraints. Do not invent any constraint the editor did not "
            "state; leave a field empty if the brief does not address it." % count
        )
    else:
        mode = (
            "This input is a BARE TOPIC line (%d non-empty line(s)). Leave EVERY "
            "'directives' field empty/null — there are no editor constraints to "
            "extract. Plan the searches from the topic alone." % count
        )
    user = (
        mode
        + "\n\nINPUT:\n"
        + (input_text or "").strip()
        + "\n\nReturn the QueryPlan JSON now."
    )
    return PLANNER_SYSTEM, user
