"""
Government-source inventory.

Reads `backend.collectors.sources.registry.SOURCE_REGISTRY` (after
auto-loading every family module) and optionally cross-references the
`govt_document_sources` and `govt_collection_runs` tables for production
health.

Usage
-----
    # Adapter-only listing (no DB)
    python -m backend.scripts.list_govt_sources

    # Include DB cross-reference (requires DATABASE_URL)
    python -m backend.scripts.list_govt_sources --with-db

    # Emit the markdown matrix used in docs/qa/govt-sources-inventory.md
    python -m backend.scripts.list_govt_sources --markdown > \
        docs/qa/govt-sources-inventory.md
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from backend.collectors.sources import registry


def _family_of(fn) -> str:
    return fn.__module__.rsplit(".", 1)[-1]


def _load_registry() -> dict[str, Any]:
    registry._autoload_family_modules()
    return registry.SOURCE_REGISTRY


def _group_by_family(reg: dict[str, Any]) -> dict[str, list[tuple[str, str]]]:
    grouped: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for url_key, fn in reg.items():
        grouped[_family_of(fn)].append((url_key, fn.__name__))
    return dict(sorted(grouped.items()))


async def _fetch_db_health() -> dict[str, dict[str, Any]]:
    """Return {url_substring: {rows_30d, last_success_at, last_error}}."""
    from backend.database import get_db  # local import — avoids hard dep

    out: dict[str, dict[str, Any]] = {}
    async with get_db() as db:
        from sqlalchemy import text

        rows = await db.execute(text(
            """
            SELECT
              s.portal_url,
              s.last_success_at,
              s.last_error,
              COALESCE(d.rows_30d, 0) AS rows_30d
            FROM govt_document_sources s
            LEFT JOIN (
              SELECT source_id, COUNT(*) AS rows_30d
              FROM govt_documents
              WHERE collected_at > NOW() - INTERVAL '30 days'
              GROUP BY source_id
            ) d ON d.source_id = s.id
            """
        ))
        for r in rows.mappings():
            out[r["portal_url"]] = {
                "rows_30d": r["rows_30d"],
                "last_success_at": r["last_success_at"],
                "last_error": r["last_error"],
            }
    return out


def _health_label(rec: dict[str, Any] | None) -> str:
    if rec is None:
        return "no DB row (orphan adapter)"
    last = rec.get("last_success_at")
    if last is None:
        return "never succeeded"
    if isinstance(last, datetime):
        age_d = (datetime.now(timezone.utc) - last).days
        if age_d > 7:
            return f"stale ({age_d}d)"
        return f"healthy ({age_d}d)"
    return str(last)


def _print_text(grouped: dict[str, list[tuple[str, str]]],
                health: dict[str, dict[str, Any]] | None) -> None:
    total = sum(len(v) for v in grouped.values())
    print(f"Registered govt-source adapters: {total}\n")
    for family, items in grouped.items():
        print(f"## {family} ({len(items)})")
        for url_key, fn_name in sorted(items):
            line = f"  - {url_key}  ->  {fn_name}"
            if health is not None:
                rec = next(
                    (v for k, v in health.items() if url_key in k),
                    None,
                )
                line += f"   [{_health_label(rec)}]"
                if rec:
                    line += f"  rows30d={rec['rows_30d']}"
            print(line)
        print()


def _print_markdown(grouped: dict[str, list[tuple[str, str]]],
                    health: dict[str, dict[str, Any]] | None) -> None:
    total = sum(len(v) for v in grouped.values())
    print("# Government Source Inventory\n")
    print(f"**Total registered adapters:** {total}")
    print(f"**Families:** {len(grouped)}\n")
    print("| Family | Adapter | URL key | Rows (30d) | Last success | Health |")
    print("|---|---|---|---|---|---|")
    for family, items in grouped.items():
        for url_key, fn_name in sorted(items):
            rec = None
            if health is not None:
                rec = next(
                    (v for k, v in health.items() if url_key in k),
                    None,
                )
            rows30d = rec["rows_30d"] if rec else "-"
            last = rec["last_success_at"] if rec else "-"
            print(
                f"| {family} | `{fn_name}` | `{url_key}` | {rows30d} | "
                f"{last} | {_health_label(rec)} |"
            )


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--with-db", action="store_true",
                   help="Cross-reference DB for health (requires DATABASE_URL).")
    p.add_argument("--markdown", action="store_true",
                   help="Emit a markdown table.")
    args = p.parse_args()

    reg = _load_registry()
    grouped = _group_by_family(reg)

    health: dict[str, dict[str, Any]] | None = None
    if args.with_db:
        if not os.environ.get("DATABASE_URL"):
            print("ERROR: --with-db requires DATABASE_URL", file=sys.stderr)
            return 2
        health = asyncio.run(_fetch_db_health())

    if args.markdown:
        _print_markdown(grouped, health)
    else:
        _print_text(grouped, health)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
