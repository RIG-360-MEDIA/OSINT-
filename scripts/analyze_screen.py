"""Tier CareersWave sources by extraction reliability from the screen JSONL."""
from __future__ import annotations

import io
import json
import sys

SRC = "scripts/eval_data/source_screen.jsonl"
OUT = "scripts/eval_data/SOURCE_RELIABILITY.md"

# Languages with NO PaddleOCR recogniser model at all.
UNSUPPORTED = {"bn", "gu", "ml", "pa"}
# DB lang tags that map to a PaddleOCR code we don't currently pass.
NEEDS_CODEMAP = {"hi": "devanagari", "mr": "devanagari", "kn": "ka"}


def tier(r: dict) -> str:
    if not r.get("live"):
        return "NO_EDITION"
    lang = r.get("lang") or ""
    anc = r.get("anchored_pct", 0)
    if not r.get("lang_ok", False) and r.get("articles"):
        return "MISTAGGED"  # detected language != declared (e.g. MT'd edition)
    if lang in UNSUPPORTED:
        return "UNSUPPORTED_OCR"
    if lang in NEEDS_CODEMAP and anc < 30:
        return "NEEDS_CODEMAP"
    if anc >= 80 and r.get("mis_anchor", 9) <= 2 and r.get("tiny_pct", 99) < 25:
        return "RELIABLE"
    if anc >= 60:
        return "WORKABLE"
    return "PARTIAL"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    rows = [json.loads(l) for l in io.open(SRC, encoding="utf-8") if l.strip()]
    for r in rows:
        r["_tier"] = tier(r)
    order = ["RELIABLE", "WORKABLE", "PARTIAL", "NEEDS_CODEMAP",
             "UNSUPPORTED_OCR", "MISTAGGED", "NO_EDITION"]
    rows.sort(key=lambda r: (order.index(r["_tier"]), -r.get("anchored_pct", 0)))

    lines = ["# CareersWave source reliability matrix",
             "",
             f"Screen: {len(rows)} sources, 3 pages each, today's live editions.",
             "Metrics: anchored% (tight snapshot located), mis (cross-article overlap),",
             "tiny% (sub-8KB sliver crops), lang_ok (detected==declared).",
             "",
             "| Tier | Paper | lang | live | articles | anchored% | mis | tiny% | lang_ok |",
             "|---|---|---|---|---|---|---|---|---|"]
    counts: dict = {}
    for r in rows:
        counts[r["_tier"]] = counts.get(r["_tier"], 0) + 1
        lines.append(
            f"| {r['_tier']} | {r['name']} | {r.get('lang','')} "
            f"| {'Y' if r.get('live') else 'N'} | {r.get('articles','-')} "
            f"| {r.get('anchored_pct','-')} | {r.get('mis_anchor','-')} "
            f"| {r.get('tiny_pct','-')} | {'Y' if r.get('lang_ok') else 'N'} |"
        )
    io.open(OUT, "w", encoding="utf-8").write("\n".join(lines) + "\n")

    print("TIER COUNTS:", {k: counts[k] for k in order if k in counts})
    print()
    for t in order:
        names = [r["name"] for r in rows if r["_tier"] == t]
        if names:
            print(f"{t} ({len(names)}): {', '.join(names)}")


if __name__ == "__main__":
    main()
