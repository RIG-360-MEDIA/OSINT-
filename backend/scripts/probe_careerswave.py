"""One-off probe: which seeded newspapers have a downloadable PDF for today?"""
from __future__ import annotations

import asyncio
import sys
from datetime import date

sys.path.insert(0, "/app")

from sqlalchemy import text

from backend.collectors.newspaper_collector import (
    _find_gdrive_id_near_date,
    _GDRIVE_FILE_ID_RE,
)
from backend.database import get_db

import httpx

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


async def probe_one(client: httpx.AsyncClient, name: str, lang: str, url: str) -> dict:
    today = date.today()
    try:
        r = await client.get(url, timeout=20)
    except Exception as exc:
        return {"name": name, "lang": lang, "status": "PAGE_FAIL", "detail": str(exc)[:60]}
    if r.status_code != 200:
        return {"name": name, "lang": lang, "status": "PAGE_HTTP", "detail": str(r.status_code)}
    html = r.text
    for offset in (0, 1, 2):
        target = today.fromordinal(today.toordinal() - offset)
        fid = _find_gdrive_id_near_date(html, target)
        if fid:
            return {
                "name": name, "lang": lang,
                "status": "DATED_OK",
                "detail": f"d-{offset} {fid[:14]}…",
            }
    m = _GDRIVE_FILE_ID_RE.search(html)
    if m:
        return {
            "name": name, "lang": lang,
            "status": "UNDATED",
            "detail": m.group(1)[:14] + "…",
        }
    return {"name": name, "lang": lang, "status": "NO_PDF", "detail": ""}


async def main() -> None:
    async with get_db() as db:
        r = await db.execute(
            text(
                "SELECT name, language, careerswave_url FROM newspaper_sources "
                "WHERE is_active=TRUE AND careerswave_url IS NOT NULL ORDER BY name"
            )
        )
        papers = [(row.name, row.language, row.careerswave_url) for row in r.fetchall()]

    sem = asyncio.Semaphore(8)
    async with httpx.AsyncClient(
        timeout=20, follow_redirects=True, headers={"User-Agent": UA}
    ) as client:

        async def go(name: str, lang: str, url: str) -> dict:
            async with sem:
                return await probe_one(client, name, lang, url)

        results = await asyncio.gather(*[go(*p) for p in papers])

    by_status: dict[str, list[dict]] = {}
    for r in results:
        by_status.setdefault(r["status"], []).append(r)

    print(f"\n{len(results)} newspapers probed for {date.today().isoformat()}\n")
    for status in ("DATED_OK", "UNDATED", "NO_PDF", "PAGE_HTTP", "PAGE_FAIL"):
        rows = by_status.get(status, [])
        print(f"── {status} ({len(rows)}) ──")
        for row in sorted(rows, key=lambda x: (x["lang"], x["name"])):
            print(f"  [{row['lang']}] {row['name']:<22} {row['detail']}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
