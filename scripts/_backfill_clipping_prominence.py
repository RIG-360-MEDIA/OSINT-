"""Backfill `prominence` into clipping entities (#9). Clipping entities were {name,type}
only — no centrality signal — so the relevance scorer treated a passing mention the same as
the subject. Heuristic (no LLM): headline mention = 1.0, lead (first 300 chars) = 0.8,
repeated in body = 0.6, single body mention = 0.4, not locatable = 0.3. Idempotent
(skips entities that already carry prominence). Run inside rig-backend."""
import asyncio
import json

from sqlalchemy import text


def _prom(name: str, headline: str, body: str) -> float:
    n = (name or "").strip().lower()
    if not n:
        return 0.3
    if n in headline:
        return 1.0
    if n in body[:300]:
        return 0.8
    c = body.count(n)
    if c >= 2:
        return 0.6
    if c == 1:
        return 0.4
    return 0.3


async def go(days: int = 90, batch: int = 500):
    from backend.database import get_db
    updated = 0
    while True:
        async with get_db() as db:
            rows = (await db.execute(text("""
                SELECT id::text AS id, headline, body_text, body_text_translated, entities_extracted
                FROM clippings
                WHERE edition_date > now() - (:d || ' days')::interval
                  AND jsonb_typeof(entities_extracted) = 'array'
                  AND jsonb_array_length(entities_extracted) > 0
                  AND NOT (entities_extracted->0 ? 'prominence')
                ORDER BY edition_date DESC LIMIT :b
            """), {"d": str(days), "b": batch})).fetchall()
            if not rows:
                break
            for r in rows:
                hl = (r.headline or "").lower()
                body = ((r.body_text or "") + " " + (r.body_text_translated or "")).lower()
                ents = r.entities_extracted
                if isinstance(ents, str):
                    ents = json.loads(ents)
                new = []
                for e in ents:
                    if isinstance(e, dict) and e.get("name"):
                        e = {**e, "prominence": _prom(e["name"], hl, body)}
                    new.append(e)
                await db.execute(text(
                    "UPDATE clippings SET entities_extracted = CAST(:e AS jsonb) WHERE id = CAST(:id AS uuid)"
                ), {"e": json.dumps(new, ensure_ascii=False), "id": r.id})
                updated += 1
            await db.commit()
            print(f"backfilled prominence into {updated} clippings", flush=True)
    print(f"DONE: {updated} clippings", flush=True)


if __name__ == "__main__":
    asyncio.run(go())
