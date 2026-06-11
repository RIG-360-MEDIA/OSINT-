"""extract_journalists.py — multi-stage journalist-name extractor.

Stage 1 — regex over the existing `articles.byline` column (free, fast).
Stage 2 — re-fetch article HTML, parse meta tags / JSON-LD / body patterns.

Usage:
  # Test mode (no DB writes, prints quality matrix):
  python extract_journalists.py --test --sample 100
  # Production mode (writes to articles.author_name):
  python extract_journalists.py --apply --limit 50000

Designed to be safe for the Hetzner IP — concurrent_fetch limited to 8,
respects robots.txt timeouts, falls through silently on 4xx/5xx.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
import re
import sys
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass
from typing import Optional

sys.path.insert(0, "/app")
from sqlalchemy import text  # noqa: E402
from backend.database import get_db  # noqa: E402

# Reuse the browser-like fetcher from substrate so we don't trip WAFs
try:
    from backend.tasks.substrate.run_corpus_pass import _fetch_html_browser  # type: ignore
except ImportError:
    _fetch_html_browser = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("extract_journalists")

CONCURRENT_FETCH = 8

# ── Stage 1: byline regex ────────────────────────────────────────────

# Common tokens that mean "this is the source / publisher, not a person"
PUBLISHER_TOKENS = {
    "today", "news", "bureau", "desk", "updated", "follow", "twitter", "instagram",
    "facebook", "team", "editor", "reporter", "correspondent", "staff", "web",
    "online", "agency", "service", "feed", "feeds", "network", "media", "newsroom",
    "wire", "agencies", "tv", "channel", "post", "post.", "times", "express",
    "express.", "express ", "tribune", "guardian", "hindu", "indianexpress",
    "ie", "pti", "ani", "ians", "ant", "ndtv", "ap", "afp", "reuters", "bloomberg", "iht",
    "fp", "scroll", "thewire", "wire.", "thelogical", "minute", "min",
    "minutes", "hours", "ago", "live", "blog", "blog.", "bot", "automated",
    "ie online", "ie staff", "agency", "agencies", "report", "reports",
    "exclusive", "special", "syndication", "syndicated",
    "telugu", "hindi", "english", "kannada", "tamil", "malayalam", "marathi",
    "bengali", "gujarati", "punjabi", "urdu",
    # newly added after first test
    "velugu", "trust", "author", "about",
}

# Exact-match (lowercased) blocklist for multi-word publisher / aggregator names
# that pass the per-token filter. Compared as a whole lowercase string.
KNOWN_PUBLISHER_PHRASES = {
    "v6 velugu", "daily trust", "press trust", "press trust of india",
    "about the author livemint", "about the author", "the author",
    "namasthe telangana", "telangana today", "nt news telugu",
    "hindu business line", "hindu businessline", "the hindu bureau",
    "bl chennai bureau", "bl mumbai bureau", "bl delhi bureau",
    "mint industry", "economic times", "indian express", "the indian express",
    "livemint", "live mint", "news desk", "web desk", "online desk",
    "news network", "news service", "news agency",
    "by ians", "by pti", "by ani", "by reuters", "by afp", "by ap",
    "press release", "staff reporter", "staff correspondent",
    "special correspondent", "our correspondent", "our bureau",
    "csr journal", "the csr journal", "joy online",
    "this day", "this day nigeria",
    # generic byline placeholders (newly added)
    "dc correspondent", "ht news desk", "ht correspondent", "ht national desk",
    "et bureau", "et online", "et markets", "et online desk",
    "agencies", "wire services", "express news service",
    "the hindu", "hindu net desk", "the wire staff",
    "moneycontrol news", "mc news desk", "mc bureau",
    "tnn", "tnn bureau", "agence france-presse",
    "afp reporters", "reuters staff", "ap reporters",
    "bs reporter", "business standard", "fe online",
    "fp staff", "firstpost staff",
    "abp news bureau", "india tv news desk", "news18 india",
    "read more", "about the author", "share this", "twitter facebook",
    # v3 fixes — band-aid for remaining false positives
    "published by", "please enter your name here", "enter your name",
    "your name", "your email", "leave a comment", "leave a reply",
}

PERSON_NAME_RE = re.compile(
    r"^(?:by\s+|story\s+by\s+|written\s+by\s+|opinion\s+by\s+|reported\s+by\s+)?"
    r"(?P<name>[A-Z][a-zA-Z\.\'\-]+(?:\s+[A-Z][a-zA-Z\.\'\-]+){1,3})"
    r"(?:[,|;]|\s+for\s+|\s+\(|$)",
    re.IGNORECASE,
)

# Reject byline entirely if it matches a date-only / time-only string
DATE_ONLY_RE = re.compile(
    r"^(?:\d|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|mon|tue|wed|thu|fri|sat|sun|am|pm|\s|,|:)+$",
    re.IGNORECASE,
)


def _normalize_candidate(s: str) -> str:
    """Clean a raw candidate before validation."""
    s = s.strip()
    # Strip leading "By " / "Story by " / "Written by " (case-insensitive)
    s = re.sub(r"^(?:by|story\s+by|written\s+by|reported\s+by|opinion\s+by)\s+",
               "", s, flags=re.IGNORECASE).strip()
    # Cut at first comma / semicolon / pipe / parenthesis — these usually
    # introduce a location, role, or affiliation we don't want
    for sep in [",", ";", "|", "(", " - ", " — "]:
        if sep in s:
            s = s.split(sep, 1)[0].strip()
    # Cut at " for " / " is " / " writes " / " reports for "
    s = re.split(r"\s+(?:for|is|writes|reports for)\s+", s, maxsplit=1, flags=re.IGNORECASE)[0].strip()
    # Collapse internal whitespace
    s = re.sub(r"\s+", " ", s)
    return s


def looks_like_person(s: Optional[str]) -> bool:
    """Heuristic: does this string look like a real person's name?"""
    if not s:
        return False
    s = _normalize_candidate(s)
    if len(s) < 4 or len(s) > 60:
        return False
    if DATE_ONLY_RE.match(s):
        return False
    # Exact-match known publisher phrases (highest precision filter)
    if s.lower() in KNOWN_PUBLISHER_PHRASES:
        return False
    # Reject single words (usernames, "Updated", "Reuters")
    words = s.split()
    if len(words) < 2 or len(words) > 5:
        return False
    # All words must start with a letter
    if not all(w and w[0].isalpha() for w in words):
        return False
    # Reject if ANY token is a publisher word
    lowered = [w.lower().strip(".,") for w in words]
    if any(t in PUBLISHER_TOKENS for t in lowered):
        return False
    # Must contain at least one capitalised word (proper noun)
    if not any(w[0].isupper() for w in words):
        return False
    # NOTE: do NOT reject ALL-CAPS — Indian regional newspapers commonly
    # publish journalist names in uppercase ("PONNALA SWAMY", "V.SESHU").
    # Title-casing happens in _clean_extracted on the way out.
    return True


def _clean_extracted(s: Optional[str]) -> Optional[str]:
    """Normalize an accepted candidate before returning to caller."""
    if not s:
        return None
    s = _normalize_candidate(s)
    # Title-case if ALL-CAPS (PONNALA SWAMY → Ponnala Swamy) but preserve
    # 2-letter / dotted initials (P.V Sindhu, V.SESHU → V.Seshu)
    words = s.split()
    out_words = []
    for w in words:
        if w.isupper() and len(w) >= 3 and "." not in w:
            out_words.append(w.title())
        else:
            out_words.append(w)
    return " ".join(out_words)


def extract_from_byline(raw: Optional[str]) -> Optional[str]:
    """Stage 1 — extract a journalist name from the existing byline string."""
    if not raw:
        return None
    raw = raw.strip()
    if not raw:
        return None
    # Quick exits on date-like or pure publisher names
    if DATE_ONLY_RE.match(raw):
        return None
    # Try the formal "By X" pattern
    m = PERSON_NAME_RE.match(raw)
    if m:
        name = m.group("name").strip()
        if looks_like_person(name):
            return _clean_extracted(name)
    # Try the raw string as a candidate (some sites write just "Sandeep Kanoi")
    if looks_like_person(raw):
        return _clean_extracted(raw)
    return None


# ── Stage 2: HTML re-fetch and parsing ───────────────────────────────

# Lightweight HTML inspector — avoid bringing in BeautifulSoup at import time
# unless we're actually parsing.
def _import_bs4():
    from bs4 import BeautifulSoup
    return BeautifulSoup


META_AUTHOR_KEYS = {
    "author", "article:author", "twitter:creator", "dc.creator",
    "sailthru.author", "parsely-author", "byl",
}


def extract_from_html(html: str) -> Optional[str]:
    """Stage 2 — parse author from meta tags / JSON-LD / body patterns."""
    if not html or len(html) < 50:
        return None
    BS = _import_bs4()
    soup = BS(html, "html.parser")

    # 1. meta tags
    for m in soup.find_all("meta"):
        key = (m.get("name") or m.get("property") or "").lower().strip()
        if key in META_AUTHOR_KEYS:
            val = (m.get("content") or "").strip()
            # Strip leading @ for twitter:creator
            val = val.lstrip("@")
            if looks_like_person(val):
                return _clean_extracted(val)

    # 2. <a rel="author"> or <span class="author">
    for tag in soup.find_all(["a", "span", "div"], attrs={"rel": "author"}):
        val = tag.get_text(" ", strip=True)
        if looks_like_person(val):
            return _clean_extracted(val)
    for tag in soup.find_all(class_=re.compile(r"\b(author|byline)\b", re.IGNORECASE)):
        val = tag.get_text(" ", strip=True)
        # Strip noise headers that often wrap the actual name
        val = re.sub(
            r"^(?:ABOUT THE AUTHOR\s*|Follow on Twitter\s*|Follow\s*|Read More\s*|"
            r"Share\s+(?:this|on)\s+\w+\s*|Authored by\s*|Reviewed by\s*)",
            "",
            val,
            flags=re.IGNORECASE,
        ).strip()
        # Strip trailing date/time fragments like "Published on: 23 May 2026 3:46 PM IST"
        val = re.split(
            r"\s+(?:Published\s+on|Updated\s+on|Last\s+Updated|"
            r"\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec))",
            val,
            maxsplit=1,
        )[0].strip()
        # Common pattern: "By Sandeep Kanoi" inside an .author div
        m = PERSON_NAME_RE.match(val)
        if m:
            name = m.group("name").strip()
            if looks_like_person(name):
                return _clean_extracted(name)
        # Also try the entire cleaned string (some sites put just the name)
        if looks_like_person(val):
            return _clean_extracted(val)

    # 3. JSON-LD
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            payload = (script.string or "").strip()
            if not payload:
                continue
            data = json.loads(payload)
        except (json.JSONDecodeError, AttributeError):
            continue
        # JSON-LD can be a list or single object
        if isinstance(data, list):
            data = data[0] if data else {}
        if not isinstance(data, dict):
            continue
        author = data.get("author")
        # Normalize to a flat list of candidates
        candidates: list = []
        if isinstance(author, list):
            for a in author:
                if isinstance(a, list):
                    candidates.extend(a)
                else:
                    candidates.append(a)
        elif author is not None:
            candidates.append(author)
        # Prefer @type=Person over @type=Organization
        candidates.sort(key=lambda x: (
            0 if (isinstance(x, dict) and x.get("@type") == "Person") else
            1 if (isinstance(x, dict) and x.get("@type") in ("NewsArticle", None)) else
            2  # Organization, Thing, anything else last
        ))
        for c in candidates:
            if isinstance(c, dict):
                cand = (c.get("name") or "").strip()
            elif isinstance(c, str):
                cand = c.strip()
            else:
                continue
            if cand and looks_like_person(cand):
                return _clean_extracted(cand)

    # 4. "By X" pattern in first 800 chars of body text
    body_text = soup.get_text(" ")[:1500]
    m = re.search(
        r"\bBy\s+([A-Z][\w\.\']+(?:\s+[A-Z][\w\.\']+){1,3})(?=[,|\.\n]|\s+for\s+|\s+\(|\s+is\s+|\s+writes\s+)",
        body_text,
    )
    if m:
        cand = m.group(1).strip()
        if looks_like_person(cand):
            return _clean_extracted(cand)

    return None


# ── Pipeline ─────────────────────────────────────────────────────────


@dataclass
class ExtractionResult:
    article_id: str
    url: str
    source_name: str
    raw_byline: Optional[str]
    stage1_result: Optional[str]
    stage2_result: Optional[str]
    final: Optional[str]
    stage: str  # "byline", "html", "none"


async def fetch_sample(n: int) -> list[dict]:
    """Pick `n` random recent articles."""
    async with get_db() as db:
        rows = (await db.execute(text("""
            SELECT a.id::text AS aid,
                   a.url,
                   a.byline,
                   COALESCE(s.name, 'unknown') AS source_name
              FROM articles a
              LEFT JOIN sources s ON s.id = a.source_id
             WHERE a.substrate_status = 'ok'
               AND a.collected_at > NOW() - INTERVAL '14 days'
             ORDER BY RANDOM()
             LIMIT :n
        """), {"n": n})).mappings().all()
    return [dict(r) for r in rows]


async def process_one(art: dict, do_fetch: bool = True) -> ExtractionResult:
    aid, url, byline, source = art["aid"], art["url"], art["byline"], art["source_name"]
    stage1 = extract_from_byline(byline)
    stage2 = None
    if not stage1 and do_fetch and _fetch_html_browser is not None:
        try:
            html = await asyncio.to_thread(_fetch_html_browser, url, 10.0)
            if html:
                stage2 = extract_from_html(html)
        except Exception:  # noqa: BLE001
            stage2 = None
    final = stage1 or stage2
    stage_label = "byline" if stage1 else ("html" if stage2 else "none")
    return ExtractionResult(
        article_id=aid, url=url, source_name=source,
        raw_byline=byline, stage1_result=stage1,
        stage2_result=stage2, final=final, stage=stage_label,
    )


async def run_test(sample_n: int) -> int:
    log.info("Sampling %d random articles from last 14 days...", sample_n)
    articles = await fetch_sample(sample_n)
    log.info("Processing %d articles (concurrency=%d)", len(articles), CONCURRENT_FETCH)

    sem = asyncio.Semaphore(CONCURRENT_FETCH)
    results: list[ExtractionResult] = []

    async def worker(art):
        async with sem:
            r = await process_one(art)
            results.append(r)

    await asyncio.gather(*(worker(a) for a in articles))

    # ── Quality matrix ──
    print("\n" + "=" * 70)
    print(f"JOURNALIST EXTRACTION TEST — {len(results)} articles")
    print("=" * 70)

    by_stage = Counter(r.stage for r in results)
    print(f"Stage 1 (byline regex):  {by_stage.get('byline', 0):>3}  ({by_stage.get('byline', 0)/len(results)*100:.1f}%)")
    print(f"Stage 2 (HTML re-fetch): {by_stage.get('html', 0):>3}  ({by_stage.get('html', 0)/len(results)*100:.1f}%)")
    print(f"No extraction          : {by_stage.get('none', 0):>3}  ({by_stage.get('none', 0)/len(results)*100:.1f}%)")
    extracted = by_stage.get('byline', 0) + by_stage.get('html', 0)
    print(f"TOTAL EXTRACTED        : {extracted:>3} ({extracted/len(results)*100:.1f}%)")

    print()
    print("── EXTRACTED NAMES (sample) ──")
    extracted_results = [r for r in results if r.final]
    # Top 20 by source
    print(f"\nBy stage:")
    for stage, label in [("byline", "S1 byline"), ("html", "S2 html")]:
        subset = [r for r in extracted_results if r.stage == stage]
        if not subset:
            continue
        print(f"\n  {label} ({len(subset)} hits):")
        for r in subset[:12]:
            raw = (r.raw_byline or "")[:32].ljust(32)
            name = (r.final or "")[:28].ljust(28)
            src = (r.source_name or "")[:18].ljust(18)
            print(f"    raw={raw!r:38} -> {name!r:32} [{src}]")

    print()
    print("── NOT EXTRACTED (sample) — these need investigation ──")
    no_extract = [r for r in results if not r.final][:12]
    for r in no_extract:
        raw = (r.raw_byline or "(NULL)")[:42]
        src = (r.source_name or "")[:18]
        print(f"    raw={raw!r:48} [{src}]")

    # Source-level coverage
    print()
    print("── COVERAGE BY SOURCE (top 12) ──")
    src_total: Counter = Counter()
    src_hit: Counter = Counter()
    for r in results:
        src_total[r.source_name] += 1
        if r.final:
            src_hit[r.source_name] += 1
    for src, tot in src_total.most_common(12):
        hit = src_hit.get(src, 0)
        pct = (hit / tot * 100) if tot else 0
        print(f"    {src:<28} {hit}/{tot}  ({pct:.0f}%)")

    print()
    print("── DISTINCT JOURNALIST NAMES EXTRACTED ──")
    names_seen = Counter(r.final for r in extracted_results if r.final)
    print(f"  {len(names_seen)} distinct names from {len(extracted_results)} hits")
    print(f"  Most common in this sample:")
    for name, n in names_seen.most_common(10):
        print(f"    {name:<40} {n}x")

    # Verdict
    print()
    print("=" * 70)
    yield_pct = extracted / len(results) * 100
    if yield_pct >= 40:
        print(f"VERDICT: GOOD ({yield_pct:.1f}% extraction). Ready to run at scale.")
        return 0
    elif yield_pct >= 20:
        print(f"VERDICT: PARTIAL ({yield_pct:.1f}%). Many sources don't credit individuals — expected for aggregators.")
        return 0
    else:
        print(f"VERDICT: LOW ({yield_pct:.1f}%). Most articles lack byline data; consider LLM stage.")
        return 1


async def run_apply(limit: int = 200000) -> int:
    """Production backfill — process articles where author_name is NULL and
    substrate is OK. Writes extracted name into `articles.author_name`.

    Processes in batches of 200 to keep DB tx short. Resumable — re-running
    picks up where we left off because we only touch rows still NULL.
    """
    log.info("D-AUTHOR: backfilling articles.author_name (limit=%d)", limit)

    sem = asyncio.Semaphore(CONCURRENT_FETCH)
    processed_total = 0
    extracted_total = 0
    null_after_total = 0
    batch_size = 200

    while processed_total < limit:
        # Use a NULL sentinel so we don't reprocess rows we already touched.
        # Articles with author_name = '' (empty string) get treated as "tried and failed"
        # so they aren't picked up again.
        async with get_db() as db:
            rows = (await db.execute(text("""
                SELECT id::text AS aid, url, byline
                  FROM articles
                 WHERE substrate_status = 'ok'
                   AND author_name IS NULL
                 ORDER BY collected_at DESC
                 LIMIT :n
            """), {"n": batch_size})).mappings().all()
        if not rows:
            log.info("D-AUTHOR: no more articles to process. Done.")
            break

        async def worker(art):
            async with sem:
                # Skip HTML fetch if byline already parses — saves bandwidth
                s1 = extract_from_byline(art["byline"])
                final = s1
                if not final and _fetch_html_browser:
                    try:
                        html = await asyncio.to_thread(_fetch_html_browser, art["url"], 8.0)
                        if html:
                            final = extract_from_html(html)
                    except Exception:  # noqa: BLE001
                        final = None
                return art["aid"], final

        results = await asyncio.gather(*(worker(r) for r in rows))

        # Write back — use empty string as "tried but no name found" sentinel
        async with get_db() as db:
            for aid, name in results:
                value = name if name else ""  # '' = tried, no result
                await db.execute(text("""
                    UPDATE articles SET author_name = :n WHERE id::text = :id
                """), {"n": value, "id": aid})
            await db.commit()

        batch_extracted = sum(1 for _, n in results if n)
        batch_null = sum(1 for _, n in results if not n)
        processed_total += len(results)
        extracted_total += batch_extracted
        null_after_total += batch_null
        log.info(
            "D-AUTHOR: batch=%d, processed=%d (cumulative %d), extracted=%d (%.1f%%)",
            len(results), len(results), processed_total,
            batch_extracted, batch_extracted / max(len(results), 1) * 100,
        )

    log.info(
        "D-AUTHOR DONE: processed=%d, extracted=%d (%.1f%%), no-name=%d",
        processed_total, extracted_total,
        extracted_total / max(processed_total, 1) * 100,
        null_after_total,
    )
    return 0


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true", help="Test mode (no DB writes)")
    ap.add_argument("--apply", action="store_true", help="Write to articles.author_name")
    ap.add_argument("--sample", type=int, default=100)
    ap.add_argument("--limit", type=int, default=200000)
    args = ap.parse_args()

    if args.test:
        return await run_test(args.sample)
    if args.apply:
        return await run_apply(args.limit)
    log.error("Must pass --test or --apply")
    return 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
