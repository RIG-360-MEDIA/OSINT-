"""
Sync DB RSS sources → FreshRSS subscriptions.

Finds all active RSS sources in the DB that are not yet subscribed in FreshRSS
and subscribes them via the GReader API.

Run inside the backend container:
  docker exec rig-backend python scripts/sync_freshrss_subscriptions.py
"""
import asyncio
import logging
import os
import sys

sys.path.insert(0, "/app")

import asyncpg
import httpx

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

FRESHRSS_URL = os.environ.get("FRESHRSS_URL", "http://rig-freshrss:80").rstrip("/")
FRESHRSS_USERNAME = os.environ.get("FRESHRSS_USERNAME", "admin")
FRESHRSS_PASSWORD = os.environ.get("FRESHRSS_PASSWORD", "")
DATABASE_URL = os.environ.get(
    "DATABASE_URL_SYNC", "postgresql://rig:rigpassword@rig-postgres:5432/rig"
)


async def get_auth_token(client: httpx.AsyncClient) -> str:
    resp = await client.post(
        f"{FRESHRSS_URL}/api/greader.php/accounts/ClientLogin",
        data={"Email": FRESHRSS_USERNAME, "Passwd": FRESHRSS_PASSWORD},
    )
    resp.raise_for_status()
    for line in resp.text.splitlines():
        if line.startswith("Auth="):
            return line[5:].strip()
    raise ValueError("Auth token not found in FreshRSS response")


async def get_existing_subscriptions(client: httpx.AsyncClient) -> set[str]:
    resp = await client.get(
        f"{FRESHRSS_URL}/api/greader.php/reader/api/0/subscription/list",
        params={"output": "json"},
    )
    resp.raise_for_status()
    subs = resp.json().get("subscriptions", [])
    return {(s.get("url") or "").strip().rstrip("/") for s in subs if s.get("url")}


async def subscribe_feed(client: httpx.AsyncClient, token: str, rss_url: str) -> str:
    """Returns 'ok', 'skip' (400), or 'timeout'."""
    try:
        resp = await client.post(
            f"{FRESHRSS_URL}/api/greader.php/reader/api/0/subscription/edit",
            data={"ac": "subscribe", "s": f"feed/{rss_url}", "T": token},
            timeout=90,  # FreshRSS must fetch the feed — allow up to 90s
        )
        if resp.status_code == 200:
            return "ok"
        return "skip"
    except (httpx.TimeoutException, httpx.ReadTimeout):
        return "timeout"
    except Exception:
        return "error"


async def get_action_token(client: httpx.AsyncClient) -> str:
    resp = await client.get(
        f"{FRESHRSS_URL}/api/greader.php/reader/api/0/token",
    )
    resp.raise_for_status()
    return resp.text.strip()


async def main() -> None:
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch(
        """
        SELECT name, rss_url FROM sources
        WHERE is_active = TRUE
          AND source_type = 'rss'
          AND rss_url IS NOT NULL
          AND rss_url != ''
        ORDER BY name
        """
    )
    await conn.close()

    db_sources = {row["rss_url"].strip().rstrip("/"): row["name"] for row in rows}
    logger.info("DB active RSS sources with rss_url: %d", len(db_sources))

    async with httpx.AsyncClient(
        timeout=30,
        follow_redirects=True,
        headers={"User-Agent": "RIGSurveillance/1.0"},
    ) as client:
        auth_token = await get_auth_token(client)
        client.headers["Authorization"] = f"GoogleLogin auth={auth_token}"

        existing = await get_existing_subscriptions(client)
        logger.info("FreshRSS existing subscriptions: %d", len(existing))

        missing = {
            url: name
            for url, name in db_sources.items()
            if url not in existing
        }
        logger.info("Sources missing from FreshRSS: %d", len(missing))

        if not missing:
            logger.info("Nothing to do — all sources already subscribed.")
            return

        action_token = await get_action_token(client)

        success = skipped = timeouts = 0
        for i, (url, name) in enumerate(missing.items()):
            if i > 0 and i % 30 == 0:
                action_token = await get_action_token(client)  # refresh token
                logger.info("  Token refreshed at i=%d", i)
            result = await subscribe_feed(client, action_token, url)
            if result == "ok":
                success += 1
                logger.info("  ✅ %s", name)
            elif result == "timeout":
                timeouts += 1
                logger.warning("  ⏱️  TIMEOUT: %s", name)
            else:
                skipped += 1

            if (i + 1) % 20 == 0:
                logger.info("  Progress: %d/%d (ok=%d skip=%d timeout=%d)",
                            i + 1, len(missing), success, skipped, timeouts)

    logger.info("\nDone. Subscribed: %d  Skipped(invalid): %d  Timeout: %d",
                success, skipped, timeouts)
    logger.info("FreshRSS will sync new feeds on next crawl cycle (~15 min).")


if __name__ == "__main__":
    asyncio.run(main())
