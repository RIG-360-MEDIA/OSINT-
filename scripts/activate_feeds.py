"""
Feed activation script.

Reads all active RSS sources from the database and registers any that are
not yet present in FreshRSS. Idempotent — safe to run twice.
"""
from __future__ import annotations

import os
import sys
import time
from urllib.parse import urlparse

import httpx
import psycopg2
import psycopg2.extras

DATABASE_URL: str = os.environ.get(
    "DATABASE_URL_SYNC", "postgresql://rig:rigpassword@rig-postgres:5432/rig"
)
FRESHRSS_URL: str = os.environ.get("FRESHRSS_URL", "http://rig-freshrss:80").rstrip("/")
FRESHRSS_USERNAME: str = os.environ.get("FRESHRSS_USERNAME", "admin")
FRESHRSS_PASSWORD: str = os.environ.get("FRESHRSS_PASSWORD", "")

BATCH_SIZE = 10
BATCH_PAUSE = 2  # seconds between batches


# ---------------------------------------------------------------------------
# GReader auth helpers
# ---------------------------------------------------------------------------

def get_auth_token(client: httpx.Client) -> str:
    resp = client.post(
        f"{FRESHRSS_URL}/api/greader.php/accounts/ClientLogin",
        data={"Email": FRESHRSS_USERNAME, "Passwd": FRESHRSS_PASSWORD},
        timeout=15,
    )
    resp.raise_for_status()
    for line in resp.text.splitlines():
        if line.startswith("Auth="):
            return line[5:].strip()
    raise ValueError("GReader ClientLogin: Auth token not found in response")


def get_action_token(client: httpx.Client) -> str:
    resp = client.get(
        f"{FRESHRSS_URL}/api/greader.php/reader/api/0/token",
        timeout=15,
    )
    resp.raise_for_status()
    return resp.text.strip()


def get_registered_urls(client: httpx.Client) -> set[str]:
    """Return the set of feed URLs already registered in FreshRSS."""
    resp = client.get(
        f"{FRESHRSS_URL}/api/greader.php/reader/api/0/subscription/list",
        params={"output": "json"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    urls: set[str] = set()
    for sub in data.get("subscriptions", []):
        feed_url = sub.get("url", "")
        if feed_url:
            urls.add(feed_url.strip())
    return urls


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def fetch_rss_sources(conn: psycopg2.extensions.connection) -> list[dict]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT id, name, domain, rss_url, source_tier, geo_states
            FROM sources
            WHERE source_type = 'rss'
              AND rss_url IS NOT NULL
              AND is_active = TRUE
              AND health_score > 0.0
            ORDER BY source_tier ASC, name ASC
            """
        )
        return [dict(row) for row in cur.fetchall()]


def mark_source_failed(conn: psycopg2.extensions.connection, source_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE sources SET health_score = 0.5 WHERE id = %s",
            (source_id,),
        )
    conn.commit()


# ---------------------------------------------------------------------------
# Feed registration
# ---------------------------------------------------------------------------

def register_feeds(
    client: httpx.Client,
    sources: list[dict],
    already_registered: set[str],
    conn: psycopg2.extensions.connection,
) -> tuple[int, int, int]:
    """
    Register sources not already in FreshRSS, in batches of BATCH_SIZE.
    Returns (already_count, new_count, failed_count).
    """
    already_count = 0
    new_count = 0
    failed_count = 0

    to_register = []
    for source in sources:
        rss_url = (source["rss_url"] or "").strip()
        if not rss_url:
            continue
        if rss_url in already_registered:
            already_count += 1
        else:
            to_register.append(source)

    print(f"Sources already in FreshRSS: {already_count}")
    print(f"Sources to register:          {len(to_register)}")

    # Refresh action token once before batching
    action_token = get_action_token(client)
    token_refresh_counter = 0

    for batch_start in range(0, len(to_register), BATCH_SIZE):
        batch = to_register[batch_start : batch_start + BATCH_SIZE]

        # Refresh action token every 5 batches (~50 feeds) to avoid expiry
        token_refresh_counter += 1
        if token_refresh_counter % 5 == 0:
            action_token = get_action_token(client)

        for source in batch:
            rss_url = source["rss_url"].strip()
            try:
                resp = client.post(
                    f"{FRESHRSS_URL}/api/greader.php/reader/api/0/subscription/quickadd",
                    data={"quickadd": rss_url, "T": action_token},
                    timeout=20,
                )
                if resp.status_code in (200, 201):
                    new_count += 1
                    print(f"  [OK] {source['name'][:60]}")
                else:
                    failed_count += 1
                    print(f"  [FAIL HTTP {resp.status_code}] {source['name'][:60]}")
                    mark_source_failed(conn, str(source["id"]))
            except Exception as exc:
                failed_count += 1
                print(f"  [ERROR] {source['name'][:60]}: {exc}")
                mark_source_failed(conn, str(source["id"]))

        if batch_start + BATCH_SIZE < len(to_register):
            time.sleep(BATCH_PAUSE)

    return already_count, new_count, failed_count


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    if not FRESHRSS_PASSWORD:
        print("ERROR: FRESHRSS_PASSWORD environment variable is not set.")
        sys.exit(1)

    # Connect to database
    conn = psycopg2.connect(DATABASE_URL)
    sources = fetch_rss_sources(conn)
    print(f"RSS sources in database: {len(sources)}")

    # Authenticate to FreshRSS
    with httpx.Client(follow_redirects=True, timeout=30) as client:
        try:
            token = get_auth_token(client)
        except Exception as exc:
            print(f"ERROR: FreshRSS GReader auth failed: {exc}")
            print("Run scripts/setup_freshrss.py first.")
            conn.close()
            sys.exit(1)

        client.headers["Authorization"] = f"GoogleLogin auth={token}"

        already_registered = get_registered_urls(client)
        print(f"Already in FreshRSS:     {len(already_registered)} feeds\n")

        already, new, failed = register_feeds(client, sources, already_registered, conn)

        # Trigger immediate refresh so FreshRSS polls all feeds now
        if new > 0:
            try:
                action_token = get_action_token(client)
                client.post(
                    f"{FRESHRSS_URL}/api/greader.php/reader/api/0/subscription/refresh",
                    data={"T": action_token},
                    timeout=30,
                )
                print("\nTriggered immediate FreshRSS refresh.")
            except Exception as exc:
                print(f"\nRefresh trigger failed (non-fatal): {exc}")

    conn.close()

    total = already + new
    print(
        f"\nFeed Activation Complete\n"
        f"========================\n"
        f"Already registered: {already} feeds\n"
        f"Newly registered:   {new} feeds\n"
        f"Failed:             {failed} feeds\n"
        f"Total in FreshRSS:  {total} feeds"
    )

    if total < 100:
        print(
            "\nWARNING: fewer than 100 feeds registered. "
            "Check FreshRSS is running and setup_freshrss.py succeeded."
        )


if __name__ == "__main__":
    main()
