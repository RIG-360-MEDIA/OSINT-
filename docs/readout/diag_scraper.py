"""
Comprehensive scraper diagnostic. Inspects article-body quality across:
  1. Random sample of recent articles
  2. Per-source aggregates
  3. Field-by-field comparison (full_text_scraped vs lead_*)
  4. Time analysis (before/after the silent quote-extraction failure)
  5. Junk-content heuristic across the corpus
"""
import asyncio
import re
from sqlalchemy import text
from backend.database import get_db


# Heuristic for "this body looks like HTML/Markdown chrome, not article".
# Triggers when:
#  - ≥ 40% of chars are punctuation / brackets / non-letter symbols
#  - OR first 200 chars contain ≥ 3 markdown image/link patterns
#  - OR body is dominated by URL/email tokens
_MD_LINK_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)|\[[^\]]*\]\([^)]*\)")
_URL_RE = re.compile(r"https?://\S+")


def junk_score(body: str) -> dict:
    if not body:
        return {"is_junk": True, "reason": "empty", "ratio_letters": 0.0}
    head = body[:600]
    md_links = len(_MD_LINK_RE.findall(head))
    urls = len(_URL_RE.findall(head))
    letters = sum(1 for c in body if c.isalpha())
    ratio = letters / max(1, len(body))
    is_junk = (
        md_links >= 3
        or urls >= 5 and len(body) < 1500
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
        "md_links_in_head": md_links,
        "urls_in_head": urls,
    }


async def main() -> None:
    print("=" * 78)
    print("TEST 1: random sample — 12 articles ingested last 24h, first 200 chars")
    print("=" * 78)
    async with get_db() as db:
        rows = (
            await db.execute(
                text(
                    """
                    SELECT a.id::text, a.title, s.name AS source_name,
                           s.domain AS source_domain, a.collected_at,
                           length(COALESCE(a.full_text_scraped, '')) AS full_len,
                           length(COALESCE(a.lead_text_translated, '')) AS led_len,
                           length(COALESCE(a.lead_text_original, '')) AS leo_len,
                           LEFT(COALESCE(a.full_text_scraped,
                                         a.lead_text_translated,
                                         a.lead_text_original), 200) AS preview,
                           COALESCE(a.full_text_scraped,
                                    a.lead_text_translated,
                                    a.lead_text_original) AS body_full
                    FROM articles a
                    LEFT JOIN sources s ON s.id = a.source_id
                    WHERE a.collected_at > now() - interval '24 hours'
                    ORDER BY random()
                    LIMIT 12
                    """
                )
            )
        ).mappings().all()
    junk_count = 0
    for r in rows:
        js = junk_score(r["body_full"] or "")
        mark = "JUNK" if js["is_junk"] else "ok  "
        if js["is_junk"]:
            junk_count += 1
        print(f"[{mark}] {r['source_name'] or '?':<22} "
              f"full={r['full_len']:>5} led={r['led_len']:>5} leo={r['leo_len']:>5} "
              f"({js['reason']})")
        print(f"        title: {r['title'][:80]}")
        print(f"        body : {(r['preview'] or '')[:160]!r}")
        print()
    print(f"junk: {junk_count}/{len(rows)}")

    print()
    print("=" * 78)
    print("TEST 2: per-source breakdown — last 24h, junk rate by source")
    print("=" * 78)
    async with get_db() as db:
        all_rows = (
            await db.execute(
                text(
                    """
                    SELECT s.name AS source_name, s.domain AS source_domain,
                           COALESCE(a.full_text_scraped,
                                    a.lead_text_translated,
                                    a.lead_text_original) AS body
                    FROM articles a
                    LEFT JOIN sources s ON s.id = a.source_id
                    WHERE a.collected_at > now() - interval '24 hours'
                    """
                )
            )
        ).mappings().all()
    by_source: dict[str, dict] = {}
    for r in all_rows:
        src = r["source_name"] or "(unknown)"
        if src not in by_source:
            by_source[src] = {"total": 0, "junk": 0, "domain": r["source_domain"]}
        by_source[src]["total"] += 1
        if junk_score(r["body"] or "")["is_junk"]:
            by_source[src]["junk"] += 1
    items = sorted(
        by_source.items(),
        key=lambda kv: (kv[1]["junk"] / max(1, kv[1]["total"]), kv[1]["total"]),
        reverse=True,
    )
    print(f"{'source':<32} {'domain':<28} {'junk/total':<14} {'pct':<6}")
    for src, agg in items[:30]:
        pct = agg["junk"] / max(1, agg["total"]) * 100
        print(
            f"{src[:32]:<32} {(agg['domain'] or '')[:28]:<28} "
            f"{agg['junk']:>5}/{agg['total']:<6} {pct:>5.1f}%"
        )
    overall = sum(a["junk"] for a in by_source.values())
    overall_total = sum(a["total"] for a in by_source.values())
    print()
    print(
        f"OVERALL: {overall}/{overall_total} "
        f"({overall / max(1, overall_total) * 100:.1f}%) junk"
    )

    print()
    print("=" * 78)
    print("TEST 3: which body field is cleanest? compare full vs lead_translated vs lead_original")
    print("=" * 78)
    async with get_db() as db:
        cmp_rows = (
            await db.execute(
                text(
                    """
                    SELECT
                      a.full_text_scraped,
                      a.lead_text_translated,
                      a.lead_text_original
                    FROM articles a
                    WHERE a.collected_at > now() - interval '24 hours'
                      AND (length(COALESCE(a.full_text_scraped, '')) > 0
                        OR length(COALESCE(a.lead_text_translated, '')) > 0
                        OR length(COALESCE(a.lead_text_original, '')) > 0)
                    """
                )
            )
        ).mappings().all()
    counters = {
        "full_text_scraped": {"total": 0, "junk": 0},
        "lead_text_translated": {"total": 0, "junk": 0},
        "lead_text_original": {"total": 0, "junk": 0},
    }
    for r in cmp_rows:
        for k in counters:
            v = r[k]
            if v:
                counters[k]["total"] += 1
                if junk_score(v)["is_junk"]:
                    counters[k]["junk"] += 1
    for k, c in counters.items():
        pct = c["junk"] / max(1, c["total"]) * 100
        print(f"{k:<25} populated={c['total']:>5}  junk={c['junk']:>5}  pct={pct:>5.1f}%")

    print()
    print("=" * 78)
    print("TEST 4: time analysis — junk rate by collected_at day, last 5 days")
    print("=" * 78)
    async with get_db() as db:
        day_rows = (
            await db.execute(
                text(
                    """
                    SELECT
                      date_trunc('day', collected_at) AS day,
                      COALESCE(a.full_text_scraped,
                               a.lead_text_translated,
                               a.lead_text_original) AS body
                    FROM articles a
                    WHERE collected_at > now() - interval '5 days'
                    """
                )
            )
        ).mappings().all()
    by_day: dict = {}
    for r in day_rows:
        d = str(r["day"])[:10]
        if d not in by_day:
            by_day[d] = {"total": 0, "junk": 0}
        by_day[d]["total"] += 1
        if junk_score(r["body"] or "")["is_junk"]:
            by_day[d]["junk"] += 1
    print(f"{'day':<14} {'total':<8} {'junk':<8} {'pct'}")
    for d in sorted(by_day):
        agg = by_day[d]
        pct = agg["junk"] / max(1, agg["total"]) * 100
        print(f"{d:<14} {agg['total']:<8} {agg['junk']:<8} {pct:.1f}%")

    print()
    print("=" * 78)
    print("TEST 5: pre-scraper-bug baseline — 7-9 May 2026 articles, junk rate")
    print("=" * 78)
    async with get_db() as db:
        baseline = (
            await db.execute(
                text(
                    """
                    SELECT COUNT(*) AS total,
                           COALESCE(a.full_text_scraped,
                                    a.lead_text_translated,
                                    a.lead_text_original) AS body
                    FROM articles a
                    WHERE collected_at BETWEEN '2026-05-07'::timestamptz
                                           AND '2026-05-09'::timestamptz
                    GROUP BY body
                    LIMIT 1
                    """
                )
            )
        ).mappings().all()
    if not baseline:
        print("no baseline rows in that window")
    else:
        # Re-query individually for accurate counts
        async with get_db() as db:
            agg = await db.execute(
                text(
                    """
                    SELECT COUNT(*) AS total
                    FROM articles a
                    WHERE collected_at BETWEEN '2026-05-07'::timestamptz
                                           AND '2026-05-09'::timestamptz
                    """
                )
            )
            total = agg.scalar()
            body_rows = (
                await db.execute(
                    text(
                        """
                        SELECT COALESCE(a.full_text_scraped,
                                        a.lead_text_translated,
                                        a.lead_text_original) AS body
                        FROM articles a
                        WHERE collected_at BETWEEN '2026-05-07'::timestamptz
                                               AND '2026-05-09'::timestamptz
                        """
                    )
                )
            ).mappings().all()
        junk = sum(1 for r in body_rows if junk_score(r["body"] or "")["is_junk"])
        pct = junk / max(1, total) * 100
        print(f"7-9 May ingest: total={total}, junk={junk} ({pct:.1f}%)")


asyncio.run(main())
