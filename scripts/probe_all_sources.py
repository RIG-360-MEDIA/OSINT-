"""
Discovery-only probe: hit every active govt source with a strict timeout
and report candidates per portal. No PDF downloads, no NLP — just URLs.
Tells us which sources hang/error vs work.
"""
from __future__ import annotations

import asyncio
import time

from sqlalchemy import text

from backend.collectors.govt_collector import fetch_document_urls
from backend.database import get_db


async def probe_one(name: str, url: str, doc_type: str) -> tuple[int, float, str | None]:
    started = time.time()
    try:
        docs = await asyncio.wait_for(
            fetch_document_urls(url, doc_type, since_days=2), timeout=30
        )
        return len(docs), time.time() - started, None
    except asyncio.TimeoutError:
        return 0, time.time() - started, "TIMEOUT(30s)"
    except Exception as exc:  # noqa: BLE001
        return 0, time.time() - started, f"{type(exc).__name__}: {str(exc)[:80]}"


async def main() -> None:
    async with get_db() as db:
        sources = (
            await db.execute(
                text(
                    """
                    SELECT name, portal_url, document_type
                    FROM govt_document_sources
                    WHERE is_active = TRUE
                    ORDER BY name
                    """
                )
            )
        ).fetchall()

    print(f"probing {len(sources)} active sources (30s cap each)\n", flush=True)
    total_n = 0
    working: list[tuple[str, int]] = []
    failing: list[tuple[str, str]] = []

    for s in sources:
        n, dur, err = await probe_one(s.name, s.portal_url, s.document_type)
        status = (
            f"{n:>3} candidates ({dur:5.1f}s)"
            if err is None
            else f"  0 candidates ({dur:5.1f}s) [{err}]"
        )
        print(f"  · {s.name:<32} {status}", flush=True)
        total_n += n
        if n > 0:
            working.append((s.name, n))
        elif err:
            failing.append((s.name, err))

    print(f"\n=== SUMMARY ===")
    print(f"working: {len(working)} sources, {total_n} total candidates")
    print(f"failing: {len(failing)} sources")


if __name__ == "__main__":
    asyncio.run(main())
