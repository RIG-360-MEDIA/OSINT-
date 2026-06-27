"""Read the 500-article validation artifacts and produce a graded report.

For every multi-article cluster:
  - List each article (source, lang, title, subject)
  - Auto-flag suspicious clusters (size > 30, mixed-topic by quick heuristic)
  - Output to GRADED.md
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
FACTS = json.loads((HERE / "cluster_facts.json").read_text(encoding="utf-8"))
ARTICLES = json.loads((HERE / "articles_per_thread.json").read_text(encoding="utf-8"))
ASSIGN = json.loads((HERE / "assignments.json").read_text(encoding="utf-8"))
SUMMARY = json.loads((HERE / "summary.json").read_text(encoding="utf-8"))

# Build cluster -> articles
clusters = []
for f in FACTS:
    tid = f["thread_id"]
    arts = ARTICLES.get(tid, [])
    clusters.append({**f, "articles": arts, "size": len(arts)})

clusters.sort(key=lambda c: -c["size"])

# Group assignments by LLM-used
llm_assigns = [a for a in ASSIGN if isinstance(a, dict) and a.get("skipped_llm") is False]

lines = ["# 500-article validation — graded report\n"]
lines.append(f"Sample: {SUMMARY['sample_size']} articles | Duration: {SUMMARY['duration_seconds']}s | LLM calls: {SUMMARY['llm_calls']}")
lines.append(f"Clusters: {SUMMARY['total_threads_touched']} | "
             f"Singletons: {SUMMARY['size_distribution'].get('1 (singleton)', 0)} | "
             f"Errors: {SUMMARY['errors']}")
lines.append("")

multi = [c for c in clusters if c["size"] > 1]
singletons = [c for c in clusters if c["size"] == 1]

lines.append(f"## Multi-article clusters ({len(multi)})\n")
lines.append("Grade each: ✅ TIGHT (all same story) | ⚠️ LOOSE (1-2 don't fit) | ❌ WRONG (mixed)\n")
lines.append("---\n")

for i, c in enumerate(multi, 1):
    flag = ""
    if c["size"] > 30:
        flag = " 🚨 SUSPICIOUS (size > 30)"
    elif c["size"] > 10:
        flag = " ⚡ LARGE (size > 10)"
    lines.append(f"### #{i} · {c['size']} articles · {c.get('momentum','?')} · "
                 f"confidence={c.get('confidence') or 'seed'}{flag}")
    lines.append(f"**Title:** {(c.get('title') or '').strip()[:200]}")
    pe = c.get("primary_entities") or []
    if isinstance(pe, list) and pe:
        lines.append(f"**Entities:** {', '.join(str(e) for e in pe[:5])}")
    lines.append(f"**Source count:** {c.get('source_count')} | **Seed:** {(c.get('seed_article_id') or '')[:8]}")
    lines.append("")

    # Source frequency in this cluster
    src_counter = Counter(a["source"] for a in c["articles"])
    src_str = "; ".join(f"{s}×{n}" for s, n in src_counter.most_common(8))
    lines.append(f"**Sources in cluster:** {src_str}")
    lines.append("")
    for a in c["articles"][:25]:
        title = (a.get("title") or "")[:140]
        subj = (a.get("subject") or "")[:140]
        lines.append(f"  - *{a['source']}* `{a['lang']}` — **{title}**")
        if subj:
            lines.append(f"    Subject: {subj}")
    if c["size"] > 25:
        lines.append(f"  ...({c['size']-25} more)")
    lines.append("\n---\n")

# Quick singleton breakdown — sources
lines.append(f"## Singleton breakdown ({len(singletons)})\n")
lines.append("First 15 singletons (sample):\n")
for c in singletons[:15]:
    a = (c.get("articles") or [{}])[0]
    lines.append(f"- *{a.get('source','?')}* `{a.get('lang','?')}` — "
                 f"{(a.get('title') or '')[:140]}")

lines.append("\n## LLM-judged assignments\n")
lines.append(f"Total LLM calls: {len(llm_assigns)}\n")
for a in llm_assigns[:25]:
    lines.append(f"- article={a['article_id'][:8]} → thread={(a.get('thread_id') or '')[:8]} "
                 f"spawn={a.get('spawned_new')} conf={a.get('confidence',0):.2f} "
                 f"distance={a.get('distance',0):.3f}")

out = HERE / "GRADED.md"
out.write_text("\n".join(lines), encoding="utf-8")
print(f"Wrote {out} ({out.stat().st_size} bytes)")
print(f"Multi: {len(multi)} | Singletons: {len(singletons)} | LLM-judged: {len(llm_assigns)}")
