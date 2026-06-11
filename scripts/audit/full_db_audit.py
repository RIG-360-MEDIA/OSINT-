"""full_db_audit.py — comprehensive per-table per-column DB quality audit.

Runs inside rig-backend container. Connects via SQLAlchemy, iterates every
table in the `public` schema, and emits a markdown report covering:

  - row count per table
  - column inventory with NULL%, cardinality, sample values
  - type-specific stats (min/max/avg for numerics, length for text,
    range for timestamps, true/false for booleans)
  - distinct distribution for low-cardinality columns
  - cross-table consistency checks (substrate stages, FK orphans, D1 SPO)

Output: /tmp/DB_AUDIT.md
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/app")
from sqlalchemy import text  # noqa: E402
from backend.database import get_db  # noqa: E402

OUTPUT = "/tmp/DB_AUDIT.md"

# Columns we never bother to inspect deeply (huge / opaque / non-analytical)
SKIP_DEEP = {"embedding", "labse_embedding", "summary_embedding", "vector"}


def md_escape(s: str | None) -> str:
    if s is None:
        return ""
    return str(s).replace("|", "\\|").replace("\n", " ")[:140]


async def list_tables() -> list[str]:
    async with get_db() as db:
        rows = (await db.execute(text("""
            SELECT c.relname, c.reltuples::bigint AS approx_rows
              FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE c.relkind = 'r' AND n.nspname = 'public'
             ORDER BY c.reltuples DESC
        """))).all()
    return [r[0] for r in rows]


async def table_row_count(t: str) -> int:
    async with get_db() as db:
        r = await db.execute(text(f'SELECT count(*) FROM "{t}"'))
        return int(r.scalar() or 0)


async def list_columns(t: str) -> list[tuple[str, str, str]]:
    """Returns [(column_name, data_type, is_nullable)]"""
    async with get_db() as db:
        rows = (await db.execute(text("""
            SELECT column_name, data_type, is_nullable
              FROM information_schema.columns
             WHERE table_schema = 'public' AND table_name = :t
             ORDER BY ordinal_position
        """), {"t": t})).all()
    return [(r[0], r[1], r[2]) for r in rows]


async def column_profile(t: str, col: str, ctype: str, total_rows: int) -> dict:
    """Single per-column profile query. Type-aware."""
    if col in SKIP_DEEP:
        return {"null_pct": "n/a", "distinct": "n/a", "stats": "(vector / skipped)"}
    if total_rows == 0:
        return {"null_pct": "—", "distinct": "—", "stats": ""}
    # Build the type-specific stat fragment
    safe_col = f'"{col}"'
    if ctype in ("text", "character varying", "character"):
        stat_sql = (
            f"format('avg_len=%s max_len=%s', "
            f"round(avg(length({safe_col})))::text, max(length({safe_col}))::text)"
        )
    elif ctype in ("integer", "bigint", "smallint", "numeric", "double precision", "real"):
        stat_sql = (
            f"format('min=%s max=%s avg=%s', "
            f"min({safe_col})::text, max({safe_col})::text, "
            f"round(avg({safe_col})::numeric, 2)::text)"
        )
    elif ctype in ("timestamp with time zone", "timestamp without time zone", "date"):
        stat_sql = (
            f"format('min=%s max=%s', "
            f"min({safe_col})::text, max({safe_col})::text)"
        )
    elif ctype == "boolean":
        stat_sql = (
            f"format('true=%s false=%s', "
            f"sum(CASE WHEN {safe_col} THEN 1 ELSE 0 END)::text, "
            f"sum(CASE WHEN NOT {safe_col} THEN 1 ELSE 0 END)::text)"
        )
    else:
        stat_sql = "''"

    # Distinct sampling for big tables
    if total_rows > 1_000_000:
        distinct_sql = (
            f"(SELECT count(DISTINCT {safe_col}) FROM "
            f'(SELECT {safe_col} FROM "{t}" TABLESAMPLE SYSTEM (1) LIMIT 100000) s)'
        )
        distinct_suffix = " (sampled)"
    else:
        distinct_sql = f"(SELECT count(DISTINCT {safe_col}) FROM \"{t}\")"
        distinct_suffix = ""

    sql = f"""
    SELECT
      round(100.0 * sum(CASE WHEN {safe_col} IS NULL THEN 1 ELSE 0 END)::numeric / nullif(count(*),0), 1) AS null_pct,
      {distinct_sql} AS distinct_count,
      ({stat_sql}) FILTER (WHERE {safe_col} IS NOT NULL) AS stats
    FROM "{t}"
    """
    async with get_db() as db:
        try:
            r = (await db.execute(text(sql))).first()
        except Exception as e:  # noqa: BLE001
            return {"null_pct": "err", "distinct": "err", "stats": str(e)[:100]}
    if not r:
        return {"null_pct": "—", "distinct": "—", "stats": ""}
    null_pct, distinct, stats = r
    return {
        "null_pct": f"{null_pct}%" if null_pct is not None else "—",
        "distinct": (f"{distinct}{distinct_suffix}" if distinct is not None else "—"),
        "stats": stats or "",
    }


async def column_distinct_distribution(t: str, col: str, max_card: int = 12) -> str:
    """For low-cardinality columns, show the value distribution."""
    safe_col = f'"{col}"'
    sql = f"""
    SELECT string_agg(format('%s(%s)', COALESCE(v::text, 'NULL'), n), ' · ')
    FROM (
        SELECT {safe_col} AS v, count(*) AS n
        FROM "{t}"
        GROUP BY 1
        ORDER BY 2 DESC
        LIMIT :lim
    ) x
    """
    async with get_db() as db:
        try:
            r = await db.execute(text(sql), {"lim": max_card})
            return r.scalar() or ""
        except Exception:
            return ""


async def cross_table_checks() -> str:
    lines: list[str] = ["## Cross-table consistency", ""]
    async with get_db() as db:
        # Substrate stages
        rows = (await db.execute(text("""
            SELECT substrate_status, count(*)
              FROM articles GROUP BY substrate_status
             ORDER BY count(*) DESC
        """))).all()
        lines.append("### Substrate pipeline coverage\n")
        lines.append("| substrate_status | rows |\n|---|---:|")
        for r in rows:
            lines.append(f"| {r[0] or '(null)'} | {r[1]:,} |")
        lines.append("")

        # extraction_version
        rows = (await db.execute(text("""
            SELECT extraction_version, count(*)
              FROM articles WHERE substrate_status='ok'
             GROUP BY extraction_version ORDER BY 1
        """))).all()
        lines.append("### `extraction_version` (substrate=ok only)\n")
        lines.append("| version | rows |\n|---|---:|")
        for r in rows:
            lines.append(f"| v{r[0]} | {r[1]:,} |")
        lines.append("")

        # article_type
        rows = (await db.execute(text("""
            SELECT article_type, count(*)
              FROM articles WHERE substrate_status='ok'
             GROUP BY article_type ORDER BY count(*) DESC LIMIT 20
        """))).all()
        lines.append("### article_type distribution\n")
        lines.append("| type | rows |\n|---|---:|")
        for r in rows:
            lines.append(f"| {r[0] or '(null)'} | {r[1]:,} |")
        lines.append("")

        # SPO progress (D1)
        r = (await db.execute(text("""
            SELECT
              count(*) FILTER (WHERE subject_text IS NOT NULL AND predicate IS NOT NULL AND object_text IS NOT NULL) AS full_spo,
              count(*) FILTER (WHERE subject_text IS NOT NULL AND predicate IS NULL) AS subj_only,
              count(*) FILTER (WHERE predicate IS NOT NULL AND object_text IS NULL) AS pred_only,
              count(*) FILTER (WHERE subject_entity_id IS NOT NULL) AS entity_linked,
              count(*) FILTER (WHERE embedding IS NOT NULL) AS embedded,
              count(*) AS total
              FROM article_claims
        """))).first()
        full_pct = round(100.0 * r[0] / max(r[5], 1), 1)
        emb_pct = round(100.0 * r[4] / max(r[5], 1), 1)
        ent_pct = round(100.0 * r[3] / max(r[5], 1), 1)
        lines.append("### D1 — claims SPO state\n")
        lines.append(f"- **Full SPO**: {r[0]:,} / {r[5]:,} ({full_pct}%)")
        lines.append(f"- Subject only (no predicate): {r[1]:,}")
        lines.append(f"- Predicate only (no object): {r[2]:,}")
        lines.append(f"- Entity-linked (subject_entity_id NOT NULL): {r[3]:,} ({ent_pct}%)")
        lines.append(f"- LaBSE embedded: {r[4]:,} ({emb_pct}%)")
        lines.append("")

        # FK orphans
        r = (await db.execute(text("""
            SELECT count(*) FROM article_claims c
            LEFT JOIN articles a ON a.id = c.article_id
            WHERE a.id IS NULL
        """))).scalar()
        lines.append(f"### FK orphans — `article_claims` → `articles`: {r:,}\n")

        # Quote language coverage
        rows = (await db.execute(text("""
            SELECT a.language_iso, count(*) total,
                   count(*) FILTER (WHERE q.quote_text_en IS NOT NULL) translated
              FROM article_quotes q JOIN articles a ON a.id = q.article_id
             GROUP BY a.language_iso ORDER BY count(*) DESC LIMIT 15
        """))).all()
        lines.append("### Quotes — language vs translation coverage\n")
        lines.append("| lang | quotes | translated | % |\n|---|---:|---:|---:|")
        for lang, total, translated in rows:
            pct = round(100.0 * (translated or 0) / max(total, 1), 1)
            lines.append(f"| {lang or '(null)'} | {total:,} | {translated:,} | {pct}% |")
        lines.append("")

        # entity_dictionary cardinality
        r = (await db.execute(text(
            "SELECT count(*), count(DISTINCT entity_type) FROM entity_dictionary"
        ))).first()
        lines.append(f"### entity_dictionary: {r[0]:,} rows · {r[1]} types\n")

        rows = (await db.execute(text("""
            SELECT entity_type, count(*)
              FROM entity_dictionary
             GROUP BY entity_type ORDER BY count(*) DESC
        """))).all()
        lines.append("| entity_type | rows |\n|---|---:|")
        for r in rows:
            lines.append(f"| {r[0] or '(null)'} | {r[1]:,} |")
        lines.append("")

    return "\n".join(lines)


async def main() -> int:
    parts: list[str] = []
    parts.append("# RIG-Surveillance Database Quality Audit\n")
    parts.append(f"Generated: {datetime.now(timezone.utc).isoformat()}\n")
    parts.append("")

    # Table inventory
    tables = await list_tables()
    parts.append(f"## Table inventory ({len(tables)} tables in `public` schema)\n")
    parts.append("| Table | Rows |\n|---|---:|")
    table_rowcounts: dict[str, int] = {}
    for t in tables:
        try:
            n = await table_row_count(t)
        except Exception:
            n = 0
        table_rowcounts[t] = n
        parts.append(f"| `{t}` | {n:,} |")
    parts.append("")

    # Per-table deep dive — biggest first, skip bak/backup/empty
    skip_prefixes = ("_bak_", "_backup_", "articles_lang_backup_",
                     "article_events_is_future_backup_", "kombu_message",
                     "celery_taskmeta")
    sorted_tables = sorted(tables, key=lambda t: -table_rowcounts.get(t, 0))
    for t in sorted_tables:
        if any(t.startswith(p) or t == p for p in skip_prefixes):
            continue
        n = table_rowcounts.get(t, 0)
        if n == 0:
            continue
        cols = await list_columns(t)
        parts.append(f"\n## `{t}`\n")
        parts.append(f"**Rows:** {n:,} · **Columns:** {len(cols)}\n")
        parts.append("| Column | Type | Nullable | NULL% | Distinct | Stats / Top values |")
        parts.append("|---|---|---|---:|---:|---|")
        for col, ctype, nullable in cols:
            prof = await column_profile(t, col, ctype, n)
            notes = prof["stats"]
            # Low-cardinality enrichment
            distinct_str = str(prof["distinct"])
            try:
                d_int = int(distinct_str.split(" ")[0])
                if 0 < d_int <= 12 and col not in SKIP_DEEP:
                    dist = await column_distinct_distribution(t, col, max_card=12)
                    if dist:
                        notes = f"{notes} · {dist}" if notes else dist
            except (ValueError, IndexError):
                pass
            parts.append(
                f"| `{col}` | {ctype} | {nullable} | {prof['null_pct']} | "
                f"{prof['distinct']} | {md_escape(notes)} |"
            )

    # Cross-table checks
    parts.append("")
    parts.append(await cross_table_checks())
    parts.append("\n_Audit complete._\n")

    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    print(f"Wrote {OUTPUT}")
    print(f"Lines: {len(parts)}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
