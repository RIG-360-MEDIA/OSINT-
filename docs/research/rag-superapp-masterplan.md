# RIG Intelligence — Agentic RAG Super-App Master Plan

> Founder + product-designer deep dive: how to turn the RIG Surveillance corpus
> (285K multilingual articles + structured extractions + entity graph + clips +
> clippings + story clusters) into a **per-user, internet-connected, agentic
> intelligence product** that does things no general LLM can.
>
> Companion research files (read alongside):
> - [`rag-stack-survey-2026.md`](./rag-stack-survey-2026.md) — retrieval / RAG / GraphRAG / eval survey
> - [`market-monetization-research.md`](./market-monetization-research.md) — what people pay for, pricing ladder
>
> Date: 2026-06-14. All repo stars/licenses verified live by research agents on this date.

---

## 0. The one-sentence thesis

A general LLM (ChatGPT, Perplexity) searches the *open web* and forgets you.
We search a **curated, multilingual (EN/HI/TE), structurally-extracted Indian
news+OSINT corpus that exists nowhere else**, *fuse* it with the live web, and
*remember each user* — so we can answer "**who said what, first, in which
language, framed how, and is it heating up?**" That question is unanswerable by
any product on the market. That is the moat. Everything below serves it.

> **It is "more than a RAG"** because RAG = retrieve-then-generate. We add four
> layers a RAG doesn't have: (1) **live web fusion**, (2) **per-user memory &
> agents**, (3) **structured intelligence** (stances/claims/quotes/numbers/entities
> as queryable facts, not just text), and (4) **cross-lingual event stitching**.

---

## 1. What we are actually sitting on (the unfair advantages)

Grounded in the documented schema (live row-level verification pending a
read-only tunnel + `mc_readonly` role — see §9). These are the assets that make
the moat features in §3 / Category 2 *possible*:

| Asset | Why it's a weapon |
|---|---|
| `articles.labse_embedding_v4` (768-d, HNSW) | **Cross-lingual** semantic search — a query in English retrieves Hindi/Telugu articles. No re-embed needed; the index is built. |
| `article_stances` / `article_claims` / `article_quotes` / `article_numbers` | Structured **facts**, not prose. Enables who-said-what, figure-discrepancy, stance-trend — queries impossible over raw text. |
| `entity_dictionary` (~44K, party/state/country, aliases) + `article_entity_mentions` | A **resolved entity graph** that unifies `मोदी`/`మోదీ`/`Modi`. General LLMs have no such cross-script resolver for Indian politics. |
| `analytics.story_clusters` / `story_cluster_members` | Events already grouped → **dedup**, timelines, cross-source/cross-language stitching for free. |
| `clippings` (~3.5K newspaper cuttings, text layer) | **Off-web** primary-source intelligence — physical editions that don't exist on the open internet. |
| `youtube_clips_v2` (~1.2K, transcript + entities) | A **third modality** of the same events, fusible by embedding. |
| Per-user **relevance v3** (canon / geo-wb / recency / mute) | A ranking signal tuned to *this user*, over a *private* corpus — not generic web PageRank. |
| Multilingual `_translated` columns | Read any regional story in English instantly; zero translation latency at query time. |

**The product reframing:** we are not "an LLM with our data." We are a
**multilingual, structurally-indexed, time-aware intelligence layer** with an
LLM as the conversational surface. The LLM is the cheapest, most replaceable
part. The corpus + extractions + entity graph is the defensible part.

---

## 2. The 20+ open-source repos to build on (verified June 2026)

Picked for our exact constraints: **Python/Celery/FastAPI stack, reuse the
existing pgvector HNSW index (no vector-store migration), self-hostable, cheap,
MIT/Apache preferred.** AGPL components are fine *only* as network services
behind our API boundary.

### Agent / orchestration / memory
| # | Repo | Stars | Lic | Use it for |
|---|---|---|---|---|
| 1 | `langchain-ai/langgraph` | 34.7k | MIT | **Primary agent runtime** — durable per-user threads, checkpointing, human-in-loop |
| 2 | `pydantic/pydantic-ai` | 17.7k | MIT | Type-safe, **citation-guaranteed** structured outputs (OSINT faithfulness) |
| 3 | `run-llama/llama_index` | 50.1k | MIT | RAG glue: query-rewrite (multi-query/HyDE/RAG-Fusion), `PGVectorStore` |
| 4 | `mem0ai/mem0` | 58.5k | Apache | Per-user prefs / read-state / mute (lightweight memory) |
| 5 | `getzep/graphiti` | 27.4k | Apache | **Temporal** entity memory — bi-temporal KG for facts that change/retract |
| 6 | `agno-agi/agno` | 40.7k | Apache | Fallback batteries-included option (agents+sessions) if we want one framework |
| 7 | `stanfordnlp/dspy` | 35k | MIT | *Optimize* retrieval/answer prompts (not the runtime) |

### Retrieval quality (all sit ON TOP of our pgvector — no migration)
| # | Repo / tool | Lic | Use it for |
|---|---|---|---|
| 8 | `paradedb/paradedb` (`pg_search`) | AGPL | **BM25 inside Postgres** → entity/transliteration recall, fuse w/ pgvector via RRF |
| 9 | `AnswerDotAI/rerankers` + `bge-reranker-v2-m3` | MIT/Apache | Cross-encoder rerank of top-k (multilingual) |
| 10 | `HKUNLP`/ColPali + `RAGatouille` | Apache | Late-interaction side-index for **scanned newspaper** clippings |
| 11 | `HKUDS/LightRAG` | MIT | Optional **graph hop** over the 44K entity dict (Postgres+AGE backend) |

### Live web / deep research
| # | Repo | Stars | Lic | Use it for |
|---|---|---|---|---|
| 12 | `searxng/searxng` | 32k | AGPL | **Free meta-search backbone** (already running as `rig-searxng`) |
| 13 | `unclecode/crawl4ai` | 68.4k | Apache | Default async crawler (free, no per-page cost) |
| 14 | `adbar/trafilatura` | 6.1k | Apache | Cheapest/best news-body extraction (likely already in stack) |
| 15 | `firecrawl/firecrawl` | 132k | AGPL | JS-rendered / hard pages — pay-per-page fallback only |
| 16 | `assafelovic/gpt-researcher` | 27.7k | Apache | **Deep-research loop** → cited reports (matches "must cite") |
| 17 | `langchain-ai/open_deep_research` | 11.7k | MIT | LangGraph-native DR alternative (stack consistency) |
| 18 | `microsoft/playwright-mcp` | 33.9k | Apache | Paywall/login-gated sources as a cheap MCP tool |
| 19 | `jina-ai/reader` (r.jina.ai) | 11.2k | Apache | One-call URL→clean-markdown for live links |

### Answer UI + eval
| # | Repo | Stars | Lic | Use it for |
|---|---|---|---|---|
| 20 | `miurla/morphic` | 8.9k | Apache | **Fork as the answer surface** (generative UI + citations, Next.js) |
| 21 | `ItzCrazyKns/Perplexica` | 35.3k | MIT | Reference / alt answer-engine over SearXNG |
| 22 | `explodinggradients/ragas` | — | Apache | Faithfulness / answer-relevance eval |
| 23 | `confident-ai/deepeval` | — | Apache | Unit-test RAG, red-team guardrails |
| 24 | `Arize-ai/phoenix` | — | Elastic2 | Tracing/observability of agent runs |
| 25 | `microsoft/markitdown` + `docling-project/docling` | MIT | Normalize uploaded PDFs/docs → corpus format (private-corpus tier) |

**Cautions flagged by research:** AutoGen → maintenance mode (avoid); Zep OSS
deprecated (use Graphiti); Verba archived; Morphik non-OSI license; Onyx/RAGFlow
*mandate* Vespa/Weaviate stores (adopt their parsers, not their stores —
violates no-migration). Keep AGPL pieces (SearXNG, Firecrawl, pg_search) as
self-hosted services behind the API, never linked into shipped code.

---

## 3. The 70 features — 7 categories × 10

### Category 1 — Logical / easy wins (ship in weeks, leverage what exists)
1. **Semantic "find similar stories"** — cosine on `labse_embedding_v4` via the existing HNSW index. Near-zero build.
2. **NL search with cited answers** — RAG over the corpus, every sentence linked to an `article.id`.
3. **Entity feed** — everything about a person/party/place via `entity_lookup` + `article_entity_mentions`.
4. **Topic & geo dashboards** — aggregations over `topic_category` / `geo_primary` / `published_at`.
5. **Saved searches → alerts** — reuse relevance v3 scoring as the match function.
6. **Agentic daily brief** — extend the existing `/brief` pillar with an LLM summarizer + citations.
7. **Cross-lingual answer** — query EN, retrieve HI/TE via cross-lingual embeddings, answer EN from `_translated`.
8. **Stance / sentiment trend charts** — time series from `article_stances` per entity.
9. **Quote finder** — full-text over `article_quotes` ("what did X actually say about Y?").
10. **Numbers feed** — track figures/stats from `article_numbers` (budgets, casualties, prices).

### Category 2 — Only OUR system can do (the moat — no other product can)
1. **Cross-language story stitching** — the *same event* across EN/HI/TE newspapers + web + YouTube, unified by embeddings + `story_clusters`. **Nobody does EN/HI/TE.**
2. **Cross-language framing contrast** — how Telugu vs Hindi vs English press frame the *same* story differently (`article_stances` grouped by `language_detected` within a cluster). The killer feature.
3. **Cross-pillar event view** — one event fused across `articles` + `clippings` + `youtube_clips_v2` (we hold all three, all embedded).
4. **Who-said-it-first** — `article_quotes`/`article_claims` × `published_at` → first-attribution timeline for any claim.
5. **Cross-script entity resolution** — `entity_dictionary` aliases unify `मोदी`/`మోదీ`/`Modi`; no general LLM has this Indian-politics resolver.
6. **Figure-discrepancy detector** — same metric, different numbers across sources (`article_numbers`) → "Source A: 500 dead, Source B: 50."
7. **Newspaper-cutting OSINT** — searchable text layer over physical editions (`clippings`) that aren't on the open web.
8. **Per-user relevance over a private curated corpus** — relevance v3 (canon/geo-wb/recency/mute), not generic web ranking.
9. **Stance-shift detection** — an actor's position changing over time, from the `article_stances` timeline.
10. **District/state-level intelligence** — regional Indian politics at a granularity no global product covers.

### Category 3 — User pain points (solve real, felt frustrations)
1. **Trustworthy citations** — answers grounded *only* in the curated corpus (kills Perplexity's spam-citation problem).
2. **Article-level bias/framing** — per-story, not just outlet-level like Ground News.
3. **"What's actually new"** — collapse 20 versions of one story into one via `story_clusters` (ends repetition fatigue).
4. **Blindspot alerts** — stories your usual sources *aren't* covering.
5. **"Catch me up"** — what happened on topic X since I last looked (read-state diff).
6. **Notification-fatigue control** — per-user mute lists (already in relevance v3).
7. **Reading-budget brief** — "5 minutes" vs "deep dive" length control.
8. **Verify-this** — paste a claim → corpus corroboration vs contradiction.
9. **Zero translation friction** — read any regional story in your language instantly (`_translated`).
10. **Source transparency** — every claim shows source + date + original language, one click to the original.

### Category 4 — Creative / never-thought-of
1. **Story "time machine"** — replay a story's hour-by-hour evolution as a scrollable narrative (`story_timeline`).
2. **Counter-narrative pairs** — auto-surface the strongest opposing framing (we already run dissent/counter-narrative tasks).
3. **Live multilingual audio brief** — NotebookLM-style, but over a *live* EN/HI/TE feed. Audio is proven payable; nobody does it live + multilingual.
4. **Debate mode** — two agents argue both sides, each citing corpus evidence.
5. **Entity relationship explorer** — co-mention graph (`article_entity_mentions`) as visual OSINT ("who's connected to whom").
6. **"This is heating up"** — story-cluster growth velocity → early-trend detection (Dataminr-lite).
7. **Framing fingerprint** — show users their own consumption bias and nudge balance.
8. **Ask-the-archive** — RAG over years of newspaper clippings absent from the open web.
9. **Quote-watch** — "ping me whenever [politician] says anything about [topic]."
10. **"What are THEY saying"** — surface coverage in a language/region the user doesn't read.

### Category 5 — Borrow from others (port proven OSS, don't reinvent)
1. **Perplexity-style answer UI** ← fork `morphic` / `Perplexica`.
2. **Deep-research loop** ← `gpt-researcher` (plan→search→synthesize, cited).
3. **Per-user memory** ← `mem0` (prefs) + `graphiti` (temporal entities).
4. **Agent orchestration** ← `langgraph` (durable per-user threads).
5. **Hybrid retrieval** ← ParadeDB `pg_search` BM25 + RRF over pgvector.
6. **Reranking** ← `bge-reranker-v2-m3` via `rerankers`.
7. **Live web** ← `searxng` (running) + `crawl4ai` + `trafilatura`.
8. **Query rewriting** ← LlamaIndex multi-query / HyDE / RAG-Fusion.
9. **Graph hop** ← `LightRAG` over the entity dictionary (in-Postgres AGE).
10. **Eval/guardrails** ← `ragas` + `deepeval` + `promptfoo` + `phoenix`.

### Category 6 — Features people WILL pay for (our monetization)
1. **Real-time first-alert** on entities/topics (Dataminr proved $40k+ demand).
2. **Saved entity/topic monitors + push** (Feedly TI model).
3. **Metered deep-research credits** (Hebbia/Elicit model — protects LLM margin).
4. **Premium archive access** — the newspaper-clippings back-catalog.
5. **Team/desk shared workspaces** — collaborative OSINT (AlphaSense model).
6. **Data API** — stances/claims/entities/numbers as a structured feed.
7. **Scheduled + audio briefs** (NotebookLM proved audio is payable).
8. **Bias/blindspot pro analytics** (Ground News proved consumers pay ~$30/yr).
9. **Cited report export** — analyst-grade PDF briefs.
10. **Private-corpus add-on** — upload your docs, RAG over them *plus* the news corpus.

### Category 7 — Features people DO pay for today (validated demand, ranked)
1. **Cited synthesis over a *trusted* corpus** — Perplexity Pro, $20/mo.
2. **Search over a premium/private corpus you can't read manually** — AlphaSense / Hebbia, $10k+/seat.
3. **Real-time event detection / first-alert** — Dataminr / Recorded Future, $40k–500k/yr.
4. **AI feeds + entity monitoring + alerts** — Feedly TI, $1.6–3.2k/mo.
5. **Bias / blindspot / news comparison** — Ground News, ~$30/yr (consumer-scale).
6. **Audio overview / brief** — NotebookLM (massive adoption driver).
7. **Cited research-report generation** — Elicit / Consensus subscriptions.
8. **Enterprise connector search across sources** — Glean.
9. **Real-time news terminal + analytics** — Bloomberg / Factiva, $2.6k+/yr.
10. **Semantic "find similar / discovery"** — Exa; AlphaSense "smart synonyms."

> **Strategic read (from market research):** consumer news WTP in India is low
> (~17–18% globally, lower locally) — keep the **consumer tier free** as a funnel,
> and **monetize prosumers/B2B who expense tools** (journalists, analysts, PR/comms,
> political research, govt/NGO). Artifact's death lesson: personalized consumer
> news *alone* is a feature, not a company. Sell **"know first + know fairly + in
> every language"** to people *paid to know*.

---

## 4. Target architecture (reuse, don't rebuild)

```
                    ┌──────────────────────────────────────────┐
   USER  ──────────▶│  Answer surface (fork of morphic / Vite   │
                    │  night-desk) — streaming, citations, audio │
                    └───────────────┬──────────────────────────┘
                                    │
                       ┌────────────▼─────────────┐
                       │  AGENT RUNTIME (LangGraph) │  ← per-user durable threads
                       │  + Pydantic AI (typed,     │     (checkpointed)
                       │    citation-guaranteed)    │
                       └───┬───────┬───────┬───────┘
            tools:         │       │       │
   ┌────────────────┐  ┌───▼───┐ ┌─▼──────┐ ┌▼───────────────┐
   │ corpus_search  │  │ web   │ │ deep_  │ │ entity / stance │
   │ (hybrid+rerank)│  │ search│ │research│ │ /quote /numbers │
   └───────┬────────┘  └──┬────┘ └──┬─────┘ └───────┬────────┘
           │              │         │               │
   ┌───────▼──────────────▼─────────▼───────────────▼────────┐
   │ RETRIEVAL: pgvector HNSW (semantic)  +  pg_search BM25   │  READ-ONLY
   │ (lexical) → RRF(k=60) → bge-reranker-v2-m3 → top-k       │  corpus DB
   │ LIVE WEB: SearXNG → crawl4ai/trafilatura → Tavily/Exa fb │  (untouchable)
   └─────────────────────────────────────────────────────────┘
           │ writes go to a SEPARATE store ↓
   ┌─────────────────────────────────────────────────────────┐
   │ APP DB (new, writable): users, chat threads, saved       │
   │ monitors, read-state, Mem0 prefs, Graphiti temporal KG   │
   └─────────────────────────────────────────────────────────┘
   Models: Groq qwen3-32b (cheap path) → Claude Sonnet/Opus (premium synthesis)
   Eval: Ragas + DeepEval faithfulness + cite-ID guardrail before any answer ships
```

**Non-negotiable architectural rules (from the hard rules + repo memory):**
- The surveillance corpus DB is **READ-ONLY**. This app **NEVER** writes to it.
  All per-user state (auth, threads, memory, monitors, read-state) lives in a
  **separate, app-owned writable DB**. This also dodges the known
  `analytics.users` ↔ `user_profiles` two-system split (0 overlap) — the new app
  owns its own user table and maps outward, rather than fighting that schism.
- **Cite-ID guardrail** is mandatory: every LLM claim must carry a resolvable
  `article.id` / `clipping.id` / `clip.id`, validated before render (your
  CM-content-correctness lesson — no fabricated handles/quotes).
- **Faithfulness gate**: Ragas/DeepEval score in CI + a runtime check; below
  threshold → fall back to extractive ("here's what sources say") not generative.
- Keep **AGPL** services (SearXNG, Firecrawl, pg_search) behind the API boundary.

---

## 5. Build order (de-risked, value-first)

| Phase | Ships | Why first |
|---|---|---|
| **P0 — read-only foundation** | `mc_readonly` role + SSH-tunnel data layer; hybrid retrieval (pgvector + pg_search + RRF + bge-rerank) exposed as one `corpus_search` tool | Everything depends on good retrieval; cheap, no new infra |
| **P1 — cited answer surface** | Fork `morphic`; NL search → cited answers over corpus; cross-lingual + `_translated` | Immediate demoable "wow"; Category 1 + pain-point #1/#9/#10 |
| **P2 — live web fusion** | SearXNG + crawl4ai + gpt-researcher loop as tools; source-fused answers | Turns RAG into "more than RAG"; Category 5 |
| **P3 — per-user + agents** | App DB + LangGraph threads + Mem0 prefs; saved monitors + alerts | Unlocks Category 6 monetization (monitors, alerts) |
| **P4 — the moat** | Cross-language framing contrast, story-cluster dedup/timeline, figure-discrepancy, entity graph explorer | Category 2 — the defensible, uncopyable features |
| **P5 — monetize** | Deep-research credits, premium archive, audio brief, team workspaces, data API | Category 6/7; gate behind Pro/Team/Enterprise |

---

## 6. Pricing ladder (from market research)
- **Free** — consumer feed, basic cited search, 1 saved monitor. (Funnel + data.)
- **Pro ₹799–1,499/mo (~$10–18)** — unlimited monitors, deep-research credits, audio brief, bias/blindspot, archive search.
- **Team / Desk ₹5–15k/seat/mo** — shared workspaces, export, more credits.
- **Enterprise ₹15L–1Cr+/yr** — API, real-time first-alert, private-corpus, SSO.
- **Add-ons** — premium-content packs (+₹199/mo), metered deep-research credits.

---

## 7. The 3 things that make this fundable (not just cool)
1. **Cross-language EN/HI/TE story stitching + framing contrast** — literally nobody does this; it's a wedge no incumbent can copy without our corpus + entity graph.
2. **Trusted curated corpus** — solves the #1 complaint about Perplexity (spam/hallucinated citations) by construction.
3. **Mid-market India OSINT gap** — between $20/mo consumer toys and $100k/yr enterprise terminals there is *nothing*. That whitespace is the business.

---

## 8. Open risks / honest caveats
- **LLM faithfulness** over multilingual structured data is the hard engineering problem — budget for eval/guardrails from day one (it's not free).
- **Live-web cost** — keep 90% of volume on free SearXNG+crawl4ai; pay-per-call (Tavily/Exa/Firecrawl) only on fallback.
- **Corpus freshness** — moat features assume the ingestion pipeline keeps story_clusters/embeddings current; the app rides on that, doesn't own it.
- **Read-only discipline** — the single most important rule; a stray write into the corpus DB is the one unrecoverable mistake.

## 9. Database deep-dive status (honesty note)
This plan is grounded in the **documented schema** (CLAUDE.md + onboarding +
session memory), not live row counts — the hard rules require a read-only role
(`mc_readonly`) and an SSH tunnel whose credentials weren't provided to this
session, and I will not invent them. **Next step on request:** with a tunnel +
read-only role I'll run live `SELECT`s to verify row counts, embedding coverage,
per-language splits, extraction completeness, and cluster sizes — and tighten
every "moat" feature against what the data actually supports.
