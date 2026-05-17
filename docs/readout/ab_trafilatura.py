"""
A/B audit: take 30 articles from the worst-offender sources, fetch each
via trafilatura, score before-vs-after junk-rate.

Hypothesis: trafilatura cleans the body in most cases. We confirm that
empirically before rewriting any production code.
"""
import asyncio
import re
import time
from typing import Any

import trafilatura
from sqlalchemy import text
from backend.database import get_db


_MD_LINK_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)|\[[^\]]*\]\([^)]*\)")
_URL_RE = re.compile(r"https?://\S+")


def junk_score(body: str | None) -> dict[str, Any]:
    if not body:
        return {"is_junk": True, "reason": "empty", "ratio_letters": 0.0,
                "md_links": 0, "urls": 0, "len": 0}
    head = body[:600]
    md_links = len(_MD_LINK_RE.findall(head))
    urls = len(_URL_RE.findall(head))
    letters = sum(1 for c in body if c.isalpha())
    ratio = letters / max(1, len(body))
    is_junk = (
        md_links >= 3
        or (urls >= 5 and len(body) < 1500)
        or ratio < 0.55
    )
    reason = []
    if md_links >= 3:
        reason.append(f"md_links={md_links}")
    if urls >= 5 and len(body) < 1500:
        reason.append(f"urls={urls}")
    if ratio < 0.55:
        reason.append(f"letters_ratio={ratio:.2f}")
    return {
        "is_junk": is_junk,
        "reason": ",".join(reason) or "ok",
        "ratio_letters": ratio,
        "md_links": md_links,
        "urls": urls,
        "len": len(body),
    }


# Sources we want to audit — top junk sources from the previous diagnostic.
TARGET_SOURCES = [
    "TV9 Telugu",
    "HMTV",
    "Telangana Today",
    "NTV Telugu",
    "Sportskeeda — India",
    "Prabhat Khabar",
    "Mana Telangana",
    "South China Morning Post — Military",
    "TaxGuru — Legal & Tax",
    "Prajavani",
    "Namasthe Telangana",
    "V6 Velugu",
    "Punch Nigeria",
    "Dharitri",
    "Daily Trust Nigeria",
]


async def main() -> None:
    print("=" * 100)
    print("A/B TEST: trafilatura vs current scraper on broken sources")
    print("=" * 100)

    # Pull up to 2 articles per source (so we have a spread, not all from one site)
    rows: list[dict[str, Any]] = []
    async with get_db() as db:
        for src in TARGET_SOURCES:
            res = await db.execute(
                text(
                    """
                    SELECT a.id::text AS id, a.title, a.url,
                           s.name AS source_name,
                           COALESCE(a.full_text_scraped,
                                    a.lead_text_translated,
                                    a.lead_text_original) AS current_body
                    FROM articles a
                    JOIN sources s ON s.id = a.source_id
                    WHERE s.name = :src
                      AND a.collected_at > now() - interval '24 hours'
                      AND a.url IS NOT NULL
                    ORDER BY random()
                    LIMIT 2
                    """
                ),
                {"src": src},
            )
            rows.extend([dict(r) for r in res.mappings().all()])

    print(f"sampled {len(rows)} articles across {len(TARGET_SOURCES)} sources\n")

    summary: dict[str, dict[str, int]] = {}
    fixed = 0
    still_broken = 0
    fetch_failed = 0

    for i, art in enumerate(rows, 1):
        src = art["source_name"]
        if src not in summary:
            summary[src] = {"total": 0, "before_junk": 0,
                            "after_junk": 0, "fetch_fail": 0}
        summary[src]["total"] += 1

        before = junk_score(art["current_body"])
        if before["is_junk"]:
            summary[src]["before_junk"] += 1

        # Fetch + extract via trafilatura
        new_body: str | None = None
        try:
            t0 = time.time()
            downloaded = trafilatura.fetch_url(art["url"])
            if downloaded is None:
                summary[src]["fetch_fail"] += 1
                fetch_failed += 1
                after = {"is_junk": True, "reason": "fetch_failed",
                         "len": 0, "ratio_letters": 0.0,
                         "md_links": 0, "urls": 0}
            else:
                new_body = trafilatura.extract(
                    downloaded,
                    include_comments=False,
                    include_tables=False,
                    include_links=False,
                    deduplicate=True,
                ) or ""
                after = junk_score(new_body)
            dt = time.time() - t0
        except Exception as exc:
            summary[src]["fetch_fail"] += 1
            fetch_failed += 1
            after = {"is_junk": True, "reason": f"err:{type(exc).__name__}",
                     "len": 0, "ratio_letters": 0.0,
                     "md_links": 0, "urls": 0}
            dt = 0.0

        if after["is_junk"]:
            summary[src]["after_junk"] += 1
            if not before["is_junk"]:
                still_broken += 1  # was ok, now broken — should not happen often
        else:
            if before["is_junk"]:
                fixed += 1

        print(
            f"[{i:>2}] {src[:24]:<24} "
            f"before={'JUNK' if before['is_junk'] else 'ok':<5} "
            f"({before['len']:>5}) "
            f"after={'JUNK' if after['is_junk'] else 'ok':<5} "
            f"({after['len']:>5}) "
            f"{dt:.2f}s "
            f"-> {after['reason'][:40]}"
        )
        if (
            new_body
            and not before["is_junk"]
            and not after["is_junk"]
            and i <= 4
        ):
            print(f"     before head: {(art['current_body'] or '')[:150]!r}")
            print(f"     after  head: {new_body[:150]!r}")
        elif new_body and before["is_junk"] and not after["is_junk"]:
            print(f"     ✓ fixed. before: {(art['current_body'] or '')[:120]!r}")
            print(f"            after:  {new_body[:120]!r}")
        elif before["is_junk"] and after["is_junk"]:
            if new_body is not None:
                print(f"     × still junk. after: {new_body[:120]!r}")

    print()
    print("=" * 100)
    print("PER-SOURCE SUMMARY")
    print("=" * 100)
    print(f"{'source':<32} {'total':>6} {'before_junk':>12} "
          f"{'after_junk':>11} {'fetch_fail':>11} {'verdict':>14}")
    for src, agg in summary.items():
        before_pct = agg["before_junk"] / max(1, agg["total"]) * 100
        after_pct = agg["after_junk"] / max(1, agg["total"]) * 100
        verdict = (
            "fixed" if (agg["before_junk"] > 0 and agg["after_junk"] == 0)
            else "improved" if agg["after_junk"] < agg["before_junk"]
            else "unchanged" if agg["after_junk"] == agg["before_junk"]
            else "worse"
        )
        print(
            f"{src[:32]:<32} {agg['total']:>6} "
            f"{agg['before_junk']:>4} ({before_pct:>3.0f}%) "
            f"{agg['after_junk']:>4} ({after_pct:>3.0f}%) "
            f"{agg['fetch_fail']:>11} {verdict:>14}"
        )

    print()
    total = len(rows)
    before_junk = sum(s["before_junk"] for s in summary.values())
    after_junk = sum(s["after_junk"] for s in summary.values())
    print(
        f"OVERALL: total={total}  "
        f"before_junk={before_junk} ({before_junk / max(1, total) * 100:.0f}%)  "
        f"after_junk={after_junk} ({after_junk / max(1, total) * 100:.0f}%)  "
        f"fetch_failed={fetch_failed}  fixed={fixed}  regressions={still_broken}"
    )


asyncio.run(main())
