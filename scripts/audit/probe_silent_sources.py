"""probe_silent_sources.py — actually fetch silent sources, classify failure.

For 60 random silent sources (mix of bucket A/B/D), make an HTTP GET to
their rss_url with a real browser User-Agent and classify the response:

  - 200 + valid RSS XML → OUR FAULT (parser bug, schedule, blocked, etc.)
  - 200 + HTML / empty → site changed (RSS deprecated or replaced)
  - 301/302 → URL moved (need to update rss_url)
  - 403/406 → blocked (User-Agent banned)
  - 404/410 → feed deleted
  - SSL error → cert issue
  - timeout → site slow/down
"""
from __future__ import annotations

import asyncio
import sys
from collections import Counter, defaultdict

sys.path.insert(0, "/app")
import httpx  # noqa: E402
from sqlalchemy import text  # noqa: E402

from backend.database import get_db  # noqa: E402

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


async def probe_one(client: httpx.AsyncClient, source: dict) -> dict:
    url = source["rss_url"]
    if not url:
        return {**source, "verdict": "NO_URL"}
    try:
        r = await client.get(url, timeout=12.0, follow_redirects=False)
    except httpx.ConnectError as e:
        msg = str(e)[:60]
        if "ssl" in msg.lower() or "cert" in msg.lower():
            return {**source, "verdict": "SSL_ERROR", "detail": msg}
        return {**source, "verdict": "CONNECT_FAIL", "detail": msg}
    except httpx.ReadTimeout:
        return {**source, "verdict": "TIMEOUT"}
    except Exception as e:  # noqa: BLE001
        return {**source, "verdict": "FETCH_EXC", "detail": str(e)[:80]}

    status = r.status_code
    body = r.text[:800] if r.content else ""
    redir = r.headers.get("location", "")

    if status in (301, 302, 307, 308):
        return {**source, "verdict": "MOVED", "detail": redir[:120], "status": status}
    if status == 403:
        return {**source, "verdict": "BLOCKED_403", "status": status}
    if status == 404:
        return {**source, "verdict": "GONE_404", "status": status}
    if status == 410:
        return {**source, "verdict": "GONE_410", "status": status}
    if status == 406:
        return {**source, "verdict": "BLOCKED_406", "status": status}
    if status == 429:
        return {**source, "verdict": "RATELIMITED_429", "status": status}
    if status >= 500:
        return {**source, "verdict": f"SERVER_{status}", "status": status}
    if status == 200:
        # Check if body is actually RSS/Atom
        bl = body.lower().lstrip()
        if "<rss" in bl or "<feed" in bl or "<?xml" in bl or "<rdf:rdf" in bl:
            return {**source, "verdict": "RSS_OK_OUR_FAULT", "status": 200,
                    "detail": f"valid RSS, {len(r.content)} bytes"}
        if "<html" in bl or "<!doctype html" in bl:
            return {**source, "verdict": "HTML_NOT_RSS", "status": 200,
                    "detail": "got HTML page where RSS expected"}
        if len(body.strip()) < 50:
            return {**source, "verdict": "EMPTY_BODY", "status": 200}
        return {**source, "verdict": "UNKNOWN_BODY", "status": 200,
                "detail": body[:80].replace("\n", " ")}
    return {**source, "verdict": f"HTTP_{status}", "status": status}


async def main() -> int:
    # Pull 60 silent sources, weighted across buckets
    async with get_db() as db:
        rows = (await db.execute(text("""
            WITH last_per_source AS (
              SELECT s.id, s.name, s.rss_url, s.source_type,
                     s.consecutive_failures, s.health_score, s.source_tier,
                     MAX(a.collected_at) AS last_article_at
              FROM sources s LEFT JOIN articles a ON a.source_id = s.id
              WHERE s.is_active = true AND s.source_type = 'rss'
              GROUP BY s.id
            )
            SELECT id, name, rss_url, source_type, consecutive_failures,
                   health_score, source_tier, last_article_at,
                   CASE
                     WHEN last_article_at IS NULL THEN 'A_never'
                     WHEN last_article_at < NOW() - INTERVAL '30 days' THEN 'B_30d+'
                     WHEN last_article_at < NOW() - INTERVAL '7 days' THEN 'C_7-30d'
                     WHEN last_article_at < NOW() - INTERVAL '24 hours' THEN 'D_1-7d'
                     ELSE 'F_recent'
                   END AS bucket
            FROM last_per_source
            WHERE last_article_at IS NULL
               OR last_article_at < NOW() - INTERVAL '24 hours'
            ORDER BY RANDOM()
            LIMIT 60
        """))).mappings().all()
    sources = [dict(r) for r in rows]
    print(f"Probing {len(sources)} silent RSS sources...\n")

    async with httpx.AsyncClient(
        headers={"User-Agent": UA, "Accept": "application/rss+xml, application/xml, text/xml, */*"},
        verify=True,
    ) as client:
        sem = asyncio.Semaphore(6)

        async def worker(s):
            async with sem:
                return await probe_one(client, s)

        results = await asyncio.gather(*(worker(s) for s in sources))

    # Print per-source verdicts
    print(f"{'Source':<32} {'Bucket':<10} {'Verdict':<22} {'Detail':<50}")
    print("-" * 116)
    for r in sorted(results, key=lambda x: (x.get("verdict", ""), x.get("name", ""))):
        name = (r.get("name") or "?")[:32]
        bucket = r.get("bucket", "?")
        verdict = r.get("verdict", "?")
        detail = (r.get("detail") or "")[:48]
        print(f"{name:<32} {bucket:<10} {verdict:<22} {detail:<50}")

    # Roll up
    print("\n" + "=" * 80)
    print("VERDICT ROLL-UP")
    print("=" * 80)
    verdicts = Counter(r.get("verdict", "?") for r in results)
    for v, n in verdicts.most_common():
        pct = n / len(results) * 100
        print(f"  {v:<22} {n:>3} ({pct:.1f}%)")
    print()
    # OURS vs THEIRS
    ours = sum(verdicts[v] for v in ("RSS_OK_OUR_FAULT",))
    theirs_dead = sum(verdicts[v] for v in ("GONE_404", "GONE_410", "HTML_NOT_RSS", "EMPTY_BODY", "BLOCKED_403", "BLOCKED_406", "SSL_ERROR"))
    theirs_recoverable = sum(verdicts[v] for v in ("MOVED", "RATELIMITED_429", "TIMEOUT"))
    server_issues = sum(v for k, v in verdicts.items() if k.startswith("SERVER_") or k.startswith("HTTP_5") or k == "CONNECT_FAIL")
    print(f"  OUR FAULT (feed is fine, we're not reading it):   {ours}")
    print(f"  THEIR FAULT (dead permanently):                   {theirs_dead}")
    print(f"  THEIR FAULT (recoverable — update URL / retry):   {theirs_recoverable}")
    print(f"  SHARED (server-side issues, may resolve):         {server_issues}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
