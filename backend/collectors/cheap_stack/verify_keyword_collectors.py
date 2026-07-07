"""Phase-1 verifier: prove keyword-search collectors return REAL matched posts.

One keyword in -> per platform: method used, # real results, quality metrics,
and 2-3 sample rows (text + url + engagement + timestamp). Runs the platforms
registered in `keyword_search.REGISTRY`. Designed to run identically on dev and
on Hetzner's datacenter IP.

Proof bar (per the rebuild plan): run on >=2 keywords — one hot, one fresh — and
confirm each platform returns real keyword-matched rows OR an HONEST labeled
limitation. No platform silently returns empty and is called "done".

Usage:
    python -m backend.collectors.cheap_stack.verify_keyword_collectors
    python -m backend.collectors.cheap_stack.verify_keyword_collectors Rafale Tridel
    python -m backend.collectors.cheap_stack.verify_keyword_collectors --platform reddit --limit 25 Modi Tridel

Exit code 0 iff every (platform, keyword) pair is PASS or an explicitly
labeled/known limitation; non-zero if anything is FAIL or SUSPECT.
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from .keyword_search import REGISTRY, SOCIAL_POST_KEYS, KeywordSearchResult

# Default keyword pair: one hot/common, one fresh/niche. Override via CLI.
DEFAULT_KEYWORDS = ("Modi", "Tridel")

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_NOW = datetime.now(timezone.utc)


# ── quality metrics ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Quality:
    total: int
    shape_ok: int
    dup_ids: int
    empty_text: int
    kw_any: int          # rows containing >=1 query token
    kw_all: int          # rows containing ALL query tokens
    url_ok: int
    ts_ok: int
    oldest: Optional[str]
    newest: Optional[str]

    @property
    def kw_any_rate(self) -> float:
        return self.kw_any / self.total if self.total else 0.0

    @property
    def shape_rate(self) -> float:
        return self.shape_ok / self.total if self.total else 0.0

    @property
    def ts_rate(self) -> float:
        return self.ts_ok / self.total if self.total else 0.0

    @property
    def url_rate(self) -> float:
        return self.url_ok / self.total if self.total else 0.0


def _tokens(query: str) -> list[str]:
    return _TOKEN_RE.findall(query.lower())


def _parse_ts(value: Any) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _shape_valid(row: dict[str, Any]) -> bool:
    if not all(k in row for k in SOCIAL_POST_KEYS):
        return False
    return (
        isinstance(row["platform_post_id"], str) and bool(row["platform_post_id"])
        and isinstance(row["upvotes"], int)
        and isinstance(row["comment_count"], int)
        and isinstance(row["post_text"], str)
    )


def assess(query: str, posts: tuple[dict[str, Any], ...]) -> Quality:
    """Compute quality metrics over the returned rows. Pure, no I/O."""
    toks = _tokens(query)
    ids: list[str] = []
    shape_ok = empty_text = kw_any = kw_all = url_ok = ts_ok = 0
    parsed: list[datetime] = []

    for row in posts:
        if _shape_valid(row):
            shape_ok += 1
        ids.append(str(row.get("platform_post_id") or ""))

        text = (row.get("post_text") or "").lower()
        subreddit = str(row.get("subreddit") or "").lower()
        author = str(row.get("author_username") or "").lower()
        haystack = " ".join((text, subreddit, author))
        if not text.strip():
            empty_text += 1
        if toks:
            hits = [t for t in toks if t in haystack]
            if hits:
                kw_any += 1
            if len(hits) == len(toks):
                kw_all += 1

        url = row.get("post_url") or ""
        if isinstance(url, str) and url.startswith("http") and "." in url:
            url_ok += 1

        dt = _parse_ts(row.get("posted_at"))
        if dt and 2005 <= dt.year <= _NOW.year + 1 and dt.timestamp() > 0:
            ts_ok += 1
            parsed.append(dt)

    dup_ids = len(ids) - len(set(i for i in ids if i))
    parsed.sort()
    oldest = parsed[0].isoformat()[:19] if parsed else None
    newest = parsed[-1].isoformat()[:19] if parsed else None
    return Quality(
        total=len(posts), shape_ok=shape_ok, dup_ids=dup_ids,
        empty_text=empty_text, kw_any=kw_any, kw_all=kw_all,
        url_ok=url_ok, ts_ok=ts_ok, oldest=oldest, newest=newest,
    )


# ── verdict ────────────────────────────────────────────────────────────────────

def verdict(result: KeywordSearchResult, q: Quality) -> tuple[str, str]:
    """Return (tag, reason). PASS/LIMIT are acceptable; FAIL/SUSPECT are not."""
    if not result.ok:
        # Could not run — a real, honest failure state (no cookie, 403, error).
        return "FAIL", result.error or "collector reported not-ok"
    if result.note and q.total == 0:
        # Genuinely zero but with a declared limitation (e.g. channel-set scope).
        return "LIMIT", result.note
    if q.total == 0:
        return "SUSPECT", "0 rows with a healthy session — genuine no-match or silent block?"
    reasons = []
    if q.shape_rate < 1.0:
        reasons.append(f"shape {q.shape_ok}/{q.total}")
    if q.dup_ids > 0:
        reasons.append(f"{q.dup_ids} dup ids")
    if q.ts_rate < 0.9:
        reasons.append(f"ts_ok {q.ts_rate:.0%}")
    if q.url_rate < 0.9:
        reasons.append(f"url_ok {q.url_rate:.0%}")
    if q.kw_any_rate < 0.5:
        reasons.append(f"kw-match {q.kw_any_rate:.0%} (<50%)")
    if reasons:
        return "SUSPECT", "; ".join(reasons)
    return "PASS", f"{q.total} rows, kw-match {q.kw_any_rate:.0%}, all-shape-ok, no dups"


# ── rendering ──────────────────────────────────────────────────────────────────

def _safe(s: Any, n: int) -> str:
    txt = str(s or "").replace("\n", " ").replace("\r", " ")
    return txt[:n].encode("ascii", "replace").decode()


def render_transcripts(result: KeywordSearchResult, top: int) -> None:
    """Opt-in: fetch transcripts for the top-N YouTube hits and report quality.

    Reuses the existing youtube_v2.fetch_transcript, which routes via a
    residential relay (YT_RELAY_URL) / proxy when set, else direct. From the
    Hetzner box with no relay this HONESTLY reports ip_blocked — the caption
    endpoint blocks datacenter IPs (unlike search). Never inline in the
    collector: it's rate-limited and residential-only.
    """
    if top <= 0 or result.platform != "youtube" or not result.posts:
        return
    try:
        from backend.collectors.youtube_v2.free_transcript import fetch_free_transcript
    except Exception as exc:
        print(f"        transcripts: unavailable ({type(exc).__name__})")
        return
    n = min(top, len(result.posts))
    print(f"        transcripts (top {n}, box-native via free provider — no relay/proxy):")
    for row in result.posts[:n]:
        vid = row.get("platform_post_id")
        ft = fetch_free_transcript(vid)
        if ft is not None:
            more = " (+more)" if ft.truncated else ""
            print(f"          [OK]   {vid} via {ft.provider} chars={ft.chars}{more}")
        else:
            print(f"          [MISS] {vid} no free transcript (no captions or all providers down)")


def render(result: KeywordSearchResult, q: Quality, tag: str, reason: str) -> None:
    head = f"[{tag}] {result.platform:<9} q={result.query!r:<12} method={result.method}"
    print(head)
    print(f"        {result.count} rows in {result.elapsed_s:.2f}s  ->  {reason}")
    if result.count:
        print(
            f"        quality: shape={q.shape_ok}/{q.total} dups={q.dup_ids} "
            f"kw_any={q.kw_any_rate:.0%} kw_all={q.kw_all}/{q.total} "
            f"url_ok={q.url_rate:.0%} ts_ok={q.ts_rate:.0%} "
            f"range={q.oldest}..{q.newest}"
        )
        for row in result.posts[:3]:
            sub = row.get("subreddit")
            loc = f"r/{_safe(sub, 18)}" if sub else f"@{_safe(row.get('author_username'), 18)}"
            extra = f" {row.get('views')}v" if row.get("views") is not None else ""
            print(
                f"        - [{row.get('upvotes')}up {row.get('comment_count')}c{extra}] "
                f"{loc} {_safe(row.get('posted_at'), 19)}"
            )
            print(f"          {_safe(row.get('post_text'), 90)!r}")
            print(f"          {_safe(row.get('post_url'), 90)}")
            # enriched media/link line — only when present
            media = row.get("media_url") or next(iter(row.get("media_urls") or []), "")
            bits = []
            if media:
                bits.append(f"media={_safe(media, 58)}")
            dur = row.get("duration")
            if dur:
                bits.append(f"{dur}s" if isinstance(dur, int) else _safe(dur, 8))
            ext = row.get("external_url")
            if ext and ext != media:      # don't repeat a media URL as a link
                bits.append(f"link={_safe(ext, 46)} ({_safe(row.get('domain'), 20)})")
            if row.get("over_18"):
                bits.append("NSFW")
            if bits:
                print("          " + "  ".join(bits))


# ── runner ─────────────────────────────────────────────────────────────────────

async def run(keywords: list[str], platforms: list[str], limit: int,
              transcripts: int = 0) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    print("\n=== KEYWORD-SEARCH VERIFIER (Phase 1, live, no DB write) ===")
    print(f"keywords={keywords}  platforms={platforms}  limit={limit}\n")

    all_ok = True
    for platform in platforms:
        collector = REGISTRY.get(platform)
        if collector is None:
            print(f"[SKIP] {platform:<9} not registered\n")
            continue
        for kw in keywords:
            try:
                result = await collector(kw, limit=limit)
            except Exception as exc:  # a collector must never crash the run
                result = KeywordSearchResult(
                    platform=platform, method="?", query=kw, ok=False,
                    error=f"uncaught {type(exc).__name__}: {exc}",
                )
            q = assess(kw, result.posts)
            tag, reason = verdict(result, q)
            render(result, q, tag, reason)
            render_transcripts(result, transcripts)
            print()
            if tag in ("FAIL", "SUSPECT"):
                all_ok = False

    print("=" * 62)
    print("RESULT:", "ALL CLEAR" if all_ok else "ATTENTION NEEDED (see FAIL/SUSPECT above)")
    return 0 if all_ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Phase-1 keyword-search verifier")
    ap.add_argument("keywords", nargs="*", default=list(DEFAULT_KEYWORDS),
                    help="keywords to test (>=2: one hot, one fresh)")
    ap.add_argument("--platform", action="append", dest="platforms",
                    help="restrict to platform(s); default = all registered")
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--transcripts", type=int, default=0,
                    help="YouTube only: fetch transcripts for the top-N hits "
                         "(residential/relay required — off by default)")
    args = ap.parse_args()

    keywords = args.keywords or list(DEFAULT_KEYWORDS)
    platforms = args.platforms or list(REGISTRY.keys())
    return asyncio.run(run(keywords, platforms, args.limit, args.transcripts))


if __name__ == "__main__":
    sys.exit(main())
