"""Add missing Uttarakhand sources (from the Excel diff) to the sources table.
For each: try to discover an RSS/Atom feed (homepage <link> + common paths). If found →
source_type='rss' + rss_url; else 'scrape'. Tags geo_states={Uttarakhand}, country=IN,
is_active=true. Idempotent (skips domains already present). Run inside rig-backend.
"""
import asyncio
import json
import os
import re
from urllib.parse import urljoin

import httpx
import psycopg2

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = json.load(open(os.path.join(HERE, "ut_sources.json"), encoding="utf-8"))
CANDIDATES = ["/feed", "/rss", "/feed/", "/rss.xml", "/?feed=rss2", "/index.xml",
              "/atom.xml", "/feeds/posts/default?alt=rss", "/category/uttarakhand/feed"]
LINK_RE = re.compile(r"<link\b[^>]*>", re.I)


def _is_feed_link(tag: str) -> str | None:
    if not re.search(r'type=["\']application/(rss|atom)\+xml', tag, re.I):
        return None
    m = re.search(r'href=["\']([^"\']+)["\']', tag, re.I)
    return m.group(1) if m else None


async def _valid(client, url) -> bool:
    try:
        r = await client.get(url, timeout=8.0, follow_redirects=True)
        if r.status_code != 200:
            return False
        t = r.text[:600].lower()
        return ("<rss" in t) or ("<feed" in t) or ("<?xml" in t and ("rss" in t or "atom" in t))
    except Exception:
        return False


async def discover(client, base: str) -> str | None:
    try:
        r = await client.get(base, timeout=8.0, follow_redirects=True)
        if r.status_code == 200:
            for tag in LINK_RE.findall(r.text[:300000]):
                href = _is_feed_link(tag)
                if href:
                    feed = urljoin(str(r.url), href)
                    if await _valid(client, feed):
                        return feed
    except Exception:
        pass
    for p in CANDIDATES:
        feed = base.rstrip("/") + p
        if await _valid(client, feed):
            return feed
    return None


async def main():
    sem = asyncio.Semaphore(8)
    headers = {"User-Agent": "Mozilla/5.0 (compatible; RIGSourceDiscovery/1.0)"}
    results = []
    async with httpx.AsyncClient(headers=headers) as client:
        async def one(s):
            async with sem:
                feed = await discover(client, s["url"])
                return {**s, "rss_url": feed, "source_type": "rss" if feed else "scrape"}
        results = await asyncio.gather(*[one(s) for s in SRC])

    dsn = (os.environ.get("DATABASE_URL_SYNC") or os.environ["DATABASE_URL"]).replace("+asyncpg", "").replace("+psycopg2", "")
    conn = psycopg2.connect(dsn); cur = conn.cursor()
    inserted = rss = scrape = 0
    for r in results:
        cur.execute("SELECT 1 FROM sources WHERE lower(domain)=lower(%s)", (r["domain"],))
        if cur.fetchone():
            continue
        cur.execute(
            "INSERT INTO sources (name, domain, rss_url, source_type, source_tier, language, "
            "geo_states, country, is_active, health_score) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,true,1.0)",
            (r["name"], r["domain"], r["rss_url"], r["source_type"], r["tier"], r["language"],
             "{Uttarakhand}", "IN"),
        )
        inserted += 1
        rss += r["source_type"] == "rss"
        scrape += r["source_type"] == "scrape"
    conn.commit()
    print(f"feeds discovered: {sum(1 for r in results if r['rss_url'])}/{len(results)}", flush=True)
    print(f"INSERTED {inserted} (rss={rss}, scrape={scrape})", flush=True)
    for r in results:
        print(f"  {r['domain']:30s} -> {r['source_type']:6s} {r['rss_url'] or ''}", flush=True)
    conn.close()


if __name__ == "__main__":
    asyncio.run(main())
