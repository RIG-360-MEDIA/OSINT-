"""Generate a graded markdown report for the event-clustering validation.

Reads clusters.json + articles_per_cluster.json + summary.json and produces
GRADED.md grouped by size (largest first), plus auto-flagged suspicious
clusters (single-source, off-window date).
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
CLUSTERS = json.loads((HERE / "clusters.json").read_text(encoding="utf-8"))
APC = json.loads((HERE / "articles_per_cluster.json").read_text(encoding="utf-8"))
SUMMARY = json.loads((HERE / "summary.json").read_text(encoding="utf-8"))

# Attach articles to clusters
for c in CLUSTERS:
    c["articles"] = APC.get(c["id"], [])
    c["size"] = c.get("article_count") or len(c["articles"])

multi = [c for c in CLUSTERS if c["size"] > 1]
multi.sort(key=lambda c: -c["size"])

lines = ["# Event-clustering validation — graded report\n"]
lines.append(f"- **Sample window:** {SUMMARY.get('since_days')} days")
lines.append(f"- **Events processed:** {SUMMARY.get('events_total')}")
lines.append(f"- **Total clusters:** {SUMMARY.get('clusters_total')} | "
             f"**Multi-event:** {SUMMARY.get('multi_article_clusters')} | "
             f"**Singletons:** {SUMMARY.get('singletons')}")
lines.append(f"- **Duration:** {SUMMARY.get('duration_sec')}s")
lines.append(f"- **Size buckets:** {SUMMARY.get('size_buckets')}")
lines.append(f"- **Source diversity:** {SUMMARY.get('source_diversity')}")
lines.append("")
lines.append("## Grading legend\n")
lines.append("- ✅ **TIGHT** — every article describes the same atomic event")
lines.append("- ⚠️ **LOOSE** — most match; 1-2 don't fit")
lines.append("- ❌ **WRONG** — mixed/unrelated events")
lines.append("")
lines.append("---\n")

# Auto-flag suspicious clusters
def flag(c):
    flags = []
    if c["size"] > 30: flags.append("🚨 SIZE>30")
    elif c["size"] > 10: flags.append("⚡ LARGE")
    if (c.get("source_count") or 0) <= 1 and c["size"] > 2:
        flags.append("⚠️ SINGLE-SOURCE")
    return " ".join(flags)

# Top 50 multi-article clusters in detail
lines.append(f"## Top 50 multi-event clusters (of {len(multi)})\n")
for i, c in enumerate(multi[:50], 1):
    f = flag(c)
    lines.append(f"### #{i} · size={c['size']} · sources={c.get('source_count')} · "
                 f"type={c.get('etype','?')} · date={c.get('d','?')} {f}".strip())
    desc = (c.get('desc') or '').strip()[:200]
    lines.append(f"**Canonical:** {desc}")
    actors = c.get('actors') or []
    if actors:
        lines.append(f"**Actors:** {', '.join(str(a) for a in actors[:6])}"
                     f"{' (+'+str(len(actors)-6)+' more)' if len(actors) > 6 else ''}")
    src_counter = Counter(a.get("source", "?") for a in c["articles"])
    src_str = "; ".join(f"{s}×{n}" for s, n in src_counter.most_common(8))
    lines.append(f"**Sources:** {src_str}")
    lines.append("")
    for a in c["articles"][:20]:
        title = (a.get("title") or "")[:130]
        ed = (a.get("event_desc") or "")[:120]
        lines.append(f"  - *{a.get('source')}* `{a.get('lang')}` — **{title}**")
        if ed:
            lines.append(f"    Event: {ed}")
    if c["size"] > 20:
        lines.append(f"  ...({c['size']-20} more)")
    lines.append("")
    lines.append("---")
    lines.append("")

# Summary statistics
lines.append("## Statistics across all 385 multi-event clusters\n")
size_counts = Counter()
for c in multi:
    size_counts[c["size"]] += 1
lines.append("**Size distribution (multi-event only):**")
for sz in sorted(size_counts):
    lines.append(f"- size {sz}: {size_counts[sz]} clusters")
lines.append("")

# Single-source mega-cluster watch
single_src_mega = [c for c in multi if (c.get("source_count") or 0) <= 1 and c["size"] > 2]
lines.append(f"## Single-source clusters > 2 articles (failure mode flag): {len(single_src_mega)}\n")
for c in single_src_mega[:15]:
    lines.append(f"- size={c['size']} sources={c.get('source_count')} "
                 f"type={c.get('etype')} date={c.get('d')} — {(c.get('desc') or '')[:100]}")

out = HERE / "GRADED.md"
out.write_text("\n".join(lines), encoding="utf-8")
print(f"Wrote {out} ({out.stat().st_size} bytes)")
print(f"Total multi: {len(multi)} | Top size: {multi[0]['size']} | Single-source-mega: {len(single_src_mega)}")
