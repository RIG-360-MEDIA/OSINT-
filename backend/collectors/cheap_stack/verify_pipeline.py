"""Verify the pipeline adapter emits correctly-shaped `social_posts` rows.

Dry-run: fetches live but does NOT write to the DB. Confirms each collector
returns the exact dict shape social_task expects, so wiring is a drop-in.

    python -m backend.collectors.cheap_stack.verify_pipeline
"""
from __future__ import annotations

import sys

from .pipeline_adapter import (
    collect_instagram_posts,
    collect_telegram_web,
    collect_tiktok_posts,
)

REQUIRED = {"platform", "platform_post_id", "author_username", "post_text",
            "post_url", "upvotes", "comment_count", "posted_at"}


def _check(label: str, rows: list) -> bool:
    if not rows:
        print(f"[EMPTY] {label:<22} 0 rows (blocked or no posts)")
        return False
    sample = rows[0]
    missing = REQUIRED - set(sample.keys())
    ok = not missing
    tag = "PASS" if ok else "FAIL"
    txt = (sample["post_text"] or "")[:46].replace("\n", " ")
    print(f"[{tag}] {label:<22} rows={len(rows):<3} shape_ok={ok} "
          f"missing={missing or '-'}")
    print(f"        sample: id={sample['platform_post_id']} at={sample['posted_at'][:19]} "
          f"txt={txt!r}")
    return ok


def run() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    print("\n=== PIPELINE ADAPTER VERIFICATION (dry-run, no DB write) ===\n")
    results = [
        _check("instagram posts", collect_instagram_posts("instagram", limit=6)),
        _check("tiktok posts", collect_tiktok_posts("tiktok", limit=6)),
        _check("telegram web", collect_telegram_web("durov", limit=6)),
    ]
    passed = sum(1 for r in results if r)
    print(f"\n{passed}/{len(results)} adapters emit valid social_posts rows.\n")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(run())
