"""diag_html_extraction.py — diagnose why Stage 2 (HTML re-fetch) yields low.

For 30 articles where Stage 1 (byline regex) fails:
  1. Attempt fetch — record success/fail
  2. If fetch ok: dump (a) all meta tags whose name/property contains 'author' or 'creator'
     (b) JSON-LD author payloads (c) any class containing "author" or "byline"
     (d) the first "By X" pattern in body text
  3. Show whether OUR extractor would find each — and what the HTML ACTUALLY contains.

This tells us: is the fetch broken, or is the parser missing patterns?
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from collections import Counter

sys.path.insert(0, "/app")
from sqlalchemy import text  # noqa: E402
from backend.database import get_db  # noqa: E402
from backend.tasks.substrate.run_corpus_pass import _fetch_html_browser  # noqa: E402

sys.path.insert(0, "/tmp")
from extract_journalists import extract_from_byline, extract_from_html  # noqa: E402


async def main() -> int:
    # Pull 30 random articles where byline either NULL or rejected by Stage 1
    async with get_db() as db:
        rows = (await db.execute(text("""
            SELECT id::text AS aid, url, byline, source_id
              FROM articles
             WHERE substrate_status = 'ok'
               AND collected_at > NOW() - INTERVAL '14 days'
             ORDER BY RANDOM()
             LIMIT 60
        """))).mappings().all()
    # Keep only the rows where Stage 1 would FAIL
    targets = [r for r in rows if not extract_from_byline(r["byline"])][:30]
    print(f"Diagnosing {len(targets)} articles where Stage 1 byline regex returned None\n")

    stats = Counter()
    for art in targets:
        url = art["url"]
        byline = art["byline"]
        print("=" * 80)
        print(f"URL: {url[:100]}")
        print(f"Stored byline: {byline!r}")
        try:
            html = await asyncio.to_thread(_fetch_html_browser, url, 10.0)
        except Exception as e:
            print(f"  FETCH ERROR: {e}")
            stats["fetch_exception"] += 1
            continue
        if not html:
            print("  FETCH RETURNED EMPTY")
            stats["fetch_empty"] += 1
            continue
        print(f"  fetched {len(html)} bytes")
        stats["fetch_ok"] += 1

        # Parse with BS
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")

        # 1. Show ALL meta tags with 'author' or 'creator' or 'byline' in the key
        meta_hits = []
        for m in soup.find_all("meta"):
            key = (m.get("name") or m.get("property") or "").lower().strip()
            if "author" in key or "creator" in key or "byline" in key:
                meta_hits.append((key, (m.get("content") or "").strip()[:120]))
        if meta_hits:
            print("  META AUTHOR TAGS:")
            for k, v in meta_hits[:8]:
                print(f"    {k!r:40} = {v!r}")
        else:
            print("  META AUTHOR TAGS: (none found)")
        if meta_hits:
            stats["had_meta_author"] += 1

        # 2. JSON-LD authors
        ld_hits = []
        for s in soup.find_all("script", type="application/ld+json"):
            try:
                payload = (s.string or "").strip()
                if not payload:
                    continue
                data = json.loads(payload)
            except (json.JSONDecodeError, AttributeError):
                continue
            if isinstance(data, list):
                data = data[0] if data else {}
            if not isinstance(data, dict):
                continue
            au = data.get("author")
            if au is not None:
                ld_hits.append(au)
        if ld_hits:
            print(f"  JSON-LD authors: {ld_hits[:3]}")
            stats["had_jsonld_author"] += 1

        # 3. Author / byline classes
        by_class = []
        for tag in soup.find_all(class_=re.compile(r"\b(author|byline)\b", re.IGNORECASE))[:5]:
            txt = tag.get_text(" ", strip=True)[:120]
            cls = " ".join(tag.get("class") or [])[:60]
            if txt:
                by_class.append((cls, txt))
        if by_class:
            print("  AUTHOR/BYLINE CLASS HITS:")
            for cls, txt in by_class:
                print(f"    class={cls!r:36} = {txt!r}")
            stats["had_byline_class"] += 1

        # 4. "By X" in first 1500 chars
        body_text = soup.get_text(" ")[:1500]
        m = re.search(
            r"\bBy\s+([A-Z][\w\.\']+(?:\s+[A-Z][\w\.\']+){1,3})",
            body_text,
        )
        if m:
            print(f"  BODY 'By X' MATCH: {m.group(1)!r}")
            stats["had_body_by_pattern"] += 1

        # What does OUR extractor return?
        extracted = extract_from_html(html)
        print(f"  >>> OUR EXTRACTOR RETURNED: {extracted!r}")
        if extracted:
            stats["our_extractor_succeeded"] += 1
        else:
            stats["our_extractor_failed_despite_signals"] += (
                1 if (meta_hits or ld_hits or by_class) else 0
            )

    print("\n" + "=" * 80)
    print("DIAGNOSIS SUMMARY")
    print("=" * 80)
    for k, v in stats.most_common():
        print(f"  {k:<40} {v}")
    print()
    fetch_ok = stats["fetch_ok"]
    if fetch_ok:
        had_any = sum(stats[k] for k in ["had_meta_author", "had_jsonld_author", "had_byline_class", "had_body_by_pattern"])
        print(f"Of {fetch_ok} successful fetches:")
        print(f"  - {stats['our_extractor_succeeded']} ({stats['our_extractor_succeeded']/fetch_ok*100:.0f}%) → OUR extractor caught a name")
        print(f"  - {stats['our_extractor_failed_despite_signals']} had author signals in HTML but our parser MISSED them")
        print(f"  - Pages with ANY author meta/JSON-LD/class/body-by signal: ~{had_any} occurrences (sum may overlap)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
