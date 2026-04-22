"""
Delete documents that are irrelevant to the demo user's CM-aide profile.

Criteria for deletion (a doc must satisfy ALL):
  1. No matched_entity_names for the demo user (entity miss)
  2. No Telangana / Hyderabad / TS-district mention in geography_affected
  3. EITHER:
        a. action_posture = 'ROUTINE_ADMIN' (CAG recruitment, RTI templates,
           citizen charters, holiday lists), OR
        b. relevance_tier = 0 (score_final < 0.20), OR
        c. document_nature = 'OTHER' AND intrinsic_importance < 0.30

Govt-doc chunks cascade-delete via FK. user_govt_doc_relevance also cascades.

Run AFTER the per-user relevance scoring is current.
"""
from __future__ import annotations

import asyncio

from sqlalchemy import text

from backend.database import get_db


_TS_GEOS = (
    "telangana", "hyderabad", "secunderabad", "cyberabad", "rangareddy",
    "medchal", "warangal", "karimnagar", "nizamabad", "nalgonda",
    "khammam", "mahbubnagar", "adilabad",
)


_PREVIEW_SQL = """
    SELECT
      d.id::text AS id,
      LEFT(d.title, 60) AS title,
      d.document_nature,
      d.action_posture,
      ROUND(d.intrinsic_importance::numeric, 2) AS imp,
      ROUND(COALESCE(r.score_final, 0)::numeric, 2) AS score,
      r.relevance_tier AS tier,
      array_length(r.matched_entity_names, 1) AS matched_n,
      d.geography_affected
    FROM govt_documents d
    LEFT JOIN user_govt_doc_relevance r
           ON r.doc_id = d.id
          AND r.user_id = (SELECT id FROM users WHERE email = 'pranavpuri03@gmail.com')
    ORDER BY COALESCE(r.score_final, 0) ASC
"""


def _is_ts_relevant(geography_affected) -> bool:
    """Return True if the doc's geography_affected JSONB array hits a TS-related place."""
    if not geography_affected:
        return False
    geos = [str(g).lower() for g in geography_affected]
    return any(any(ts in g for ts in _TS_GEOS) for g in geos)


async def main() -> None:
    async with get_db() as db:
        rows = (await db.execute(text(_PREVIEW_SQL))).fetchall()
        print(f"Inspecting {len(rows)} docs against demo-user profile...\n")

        to_delete: list[tuple[str, str, str]] = []  # (id, reason, title)
        keep = 0
        for r in rows:
            ts_relevant = _is_ts_relevant(r.geography_affected)
            entity_match = (r.matched_n or 0) > 0

            if entity_match:
                keep += 1
                continue
            if ts_relevant:
                keep += 1
                continue

            # Doesn't mention user entities or TS geo. Apply junk criteria.
            score = float(r.score or 0)
            tier = r.tier or 0
            imp = float(r.imp or 0)
            posture = r.action_posture
            nature = r.document_nature

            reason = None
            if posture == "ROUTINE_ADMIN":
                reason = "ROUTINE_ADMIN"
            elif tier == 0:
                reason = f"tier-0 (score={score})"
            elif nature == "OTHER" and imp < 0.30:
                reason = f"OTHER+low-imp ({imp})"

            if reason:
                to_delete.append((r.id, reason, r.title))
            else:
                keep += 1

        print(f"keep:   {keep}")
        print(f"delete: {len(to_delete)}\n")
        print("--- docs to delete ---")
        for did, reason, title in to_delete:
            print(f"  [{reason:<22}] {title}")

        if not to_delete:
            print("nothing to delete")
            return

        ids = [did for did, _, _ in to_delete]
        await db.execute(
            text("DELETE FROM govt_documents WHERE id = ANY(CAST(:ids AS uuid[]))"),
            {"ids": ids},
        )
        await db.commit()
        print(f"\nDeleted {len(ids)} irrelevant docs (chunks + relevance rows cascaded).")

        remaining = (await db.execute(text("SELECT COUNT(*) AS n FROM govt_documents"))).fetchone()
        print(f"Remaining govt_documents: {remaining.n}")


if __name__ == "__main__":
    asyncio.run(main())
