"""
Re-extract article bodies via trafilatura for articles with junk content.

Usage (inside rig-backend):
    python3 /tmp/reextract_bodies.py --limit 50      # smoke
    python3 /tmp/reextract_bodies.py --limit 5000    # full backfill

For each junk article:
  1. Re-fetch URL via trafilatura.fetch_url (with realistic UA).
  2. Extract body via trafilatura.extract.
  3. If clean (Unicode-aware junk-score == clean), UPDATE articles.full_text_scraped
     and articles.lead_text_translated.
  4. Reset quotes_extracted, claims_extracted to FALSE so the existing pipeline
     re-runs on the new body.
  5. Skip rows where the new body is also junk OR fetch fails.

Idempotent: re-running picks up whatever's still junk.
"""
import argparse
import asyncio
import re
import sys
import time
import unicodedata
from typing import Any

import trafilatura
from trafilatura.settings import use_config
from sqlalchemy import text
from backend.database import get_db


_MD = re.compile(r"!\[[^\]]*\]\([^)]*\)|\[[^\]]*\]\([^)]*\)")
_URL = re.compile(r"https?://\S+")

_TRAFILATURA_CFG = use_config()
_TRAFILATURA_CFG.set("DEFAULT", "DOWNLOAD_TIMEOUT", "12")
_TRAFILATURA_CFG.set("DEFAULT", "USER_AGENTS",
                     "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) "
                     "Chrome/124.0.0.0 Safari/537.36")


def _is_letter(c: str) -> bool:
    if c.isalpha():
        return True
    return unicodedata.category(c).startswith("M")


def is_junk(body: str | None) -> tuple[bool, str]:
    if not body:
        return True, "empty"
    if len(body) < 120:
        return True, f"too_short({len(body)})"
    head = body[:600]
    md = len(_MD.findall(head))
    urls = len(_URL.findall(head))
    chars = sum(1 for c in body if _is_letter(c))
    ratio = chars / max(1, len(body))
    is_j = md >= 3 or (urls >= 5 and len(body) < 1500) or ratio < 0.55
    why = []
    if md >= 3:
        why.append(f"md={md}")
    if urls >= 5 and len(body) < 1500:
        why.append(f"urls={urls}")
    if ratio < 0.55:
        why.append(f"ratio={ratio:.2f}")
    return is_j, ",".join(why) or "ok"


_REEXTRACT_SQL = text(
    """
    UPDATE articles
    SET full_text_scraped    = :body,
        lead_text_translated = :lead,
        quotes_extracted     = FALSE,
        claims_extracted     = FALSE,
        updated_at           = NOW()
    WHERE id = :id
    """
)


def _trafilatura_one(url: str) -> tuple[str | None, str]:
    try:
        downloaded = trafilatura.fetch_url(url, config=_TRAFILATURA_CFG)
        if downloaded is None:
            return None, "fetch_none"
        body = trafilatura.extract(
            downloaded,
            config=_TRAFILATURA_CFG,
            include_comments=False,
            include_tables=False,
            include_links=False,
            deduplicate=True,
        )
        return (body or None), ("extracted" if body else "extract_empty")
    except Exception as exc:
        return None, f"err:{type(exc).__name__}"


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--days", type=int, default=7)
    args = p.parse_args()

    print(f"target: re-extract junk articles, limit={args.limit}, days={args.days}")

    async with get_db() as db:
        rows = (
            await db.execute(
                text(
                    """
                    SELECT a.id::text                AS id,
                           a.url                     AS url,
                           s.name                    AS source_name,
                           COALESCE(a.full_text_scraped,
                                    a.lead_text_translated,
                                    a.lead_text_original) AS body
                    FROM articles a
                    LEFT JOIN sources s ON s.id = a.source_id
                    WHERE a.collected_at > now() - make_interval(days => :d)
                      AND a.url IS NOT NULL
                    ORDER BY a.collected_at DESC
                    LIMIT :lim
                    """
                ),
                {"d": args.days, "lim": args.limit * 4},  # over-pull, filter junk
            )
        ).mappings().all()

    junk_rows = [r for r in rows if is_junk(r["body"])[0]]
    junk_rows = junk_rows[: args.limit]

    print(f"sampled {len(rows)} articles, {len(junk_rows)} junk to re-extract\n")

    fixed = 0
    still_junk = 0
    fetch_fail = 0
    by_source: dict[str, dict[str, int]] = {}
    started = time.time()

    for i, r in enumerate(junk_rows, 1):
        src = r["source_name"] or "(unknown)"
        s_agg = by_source.setdefault(src, {"tried": 0, "fixed": 0,
                                            "still_junk": 0, "fetch_fail": 0})
        s_agg["tried"] += 1

        new_body, status = _trafilatura_one(r["url"])
        if new_body is None:
            fetch_fail += 1
            s_agg["fetch_fail"] += 1
            if i % 25 == 0 or i <= 5:
                print(f"[{i:>4}/{len(junk_rows)}] FAIL {src[:18]:<18} {status} :: {r['url'][:70]}")
            continue

        if is_junk(new_body)[0]:
            still_junk += 1
            s_agg["still_junk"] += 1
            if i % 25 == 0 or i <= 5:
                print(f"[{i:>4}/{len(junk_rows)}] STILL_JUNK {src[:18]:<18} {r['url'][:70]}")
            continue

        # Persist
        async with get_db() as db:
            await db.execute(_REEXTRACT_SQL, {
                "id": r["id"],
                "body": new_body[:8000],
                "lead": new_body[:2000],
            })
            await db.commit()

        fixed += 1
        s_agg["fixed"] += 1
        if i % 25 == 0 or i <= 5:
            print(f"[{i:>4}/{len(junk_rows)}] FIXED {src[:18]:<18} -> {new_body[:80]!r}")

    elapsed = time.time() - started
    print()
    print(f"DONE in {elapsed:.0f}s — fixed={fixed}, still_junk={still_junk}, fetch_fail={fetch_fail}")
    print()
    print("Per-source breakdown:")
    print(f"  {'source':<32} {'tried':>6} {'fixed':>6} {'still':>6} {'fail':>6}")
    for src, agg in sorted(by_source.items(),
                            key=lambda kv: -kv[1]["tried"])[:30]:
        print(f"  {src[:32]:<32} {agg['tried']:>6} {agg['fixed']:>6} "
              f"{agg['still_junk']:>6} {agg['fetch_fail']:>6}")
    sys.exit(0)


asyncio.run(main())
