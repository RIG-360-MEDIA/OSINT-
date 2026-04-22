"""
Score the demo user (pranavpuri03@gmail.com) against every govt doc that has
intel populated. After this, GET /api/documents/feed returns ranked results.
"""
from __future__ import annotations

import asyncio

from sqlalchemy import text

from backend.database import get_db
from backend.relevance.govt_relevance import score_govt_doc_for_user


async def main() -> None:
    async with get_db() as db:
        user = (
            await db.execute(
                text("SELECT id::text AS id FROM users WHERE email = 'pranavpuri03@gmail.com' LIMIT 1")
            )
        ).fetchone()
        if not user:
            print("demo user not found")
            return

        rows = (
            await db.execute(
                text(
                    """
                    SELECT id::text AS id, title
                    FROM govt_documents
                    WHERE intrinsic_importance > 0
                    ORDER BY intrinsic_importance DESC
                    """
                )
            )
        ).fetchall()
        print(f"scoring {len(rows)} docs against user {user.id}")

        for i, r in enumerate(rows, start=1):
            try:
                result = await score_govt_doc_for_user(
                    db=db, doc_id=r.id, user_id=user.id
                )
                tier = result.get("relevance_tier")
                final = result.get("score_final")
                urg = result.get("urgency")
                print(
                    f"  [{i}/{len(rows)}] T{tier} {final:.2f} {urg or '-':<6} "
                    f"{r.title[:55]}"
                )
            except Exception as exc:
                print(f"  FAIL {r.title[:50]}: {exc}")

        print("scoring complete")


if __name__ == "__main__":
    asyncio.run(main())
