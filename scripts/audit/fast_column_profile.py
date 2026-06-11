"""fast_column_profile.py — per-column NULL%/distinct via ONE query per table.

Fixes the v2 audit bug (FILTER on non-aggregate). One SELECT per table
generates count + per-column null_count + per-column distinct_count in
a single Postgres pass. ~60 tables × 1 query = ~30 seconds total.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/app")
from sqlalchemy import text  # noqa: E402
from backend.database import get_db  # noqa: E402

OUTPUT = "/tmp/DB_COLUMN_PROFILE.md"
SKIP_TABLE_PREFIXES = (
    "_bak_", "_backup_", "articles_lang_backup_",
    "article_events_is_future_backup_", "kombu_message", "celery_taskmeta",
)
SKIP_COL_TYPES = {"USER-DEFINED", "tsvector", "jsonb", "json", "ARRAY"}


async def list_tables() -> list[str]:
    async with get_db() as db:
        rows = (await db.execute(text("""
            SELECT c.relname FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind = 'r' AND n.nspname = 'public'
            ORDER BY c.reltuples DESC
        """))).all()
    return [r[0] for r in rows]


async def list_columns(t: str) -> list[tuple[str, str]]:
    async with get_db() as db:
        rows = (await db.execute(text("""
            SELECT column_name, data_type FROM information_schema.columns
            WHERE table_schema='public' AND table_name=:t
            ORDER BY ordinal_position
        """), {"t": t})).all()
    return [(r[0], r[1]) for r in rows]


async def profile_table(t: str) -> list[dict]:
    """One SELECT per table — null counts + distinct counts for every column."""
    cols = await list_columns(t)
    if not cols:
        return []
    # Build aggregates: one count(*) FILTER per column for nulls, one count(DISTINCT) per column
    parts = ["count(*) AS row_total"]
    for col, ctype in cols:
        safe = f'"{col}"'
        parts.append(f"count(*) FILTER (WHERE {safe} IS NULL) AS \"_null_{col}\"")
        if ctype not in SKIP_COL_TYPES:
            parts.append(f"count(DISTINCT {safe}) AS \"_dist_{col}\"")
    sql = f"SELECT {', '.join(parts)} FROM \"{t}\""
    async with get_db() as db:
        try:
            r = (await db.execute(text(sql))).first()
        except Exception as e:  # noqa: BLE001
            return [{"col": "ERR", "type": "—", "null_pct": "—", "distinct": str(e)[:80]}]
    if not r:
        return []
    total = int(r[0] or 0)
    out = []
    for col, ctype in cols:
        nulls = getattr(r, f"_null_{col}")
        dist = getattr(r, f"_dist_{col}", "—") if ctype not in SKIP_COL_TYPES else "n/a"
        null_pct = round(100.0 * (nulls or 0) / max(total, 1), 1)
        out.append({
            "col": col, "type": ctype,
            "rows": total,
            "null_pct": f"{null_pct}%",
            "null_count": nulls or 0,
            "distinct": dist,
        })
    return out


async def main() -> int:
    tables = await list_tables()
    parts: list[str] = []
    parts.append("# RIG-Surveillance Per-Column Quality Profile (fast pass)\n")
    parts.append(f"Generated: {datetime.now(timezone.utc).isoformat()}\n")
    parts.append("")
    for t in tables:
        if any(t.startswith(p) or t == p for p in SKIP_TABLE_PREFIXES):
            continue
        rows = await profile_table(t)
        if not rows:
            continue
        total = rows[0]["rows"]
        if total == 0:
            continue
        parts.append(f"## `{t}` — {total:,} rows · {len(rows)} columns\n")
        parts.append("| Column | Type | NULL% | Distinct |")
        parts.append("|---|---|---:|---:|")
        for r in rows:
            parts.append(f"| `{r['col']}` | {r['type']} | {r['null_pct']} | {r['distinct']} |")
        parts.append("")
        # Stdout progress
        print(f"  done {t}: {len(rows)} cols, {total:,} rows")

    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    print(f"Wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
