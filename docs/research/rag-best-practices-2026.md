# How the best RAG systems are built (2024–2026) — and what Ask-RIG should adopt

Synthesis of live web/GitHub/Reddit research. Deep dives in the sibling files:
[chunking](./rag-chunking-sota-2024-2026.md) · [retrieval/embeddings/query](./rag-retrieval-embeddings-query-transform-2026.md).
This file = the whole concept map + the verdict for our multilingual news RAG.

## 0. The pipeline every top system converged on
Perplexity, Glean, Anthropic, NotebookLM, Morphic/Perplexica all have the **same shape**:

```
Query
 → rewrite / expand (2–3 variants; normalize entities/abbreviations)
 → HYBRID retrieve: dense vectors ‖ sparse BM25  → fuse with RRF (k=60)   [top ~50–100]
 → RERANK with a cross-encoder                                            [→ top ~20]
 → DEDUP + DIVERSIFY (story-chains; source/language/stance quotas; MMR)
 → (optional) corrective re-search if results are weak (CRAG)
 → SELECT 5–8 chunks, reorder best-to-edges (lost-in-the-middle)
 → GENERATE with inline citations (cite-ID guardrail)
 → EVAL offline: context precision/recall, faithfulness, answer-relevance
Index-time: contextual chunk augmentation (Anthropic) + rich metadata + prompt-cache
```
The big takeaway: **the magic is in hybrid + rerank + diversity + grounding, not in clever chunking.**

---

## 1. Chunking — mostly a solved, overrated problem
| Technique | Verdict | Default |
|---|---|---|
| Recursive char split | **Benchmark winner (~69%)** | **512 tokens / 50 overlap** |
| Semantic chunking | **Overrated** (~54–58%); ~0 gain once you have hybrid+rerank | skip |
| **Anthropic Contextual Retrieval** | **Biggest chunking win**: prepend an LLM-written 1-line context to each chunk before embedding *and* BM25 | −35% / −49% / **−67%** retrieval failures (stacks); ~$1/M tokens w/ prompt cache |
| Late chunking (Jina) | Cheaper, no-LLM alt for long docs | needs long-ctx embedder |
| Parent-document / small-to-big | Embed small, return big | great for long features/PDFs |
| RAPTOR / hierarchical / propositions | Niche; high cost | only for deep synthesis |

**For NEWS specifically:** don't over-chunk. **Embed short articles whole**, always **prepend title + date + source** to the embedded text, and only chunk long features / govt PDFs (recursive + structure-aware, or parent-document). Chunk boundary is rarely the bottleneck — **data quality is.**

---

## 2. Embeddings — the one place Ask-RIG has a real ceiling
- **Hybrid (dense + sparse) beats either alone** by +26–31% NDCG. We have this (v4 + `fts` + RRF). ✅
- **Best multilingual model today = BGE-M3**: leads 8/13 Indic languages (Telugu MRR ~0.50), **8192-token** context, and emits **dense + sparse from one model** (its sparse leg covers Telugu/Hindi where Postgres has no stemmer). **mE5-large** is the Hindi A/B.
- **⚠ Our constraint:** the corpus is embedded with **LaBSE (`v4`), which caps at ~256 tokens** — fine for titles, but it forces fragmentation and is an *older* cross-lingual baseline. **BGE-M3 is the upgrade** — but re-embedding 354K docs is the **corpus pipeline owner's** job (Ask-RIG is read-only, and the query embedder MUST match the doc embedder). So: **keep LaBSE v4 for Ask-RIG V1**; file "re-embed corpus with BGE-M3" as the highest-value ingestion upgrade.
- **pgvector index:** HNSW `m=16, ef_construction=200, ef_search=100`, cosine; pre-filter `lang`/`published_at` in the same query.

---

## 3. Query transformation — cheap wins, one trap
- **Query rewriting + RAG-Fusion** (run 2–3 query variants, RRF the results) = **best ROI**.
- **HyDE** (hypothetical answer doc) — **adds 25–60% latency and hallucinates on fact/entity queries** → gate it OFF for breaking-news/entity lookups; use only for vague or cross-lingual queries.
- Query routing / decomposition / step-back: for complex analyst questions, not simple lookups.

---

## 4. Reranking — the single biggest lever after hybrid (and exactly our gap)
- A **cross-encoder reranker** over the top-50 → top-5/10 lifts **NDCG@10 by 5–15 points** for <200–500ms.
- **The diagnostic everyone cites:** if `recall@50` is high but `NDCG@10` is low → **ranking problem → rerank fixes it**. *That is precisely Ask-RIG's measured state* (recall@20 0.59 ≫ recall@10 0.43).
- **Pick:** `bge-reranker-v2-m3` (open, multilingual — fits our corpus) or Jina-v3 (sub-200ms) or Cohere Rerank 4 (zero-ops). Rerank **30–50 → keep 5–8**.

---

## 5. Diversity / anti-redundancy — your "I hate top-10" instinct, validated
The pros do **not** just take top-k by score (you were right). The news-specific recipe:
1. **Dedup at the story level FIRST** — cluster near-identical reprints into one story chain, keep **one representative per cluster**. *(We already have `story_clusters_v8` — this is a gift.)*
2. **Enforce facet quotas** in the final set — guarantee N distinct **sources**, both **stances** (supportive + critical, via `article_stances`), and **language** coverage (EN/TE/HI). Reranker relevance alone re-collapses diversity, so quotas are mandatory.
3. **MMR** (λ≈0.6–0.7: relevance vs novelty) on the candidate set as the general-purpose diversifier.
- Canonical order: `fetch_k=100` → dedup/story-chain → MMR k≈20 → rerank → **facet-quota select 5–8**.
- This is literally Ground News / Google News logic — and a **selling point**, not just a fix.

---

## 6. Context assembly — more is NOT better
- **Lost-in-the-middle** (U-shaped attention): models degrade 20+ points on middle context; quality drops past **~10 docs**. So: **retrieve wide, then aggressively cut to 5–8**, and **reorder best-to-edges** (best first, 2nd-best last, weakest in the middle).
- **Compression** (optional): **Provence** (NAVER) fuses rerank + sentence-pruning in one cross-encoder pass (compression ~free); LLMLingua-2 for token pruning (up to 20×).

---

## 7. Grounding & evaluation — necessary, and trickier than it looks
- **Metrics (all frameworks):** context **precision** + **recall** (retrieval), **faithfulness** + **answer-relevance** (generation). Measure **stage-wise** — end-to-end scores can't tell you what to fix.
- **Tools:** Ragas (fastest start + synthetic test sets), DeepEval (CI/red-team), TruLens (prod monitoring).
- **⚠ Correctness ≠ Faithfulness (SIGIR'25):** models **post-rationalize** citations — up to **57%** unfaithful in adversarial cases. Our cite-ID guardrail (does `[S#]` resolve?) is necessary but **not sufficient**; add a **faithfulness check** (does the cited source actually support the claim?).

---

## 8. Advanced architectures — when they're worth it
| Pattern | Worth it when | For news? |
|---|---|---|
| **Reranking + hybrid** | always | ✅ do first |
| **CRAG** (grade retrieval → re-search if weak) | corpus has coverage gaps / changes | ✅ great fit (news changes hourly) |
| **Adaptive routing** (classify difficulty → no/single/multi-hop) | controlling cost at scale | ✅ cheap "smart" |
| **Agentic RAG** (retrieval as a tool, iterate) | multi-hop/research questions | ⚠ for analyst queries only (4–8× cost) |
| **GraphRAG** (Microsoft) | whole-corpus thematic Qs over a *stable* corpus | ❌ too expensive/static for news |
| **LightRAG** | want graph reasoning + incremental updates | ◑ later, if graph needed |

**Long-context vs RAG verdict:** RAG is **not dead** — it's **8–82× cheaper**, citation-accurate, and **wins for fresh, changing, at-scale data = exactly news.** Winning teams **route**: simple → RAG, complex multi-hop → long-context.

---

## 9. Verdict for Ask-RIG — what to change, in priority order
| # | Action | Why | Effort |
|---|---|---|---|
| 1 | **Add `bge-reranker-v2-m3`** (rerank top-50 → 8) | the #1 lever; fixes our recall@20≫recall@10 gap directly | small |
| 2 | **Diversity layer**: story-chain dedup (use `story_clusters_v8`) + source/language/stance quotas + MMR | your diversity concern; uses our unique clustering; the moat | medium |
| 3 | **Context assembly**: pass 5–8 curated docs, reorder best-to-edges | lost-in-the-middle | tiny |
| 4 | **Faithfulness eval** (Ragas) on top of cite-ID guardrail | correctness≠faithfulness | small |
| 5 | **CRAG-style re-search** when retrieval scores are weak | news coverage gaps | medium |
| 6 | (ingestion-side, not Ask-RIG) **re-embed corpus with BGE-M3** | LaBSE 256-tok ceiling; better Indic | large, corpus owner |
| — | Keep: hybrid v4+fts+RRF (already the industry-standard core) | don't fix what's right | — |

**Already industry-correct:** our hybrid (v4 + fts + RRF), cite-ID guardrail, honest-refusal, read-only contract, and eval harness. The gaps are reranking + diversity — both planned, both high-ROI.
