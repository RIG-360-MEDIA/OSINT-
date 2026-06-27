# RAG / Retrieval Stack Survey for pgvector News-OSINT (June 2026)

Star counts and recency verified via GitHub REST API + shields.io badges + web
search on 2026-06-14. "pgvector-native" = works directly against an existing
Postgres+pgvector store without forcing a vector-store migration.

Constraint anchor: **285K multilingual articles, 768-dim LaBSE, HNSW index.
We reuse the existing pgvector index — no vector-store migration.**

---

## (A) End-to-end RAG frameworks / platforms

| Name | org/repo | ~Stars | Recency | Lang | License | One-line strength | Fit for news corpus |
|---|---|---|---|---|---|---|---|
| **LlamaIndex** | run-llama/llama_index | 50.1k | v0.14.22 (2026-05), pushed 06-12 | Python | MIT | Most retrieval-focused framework; richest retriever/postprocessor/query-engine toolkit | **pgvector-native** (`PGVectorStore`, `hybrid_search=True`, RRF via QueryFusionRetriever) — bolt onto existing index without migration |
| **Haystack** | deepset-ai/haystack | 25.6k | v2.30.1 (2026-06-09) | Python | Apache-2.0 | Clean, typed, production pipeline DSL; great component model | **pgvector-native** (`PgvectorDocumentStore`, keyword+embedding retrievers, RRF joiner) — composable for multilingual pipelines |
| **RAGFlow** | infiniflow/ragflow | 82.7k | v0.26.0 (2026-06-11) | Python | Apache-2.0 | Best-in-class layout-aware/deep-doc parsing + agentic RAG UI | Strong on **newspaper-clipping / PDF ingestion**; uses own engine (Infinity/ES), not your pgvector — adopt the *parser*, not the store |
| **Onyx** (ex-Danswer) | onyx-dot-app/onyx | 30.3k | v4.1.1 (2026-06-12) | Python | MIT-ish (NOASSERTION) | Turnkey enterprise RAG-chat + connectors + permissions | Per-user access control fits your RBAC; ships Vespa, not pgvector — heavier swap |
| **txtai** | neuml/txtai | 12.5k | active 2026 | Python | Apache-2.0 | Embeddings-first, lightweight, can drive Postgres/pgvector backend | Lean enough to wrap your existing index; good for fast semantic-search services |
| **R2R** | SciPhi-AI/R2R | 7.9k | v3.6.5 (2025-06), pushed 2025-11 | Python | MIT | "RAG-as-a-service" w/ built-in Postgres+pgvector + GraphRAG | **pgvector-native by default** — but momentum **slowed** (last commit Nov 2025); evaluate maintenance risk |
| **Cognita** | truefoundry/cognita | 4.4k | 2025 | Python | Apache-2.0 | Modular production RAG w/ UI + incremental indexing | pgvector supported via config; heavier platform than you need |
| **Morphik** | morphik-org/morphik-core | 3.6k | pushed 2026-05 | Python | NOASSERTION (non-OSI) | Multimodal/visual-doc RAG (ColPali-style) | Interesting for scanned newspapers; license is **not** standard OSS — check before adopting |
| **Quivr** | QuivrHQ/quivr | ~38k | active | Python | Apache-2.0 | "Opinionated RAG" lib, Supabase/pgvector heritage | pgvector-friendly but product-shaped; less a library than an app |
| **Verba** | weaviate/Verba | 7.7k | **ARCHIVED** | Python | BSD-3 | Weaviate RAG demo UI | **Discontinued + Weaviate-locked — skip** |
| **PostgresML** | postgresml/postgresml | 6.8k | pushed 2025-07 | Rust/Python | MIT | In-database ML/embeddings/RAG inside Postgres | pgvector-native by definition; in-DB inference, but slower cadence |
| **Korvus** | postgresml/korvus | 1.5k | pushed 2025-01 | Python/Rust | MIT | Single-query RAG SDK over Postgres+pgvector | **pgvector-native**; elegant but **low activity** — adoption risk |

## (B) Knowledge-graph RAG

| Name | org/repo | ~Stars | Recency | Lang | License | One-line strength | Fit |
|---|---|---|---|---|---|---|---|
| **Microsoft GraphRAG** | microsoft/graphrag | 34k | pushed May 2026 | Python | MIT | Reference global/local community-summary GraphRAG | Powerful for cross-document "who/what/where" over news; **costly indexing**, own parquet store (not pgvector) |
| **LightRAG** | HKUDS/LightRAG | 37k | active **today** | Python | MIT | Fast, cheap dual-level graph+vector retrieval | Best graph-RAG value; **can use pgvector + Postgres (AGE) as backend** — fits your DB |
| **Cognee** | topoteretes/cognee | 18k | active (last wk) | Python | Apache-2.0 | Modular "memory engine", graph+vector, multi-store | Flexible entity-memory layer; supports pgvector among stores |
| **nano-graphrag** | gusye1234/nano-graphrag | 3.9k | Jan 2026 | Python | MIT | ~1.1k-LOC hackable GraphRAG core | Great to *learn/port*; slower upstream |
| **fast-graphrag** | circlemind-ai/fast-graphrag | 3.8k | Nov 2025 | Python | MIT | PageRank-guided, deterministic, cheaper graph RAG | Good entity-centric retrieval; check maintenance |
| **neo4j-graphrag** | neo4j/neo4j-graphrag-python | 1.2k | June 2026 | Python | Apache-2.0 | Official Neo4j GraphRAG SDK | Only if you stand up Neo4j; not pgvector |
| **itext2kg** | AuvaLab/itext2kg | 949 | April 2026 | Python | Apache-2.0 | Incremental LLM text→KG construction | Useful to build the entity-relation graph from articles |

## (C) Retrieval quality (rerank / hybrid / query-rewrite / late-interaction)

| Name | org/repo | ~Stars | Recency | Lang | License | One-line strength | Fit |
|---|---|---|---|---|---|---|---|
| **FlagEmbedding (BGE)** | FlagOpen/FlagEmbedding | 12k | April 2026 | Python | MIT | Home of **bge-reranker-v2-m3** (multilingual, <600M) | **Top reranker pick** for multilingual news; runs on modest GPU/CPU |
| **rerankers** | AnswerDotAI/rerankers | 1.6k | Dec 2025 | Python | Apache-2.0 | One unified API over BGE/Jina/Cohere/ColBERT/cross-enc | Swap rerankers w/o code churn; ideal abstraction layer |
| **ParadeDB / pg_search** | paradedb/paradedb | 8.9k | active (last wk) | Rust | AGPL-3.0 | True **BM25 inside Postgres** (`@@@`), V2 API | **The hybrid key**: BM25 + pgvector + RRF in one DB — no Elastic. (AGPL — check licensing posture) |
| **ColBERT** | stanford-futuredata/ColBERT | 3.9k | Oct 2025 | Python | MIT | Reference late-interaction (PLAID) retriever | Strong recall; index is separate from pgvector — adds infra |
| **RAGatouille** | AnswerDotAI/RAGatouille | 3.9k | May 2025 | Python | Apache-2.0 | Easy ColBERT training/inference wrapper | If you want late-interaction without low-level ColBERT |
| **ColPali** | illuin-tech/colpali | 2.7k | active (last wk) | Python | MIT | Vision late-interaction over **document images** | Best-fit for **newspaper-page images** (skip OCR); needs multi-vector store |
| **Jina Reranker v2/v3** | (HF model + API) | — | 2026 | — | model-license | Multilingual cross-encoder, 8k-ctx, fast | Strong alt/complement to bge-m3; API or self-host |
| **Tiger pg_textsearch** | tigerdata | — | late-2025 | Rust | — | Okapi-BM25 in Postgres (TimescaleDB-friendly) | ParadeDB alternative if you're in Timescale |

## (D) RAG evaluation

| Name | org/repo | ~Stars | Recency | Lang | License | One-line strength | Fit |
|---|---|---|---|---|---|---|---|
| **promptfoo** | promptfoo/promptfoo | 22k | active (yest.) | TS | MIT | Prompt/RAG regression + **red-teaming** in CI | Quality gates + adversarial tests for an OSINT product |
| **DeepEval** | confident-ai/deepeval | 16k | active (yest.) | Python | Apache-2.0 | Broadest metric library, strongest **CI/CD** | pytest-style faithfulness/context-recall gates |
| **Ragas** | explodinggradients/ragas | 14k | Feb 2026 | Python | Apache-2.0 | Reference-free, RAG-specific core metrics | Fastest way to measure retrieval+answer quality |
| **Arize Phoenix** | Arize-ai/phoenix | 10k | active (last wk) | Python | Elastic-2.0 | OTel-based **tracing/observability** at span level | Production monitoring of the live RAG pipeline |
| **TruLens** | truera/trulens | 3.4k | June 2026 | Python | MIT | RAG-triad metrics + OTel tracing | Diagnose pipeline failures span-by-span |

---

## PICKS — the stack I'd assemble on top of pgvector for multilingual news

**Keep pgvector + HNSW as the single source of truth. Add layers around it, do not migrate.**

1. **Hybrid retrieval, all in Postgres** — add **ParadeDB `pg_search`** for real
   BM25 (`@@@`) alongside your existing pgvector HNSW, and fuse with
   **Reciprocal Rank Fusion (k=60)** in a single SQL/CTE. This kills the classic
   weakness of pure-dense retrieval on news: named entities, transliterations,
   rare proper nouns, dates/numbers. (If AGPL is a blocker, fall back to native
   `tsvector` + ts_rank or Tiger `pg_textsearch`.) LaBSE handles cross-lingual
   semantics; BM25 handles exact-token recall — the combination is the whole game
   for OSINT.

2. **Reranker = bge-reranker-v2-m3** (FlagEmbedding), driven through the
   **AnswerDotAI `rerankers`** unified API so you can A/B Jina-v3/Cohere later
   without code churn. bge-m3 is multilingual, <600M, CPU-tolerable, and tops
   the price/quality curve for 100+ languages — exactly your corpus. Retrieve
   top-50 hybrid → rerank to top-8.

3. **Query transformation** — implement **multi-query + RAG-Fusion** (and
   **HyDE** for sparse/foreign-language queries) using **LlamaIndex**
   `QueryFusionRetriever`. LlamaIndex is the orchestration layer because its
   `PGVectorStore` is **pgvector-native** (hybrid mode + RRF built in) and its
   retriever/postprocessor abstractions let you slot the reranker as a
   node-postprocessor cleanly. (Haystack is the equally-valid alternative if you
   prefer a typed pipeline DSL.)

4. **Optional graph layer = LightRAG** over your **44K-entity dictionary +
   story clusters**, backed by **Postgres (pgvector + Apache AGE)** so it stays
   in your DB. It adds multi-hop "how is X connected to Y across these events"
   answers without the heavy/costly indexing of Microsoft GraphRAG. Use
   **itext2kg** to seed/incrementally build the entity-relation graph from
   articles. Reserve Microsoft GraphRAG for offline, high-value cross-corpus
   investigative briefs only.

5. **Document-image track (newspapers)** — for scanned editions where OCR is
   lossy, pilot **ColPali** (late-interaction over page images). Keep it on a
   side multi-vector index; do not force it into the pgvector single-vector
   index.

6. **Evaluation harness** — **Ragas** for RAG-specific scores (faithfulness,
   context-precision/recall, answer-relevancy) + **DeepEval** as pytest-style
   CI quality gates + **promptfoo** for regression & red-team (critical for an
   OSINT product that must resist prompt-injection from ingested content) +
   **Arize Phoenix** for OTel tracing in production.

**One-line rationale:** dense (LaBSE/pgvector) gives cross-lingual recall, BM25
(pg_search) restores exact-entity precision, RRF fuses them in-database,
bge-m3 reranks for multilingual ordering, LlamaIndex rewrites/orchestrates, and
LightRAG adds an in-Postgres graph hop — all without leaving your existing
pgvector HNSW index.

**Avoid / caution:** Verba (archived), Korvus & R2R (pgvector-native but
slowing cadence — maintenance risk), Morphik (non-OSI license), and any pick
that mandates Vespa/Weaviate/Elastic (Onyx, RAGFlow store, Verba) since that
violates the no-migration constraint — adopt their *parsers/ideas*, not stores.
