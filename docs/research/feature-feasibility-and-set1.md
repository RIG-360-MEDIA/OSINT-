# 70 Features → Feasibility (grounded in live data) + Proposed Set 1

> Companion to [`db-field-audit.md`](./db-field-audit.md). Every status below is
> backed by the live read-only audit of 2026-06-14, not the schema doc.

## How to read this

- 🟢 **Ready now** — data + OSS both support it; proven or near-proven in the audit.
- 🟡 **Partial** — works, but with a *named* caveat: either a coverage limit / needs a
  guardrail, **or** it needs a delivery layer we build in our *own* app DB (alerts,
  read-state, monitors) — which we were going to build anyway. Not a data problem.
- 🔴 **Blocked** — needs data that does not exist yet (empty tables) or is out of scope.

**The one big takeaway:** almost nothing is impossible. ~33 features are 🟢 today,
~34 are 🟡 (mostly "build our own per-user/alert layer" or "add a reranker/filter"),
and only a tiny few are truly 🔴. The corpus + OSS already covers the product.

**What proved out in the audit (so you can trust the greens):**
- v4 semantic search is tight AND cross-lingual (EN query → Telugu/Hindi docs). ✅
- `fts` tsvector is 100% populated → hybrid search needs **no new DB extension**. ✅
- One canonical entity unifies 7+ languages (Modi: en/te/hi/ml/kn/ne/ta). ✅
- Clusters already span EN/TE/HI per event → framing-contrast has material. ✅
- Cross-pillar cosine is loose → needs entity-filter + rerank (not raw). ⚠️

---

## Feasibility matrix — all 70

### Category 1 — Logical / easy wins
| # | Feature | Status | Needs / caveat |
|---|---|---|---|
|1|Semantic find-similar|🟢|v4 + HNSW; **proven tight + cross-lingual**|
|2|NL search w/ cited answers|🟢|v4 + `fts` + bge-rerank + LLM + cite-ID guard|
|3|Entity feed|🟢|`article_entity_mentions` (canonical, 82%); cross-lang proven|
|4|Topic & geo dashboards|🟡|`topic_category` 21% `OTHER`; use `article_locations`, **not** `geo_primary`/`geo_secondary`|
|5|Saved searches → alerts|🟡|search 🟢; build alert store in app DB (`alerts` table empty)|
|6|Agentic daily brief|🟢|`briefs` + `user_brief_prefs` + summary tiers + LLM|
|7|Cross-lingual answer|🟢|**proven**: EN query retrieves TE/HI, answer from `lead_text_translated`|
|8|Stance/sentiment trends|🟢|`article_stances` + `entity_mention_daily`; caveat 49% cover / 45% entity-resolved|
|9|Quote finder|🟡|`article_quotes` 36% cover; `quote_text_en` empty → translate on the fly|
|10|Numbers feed|🟡|`article_numbers` units noisy → filter to currency/percent/count|

### Category 2 — Only OUR system can do (moat)
| # | Feature | Status | Needs / caveat |
|---|---|---|---|
|1|Cross-language story stitching|🟢|`story_clusters.languages` proves EN/TE/HI per event (~945 multi-article clusters)|
|2|Cross-language framing contrast|🟢|cluster members × `article_stances` grouped by `language_detected` — **the differentiator**|
|3|Cross-pillar event view|🟡|cross-pillar cosine loose → entity/topic filter + rerank, or re-embed clippings with v4|
|4|Who-said-it-first|🟡|`article_quotes`/`claims` + `published_at`; partial coverage|
|5|Cross-script entity resolution|🟡|works via **translate-then-extract** (not native-script aliases); native-script query input needs translating first|
|6|Figure-discrepancy detector|🟡|numbers noisy + claims free-text; cluster-scoped, messy|
|7|Newspaper-cutting OSINT|🟢|`clippings` 97% translated + embedded + full substrate|
|8|Per-user relevance / private corpus|🟢|`user_article_relevance` scorer exists (rich); only 1 user populated → scale|
|9|Stance-shift over time|🟡|stance time-series per entity; 45% entity-resolved|
|10|District/state intelligence|🟡|`article_districts` (49K) has data; but `districts`/`assembly_constituencies` reference tables **empty**|

### Category 3 — User pain points
| # | Feature | Status | Needs / caveat |
|---|---|---|---|
|1|Trustworthy citations|🟢|RAG over curated corpus + cite-ID guardrail|
|2|Article-level bias/framing|🟢|`article_stances` per article/source (beats outlet-level)|
|3|"What's actually new" dedup|🟢|`story_clusters` + `is_duplicate` (17%)|
|4|Blindspot alerts|🟡|cluster source diversity via `source_id`/`story_sources`; partial|
|5|Catch-me-up|🟡|build read-state in app DB; content side 🟢|
|6|Mute / notification control|🟡|`user_brief_prefs` schema exists; build delivery|
|7|Reading-budget brief|🟢|**3 summary tiers** (preview/snippet/executive) = 5-min vs deep, perfect|
|8|Verify-this|🟡|evidence retrieval via claims/stances; not a formal fact-checker|
|9|Zero translation friction|🟢|`lead_text_translated` 97%, clippings 97%; IndicTrans2 for gaps|
|10|Source transparency|🟢|`sources` (1,220) + url + `published_at` + `language_detected`|

### Category 4 — Creative / never-thought-of
| # | Feature | Status | Needs / caveat |
|---|---|---|---|
|1|Story "time machine"|🟡|enrichment thin (716); **derive** timeline from member `published_at` → 🟢 for any cluster|
|2|Counter-narrative pairs|🟡|`cm_counter_narratives` empty; **derive** from stance critical-vs-supportive → 🟢|
|3|Live multilingual audio brief|🟡|content 🟢; TTS build (AI4Bharat IndicF5 / Kokoro)|
|4|Debate mode|🟢|agent + stances/claims as evidence for both sides|
|5|Entity relationship explorer|🟢|`article_entity_mentions` co-mention graph (1.13M)|
|6|"This is heating up"|🟢|`entity_mention_daily` velocity + cluster `first/last_seen_at`|
|7|Framing fingerprint|🟡|needs per-user read history → build tracking in app DB|
|8|Ask-the-archive|🟢|clippings RAG (embedded + translated)|
|9|Quote-watch alerts|🟡|quotes + entity; build alert delivery; translation gap|
|10|"What are THEY saying" (cross-lingual)|🟢|filter cluster members by language, translate|

### Category 5 — Borrow from OSS (integration work, all buildable)
| # | Feature | Status | Tool |
|---|---|---|---|
|1|Perplexity-style answer UI|🟢|fork **Morphic** / Perplexica|
|2|Deep-research loop|🟢|**gpt-researcher**|
|3|Per-user memory|🟢|**Mem0** + **Graphiti** (in app DB)|
|4|Agent orchestration|🟢|**LangGraph** + Pydantic AI|
|5|Hybrid retrieval|🟢|**REVISED**: existing `fts` + pgvector + RRF (no ParadeDB needed)|
|6|Reranking|🟢|**bge-reranker-v2-m3**|
|7|Live web|🟢|**SearXNG** (already running) + **Crawl4AI** + trafilatura|
|8|Query rewriting|🟢|LlamaIndex multi-query / HyDE / RAG-Fusion|
|9|Graph hop|🟡|LightRAG (optional extra infra)|
|10|Eval harness|🟢|Ragas + DeepEval + promptfoo|

### Category 6 — Features people WILL pay for
| # | Feature | Status | Needs / caveat |
|---|---|---|---|
|1|Real-time first-alert|🟡|velocity + clustering; cadence-limited; build delivery|
|2|Saved monitors + push|🟡|build app DB + ntfy/web-push|
|3|Metered deep-research credits|🟢|gpt-researcher + billing|
|4|Premium archive access|🟢|clippings + articles back to 2010|
|5|Team/desk workspaces|🟡|`analytics.orgs`/`users` multi-tenant ready; build collab|
|6|Data API|🟢|expose stances/claims/entities/numbers read-only|
|7|Scheduled + audio brief|🟡|brief 🟢; audio = TTS build|
|8|Bias/blindspot pro analytics|🟡|stances + source diversity; coverage caveat|
|9|Cited report export|🟢|WeasyPrint / Playwright PDF|
|10|Private-corpus add-on|🟢|separate app-DB vector store + Docling/Markitdown ingest|

### Category 7 — Features people DO pay for today
| # | Feature | Status | Needs / caveat |
|---|---|---|---|
|1|Cited synthesis over trusted corpus|🟢|core capability|
|2|Search over premium/private corpus|🟢|our corpus = the premium corpus; + private add-on|
|3|Real-time event detection|🟡|clustering velocity; ingestion-cadence limited|
|4|AI feeds + entity monitoring|🟡|feeds 🟢; monitoring delivery to build|
|5|Bias / blindspot|🟡|article-level via stances (better than outlet-level)|
|6|Audio brief|🟡|TTS build|
|7|Research report generation|🟢|deep-research loop|
|8|Enterprise connector search (Glean)|🔴|multi-source connectors out of scope (we are 1 corpus + web)|
|9|News-terminal real-time analytics|🟡|dashboards from substrate; cadence-limited|
|10|Semantic find-similar / discovery|🟢|**proven**|

**Tally:** 🟢 ~33 · 🟡 ~34 · 🔴 ~3. The 🔴s need either data generation (political-intel/social/govt — empty tables) or are out of scope (enterprise connectors). Everything else is a build, not a research risk.

---

## Proposed **Set 1 (Version 1)** — "Cited Multilingual Search + Moat Proof"

Chosen so that (a) **every item is 🟢**, (b) they all ride **one engine** (hybrid
retrieval) so we build the foundation once, (c) two of them are **moat** features so
V1 is already "more than a RAG," and (d) **zero dependency on empty tables**.

| V1 feature | From | Why it's in Set 1 |
|---|---|---|
| **0. Hybrid retrieval engine** | C5 #5/#6/#8 | foundation: pgvector v4 + `fts` + RRF + bge-rerank + query-rewrite |
| **1. NL cited answer (cross-lingual)** | C1 #2/#7, C3 #1/#9 | the headline surface; proven cross-lingual |
| **2. Semantic find-similar** | C1 #1, C7 #10 | proven excellent (0.19–0.24 dist) |
| **3. Canonical entity feed (cross-language)** | C1 #3, C2 moat | Modi across 7 languages; needs disambiguation guard |
| **4. Cross-language framing contrast** | C2 #2 | **the differentiator** — EN vs TE vs HI stance on one event |
| **5. "What's actually new" dedup view** | C3 #3 | clusters + `is_duplicate`; kills repetition fatigue |

> Deliberately **excluded** from V1: anything needing the app-DB delivery layer
> (alerts, monitors, read-state), live-web, audio/TTS, or cross-pillar fusion —
> those are Set 2+.

### The hard test plan (the quality gate to "great")

**First build the ground-truth eval set** (this is the gate, not an afterthought):
- 50 labeled queries (EN + TE + HI), relevant-doc sets sampled from story clusters.
- 30 Q&A pairs for faithfulness scoring.
- 20 entities incl. cross-script + collision traps (Narendra Modi vs Lalit Modi vs "Modi government").
- 10 multi-language clusters hand-labeled for framing.
- 20 known-duplicate sets.

**Per-feature acceptance thresholds — V1 is frozen only when ALL pass:**

| Feature | "Great" threshold | Verification method |
|---|---|---|
| Retrieval engine | Recall@10 ≥ 0.85, nDCG@10 ≥ 0.70; reranker beats raw cosine ≥ +10% nDCG; cross-lingual subset Recall@10 ≥ 0.75 | run labeled query set; compare raw-cosine vs +rerank |
| Cited answer | Ragas faithfulness ≥ 0.90, answer-relevance ≥ 0.85; **100%** citations resolve to a real id; **0** hallucinated cites on 30 Q&A | Ragas + cite-ID guardrail check + manual read |
| Find-similar | mean top-5 on-topic ≥ 0.80 (human judge, 30 seeds) | blind human rating |
| Entity feed | precision ≥ 0.92 on 20 entities; **no wrong-entity bleed** (Lalit vs Narendra Modi) | manual precision + cross-language count sanity |
| Framing contrast | EN/TE/HI stance dists match hand-labels within tolerance; suppress clusters with < N articles/language (no small-sample noise) | hand-label 10 clusters; statistical check |
| Dedup view | recall ≥ 0.90 collapsing dupes; false-merge ≤ 0.10 | 20 known-duplicate sets |

**Loop:** build feature → run its eval → below threshold? refine (rerank weights,
RRF k, query rewrite, disambiguation filter) → re-eval → only when all six are green,
**freeze V1 and move to Set 2.**

### Clustering generation — RESOLVED, and it's a MOVING TARGET
Live keeper = `analytics.story_clusters_v8` (200,823 clusters, **92%** of 354,533
articles), written today. Old `story_clusters` (34,599) is **DROPPED** →
`story_clusters_archive` kept only for Chronicle FKs. The *algorithm* is actively
migrating — inside `story_clusters_v8`, `algo_version` shows `cluster_job_7…/_v8`
(base) → `cluster_v9/pure+recall…/_v8` (**v9, live since 06-18**) →
`graph-incr/v4/_v8` (hourly incremental loop), with **v10 anticipated**.
`analytics._v9_cand` / `_v9_members` / `_v9_members_pure` are **scratch staging**
(not a keeper); no `_v10` tables yet.

**Architectural rule for Set 1 (features 4–5):** NEVER hardcode `story_clusters_v8`.
Read clusters through ONE indirection — a DB view `analytics.story_clusters_current`
(or a single app config constant) — so when v9/v10 promotes (new `algo_version`, or a
renamed `_v10` table) we repoint in **one place**. This is exactly what broke
**Chronicle**: its router hardcoded the unsuffixed names, the keeper was renamed on
promotion, and it now returns nothing. Do not repeat that mistake.

---

## What comes after V1 (so the path is visible)

- **Set 2 — Personalization & delivery:** app-DB user store, scale relevance to new
  users, saved monitors + alerts (ntfy/web-push), catch-me-up, mute. (Turns most
  🟡 "build our layer" items green.)
- **Set 3 — Live-web fusion:** SearXNG + Crawl4AI + gpt-researcher; deep-research
  credits. (Makes it "more than RAG" on the web side.)
- **Set 4 — Creative/moat-2:** time machine, debate mode, entity-graph explorer,
  "heating up," audio brief.
- **Backfills that unlock 🟡/🔴 later:** translate `quote_text_en`; re-embed
  clippings/youtube with the v4 recipe (clean cross-pillar); run story-enrichment
  beyond 716; score relevance for more users; (much later) generate the empty
  political-intel/social/govt data if those pillars are wanted.
