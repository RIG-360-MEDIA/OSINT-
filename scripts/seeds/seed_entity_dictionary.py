"""
Seed entity_dictionary table from entity_dict_backup.csv.

CSV columns: name, type, subtype, aliases, state, party, metadata
Table columns: canonical_name, entity_type, aliases, state, party, metadata

Aliases in CSV are JSON arrays: ["alias1", "alias2"]
"""

import csv
import json
import os
import sys

import psycopg2

# Prefer DATABASE_URL_SYNC (plain postgresql://) so psycopg2 works correctly
# inside the container where DATABASE_URL carries the +asyncpg scheme.
_raw_url = os.getenv(
    "DATABASE_URL_SYNC",
    os.getenv("DATABASE_URL", "postgresql://rig:rigpassword@localhost:5433/rig"),
)
DATABASE_URL = _raw_url.replace("postgresql+asyncpg", "postgresql")

CSV_PATH = os.path.join(os.path.dirname(__file__), "entity_dict_backup.csv")


def parse_aliases(raw: str) -> list[str]:
    """Parse aliases from JSON array string or empty value."""
    if not raw or raw.strip() == "":
        return []
    raw = raw.strip()
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(a) for a in parsed]
    except (json.JSONDecodeError, ValueError):
        pass
    # Fallback: treat as single alias
    return [raw]


def parse_metadata(raw: str) -> dict:
    """Parse metadata from JSON object string."""
    if not raw or raw.strip() == "":
        return {}
    try:
        result = json.loads(raw)
        if isinstance(result, dict):
            return result
    except (json.JSONDecodeError, ValueError):
        pass
    return {}


def main() -> None:
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    insert_sql = """
        INSERT INTO entity_dictionary
            (canonical_name, entity_type, aliases, state, party, metadata)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (canonical_name) DO NOTHING
    """

    inserted = 0
    skipped = 0
    total = 0

    with open(CSV_PATH, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        batch: list[tuple] = []

        for row in reader:
            total += 1
            canonical_name = row["name"].strip()
            entity_type = row["type"].strip()
            aliases = parse_aliases(row.get("aliases", ""))
            state = row.get("state", "").strip() or None
            party = row.get("party", "").strip() or None
            metadata = parse_metadata(row.get("metadata", ""))

            batch.append((
                canonical_name,
                entity_type,
                aliases,
                state,
                party,
                json.dumps(metadata),
            ))

            if len(batch) >= 500:
                for record in batch:
                    cur.execute(insert_sql, record)
                    if cur.rowcount == 1:
                        inserted += 1
                    else:
                        skipped += 1
                conn.commit()
                batch = []

            if total % 1000 == 0:
                print(f"  Progress: {total} rows processed…")

        # flush remainder
        for record in batch:
            cur.execute(insert_sql, record)
            if cur.rowcount == 1:
                inserted += 1
            else:
                skipped += 1
        conn.commit()

    cur.close()
    conn.close()

    print(f"Entity dictionary seeded: {inserted} rows inserted, {skipped} skipped (duplicates)")


if __name__ == "__main__":
    main()
