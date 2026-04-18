"""
One-time script: resolve all user_entities canonical names against
entity_dictionary. Alias matches are upgraded to their canonical form.
Entities not found in the dictionary are left unchanged.
Safe to run multiple times (idempotent).
"""
from __future__ import annotations

import asyncio

from sqlalchemy import text


async def fix_canonicals() -> None:
    from backend.database import get_db

    async with get_db() as db:
        rows = (await db.execute(text(
            "SELECT id, user_id, canonical_name FROM user_entities ORDER BY canonical_name"
        ))).fetchall()

        fixed = 0
        not_found = 0
        already_correct = 0

        for ue in rows:
            match = (await db.execute(
                text("""
                    SELECT canonical_name
                    FROM entity_dictionary
                    WHERE canonical_name ILIKE :name
                       OR :name ILIKE ANY(aliases::text[])
                    LIMIT 1
                """),
                {"name": ue.canonical_name},
            )).fetchone()

            if not match:
                not_found += 1
                print(f"  NOT IN DICT: {ue.canonical_name}")
                continue

            if match.canonical_name == ue.canonical_name:
                already_correct += 1
                continue

            await db.execute(
                text("UPDATE user_entities SET canonical_name = :canonical WHERE id = :id"),
                {"canonical": match.canonical_name, "id": ue.id},
            )
            fixed += 1
            print(f"  FIXED: '{ue.canonical_name}' → '{match.canonical_name}'")

        await db.commit()

    print(f"\nSUMMARY")
    print(f"  Fixed:             {fixed}")
    print(f"  Already correct:   {already_correct}")
    print(f"  Not in dictionary: {not_found}  (kept as-is — user-defined entities)")


asyncio.run(fix_canonicals())
