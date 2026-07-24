"""Load a tenant's roster + vocabularies from the briefing.* tables.

All matching-relevant name strings (canonical + variants + Telugu) are flattened
so callers can do wide-net candidate matching, while the prompt gets clean
canonical lists.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text

# Static "not the government" reference is baked into the prompt; nothing here.


async def load_refdata(db, org_id: str) -> dict[str, Any]:
    """Return the org's roster + vocab as a dict the prompt + pipeline consume."""
    org = (await db.execute(
        text("SELECT name FROM analytics.orgs WHERE id = CAST(:o AS uuid)"),
        {"o": org_id},
    )).scalar() or "the government"

    roster = (await db.execute(text("""
        SELECT canonical_name, side, role, name_variants, telugu_names
          FROM briefing.roster
         WHERE org_id = CAST(:o AS uuid) AND active
    """), {"o": org_id})).fetchall()

    def label(r) -> str:
        return f"{r.canonical_name}" + (f" ({r.role})" if r.role else "")

    gov = [label(r) for r in roster if r.side == "government"]
    opp = [label(r) for r in roster if r.side == "opposition"]
    inst = [label(r) for r in roster if r.side == "institution"]

    # Flat match set: every string that identifies a roster entity, with its side.
    match_names: list[dict[str, str]] = []
    for r in roster:
        for nm in [r.canonical_name, *(r.name_variants or []), *(r.telugu_names or [])]:
            if nm and nm.strip():
                match_names.append({"name": nm.strip(), "side": r.side,
                                    "canonical": r.canonical_name})

    topics = [r.name for r in (await db.execute(text(
        "SELECT name FROM briefing.topics WHERE org_id=CAST(:o AS uuid) AND active ORDER BY sort_order"
    ), {"o": org_id})).fetchall()]
    depts = [r.name for r in (await db.execute(text(
        "SELECT name FROM briefing.departments WHERE org_id=CAST(:o AS uuid) AND active ORDER BY name"
    ), {"o": org_id})).fetchall()]

    scheme_rows = (await db.execute(text("""
        SELECT name, department, name_variants, telugu_names, disambiguation_terms
          FROM briefing.schemes WHERE org_id=CAST(:o AS uuid) AND active ORDER BY name
    """), {"o": org_id})).fetchall()
    schemes = [r.name for r in scheme_rows]
    scheme_defs = [{"name": r.name, "department": r.department,
                    "variants": list(r.name_variants or []),
                    "telugu": list(r.telugu_names or []),
                    "disambiguation": list(r.disambiguation_terms or [])}
                   for r in scheme_rows]

    return {
        "org_id": org_id,
        "org_name": org,
        "government_names": gov,
        "opposition_names": opp,
        "institution_names": inst,
        "match_names": match_names,      # [{name, side, canonical}]
        "topics": topics,
        "departments": depts,
        "schemes": schemes,
        "scheme_defs": scheme_defs,
    }
