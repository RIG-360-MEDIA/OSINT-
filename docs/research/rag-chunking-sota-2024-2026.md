# RAG Chunking & Document Processing — State of the Art (2024–2026)

Scope: chunking + document processing for a **multilingual (EN/Telugu/Hindi) news RAG**.
All headline numbers are from primary sources (verified, cited inline). Practitioner
consensus is flagged as such (blogs/benchmarks, not peer-reviewed).

---

## 1. Baseline chunking strategies

| Technique | What it is / who uses it | When to use | Recommended params |
|---|---|---|---|
| **Fixed-size (token)** | Split every N tokens, ignore structure. Simplest. | Throwaway prototypes only — "convenient but destructive", splits sentences mid-thought. | Avoid for prod; if used, 256–512 tok + 10–15% overlap. |
| **Recursive character splitting** | Split on a hierarchy of separators (`\n\n`→`\n`→`. `→` `). LangChain `RecursiveCharacterTextSplitter` **default**; used by ~everyone as baseline. | Default for 80% of RAG. Best accuracy/cost ratio in independent benchmarks (Vecta Feb-2026: recursive 512-tok = **69%** end-to-end, #1 of 7 strategies). | **512 tokens, 50 overlap** is the canonical starting point. |
| **Sentence / semantic chunking** | Embed sentences, cut at embedding-distance breakpoints (LlamaIndex `SemanticSplitterNodeParser`, LangChain `SemanticChunker`). | Only if retrieval precision is the proven bottleneck **and** you have no reranker yet. | Breakpoint percentile 90–95. |
| **Sliding-window overlap** | Carry K tokens/sentences across adjacent chunks so boundary facts survive. | Always layer on top of recursive/fixed. | 10–20% of chunk size (e.g. 50–100 tok on a 512 chunk). |
| **Structure-aware (Markdown/HTML/table/code)** | Split on document structure (headers, `<table>`, code blocks) before size-splitting. `MarkdownHeaderTextSplitter`, Unstructured `by_title`, LlamaIndex `MarkdownNodeParser`. | Whenever source has real structure (HTML news, govt PDFs, tables). Keep tables atomic; never split a row. | Header-split first, then recursive within sections. |

**Verified consensus (the surprising one):** semantic chunking is **not** worth it for most teams. Vecta's benchmark put semantic chunking at **54–58%** vs recursive's **69%**, because it produced fragments averaging ~43 tokens that "retrieved well but lacked enough context for the LLM to answer." Multiple practitioner guides agree the marginal gain shrinks to ~zero once you already run **hybrid search + a reranker**. Chunk-boundary tuning is rarely the binding constraint — data quality usually is.

---

## 2. Advanced techniques (with measured numbers)

### Anthropic Contextual Retrieval — the strongest single win
Prepend a 50–100-token LLM-generated blurb situating each chunk in its parent doc, **before** embedding + before building the BM25 index. Measured on codebases, fiction, ArXiv, Science papers; metric = 1−recall@20, top-20 chunks, Gemini-text-004 embeddings:

- Contextual Embeddings alone: **−35%** failed retrievals (5.7% → 3.7%)
- \+ Contextual BM25: **−49%** (5.7% → 2.9%)
- \+ reranking (Cohere): **−67%** (5.7% → 1.9%)

Cost is made viable by **prompt caching**: load the doc into cache once, generate context per chunk against the cached doc. At 800-tok chunks / 8k-tok docs / 50-tok instruction / 100-tok context, one-time cost ≈ **$1.02 per million doc tokens**. Anthropic's own guidance: use top-20 (beats 5/10), Gemini & Voyage embeddings benefited most, **always eval**. (Source: Anthropic, Sep 19 2024 + Claude cookbook.)

### Late Chunking (Jina) — cheap, no LLM
Run the **whole document** through a long-context embedding model first, get per-token embeddings, *then* split and mean-pool per chunk. Each chunk embedding is conditioned on full-doc context (pronouns/"the city"→"Berlin" resolve). One forward pass, **no LLM, no per-chunk storage blowup**. BEIR (nDCG@10): **+1.8–3.6% relative** over naive chunking — modest on average but **grows with document length**, and fixed-size+late-chunking beats naive+semantic-boundaries. Requires a long-context embedder (jina-v2/v3, 8192 tok). (Source: Jina, arXiv 2409.04701.)

> **Late chunking vs Contextual Retrieval (practitioner take):** Contextual Retrieval wins on coherence but adds LLM token cost, latency, slower/harder-to-parallelize indexing, and cache/prompt ops overhead. Late chunking is one model pass, far cheaper, but a smaller lift. They are **complementary**, not exclusive.

### Parent-document / small-to-big retriever
Embed & retrieve **small** child chunks for precision; return the **parent** (section/full doc) to the LLM for context. LangChain `ParentDocumentRetriever`, LlamaIndex `AutoMergingRetriever`. The pragmatic, low-complexity workhorse. Child **50–200 tokens**, parent = section or full article.

### Sentence-window retrieval
Embed single sentences; at retrieval, return ±K surrounding sentences. LlamaIndex `SentenceWindowNodeParser`, **default window = 3** (docs/tutorials often show 3–5 each side). Great when answers are localized to a sentence. A special case of small-to-big.

### Hierarchical / RAPTOR
Recursively cluster → LLM-summarize → re-embed, building a tree (leaf chunks + multi-level summaries); retrieve across levels. Best for **whole-corpus / thematic / "what's the big picture"** questions. Significant gains on NarrativeQA/QASPER/QuALITY across UnifiedQA/GPT-3/GPT-4. Supported in RAGFlow. Expensive to build/maintain; overkill for single short articles. (Source: RAPTOR ICLR 2024.)

### Proposition-based ("Dense X") chunking
LLM rewrites text into atomic, self-contained factoids; embed those. Highest Recall@5 / EM vs sentence & passage units across 5 open-domain QA sets. LlamaIndex `DenseXRetrievalPack`. **Costly to generate** → only for small/medium high-value corpora, not a firehose news feed.

---

## 3. Chunk size, overlap & embedding limits

- **Tradeoff:** small chunks = precise retrieval, fragmented context; large = rich context, diluted/noisy similarity. Pick by query type, then verify with an eval set — do not guess.
- **Rules of thumb:** start **512 tok / 50 overlap** (recursive). Precision-first: 100–200 tok children. Context-first: 500–1000 tok. Overlap 10–20%.
- **Hard ceiling = your embedding model's max sequence length.** Chunks longer than this are silently truncated. Multilingual options:
  - **LaBSE: 256 tokens** (very tight — current RIG `labse_embedding` recipe). Forces small chunks; a long news article *must* be split.
  - **multilingual-e5: 512 tokens.**
  - **BGE-M3: 8192 tokens** + native dense+sparse+ColBERT multi-vector — strong EN/HI/TE coverage and the only one of these that enables late chunking / whole-article embedding.

---

## 4. Metadata enrichment per chunk (why it matters)
Attach `title, publish_date, source/outlet, url, language, section, entities, geo` to every chunk. Enables **metadata pre-filtering** (date windows, source/lang scoping) which cuts the candidate set before vector search → big precision + latency win, and lets the LLM cite/attribute. For news, **recency filtering is essential** (dedup near-identical wire copy, prefer fresh). Prepending `title + date + source` into the embedded text is a cheap, poor-man's contextual retrieval that measurably helps short docs.

---

## 5. NEWS-specific: chunk or not?
- **Short articles (≤ model token limit): embed whole.** Splitting a 200–400-word brief only fragments context and dilutes the title signal. Whole-doc embedding is preferred when it fits.
- **Long features / explainers / govt PDFs: chunk** (recursive + structure-aware), or use parent-document so children are precise but the article is returned whole.
- **Title is the strongest signal in news.** Always include it in the embedded text (prepend to body, or dual-embed title + body and combine). Headlines are dense, entity-rich summaries.
- **Cross-lingual (EN/HI/TE):** correctness depends far more on a **strong multilingual embedder** (BGE-M3 / mE5) than on the splitter. Chunk on language-aware sentence boundaries (Indic scripts use Danda `।`, not just `.`). Hybrid dense+BM25/FTS is especially valuable since BM25 rescues exact names/transliterations the dense model fuzzes.

---

## PICKS for a multilingual (EN/Telugu/Hindi) news RAG

1. **Don't chunk short articles — embed whole.** Chunk only long features/PDFs, via **recursive + structure-aware (HTML/Markdown headers), 512 tok / 50 overlap**, or **parent-document** (small children → return full article).
2. **Always prepend `title + date + source` to the embedded text**, and store them as filterable metadata (+ entities, geo, language). Date filtering is non-negotiable for news.
3. **Embedding model is the real lever.** LaBSE's 256-tok cap is the current constraint — it *forces* fragmentation of long pieces. Strongly consider **BGE-M3** (8192 tok, native dense+sparse, good HI/TE) — it unlocks whole-article embedding **and** late chunking.
4. **Hybrid retrieval + reranker first.** Dense + BM25/FTS + a multilingual reranker (e.g. bge-reranker-v2-m3 / Cohere multilingual) is the highest ROI, and it shrinks any need for fancy chunking. (Matches RIG's existing v4+FTS+RRF direction.)
5. **Add Contextual Retrieval selectively** to long/ambiguous docs (govt PDFs, multi-topic features) — biggest measured win (−49% to −67% failed retrievals) but LLM-cost + ops overhead; gate it behind an eval and prompt-caching.
6. **Late chunking** is the cheaper alternative to #5 once on a long-context embedder (BGE-M3/Jina) — one pass, no LLM. Use it as the default contextualizer; reserve LLM Contextual Retrieval for the hardest docs.
7. **Skip pure semantic chunking, RAPTOR, and proposition chunking for the live feed** — cost/complexity unjustified at news volume. RAPTOR *could* power a separate "thematic/Chronicle big-picture" index over a curated subset.
8. **Eval everything on a held-out EN/HI/TE query set** (recall@k + answer faithfulness). Every credible source repeats: there is no universal best — measure on your corpus.

---

## SOURCES

**Primary (numbers verified against source text):**
- Anthropic — Introducing Contextual Retrieval (Sep 19 2024): https://www.anthropic.com/news/contextual-retrieval
- Anthropic Claude Cookbook — contextual embeddings guide: https://platform.claude.com/cookbook/capabilities-contextual-embeddings-guide
- Jina AI — Late Chunking in Long-Context Embedding Models: https://jina.ai/news/late-chunking-in-long-context-embedding-models/
- Jina — What Late Chunking Really Is (Part II): https://jina.ai/news/what-late-chunking-really-is-and-what-its-not-part-ii/
- Late Chunking paper, arXiv 2409.04701: https://arxiv.org/abs/2409.04701
- RAPTOR (ICLR 2024): https://openreview.net/forum?id=GN921JHCRw — code: https://github.com/parthsarthi03/raptor
- Dense X Retrieval (propositions): https://clusteredbytes.pages.dev/posts/2024/llamaindex-dense-x-retrieval/
- BGE-M3 paper, arXiv 2402.03216: https://arxiv.org/html/2402.03216v3
- Multilingual E5 report, arXiv 2402.05672: https://arxiv.org/pdf/2402.05672

**Frameworks / docs:**
- LlamaIndex small-to-big & sentence-window (Sophia Yang): https://medium.com/data-science/advanced-rag-01-small-to-big-retrieval-172181b396d4
- RAGFlow — Enable RAPTOR: https://ragflow.io/docs/enable_raptor
- Unstructured — chunking for RAG best practices: https://unstructured.io/blog/chunking-for-rag-best-practices
- Unstructured — contextual chunking: https://unstructured.io/blog/contextual-chunking-in-unstructured-platform-boost-your-rag-retrieval-accuracy

**Benchmarks / practitioner consensus:**
- Firecrawl — Best Chunking Strategies for RAG (2026): https://www.firecrawl.dev/blog/best-chunking-strategies-rag
- Vecta 7-strategy benchmark (via langcopilot): https://langcopilot.com/posts/2025-10-11-document-chunking-for-rag-practical-guide
- Late Chunking vs Contextual Retrieval, the math (KX/Michael Ryaboy): https://medium.com/kx-systems/late-chunking-vs-contextual-retrieval-the-math-behind-rags-context-problem-d5a26b9bbd38
- Weaviate — Late Chunking: https://weaviate.io/blog/late-chunking
- Milvus — Late chunking with Jina + Milvus: https://milvus.io/blog/smarter-retrieval-for-rag-late-chunking-with-jina-embeddings-v2-and-milvus.md
- Towards AI — Production RAG strategies that actually work: https://towardsai.net/p/machine-learning/production-rag-the-chunking-retrieval-and-evaluation-strategies-that-actually-work
- DataCamp — Contextual Retrieval guide: https://www.datacamp.com/tutorial/contextual-retrieval-anthropic
- AWS — Contextual retrieval in Bedrock Knowledge Bases: https://aws.amazon.com/blogs/machine-learning/contextual-retrieval-in-anthropic-using-amazon-bedrock-knowledge-bases/
