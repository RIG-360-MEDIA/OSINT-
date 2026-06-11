"""gold_set_freeze.py — Phase 4 deliverable.

Reads a judge_results JSONL produced by llm_judge.py, picks the top 200
high-confidence articles (judged accurate across all fields), and writes
them to docs/quality/gold_set_v1.jsonl as the permanent regression baseline.

Selection rules:
  * verdict.confidence >= 0.85
  * verdict.overall_score >= 9
  * spread across sources: cap any one source at 10% of gold set
  * spread across languages

Run AFTER llm_judge.py finishes.

Usage:
    python3 scripts/audit/gold_set_freeze.py \
        --input /tmp/judge_5k.jsonl \
        --out docs/quality/gold_set_v1.jsonl
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("gold_freeze")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
QUALITY_DIR = REPO_ROOT / "docs" / "quality"
GOLD_SIZE = 200
MAX_PER_SOURCE_PCT = 0.10  # no source dominates more than 10% of gold


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return rows


def is_high_confidence(r: dict) -> bool:
    v = r.get("verdict")
    if not v or "error" in r:
        return False
    if not isinstance(v.get("confidence"), (int, float)):
        return False
    if v.get("confidence") < 0.85:
        return False
    if not isinstance(v.get("overall_score"), (int, float)):
        return False
    if v.get("overall_score") < 9:
        return False
    # Every field score must be >= 8 (no glaring weak field)
    for field in ("primary_subject_score", "summary_executive_score",
                  "article_type_score", "actors_score"):
        s = v.get(field)
        if isinstance(s, (int, float)) and s < 8:
            return False
    return True


def select_gold(candidates: list[dict], size: int = GOLD_SIZE) -> list[dict]:
    """Pick `size` rows, capping per-source to MAX_PER_SOURCE_PCT."""
    per_source_cap = max(2, int(size * MAX_PER_SOURCE_PCT))
    selected: list[dict] = []
    source_counts: Counter[str] = Counter()
    random.seed(42)
    random.shuffle(candidates)
    for r in candidates:
        src = r.get("source", "?")
        if source_counts[src] >= per_source_cap:
            continue
        selected.append(r)
        source_counts[src] += 1
        if len(selected) >= size:
            break
    return selected


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, help="judge_results JSONL path")
    p.add_argument("--out", default=str(QUALITY_DIR / "gold_set_v1.jsonl"))
    p.add_argument("--size", type=int, default=GOLD_SIZE)
    args = p.parse_args(argv)

    in_path = Path(args.input)
    if not in_path.exists():
        log.error("Input not found: %s", in_path)
        return 1

    rows = load_jsonl(in_path)
    log.info("Loaded %d judge results", len(rows))

    # Filter to high-confidence rows
    candidates = [r for r in rows if is_high_confidence(r)]
    log.info("High-confidence candidates: %d", len(candidates))

    if len(candidates) < args.size:
        log.warning("Only %d candidates (asked for %d) — gold set will be smaller",
                    len(candidates), args.size)

    gold = select_gold(candidates, args.size)
    log.info("Selected %d gold rows", len(gold))

    # Per-source/lang spread report
    src_counts = Counter(r.get("source", "?") for r in gold)
    lang_counts = Counter(r.get("lang", "?") for r in gold)
    log.info("Source spread (top 10): %s", src_counts.most_common(10))
    log.info("Language spread: %s", lang_counts.most_common())

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for r in gold:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    summary = {
        "frozen_at": str(in_path.stat().st_mtime),
        "input": str(in_path),
        "size_requested": args.size,
        "size_actual": len(gold),
        "candidates_pool": len(candidates),
        "source_counts": dict(src_counts.most_common(20)),
        "language_counts": dict(lang_counts.most_common()),
    }
    (QUALITY_DIR / "gold_set_v1.summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    log.info("Wrote gold set to %s", out_path)
    log.info("Wrote summary to docs/quality/gold_set_v1.summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
