"""Entity portrait resolver — Wikipedia REST summary -> analytics.entity_image.

The integrated image source for the Dossier. Conservative by design: only store a
photo when the Wikipedia page is a 'standard' article, has a thumbnail, AND its
description/extract confirms the right kind of entity (person/org/place) — so we
never attach the wrong person's face. Misses are marked ok=false; the UI then falls
back to initials. Re-run to refresh or to cover newly-watched entities:

    docker exec osint-backend python /app/resolve_entity_images.py
"""
from __future__ import annotations

import asyncio
import json
import re
import urllib.parse
import urllib.request

from sqlalchemy import text
from db import get_db

UA = "RIG-OSINT/1.0 (research; contact tdsworks@gmail.com)"
PERSON_RE = re.compile(r"politician|minister|chief|leader|\bMP\b|\bMLA\b|president|spokesperson|"
                       r"party|indian|actor|chairman|governor|economist|bureaucrat|official", re.I)
ORG_RE = re.compile(r"party|court|bank|commission|ministry|organi|government|aayog|agency|council|institution|company|corporation|technology", re.I)
PLACE_RE = re.compile(r"city|district|state|town|region|capital|village|india|metropolis|municipal|mandal", re.I)


def wiki_summary(title: str):
    url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(title.replace(" ", "_"))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.load(r)
    except Exception:
        return None


def accept(data, etype: str):
    if not data or data.get("type") != "standard":
        return None
    thumb = (data.get("thumbnail") or {}).get("source")
    if not thumb:
        return None
    desc = ((data.get("description") or "") + " " + (data.get("extract") or "")).strip()
    rx = PERSON_RE if etype == "person" else ORG_RE if etype == "organization" else PLACE_RE
    if not rx.search(desc):
        return None
    return {"image_url": thumb, "url": ((data.get("content_urls") or {}).get("desktop") or {}).get("page")}


async def main():
    async with get_db() as db:
        ids = [r.e for r in (await db.execute(text("""
            SELECT DISTINCT e FROM (
              SELECT jsonb_array_elements_text(watchlist->'entity_ids') e FROM analytics.user_brief_prefs
              UNION SELECT primary_subject_id::text FROM analytics.user_brief_prefs WHERE primary_subject_id IS NOT NULL
            ) x WHERE e IS NOT NULL
        """))).fetchall()]
        ents = (await db.execute(text("""
            SELECT id::text id, canonical_name, entity_type, aliases
              FROM entity_dictionary WHERE id = ANY(CAST(:ids AS uuid[]))
        """), {"ids": ids})).fetchall()

        ok = miss = 0
        for e in ents:
            got = None
            for nm in [e.canonical_name, *(list(e.aliases or [])[:2])]:
                got = accept(await asyncio.to_thread(wiki_summary, nm), e.entity_type)
                if got:
                    break
            if got:
                await db.execute(text("""
                    INSERT INTO analytics.entity_image (entity_id, image_url, attribution, source, ok)
                    VALUES (CAST(:id AS uuid), :u, :a, 'wikipedia', true)
                    ON CONFLICT (entity_id) DO UPDATE SET image_url = EXCLUDED.image_url,
                      attribution = EXCLUDED.attribution, source = 'wikipedia', ok = true, fetched_at = now()
                """), {"id": e.id, "u": got["image_url"], "a": got.get("url")})
                ok += 1
            else:
                await db.execute(text("""
                    INSERT INTO analytics.entity_image (entity_id, ok, source)
                    VALUES (CAST(:id AS uuid), false, 'wikipedia')
                    ON CONFLICT (entity_id) DO UPDATE SET ok = false, fetched_at = now()
                """), {"id": e.id})
                miss += 1
        await db.commit()
        print(f"images: {ok} resolved, {miss} fallback, total {len(ents)}")


if __name__ == "__main__":
    asyncio.run(main())
