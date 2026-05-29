"""Load entity-seed YAML files into entity_dictionary.

Idempotent: skips duplicates by (canonical_name, entity_type, country).
On re-run, updates aliases and source tag for rows that match.

Usage:
    # Load one country
    python load_seeds.py --dsn $PG_DSN by_country/US.yaml

    # Load all countries
    python load_seeds.py --dsn $PG_DSN by_country/*.yaml

    # Dry-run (no writes)
    python load_seeds.py --dsn $PG_DSN --dry-run by_country/US.yaml
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
from contextlib import closing
from pathlib import Path
from typing import Any

import psycopg2  # type: ignore
import yaml  # type: ignore


# Map YAML section name → entity_type column value
SECTION_TO_TYPE: dict[str, str] = {
    "persons":        "person",
    "organizations":  "organization",
    "constituencies": "constituency",
    "locations":      "location",
    "roles":          "role",
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("files", nargs="+", help="YAML files (globs supported)")
    p.add_argument("--dsn", default=os.environ.get("PG_DSN"))
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def expand_globs(paths: list[str]) -> list[Path]:
    out: list[Path] = []
    for p in paths:
        matches = glob.glob(p)
        if not matches:
            print(f"WARN: no match for {p}", file=sys.stderr)
            continue
        out.extend(Path(m) for m in matches)
    return sorted(set(out))


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if "country" not in data:
        raise ValueError(f"{path}: missing 'country' field")
    if len(data["country"]) != 2:
        raise ValueError(f"{path}: country must be 2-char ISO code, got {data['country']!r}")
    return data


def upsert(
    conn: "psycopg2.extensions.connection",
    name: str,
    aliases: list[str],
    entity_type: str,
    country: str,
    source: str,
    notes: str | None,
    party: str | None = None,
    role: str | None = None,
    dry_run: bool = False,
) -> str:
    """Insert or upsert one entity via ON CONFLICT on canonical_name.

    Schema constraint: UNIQUE(canonical_name) — so we upsert on that key
    regardless of entity_type/country. If an existing row has a different
    entity_type, we DO NOT overwrite it (preserve LLM judgment) — we only
    fill in country/source/aliases.

    Returns action: 'insert' | 'update' | 'skip'.
    """
    if not name or not name.strip():
        return "skip"

    import json as _json
    metadata: dict[str, object] = {}
    if notes:
        metadata["notes"] = notes
    if role:
        metadata["role"] = role
    md_json = _json.dumps(metadata) if metadata else None

    cur = conn.cursor()

    if dry_run:
        # Probe — does row exist?
        cur.execute(
            "SELECT 1 FROM entity_dictionary WHERE canonical_name = %s",
            (name,),
        )
        return "update" if cur.fetchone() else "insert"

    # Upsert: insert if new, otherwise merge aliases + set country/source/party
    # without touching entity_type (preserve LLM-extracted type).
    cur.execute(
        """
        INSERT INTO entity_dictionary
          (canonical_name, entity_type, aliases, country, source, party, metadata, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, now())
        ON CONFLICT (canonical_name) DO UPDATE
          SET aliases  = (
                SELECT array(SELECT DISTINCT UNNEST(
                  COALESCE(entity_dictionary.aliases, ARRAY[]::text[])
                  || EXCLUDED.aliases))
              ),
              country  = COALESCE(entity_dictionary.country, EXCLUDED.country),
              source   = COALESCE(EXCLUDED.source, entity_dictionary.source),
              party    = COALESCE(EXCLUDED.party,   entity_dictionary.party),
              metadata = COALESCE(entity_dictionary.metadata, '{}'::jsonb)
                         || COALESCE(EXCLUDED.metadata, '{}'::jsonb)
        RETURNING (xmax = 0) AS inserted
        """,
        (name, entity_type, aliases or [], country, source, party, md_json),
    )
    row = cur.fetchone()
    return "insert" if (row and row[0]) else "update"


def process_file(
    conn: "psycopg2.extensions.connection",
    path: Path,
    dry_run: bool,
) -> dict[str, int]:
    data = load_yaml(path)
    country = data["country"]
    version = data.get("version", "v1")
    source_tag = f"seed:{country.lower()}_{version}"
    counts = {"insert": 0, "update": 0, "skip": 0, "section": 0}

    for section, type_label in SECTION_TO_TYPE.items():
        rows = data.get(section) or []
        if not rows:
            continue
        counts["section"] += 1
        for row in rows:
            name = (row.get("name") or "").strip()
            aliases = [a.strip() for a in (row.get("aliases") or []) if a.strip()]
            party = row.get("party")
            role = row.get("role")
            notes = row.get("notes")
            action = upsert(
                conn, name, aliases, type_label, country,
                source_tag, notes, party=party, role=role, dry_run=dry_run,
            )
            counts[action] += 1

    if not dry_run:
        conn.commit()
    return counts


def main() -> int:
    args = parse_args()
    if not args.dsn:
        print("ERROR: --dsn or PG_DSN required", file=sys.stderr)
        return 2

    paths = expand_globs(args.files)
    if not paths:
        print("ERROR: no YAML files matched", file=sys.stderr)
        return 2

    with closing(psycopg2.connect(args.dsn)) as conn:
        conn.autocommit = False
        grand = {"insert": 0, "update": 0, "skip": 0}
        for path in paths:
            try:
                counts = process_file(conn, path, dry_run=args.dry_run)
            except Exception as e:
                conn.rollback()
                print(f"ERROR [{path}]: {e}", file=sys.stderr)
                continue
            print(
                f"[{path.name:20}] sections={counts['section']:>2}  "
                f"insert={counts['insert']:>4}  "
                f"update={counts['update']:>4}  skip={counts['skip']:>2}"
            )
            for k in ("insert", "update", "skip"):
                grand[k] += counts[k]
        print(
            f"\nTOTAL  insert={grand['insert']}  "
            f"update={grand['update']}  skip={grand['skip']}"
            + ("  (dry-run, nothing written)" if args.dry_run else "")
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
