"""End-to-end demo: embed -> hybrid retrieve -> cited answer (+ guardrail).

Run with ASKRIG_DB_URL (tunnel) and ASKRIG_LLM_API_KEY set. Pass queries as args,
or use the defaults.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.answer import answer_question  # noqa: E402
from app.config import load_settings  # noqa: E402
from app.db import connect  # noqa: E402
from app.embedding import LabseEmbedder  # noqa: E402
from app.llm import get_llm  # noqa: E402
from app.retrieval import retrieve_and_curate  # noqa: E402

QUERIES = sys.argv[1:] or [
    "What is happening with farmer loan waivers in Telangana?",
    "Latest on the Hyderabad metro rail expansion",
]


async def main() -> None:
    settings = load_settings()
    embedder = LabseEmbedder(settings.embed_model)
    llm = get_llm(settings)
    async with connect(settings) as conn:
        for query in QUERIES:
            docs = await retrieve_and_curate(conn, settings, query, embedder.embed(query))
            result = answer_question(llm, query, docs)
            print("\n" + "=" * 72)
            print("Q:", query)
            print(f"FAITHFUL: {result.faithful} | notes: {result.notes}")
            print("ANSWER:\n" + result.answer)
            print("CITATIONS:")
            for c in result.citations:
                print(f"  [{c.marker}] ({(c.language or '?').upper()}) {c.title} | {c.url}")
            print("TOP RETRIEVED (precision eyeball):")
            for d in docs:
                lang = (d.language or "?").upper()
                print(f"  [{lang}] {(d.title or '')[:58]} :: {(d.snippet or '(no snippet)')[:66]}")


if __name__ == "__main__":
    asyncio.run(main())
