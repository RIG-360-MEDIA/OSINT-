"""Smoke test for v2.1 helpers."""
import asyncio
import sys
sys.path.insert(0, "/app")
from backend.database import get_db
from backend.observability.overview_helpers import breaking_now, top_speakers, article_types


async def main():
    async with get_db() as db:
        b = await breaking_now(db, limit=3)
        print(f"breaking: {len(b['items'])} items")
        for x in b['items'][:3]:
            print(f"  • [{x['source']}] {x['title'][:80]}")
        print()
        s = await top_speakers(db, limit=5)
        print(f"speakers: {len(s['speakers'])} entries")
        for x in s['speakers']:
            print(f"  • {x['speaker']:25s} {x['n_quotes']} quotes / {x['n_sources']} sources")
        print()
        a = await article_types(db)
        print(f"atlas:")
        print(f"  article_types: {len(a['article_types'])}")
        print(f"  languages_24h: {len(a['languages_24h'])}")
        print(f"  stances:       {len(a['stances'])}")
        print(f"  countries:     {len(a['top_countries'])}")
        print(f"  entity_dict:   {a['entity_dictionary']}")


asyncio.run(main())
