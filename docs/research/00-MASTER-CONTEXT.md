# RIG Intelligence — MASTER CONTEXT & HANDOFF BRIEF

> **Purpose:** Give any AI chat/agent the *complete* context to answer questions and
> do real work on this project — the database, the product we're building, the
> current state of work, and the rules to operate safely. This document is
> **self-contained**; deeper detail lives in the companion files listed in §11.
>
> **Status as of 2026-06-14.** All database numbers below are from a *live* read-only
> audit (not the schema doc) and are trustworthy. Where something is unverified, it
> says so.

---

## 0. Ground rules for whoever uses this context
1. **The corpus database is READ-ONLY and production.** SELECT only. Never INSERT/
   UPDATE/DELETE/DDL. A stray write is the one unrecoverable mistake.
2. **Never fabricate data.** If you don't know a value, query it or say "unknown."
   Anchored ≠ correct; report trusted / unverified / failed separately.
3. **Per-user/app state goes in a SEPARATE writable database**, never in the corpus.
4. **Every generated claim must cite a real row id** (article/clipping/clip) — a
   cite-ID guardrail is mandatory for this product.
5. Prefer the **rich/canonical** field over the primitive one (see §4.3).

---

## 1. What the project is
**RIG Surveillance** is a multi-pillar news/OSINT intelligence corpus for India,
strongly multilingual (English + Telugu + Hindi + 5 more Indian languages), with a
heavy Telangana/Hyderabad focus. Backend: FastAPI + Celery workers + Postgres 16 +
pgvector, on a Hetzner box. An existing product ("night-desk" / desk.rig360media.com)
already reads this data.

Pillars with real data: **Articles** (~293K), **Clippings** (newspaper cuttings,
~4.9K), **YouTube clips** (~1.2K). Each has a full structured "substrate"
(stances/claims/quotes/numbers/locations/entity-mentions). Plus an **entity graph**,
**story clustering**, and **per-user relevance** scoring.

## 2. What we are building (the new app)
A **per-user, internet-connected, agentic RAG "super-app"** on top of this corpus.
It is **"more than a RAG"** because it adds four layers a plain RAG lacks:
1. **Live web fusion** (search the internet, fuse with the corpus),
2. **Per-user memory + agents** (each user gets stateful, personalized agents),
3. **Structured intelligence** (stances/claims/quotes/numbers/entities as queryable
   facts, not just text),
4. **Cross-lingual event stitching** (the same event across EN/TE/HI + pillars).

**One-line thesis:** general LLMs search the open web and forget you; we search a
*curated, multilingual, structurally-extracted Indian corpus that exists nowhere
else*, fuse it with the live web, and remember each user — answering *"who said what,
first, in which language, framed how, and is it heating up?"* No product on the
market answers that. That is the moat.

## 3. How to access the database (for an agent with shell access)
- SSH key on the operator's machine: `~/.ssh/rig_hetzner` → `root@178.105.63.154`.
- Postgres runs in the `rig-postgres` Docker container. **This document contains no
  secrets**; access requires the key, which lives only on the operator's machine.
- **Read-only recipe (use exactly this):**
  ```
  ssh -i ~/.ssh/rig_hetzner root@178.105.63.154 \
    "docker exec -i -e PGOPTIONS='-c default_transaction_read_only=on -c role=analytics_user' \
     rig-postgres psql -U rig -d rig -f -"   # pipe SQL via stdin
  ```
  This drops privileges to the read-only `analytics_user` role and forces the session
  read-only, so writes are impossible even by accident. `analytics_user` = read-only
  on `public.*`, RW on `analytics.*` (we only SELECT).

## 4. The database — verified truth

### 4.1 Census (the #1 thing to know)
**~200 tables exist; only ~40 hold real data.** A promising table name means nothing.
- **Populated:** `articles` (~293K) + substrate (`article_stances` 378K, `article_claims`
  541K, `article_quotes` 244K, `article_numbers` 461K, `article_locations` 564K,
  `article_entity_mentions` 1.13M, `entity_mention_daily` 256K, `article_districts` 49K,
  `article_links` 12M, `article_media` 3.8M); `clippings` 4.9K + full substrate;
  `youtube_clips_v2` 1.2K + full substrate; `entity_dictionary` 19.3K; clustering
  (`analytics.story_clusters` 34.6K, `story_clusters_v8` 178K, `event_clusters` 6.9K);
  per-user (`user_article_relevance` 264K, `analytics.users` 2, `user_brief_prefs` 5).
- **EMPTY (0 rows) → features needing these are BLOCKED:** all `cm_*` (political
  intelligence), all `social_*` (signals/threads), all `govt_*` (documents),
  `districts`/`assembly_constituencies`/`mandi_prices`/`weather_*`, `dossier_*`,
  `narrative_*`, `alerts`/`notification_*`/`user_watchlist`, `analyst_*`, `collections`,
  and the empty user system `public.users`/`public.user_profiles`. **(OPEN QUESTION:
  is this DB the full production set, or do these live in another environment?)**

### 4.2 Clean working set
Usable articles = `substrate_status='ok' AND NOT is_duplicate` ≈ **~200K** of 293K.
(`substrate_status`: ok 80%, fetch_failed 11%, junk 7%. **17% are duplicates.**)
Languages: **en 66.5%, te 9.4%, hi 4.6%**, + ml/kn/ta/bn/mr; ~9.5% null. Live through today.

### 4.3 Field quality + "use this, NOT that" (build on the rich field)
| Need | ✅ USE | ❌ AVOID | Why |
|---|---|---|---|
| Semantic vector | `labse_embedding_v4` (94%, recipe `v4-tr-title-1024`, 768-d, HNSW) | `labse_embedding` (legacy, recipe-mixed); `_v0_backup` | only v4 is one clean recipe |
| Lexical search | `fts` tsvector (**100% populated**) | — | hybrid needs **no new extension** |
| English text | `lead_text_translated` (97%) + `title` (99%) | `full_text_translated` (17.5%, sparse) | full-EN body is rare |
| Native body | `full_text_scraped` (99%) | — | translate on the fly when needed |
| Topic | `topic_category` (99.9%, but 21% `OTHER`) + `topic_fine` (66%) | `topic_category_orig` (legacy) | |
| Geo | `article_locations` (564K, structured) | `geo_primary` (mixed granularity); `geo_secondary` (100% = **defaulted junk**) | |
| Entities | `article_entity_mentions` (canonical, 82% of articles, `surface_forms`) | `entities_extracted` jsonb (raw); `entity_lookup` (**9-row dead test stub**) | matview is resolved |
| Sentiment/framing | `article_stances` (supportive/neutral/critical) | `register_emotion` (event-emotion, 42% neutral) | stance is the real signal |
| **Dead — never use** | — | `narrative_frame` (0), `content_type` (constant 'article'), `geo_secondary` | no information |

### 4.4 Substrate quality (the moat material; ~half the corpus)
Coverage of 293K: locations 68% · claims 53% · stances 49% · numbers 45% · quotes 36%.
- **`article_stances`** (378K): clean directed signal supportive 149K / neutral 139K /
  critical 82K. **45% entity-resolved** (`actor_entity_id`). *`actor` is believed to be
  the TARGET being discussed (directed sentiment) — to be confirmed.*
- **`article_claims`** (541K): avg conf 0.73, 66% ≥0.7, **134K distinct predicates
  (free-text, not normalized)** → good for evidence, weak for rollups. 30% entity-resolved.
- **`article_quotes`** (244K): 80% direct; **`quote_text_en` is EMPTY (202 rows)** →
  English quote display needs on-the-fly translation; speaker 39% resolved.
- **`article_numbers`** (461K): units mix real figures (currency/percent/INR/count) with
  temporal junk (date/year/time) → filter before use.

### 4.5 Entities
- **`article_entity_mentions`** (matview, the canonical path): 1.13M rows, **241K
  distinct articles (82%)**, 10,331 distinct entities; cols `article_id, entity_id,
  canonical_name, entity_type, country, surface_forms, mention_rows` (no prominence).
- **`entity_dictionary`** (19,356): person 57% / org 22% / location 12% / constituency
  6% / role 2%; country 57%, state 38%, party 18% filled. **`aliases` are English/Latin
  only** (no native script). Regional-language mentions are linked via **translate-then-
  extract**, not native-script matching.
- **Disambiguation risk:** "Modi" collides with Narendra Modi / Lalit Modi / "Modi
  government" / Modinagar (a town). Entity feeds need a disambiguation guard.

### 4.6 Clustering / stories
- **`analytics.story_clusters`** (documented LIVE): 34,599 clusters over 136,581
  articles (47%); avg 3.9, max 5,593; only **945 clusters ≥3 articles** (the real
  "events"). Fields incl. `languages` (per-cluster language histogram), `stance_
  distribution`, `importance_score`, `is_template_family`, `representative_title`.
- **`story_clusters_v8`** (178,258) = newer candidate, **status unverified**.
  **`event_clusters`** (6,859) = a separate cleaner product event table. **OPEN: which
  is wired to the live product?**
- **Cross-language = CONFIRMED in data:** big clusters span e.g. `{en:2805, te:2264,
  hi:135, …}`. Material for framing-contrast exists today (the ~945 clusters).
- **Enrichment is thin:** `story_timeline`/`sources` = 716 stories, `facts` = 567. Rich
  story pages exist for ~716 stories only; derive timelines from member `published_at`
  for the rest.

### 4.7 Per-user layer (real but barely populated)
- **`analytics.users`** (2): org-scoped, multi-tenant (`id, org_id, email, full_name,
  designation, is_super_admin`). The empty `public.users`/`user_profiles` is a dead
  parallel system.
- **`user_article_relevance`** (264K rows, **only 1 user**): rich relevance-v3
  (`score_stage1, score_final, relevance_tier, relevance_explanation, sentiment_for_user,
  geo_multiplier_applied, matched_entity_names`). Scaling to more users = a backfill.
- **`user_brief_prefs`** (5): preference schema (`watchlist, regions, topics, languages,
  stance, events, sources, personality, delivery`).

### 4.8 Cross-pillar (clippings + youtube)
- **`clippings`** (4.9K): translated headline 97%, body 75%, embedding 97%, entities 97%.
  Language **hi 1420 / te 1198 / en 1161 / mr/gu/ml/bn/kn** (mostly regional). Full substrate.
- **`youtube_clips_v2`** (1.2K): fully enriched (embedding/summary/transcript/entities
  ~100%), 41 channels. Full substrate.
- **⚠ Cross-pillar embedding caveat:** articles use recipe `v4-tr-title-1024`;
  clippings/youtube use a plain `labse_embedding` with no recorded recipe. A spot-check
  showed **loose, noisy** cross-pillar cosine. **Do not trust article↔clipping↔clip
  similarity without an entity/topic filter + reranker, or re-embedding with v4.**

### 4.9 Verified moat facts (proven this session)
- English query → relevant **Telugu** articles at tight cosine (0.19–0.24). Cross-lingual
  retrieval works well in v4 space.
- One canonical entity unifies **7+ languages** (Narendra Modi: en 2461 / te 407 / hi
  252 / ml / kn / ne / ta).
- Clusters already stitch EN/TE/HI per event (§4.6).
- `fts` is 100% populated → hybrid search with no new extension.

## 5. The known issues (plain list)
1. Data is **wide but shallow** — only ~50% has substrate; 17% dupes; clean set ~200K.
2. **English isn't always present** — full-text EN 17.5%; quote-EN ~0 → translate on the fly.
3. **Cross-pillar embeddings may not share a space** — the one real technical risk.
4. **Entity confusion** ("Modi" collisions; 45% stance / 30% claim entity-resolution).
5. **Whole pillars empty** (political-intel/social/govt/districts/dossiers/alerts).
6. **Per-user & enrichment barely populated** (1 user; 716 enriched stories).
7. **Trap fields** look useful but are dead (`entity_lookup`, `narrative_frame`,
   `content_type`, `geo_secondary`).

## 6. The 70 features → feasibility (summary)
Seven categories × 10 features. Tally: **~33 ready now (🟢), ~34 partial (🟡, mostly
"build our own per-user/alert layer" or "add a reranker/filter"), ~3 blocked (🔴,
need data generation or out of scope).** Full matrix in `feature-feasibility-and-set1.md`.
The defensible "moat" features (cross-language stitching + framing contrast, newspaper
OSINT, cross-language entity feed) are 🟢 today.

## 7. What we are CURRENTLY working on
- **Phase 0 (DONE):** full field-level DB audit + redundancy analysis + 70-feature
  feasibility map (this document + companions).
- **Set 1 (V1) — proposed, not yet built:** "Cited Multilingual Search + Moat Proof":
  (0) hybrid retrieval engine [pgvector v4 + fts + RRF + bge-reranker], (1) NL cited
  cross-lingual answer, (2) semantic find-similar, (3) cross-language entity feed,
  (4) cross-language framing contrast, (5) "what's actually new" dedup. All 🟢, share
  one engine, prove the moat, depend on no empty tables.
- **Build method (the user's rule):** build feature-by-feature → **test HARD against a
  ground-truth eval set** → refine until each hits its "great" threshold → only then
  move to the next set. Thresholds + verification methods are in
  `feature-feasibility-and-set1.md` §"hard test plan."
- **Immediate next steps:** (a) get the DB-chat answers to the open questions (§8);
  (b) confirm the live clustering generation; (c) decide the cross-pillar embedding
  approach; (d) scaffold the new read-only app with its own *separate writable* app DB.

## 8. Open questions still pending (answer these to unblock)
1. Is this DB the **full production set**, or do the empty pillars live elsewhere?
2. Are clippings/youtube embedded in the **same space** as articles v4? Re-embed plan?
3. Which clustering generation is **live** (`story_clusters` vs `story_clusters_v8`)?
   How does it relate to `event_clusters`?
4. Exact **`v4-tr-title-1024` recipe** + HNSW params + is the vector normalized?
5. Is `article_stances.actor` the **target** (directed sentiment)?
6. What pipelines are **frozen/broken** right now; matview refresh cadences?
(Full ~90-question list in `db-questions-prompt.md`.)

## 9. Recommended tech stack (OSS, verified June 2026)
- **Agents:** LangGraph + Pydantic AI. **Memory:** Mem0 + Graphiti (in app DB).
- **Retrieval:** pgvector v4 + existing `fts` + RRF + `bge-reranker-v2-m3` +
  LlamaIndex query-rewrite. (No vector-store migration; no ParadeDB needed.)
- **Live web:** SearXNG (already running) + Crawl4AI + trafilatura + gpt-researcher.
- **Answer UI:** fork Morphic. **Eval:** Ragas + DeepEval + promptfoo.
- **Models:** Groq qwen3-32b (cheap path) → Claude Sonnet/Opus (premium synthesis).
Detail + alternatives + license cautions in `rag-stack-survey-2026.md`.

## 10. Architecture in one paragraph
User → answer surface (Morphic-style) → **LangGraph agent** (durable per-user threads)
with tools: `corpus_search` (hybrid+rerank over READ-ONLY pgvector), `web_search`
(SearXNG+Crawl4AI), `deep_research` (gpt-researcher), `entity/stance/quote` tools over
the substrate. Per-user state (auth, threads, memory, monitors, read-state) lives in a
**separate writable app DB** — never the corpus. A faithfulness/cite-ID gate checks
every answer before it ships.

## 11. Companion documents (deeper detail)
- `docs/research/db-field-audit.md` — every field, coverage %, A–F grade, redundancy.
- `docs/research/feature-feasibility-and-set1.md` — all 70 features rated + Set 1 + test gates.
- `docs/research/db-questions-prompt.md` — the full ~90-question list for the DB chat.
- `docs/research/rag-superapp-masterplan.md` — the product/founder master plan.
- `docs/research/rag-stack-survey-2026.md` — the OSS retrieval/RAG/agent survey.
- `docs/research/market-monetization-research.md` — what people pay for; pricing ladder.
- `CLAUDE.md` + `docs/onboarding/` — the existing-system operational context (note:
  parts are stale; this document supersedes it for the new-app effort).
