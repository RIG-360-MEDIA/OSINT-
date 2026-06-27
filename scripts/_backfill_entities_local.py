"""Fast local-only entities backfill for the NLP entity gap (2026-06-13).

These articles are ALREADY substrate-processed (translated/topic'd/embedded) — only
`entities_extracted` is missing (the legacy nlp_processor crashed on a deleted module
2026-06-11..06-13). process_nlp_batch redundantly re-runs LLM translation/topic/embed
per article (~6s each) just to reach the LOCAL spaCy entity step. This drains the gap
directly: spaCy NER + dictionary resolution on the `lead_text_translated` already in
the DB. No LLM, no re-fetch — thousands/hr. Newest-first so the night-desk recovers
first. Scoped to substrate-processed rows; genuinely-new/unprocessed rows are left for
the full pipeline. Run detached inside rig-backend."""
import asyncio
import json

import spacy
from sqlalchemy import text


async def go(batch: int = 200):
    from backend.database import get_db
    from backend.nlp.nlp_entities import extract_entities, load_entity_dictionary

    nlp_model = spacy.load("en_core_web_sm")
    async with get_db() as db:
        n = await load_entity_dictionary(db)
    print(f"entity dictionary loaded: {n} entries", flush=True)

    total = 0
    while True:
        async with get_db() as db:
            rows = (await db.execute(text("""
                SELECT id::text AS id, title, lead_text_translated AS lt
                FROM articles
                WHERE nlp_processed = FALSE
                  AND substrate_processed_at IS NOT NULL
                ORDER BY collected_at DESC
                LIMIT :b
            """), {"b": batch})).fetchall()
            if not rows:
                break
            for r in rows:
                working = (r.lt or r.title or "")
                ents = extract_entities(title=(r.title or ""), text=working, nlp_model=nlp_model)
                await db.execute(text("""
                    UPDATE articles
                    SET entities_extracted = CAST(:e AS jsonb),
                        nlp_processed = TRUE,
                        nlp_confidence = COALESCE(nlp_confidence, 'normal')
                    WHERE id = CAST(:id AS uuid)
                """), {"e": json.dumps(ents), "id": r.id})
            await db.commit()
            total += len(rows)
            print(f"entities backfill: +{len(rows)} (total {total})", flush=True)
    print(f"DONE: {total} articles", flush=True)


if __name__ == "__main__":
    asyncio.run(go())
