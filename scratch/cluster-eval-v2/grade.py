"""Generate graded markdown report from v2 validation artifacts."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
FACTS = json.loads((HERE / "cluster_facts.json").read_text(encoding="utf-8"))
ARTICLES = json.loads((HERE / "articles_per_thread.json").read_text(encoding="utf-8"))
SUMMARY = json.loads((HERE / "summary.json").read_text(encoding="utf-8"))

clusters = []
for f in FACTS:
    arts = ARTICLES.get(f["thread_id"], [])
    clusters.append({**f, "articles": arts, "size": len(arts)})
clusters.sort(key=lambda c: -c["size"])

multi = [c for c in clusters if c["size"] > 1]
singletons = [c for c in clusters if c["size"] == 1]

lines = ["# 500-article v2 validation — graded report\n"]
lines.append(f"- **Sample:** {SUMMARY['sample_size']} articles | duration: {SUMMARY['duration_seconds']}s")
lines.append(f"- **Clusters:** {SUMMARY['total_threads_touched']} total, "
             f"{len(multi)} multi-article, {len(singletons)} singletons")
lines.append(f"- **LLM calls:** {SUMMARY['llm_calls']} ({100-SUMMARY['llm_skip_pct']:.0f}% of articles needed judge)")
lines.append(f"- **Errors:** {SUMMARY['errors']}")
lines.append(f"- **Source diversity:** {SUMMARY['source_diversity']}")
lines.append(f"- **Momentum:** {SUMMARY['momentum']}")
lines.append("")
lines.append("## Grading legend\n")
lines.append("- ✅ **TIGHT** — every article IS the same story")
lines.append("- ⚠️ **LOOSE** — most are the same; 1-2 don't fit")
lines.append("- ❌ **WRONG** — these are not the same story\n")
lines.append("---\n")

for i, c in enumerate(multi, 1):
    flag = ""
    if c["size"] > 30: flag = " 🚨 SUSPICIOUS (size > 30)"
    elif c["size"] > 10: flag = " ⚡ LARGE"
    lines.append(f"### #{i} · {c['size']} articles · "
                 f"sources={c.get('source_count','?')} · {c.get('momentum','?')}{flag}")
    title = (c.get('title') or '').strip()[:200]
    lines.append(f"**Title:** {title}")
    pe = c.get("primary_entities") or []
    if isinstance(pe, list) and pe:
        lines.append(f"**Entities:** {', '.join(str(e) for e in pe[:5])}")
    src_counter = Counter(a["source"] for a in c["articles"])
    src_str = "; ".join(f"{s}×{n}" for s, n in src_counter.most_common(8))
    lines.append(f"**Sources in cluster:** {src_str}")
    lines.append("")
    for a in c["articles"][:30]:
        title = (a.get("title") or "")[:130]
        subj = (a.get("subject") or "")[:130]
        lines.append(f"  - *{a['source']}* `{a['lang']}` — **{title}**")
        if subj:
            lines.append(f"    Subject: {subj}")
    if c["size"] > 30:
        lines.append(f"  ...({c['size']-30} more)")
    lines.append("\n---\n")

lines.append(f"## Singletons sample (first 20 of {len(singletons)})\n")
for c in singletons[:20]:
    a = (c.get("articles") or [{}])[0]
    lines.append(f"- *{a.get('source','?')}* `{a.get('lang','?')}` — "
                 f"{(a.get('title') or '')[:130]}")

out = HERE / "GRADED.md"
out.write_text("\n".join(lines), encoding="utf-8")
print(f"Wrote {out} ({out.stat().st_size} bytes)")
print(f"Multi: {len(multi)} | Singletons: {len(singletons)}")
