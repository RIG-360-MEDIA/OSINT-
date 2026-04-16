"""
Seed sources table from sources_backup.csv.

CSV columns:
  name, domain, rss_url, source_type, category, language,
  geo_states, primary_topic, secondary_topics, is_active, tier

Table columns:
  name, domain, rss_url, source_type, source_tier, language,
  geo_states, topics, is_active

Mapping:
  tier        → source_tier (int)
  is_active   → is_active (bool: 't'/'f')
  geo_states  → TEXT[] parsed from PostgreSQL array literal {val1,val2}
  primary_topic + secondary_topics → topics TEXT[]
"""

import csv
import os
import re

import psycopg2

# Prefer DATABASE_URL_SYNC (plain postgresql://) so psycopg2 works correctly
# inside the container where DATABASE_URL carries the +asyncpg scheme.
_raw_url = os.getenv(
    "DATABASE_URL_SYNC",
    os.getenv("DATABASE_URL", "postgresql://rig:rigpassword@localhost:5433/rig"),
)
DATABASE_URL = _raw_url.replace("postgresql+asyncpg", "postgresql")

CSV_PATH = os.path.join(os.path.dirname(__file__), "sources_backup.csv")

VALID_SOURCE_TYPES = {"rss", "scrape", "api", "youtube", "govt", "social"}


def parse_pg_array(raw: str) -> list[str]:
    """
    Parse a PostgreSQL array literal into a Python list.
    Handles: {}, {val}, {"val1","val2"}, {Maharashtra}, {"West Bengal"}
    """
    if not raw or raw.strip() in ("", "{}"):
        return []
    raw = raw.strip()
    if not (raw.startswith("{") and raw.endswith("}")):
        return [raw]
    inner = raw[1:-1]
    if not inner:
        return []
    # Split on commas not inside quotes
    elements = re.findall(r'"([^"]*)"|\b([^,]+)', inner)
    result = []
    for quoted, unquoted in elements:
        val = quoted if quoted else unquoted.strip()
        if val:
            result.append(val)
    return result


def parse_bool(raw: str) -> bool:
    return raw.strip().lower() in ("t", "true", "1", "yes")


def parse_tier(raw: str) -> int:
    try:
        val = int(raw.strip())
        return max(1, min(3, val))  # clamp to 1-3
    except (ValueError, AttributeError):
        return 2


def main() -> None:
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    insert_sql = """
        INSERT INTO sources
            (name, domain, rss_url, source_type, source_tier,
             language, geo_states, topics, is_active)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (domain) DO NOTHING
    """

    inserted = 0
    skipped = 0

    with open(CSV_PATH, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)

        for row in reader:
            name = row["name"].strip()
            domain = row["domain"].strip()
            rss_url = row.get("rss_url", "").strip() or None
            raw_type = row.get("source_type", "").strip().lower()
            source_type = raw_type if raw_type in VALID_SOURCE_TYPES else "scrape"
            source_tier = parse_tier(row.get("tier", "2"))
            language = row.get("language", "en").strip() or "en"
            geo_states = parse_pg_array(row.get("geo_states", ""))
            is_active = parse_bool(row.get("is_active", "t"))

            # Merge primary_topic + secondary_topics → topics[]
            primary = row.get("primary_topic", "").strip()
            secondary = parse_pg_array(row.get("secondary_topics", ""))
            topics: list[str] = []
            if primary:
                topics.append(primary)
            topics.extend(secondary)

            cur.execute(insert_sql, (
                name,
                domain,
                rss_url,
                source_type,
                source_tier,
                language,
                geo_states,
                topics,
                is_active,
            ))
            if cur.rowcount == 1:
                inserted += 1
            else:
                skipped += 1

        conn.commit()

    cur.close()
    conn.close()

    print(f"Sources seeded: {inserted} rows inserted, {skipped} skipped (duplicates)")


if __name__ == "__main__":
    main()
