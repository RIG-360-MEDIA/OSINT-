"""
One-shot: backfill intel_json + intrinsic_importance + derived columns
for every govt_documents row that doesn't yet have intel populated.
Run inside the rig-backend container after Phase 1 ships.

Usage:
  docker exec rig-backend python /app/scripts/backfill_govt_intel.py
"""
from __future__ import annotations

import asyncio
import json

from sqlalchemy import text

from backend.database import get_db
from backend.nlp.govt_intel import compute_intrinsic_importance, extract_intel


_SELECT_SQL = """
    SELECT id::text AS id,
           title,
           COALESCE(full_text_translated, full_text) AS body
    FROM govt_documents
    WHERE intrinsic_importance = 0
       OR intrinsic_importance IS NULL
    ORDER BY length(full_text) DESC
"""

_UPDATE_SQL = """
    UPDATE govt_documents
    SET intel_json              = CAST(:ij AS jsonb),
        intrinsic_importance    = :imp,
        document_nature         = :dn,
        action_posture          = :ap,
        geography_affected      = CAST(:ga AS jsonb),
        financial_magnitude_inr = :fm,
        effective_date          = CAST(:ed AS DATE),
        winners                 = CAST(:w AS jsonb),
        losers                  = CAST(:l AS jsonb),
        enforcement_strength    = :es,
        updated_at              = NOW()
    WHERE id = CAST(:did AS uuid)
"""


async def main() -> None:
    async with get_db() as db:
        rows = (await db.execute(text(_SELECT_SQL))).fetchall()
        total = len(rows)
        print(f"backfilling {total} docs")

        for i, r in enumerate(rows, start=1):
            try:
                intel = await extract_intel(r.body, r.title)
                imp = compute_intrinsic_importance(intel)
                dump = intel.model_dump(mode="json")
                await db.execute(
                    text(_UPDATE_SQL),
                    {
                        "did": r.id,
                        "ij": intel.model_dump_json(),
                        "imp": float(imp),
                        "dn": intel.document_nature,
                        "ap": intel.action_posture,
                        "ga": json.dumps(dump.get("geography_affected") or []),
                        "fm": intel.financial_magnitude_inr,
                        "ed": dump.get("effective_date"),
                        "w": json.dumps(dump.get("winners") or []),
                        "l": json.dumps(dump.get("losers") or []),
                        "es": intel.enforcement_strength,
                    },
                )
                if i % 5 == 0 or i == total:
                    await db.commit()
                    print(
                        f"  [{i}/{total}] {r.title[:42]:<42} "
                        f"{intel.document_nature}/{intel.action_posture} imp={imp}"
                    )
            except Exception as exc:
                print(f"  FAIL {r.title[:50]}: {exc}")

        await db.commit()
        print("backfill complete")


if __name__ == "__main__":
    asyncio.run(main())
