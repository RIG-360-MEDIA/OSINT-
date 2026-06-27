# RAG Retrieval, Embeddings & Query Transformation — How the Best Systems Do It (2024–2026)

Scope: retrieval architecture for a multilingual (English/Telugu/Hindi) **news** RAG on **Postgres + pgvector**.
Format: each concept = what / who uses / when / params, then sources. Verified against vendor docs, arXiv, and practitioner write-ups.

---

## 1. Dense vs Sparse vs Hybrid + RRF

- **Dense (vector)** — semantic match; good at paraphrase/meaning. Fails on rare entities, names, codes, exact strings, transliteration. Single-vector is *lossy* (compresses a passage to one vector) and degrades **out-of-domain**.
- **Sparse (BM25/keyword)** — exact lexical match; great for names, proper nouns, IDs, transliterated tokens, breaking-news jargon. No semantics.
- **Hybrid (dense + BM25, fused)** — runs both in parallel, merges. **Wins in practice** because news queries mix meaning ("farmer protests reaction") with exact strings (politician names, place names, party acronyms, transliterations). Reported lifts: **+26–31% NDCG over dense-only**; recall@1000 ~0.87→0.98 on mixed-query benchmarks. This is the **production default** across all major vector DBs.
- **Reciprocal Rank Fusion (RRF)** — fuse by rank, not score: `score(d) = Σ 1/(k + rank_i(d))`, **k=60** (universal default). Why it wins: **scale-agnostic** — cosine is 0–1, BM25 is unbounded; normalizing them is unstable, RRF sidesteps it by using only rank positions. Same RRF also fuses multi-query result sets ("RAG-Fusion").
- Common weighting when using weighted (not pure-RRF) fusion: **~0.7 dense / 0.3 sparse** as a starting point, then tune.

Sources:
- https://atlan.com/know/hybrid-rag/
- https://medium.com/@kumaran.isk/building-a-production-rag-pipeline-start-with-hybrid-retrieval-dense-bm25-rrf-e901aba17cae
- https://medium.com/@mudassar.hakim/the-quiet-hero-of-rag-pipelines-reciprocal-rank-fusion-explained-1b83af68b997
- https://www.digitalapplied.com/blog/hybrid-search-bm25-vector-reranking-reference-2026
- https://superlinked.com/vectorhub/articles/optimizing-rag-with-hybrid-search-reranking

---

## 2. Embedding Models (multilingual focus)

- **Closed/API leaders**: OpenAI `text-embedding-3-large` (3072d, MRL-truncatable), Cohere `embed-v3` multilingual, Voyage (`voyage-3`), Jina v3/v4. Strong English; convenient; cost + data-egress + per-call latency.
- **Open multilingual leaders**:
  - **BGE-M3** (568M, 100+ langs, **8192 ctx**) — emits **dense + sparse + multi-vector (ColBERT)** from one model; **single best for Indian languages** in independent benchmarks (IndicMSMarco MRR: **Telugu 0.50**, leads 8/13 langs). The pragmatic default for this project.
  - **multilingual-e5-large** (560M) — strong #2; **best on Hindi (0.52)** in the same benchmark. Needs `query:`/`passage:` prefixes.
  - **Qwen3-Embedding** (0.6B/4B/8B) — **#1 on MTEB multilingual** (8B = 70.58, Jun 2025), instruction-aware, MRL dims 32–1024. Heavier; strongest if you can afford it.
  - EmbeddingGemma-300M, E5-mistral-7b-instruct (top MTEB but 7B = heavy).
- **Late interaction (multi-vector): ColBERT / ColPali / ColQwen** — token-level embeddings, scored by sum-of-max (MaxSim). **More accurate + more robust out-of-domain + explainable**, but **10–100× storage** and heavier query compute (PLAID/quantization mitigate; ~tens ms GPU / hundreds ms CPU at scale). **Use as a reranker over top-k**, not as the primary index, unless on a DB built for it (Vespa, Qdrant multivector). ColPali = image-patch variant for scanned PDFs/newspaper pages (relevant to your *cuttings* pillar).
- **LaBSE** — 109-lang, purpose-built for **cross-lingual sentence retrieval** (find the Hindi sentence matching an English one). Strong *alignment* baseline but **older, 768d, no sparse, weaker monolingual nuance** than BGE-M3/mE5. Keep as a cross-lingual sanity check, not the primary retriever.

Sources:
- https://www.bentoml.com/blog/a-guide-to-open-source-embedding-models
- https://milvus.io/blog/choose-embedding-model-rag-2026.md
- https://arxiv.org/pdf/2506.01615  (IndicRAGSuite)
- https://arxiv.org/pdf/2409.05401  (NLLB-E5 / Hindi-BEIR)
- https://www.johal.in/finetuning-embedding-model-multilingual-legal-documents-bgem3-vs/  (BGE-M3 vs E5-mistral)
- https://weaviate.io/blog/late-interaction-overview
- https://www.emergentmind.com/topics/language-agnostic-bert-sentence-embedding-labse

---

## 3. Index Params (pgvector)

- **HNSW is the default** for RAG (better recall/latency than IVFFlat, tolerates incremental writes — important for a live news feed). IVFFlat = lower memory but needs training data present + reindex as data grows; avoid for streaming corpora.
- **HNSW build**: `m = 16` (default; 16–32 for higher recall), `ef_construction = 200` (default 64; 200 is the practical sweet spot — raise only if recall short). Build cost ↑ with both.
- **HNSW query**: `SET hnsw.ef_search = 100` (default 40; 100–200 trades latency for recall). Per-session/per-query tunable.
- **IVFFlat (if ever used)**: `lists = rows/1000` (≤1M rows) or `sqrt(rows)` (>1M); `probes = 10–50`.
- **Distance op**: cosine (`<=>`) for normalized text embeddings.
- **pgvector specifics**: pre-filter via SQL `WHERE` in the *same* query as the vector op (one round-trip); partial/composite indexes help; `maintenance_work_mem` high during HNSW build; consider `halfvec` (fp16) to halve storage at ~no recall loss for large corpora.

Sources:
- https://github.com/pgvector/pgvector
- https://neon.com/docs/ai/ai-vector-search-optimization
- https://learn.microsoft.com/en-us/azure/cosmos-db/postgresql/howto-optimize-performance-pgvector
- https://dbadataverse.com/tech/postgresql/2025/12/pgvector-postgresql-vector-database-guide

---

## 4. Hybrid Search ON pgvector (concrete)

- **Pattern**: two CTEs — one ranks by BM25-flavored `ts_rank_cd(ts, plainto_tsquery(...))` over a `tsvector` (or true BM25 via extension), one ranks by `1 - (embedding <=> $q)`; fuse with **RRF (k=60)** in SQL. All in one Postgres instance, one transaction.
- **True BM25 options**: `ParadeDB` / `pg_search` (BM25 index), or Timescale/TigerData `pg_textsearch`/`pg_text` — better than `ts_rank_cd` if lexical quality matters. Native `tsvector` is "good enough" to start.
- **Multilingual gotcha**: Postgres FTS needs per-language config/stemming; Telugu/Hindi have no built-in stemmer → use `simple` config + your own normalization (and Indic tokenization), or lean on BGE-M3's **sparse** vectors instead of `tsvector` for the lexical leg.

Sources:
- https://www.paradedb.com/blog/hybrid-search-in-postgresql-the-missing-manual
- https://jkatz05.com/post/postgres/hybrid-search-postgres-pgvector/
- https://dev.to/gabrielanhaia/hybrid-search-in-100-lines-bm25-pgvector-with-rrf-merge-58cn
- https://www.tigerdata.com/docs/build/examples/hybrid-search

---

## 5. Reranking (the highest-leverage add-on)

- **What**: cross-encoder re-scores top-N (e.g. 20–50) hybrid candidates, return top-5. Biggest single quality lift after hybrid — *unless* recall is already high (then limited headroom).
- **Multilingual picks**: **BGE-reranker-v2-m3** (open, multilingual, cheap, single-GPU) — best default for Indic. **Cohere Rerank v3 / 3.5** (API, best-in-class, strong multilingual). **Jina-reranker-v3** (compact, BEIR 61.9, 2.5× fewer params, cross-lingual). **mxbai-rerank-large-v2** (1.5B, 100+ langs, 8k ctx).
- **News caveat**: cross-encoders ignore recency — apply a **time-decay / freshness boost** after reranking for breaking news.

Sources:
- https://www.analyticsvidhya.com/blog/2025/06/top-rerankers-for-rag/
- https://arxiv.org/html/2509.25085v2  (jina-reranker-v3)
- https://localaimaster.com/blog/reranking-cross-encoders-guide

---

## 6. Metadata Filtering / Self-Query / Routing

- **Pre-filter** (filter then search): exact k, one vector call, fast — preferred in pgvector via SQL `WHERE` (date range, `lang`, `source`, `entity`, `user_id`, geo). Best for selective filters.
- **Post-filter** (search then filter): may under-return k → needs over-fetch + retries; avoid for low-selectivity filters.
- **Self-query**: LLM parses NL → structured filter + semantic query ("Telugu articles about X from last week" → `lang=te AND date>=…` + vector("X")). Give few-shot examples; validate/whitelist fields to prevent injection.
- **Query routing**: classify intent → choose corpus/pillar (articles vs clips vs cuttings), language, or even skip retrieval. High value in a multi-pillar app.

Sources:
- https://dev.to/volland/pre-and-post-filtering-in-vector-search-with-metadata-and-rag-pipelines-2hji
- https://medium.com/@lorevanoudenhove/enhancing-rag-performance-with-metadata-the-power-of-self-query-retrievers-e29d4eecdb73
- https://www.langchain.com/blog/graph-based-metadata-filtering-for-improving-vector-search-in-rag-applications

---

## 7. Query Transformation (what / benefit / when)

- **Query rewriting** — clean/expand the raw query (spelling, acronyms, add context from chat history). Cheapest, near-always-positive. **Use always** for conversational/news search.
- **Multi-query** — LLM generates N paraphrases, retrieve each, union. Boosts **recall**, fixes vocabulary mismatch. +1 LLM call + N searches. Use when recall is the failure.
- **RAG-Fusion** — multi-query **+ RRF merge** of the result sets. Better ranking than raw union; same cost. Strong general default.
- **HyDE** — LLM writes a hypothetical *answer*, embed that, retrieve. Helps most **out-of-domain / sparse-query / cross-lingual** (the hypothetical doc bridges the embedding gap). **Fails on fact-bound/entity queries** (hallucinated names mislead retrieval) and adds **25–60% latency**. Use selectively; hybrid+BM25 already covers many cases HyDE targets. *For breaking news, HyDE risks fabricating facts not yet in corpus — gate it.*
- **Step-back prompting** — generate a more abstract question, retrieve broader context, then answer. Helps multi-hop / "why/how" reasoning. Adds a call.
- **Query decomposition** — split a complex question into sub-questions, retrieve each, compose. For multi-part / comparative queries. Highest cost (N retrievals + synthesis).
- **Discipline**: don't add a transform until you can **name the failure mode it fixes** and accept its latency. Rewriting + RAG-Fusion give most of the gain for least cost.

Sources:
- https://docs.llamaindex.ai/en/stable/optimizing/advanced_retrieval/query_transformations/
- https://deepwiki.com/NirDiamant/RAG_Techniques/3.1-query-transformations
- https://www.emergentmind.com/topics/hypothetical-document-embeddings-hyde
- https://arxiv.org/abs/2506.21568  (HyDE latency 25–60% on small LLMs)
- https://alexchernysh.com/blog/query-transformation-for-rag

---

## 8. What production teams actually use (GitHub / Reddit / vendor)

- **LlamaIndex / LangChain**: ship hybrid retrievers + RRF, self-query, multi-query, HyDE, step-back as first-class — confirming these as the standard toolkit.
- **Qdrant / Vespa / Weaviate**: native multi-vector (ColBERT) + sparse + RRF; Vespa is the reference for true late-interaction at scale.
- **ParadeDB / Timescale (pg_search, pg_textsearch)**: bring real BM25 into Postgres so hybrid lives entirely in pgvector.
- **Common pitfalls (r/Rag, retrospectives)**: ~**40% retrieval-failure rate** on naive (dense-only) RAG with real users; chunking + embedding choice matter most; reranking is high-leverage but has no headroom if recall is already good; over-stacking query transforms blows latency/cost for little gain; FTS multilingual stemming is a silent footgun.

Sources:
- https://docs.llamaindex.ai/en/stable/optimizing/advanced_retrieval/query_transformations/
- https://qdrant.tech/documentation/fastembed/fastembed-colbert/
- https://ailearningguides.com/rag-production-patterns-2026/
- https://www.paradedb.com/blog/hybrid-search-in-postgresql-the-missing-manual

---

## PICKS for a multilingual news RAG on pgvector

1. **Embedding: BGE-M3** (primary). Wins Telugu, near-top Hindi, 8192-ctx, and emits **dense + sparse** from one model → use its dense vec for the vector leg and its **sparse vec for the lexical leg** (sidesteps Postgres' missing Telugu/Hindi stemmers). Keep **multilingual-e5-large** as a Hindi-leaning A/B. Skip LaBSE as primary (older, dense-only).
2. **Retrieval: HYBRID = dense (BGE-M3) + lexical (BGE-M3 sparse, or ParadeDB BM25) fused with RRF, k=60.** Non-negotiable for entities/names/transliteration in news.
3. **Index: HNSW** — `m=16`, `ef_construction=200`, `hnsw.ef_search=100` (tune 100→200 for recall). Cosine. Use `halfvec` if corpus is large.
4. **Filtering: pre-filter in SQL** — `lang`, `published_at` (date-range, critical for news), `source`/`pillar`, `entity`, `user_id` — in the same query as the vector op.
5. **Rerank: BGE-reranker-v2-m3** over top-30 → top-5 (or Cohere Rerank v3.5 if API budget allows). **Then apply recency decay** for breaking news.
6. **Query transforms (in order of ROI)**: always **rewrite**; add **RAG-Fusion** (multi-query + RRF) for recall; **decomposition** for comparative/multi-part questions; **HyDE only for cross-lingual / vague queries, gated off for fact/entity and breaking-news queries** (hallucination risk). Add each only against a named failure mode.
7. **Routing**: classify query → pillar (articles/clips/cuttings) + language before retrieval; consider **ColPali** later for scanned newspaper *cuttings* (image-native retrieval).
8. **Measure**: track recall@k + NDCG on a Telugu/Hindi/English eval set; expect hybrid ≈ +26–31% NDCG over dense-only and reranking as the next big lift.
