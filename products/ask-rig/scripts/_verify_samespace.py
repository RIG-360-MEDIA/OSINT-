"""Throwaway pre-flight: embed test queries with LaBSE and emit a .sql file of v4
vector searches. Pipe the output to psql (read-only) to confirm that FRESH query
vectors land in the stored v4 space. Run with the ask-rig venv python.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.embedding import LabseEmbedder, to_pgvector  # noqa: E402

QUERIES = [
    "Telangana farmer loan waiver",
    "Hyderabad metro rail expansion project",
    "మూసీ నది ప్రక్షాళన ప్రాజెక్టు",  # Musi river cleanup (Telugu)
    "केसीआर बनाम रेवंत रेड्डी",  # KCR vs Revanth Reddy (Hindi)
]
OUT = Path(__file__).resolve().parent / "_samespace.sql"


def block(query: str, literal: str) -> str:
    return (
        f"\\echo '=== {query} ==='\n"
        "SELECT left(title,58) t, language_detected lang, "
        f"round((labse_embedding_v4 <=> '{literal}'::vector)::numeric,3) d\n"
        "FROM articles\n"
        "WHERE labse_embedding_v4 IS NOT NULL AND substrate_status='ok' AND NOT is_duplicate\n"
        f"ORDER BY labse_embedding_v4 <=> '{literal}'::vector\nLIMIT 5;\n\\echo ''\n"
    )


def main() -> None:
    embedder = LabseEmbedder()
    parts = ["\\pset format unaligned\n\\pset fieldsep ' | '\n\\pset footer off\n"]
    for query in QUERIES:
        parts.append(block(query, to_pgvector(embedder.embed(query))))
    OUT.write_text("".join(parts), encoding="utf-8")
    print(f"WROTE {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
