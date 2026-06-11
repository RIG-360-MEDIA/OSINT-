"""Produce a manual-review markdown report.

For each multi-article cluster: show every article (source/lang/title/subject),
the LLM's SAME-reasons (the narrative thread), and the constituent edges.
Also a calibration section: sim distribution for SAME vs DIFFERENT verdicts,
high-sim splits (where embeddings agreed but LLM disagreed), and the singletons
that were near-cluster.
"""
import json, statistics
from pathlib import Path

HERE = Path(__file__).parent
with open(HERE / "meta.json", encoding="utf-8") as f:
    META = json.load(f)
with open(HERE / "clusters.json", encoding="utf-8") as f:
    D = json.load(f)

clusters = D["clusters"]
judgments = D["judgments"]
edges = D["edges"]

def fmt_article(i):
    a = META[i]
    src = a["source"]
    lang = a["lang"]
    title = (a["title"] or "").strip().replace("\n", " ")
    subj = (a["subject"] or "").strip().replace("\n", " ")
    return f"  - **[{i}]** *{src}* `{lang}` — **{title}**\n    Subject: {subj}"

def cluster_block(c, idx):
    head = f"### Cluster {idx}  ·  {len(c)} articles\n"
    arts = "\n".join(fmt_article(i) for i in c)
    # SAME edges within this cluster
    in_cluster_edges = [(i, j) for (i, j) in edges if i in c and j in c]
    reasons = "\n".join(
        f"  - [{i}↔{j}] sim={judgments[f'{i}-{j}']['sim']:.3f} → {judgments[f'{i}-{j}']['reason'][:240]}"
        for (i, j) in in_cluster_edges
    )
    return f"{head}{arts}\n\n**LLM SAME-reasons within this cluster ({len(in_cluster_edges)} edges):**\n{reasons}\n"

multi = [c for c in clusters if len(c) > 1]
singletons = [c for c in clusters if len(c) == 1]

# Calibration: sim distribution per verdict
sims_same = [j["sim"] for j in judgments.values() if j["verdict"] == "SAME"]
sims_diff = [j["sim"] for j in judgments.values() if j["verdict"] == "DIFFERENT"]

# High-sim splits: pairs LLM said DIFFERENT despite high sim
high_sim_splits = sorted(
    [(k, v) for k, v in judgments.items() if v["verdict"] == "DIFFERENT" and v["sim"] >= 0.62],
    key=lambda x: -x[1]["sim"]
)
# Low-sim joins: pairs LLM said SAME despite low sim
low_sim_joins = sorted(
    [(k, v) for k, v in judgments.items() if v["verdict"] == "SAME" and v["sim"] < 0.62],
    key=lambda x: x[1]["sim"]
)

lines = []
lines.append("# Clustering eval — manual review\n")
lines.append(f"- Corpus sample: **{D['n_articles']} articles** (May 12, 2026; Telangana-focused, multilingual: te/en/hi)")
lines.append(f"- Embedding: `paraphrase-multilingual-MiniLM-L12-v2` (384-dim, multilingual)")
lines.append(f"- Candidate retrieval: top-{D['top_k']} kNN with cosine sim ≥ {D['sim_floor']} (= {len(judgments)} pairs sent to LLM)")
lines.append(f"- LLM judge: Cerebras `{D['model']}`, temperature=0")
lines.append(f"- **Result:** {len(multi)} multi-article clusters + {len(singletons)} singletons\n")

lines.append("## How to grade this report\n")
lines.append("Read each cluster below. Mark it:")
lines.append("- ✅ **TIGHT** — every article in this cluster IS the same story")
lines.append("- ⚠️ **LOOSE** — most are the same, but 1-2 articles don't belong")
lines.append("- ❌ **WRONG** — these are not the same story")
lines.append("")
lines.append("Then scan the **high-sim splits** below — these are pairs the embedding thought close but the LLM rejected. Were any of them actually the same story (= missed clusters)?")
lines.append("")
lines.append("---\n")

lines.append("## Multi-article clusters\n")
for idx, c in enumerate(multi, 1):
    lines.append(cluster_block(c, idx))
    lines.append("")

lines.append("---\n")
lines.append("## Calibration\n")
lines.append(f"Pairs sent to LLM: **{len(judgments)}**\n")
lines.append(f"- SAME verdicts: **{len(sims_same)}** — sim min={min(sims_same):.3f}, median={statistics.median(sims_same):.3f}, max={max(sims_same):.3f}")
lines.append(f"- DIFFERENT verdicts: **{len(sims_diff)}** — sim min={min(sims_diff):.3f}, median={statistics.median(sims_diff):.3f}, max={max(sims_diff):.3f}")
lines.append("")
lines.append("If SAME-median > DIFFERENT-median, embedding sim is informative. If they overlap heavily, embedding alone is insufficient (LLM does the real work).\n")

lines.append("### High-sim splits (LLM rejected despite sim ≥ 0.62)\n")
lines.append("If any of these *should* have been clustered, embeddings can find them but the LLM is over-strict.\n")
for k, v in high_sim_splits[:15]:
    i, j = map(int, k.split("-"))
    ai, aj = META[i], META[j]
    lines.append(f"- **[{i}↔{j}]** sim={v['sim']:.3f} — LLM: *{v['reason'][:200]}*")
    lines.append(f"  - [{i}] *{ai['source']}* `{ai['lang']}` — {(ai['title'] or '')[:120]}")
    lines.append(f"  - [{j}] *{aj['source']}* `{aj['lang']}` — {(aj['title'] or '')[:120]}")
lines.append("")

lines.append("### Low-sim joins (LLM matched despite sim < 0.62)\n")
lines.append("If any of these are *wrong* matches, the LLM is too liberal.\n")
for k, v in low_sim_joins[:10]:
    i, j = map(int, k.split("-"))
    ai, aj = META[i], META[j]
    lines.append(f"- **[{i}↔{j}]** sim={v['sim']:.3f} — LLM: *{v['reason'][:200]}*")
    lines.append(f"  - [{i}] *{ai['source']}* `{ai['lang']}` — {(ai['title'] or '')[:120]}")
    lines.append(f"  - [{j}] *{aj['source']}* `{aj['lang']}` — {(aj['title'] or '')[:120]}")
lines.append("")

lines.append("---\n")
lines.append("## Singletons sample (first 25)\n")
lines.append("These are articles that didn't cluster. Many are legitimately unique; some may indicate missed clusters.\n")
for c in singletons[:25]:
    i = c[0]
    a = META[i]
    lines.append(f"- **[{i}]** *{a['source']}* `{a['lang']}` — {(a['title'] or '')[:140]}")
    lines.append(f"    {(a['subject'] or '')[:140]}")

out = HERE / "REVIEW.md"
out.write_text("\n".join(lines), encoding="utf-8")
print(f"Wrote {out} ({out.stat().st_size} bytes)")
print(f"Multi-article clusters: {len(multi)}")
print(f"Singletons: {len(singletons)}")
print(f"High-sim splits: {len(high_sim_splits)}")
print(f"Low-sim joins: {len(low_sim_joins)}")
