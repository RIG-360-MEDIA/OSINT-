"""PRE-FLIGHT: does a freshly LaBSE-embedded query land in the v4 vector space?

Embeds a few queries (English + Telugu + Hindi), runs each through hybrid search,
and prints the top hits. Pass conditions:
  1. The titles are on-topic for the query (semantic search works).
  2. An English query surfaces some Telugu/Hindi articles (cross-lingual works).
If both hold, the embedding recipe is compatible and the engine is safe to build on.

Run (needs the SSH tunnel + sentence-transformers installed + ASKRIG_DB_URL set):
    .venv/Scripts/python scripts/verify_embedding.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import load_settings  # noqa: E402
from app.db import connect  # noqa: E402
from app.embedding import LabseEmbedder  # noqa: E402
from app.retrieval import hybrid_search  # noqa: E402

QUERIES = [
    "Telangana farmer loan waiver",
    "Hyderabad metro rail expansion",
    "మూసీ నది ప్రక్షాళన ప్రాజెక్టు",  # Musi river cleanup project (Telugu)
    "केसीआर बनाम रेवंत रेड्डी",  # KCR vs Revanth Reddy (Hindi)
]


async def main() -> None:
    settings = load_settings()
    embedder = LabseEmbedder(settings.embed_model)
    async with connect(settings) as conn:
        for query in QUERIES:
            qvec = embedder.embed(query)
            docs = await hybrid_search(conn, settings, query, qvec, None, 5)
            print(f"\n=== {query} ===")
            for doc in docs:
                lang = (doc.language or "?").upper()
                print(f"  [{lang}] {(doc.title or '')[:72]}  (score={doc.score})")


if __name__ == "__main__":
    asyncio.run(main())
