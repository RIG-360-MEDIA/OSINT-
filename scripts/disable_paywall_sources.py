#!/usr/bin/env python3
"""
Disables confirmed hard-paywall sources before the retry run.

Sets is_active = FALSE — sources are NOT deleted. They remain in the database
so existing article foreign keys are preserved and the sources can be
re-enabled or audited later.
"""
from __future__ import annotations

import asyncio
import logging
import os

import asyncpg

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

DATABASE_URL: str = os.environ.get(
    "DATABASE_URL_SYNC",
    "postgresql://rig:rigpassword@rig-postgres:5432/rig",
)

# Domains confirmed as hard-paywall with no programmatic bypass.
# Matched with ILIKE to catch sub-domains and path variants.
_PAYWALL_ILIKE_PATTERNS: list[str] = [
    "%bloomberg%",
    "%straitstimes%",
    "%japantimes%",
    "%independent.co.uk%",
    "%forbesindia%",
    "%moneycontrol%",
    "%worldpoliticsreview%",
    "%rt.com%",
]

_WHERE_CLAUSE = " OR ".join(
    f"domain ILIKE '{p}'" for p in _PAYWALL_ILIKE_PATTERNS
)


async def main() -> None:
    conn: asyncpg.Connection = await asyncpg.connect(DATABASE_URL)
    try:
        # Fetch names before disabling so we can print a human-readable list
        rows = await conn.fetch(
            f"""
            SELECT name, domain
            FROM sources
            WHERE {_WHERE_CLAUSE}
            ORDER BY name
            """
        )

        result = await conn.execute(
            f"""
            UPDATE sources
            SET is_active = FALSE
            WHERE {_WHERE_CLAUSE}
            """
        )

        # asyncpg returns "UPDATE N"
        disabled_count = int(result.split()[-1])

        print(f"Disabled {disabled_count} paywall sources:")
        for row in rows:
            print(f"  — {row['name']} ({row['domain']})")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
