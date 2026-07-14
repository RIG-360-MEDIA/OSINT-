# RIG Surveillance — DB & OSINT-Product Context (session handoff)

Paste the prompt at the bottom into a new chat. This doc is the shared brain. Scope of the
new chat: **database + OSINT-product discussion.** The **client partner-API build** and the
**Sentiment-v2 (embedding-distilled) plan** are being handled in a *separate* chat — see
`docs/handoffs/client-api-build-spec.md` and `client-api-data-quality.md`; **do not redo them here.**

---

## 0. THE ONE RULE (learned the hard way this session)
**Do not trust the docs/schema files — verify against the LIVE database.** This session,
docs were wrong on: district tagging ("missing" — it exists), story columns (`member_count`
— real is `article_count`), translation ("missing" — it's 92% gist), full-text null (~10%
vs measured 6%). The `docs/handoffs/db-reference/` docset and `DB_AUDIT_*.md` have stale
column names. **Ground every claim in a real query.** No assuming from a first look.

## 1. What RIG is
Multi-pillar intelligence aggregator (political OSINT, India / Telugu-states focus).
FastAPI + Celery workers + a Vite/React night-desk SPA. Live at **desk.rig360media.com**.
Pillars: Articles (`/coverage`), Clips (YouTube), Cuttings (newspapers), Threads/Signals
(social — Reddit/Telegram/Twitter), Documents (govt PDFs), Brief (daily digest), Analyst
(RAG). Plus **Chronicle** (deep story page), **Map** (district situation map), War Room.

## 2. Infra & access
- **Host:** Hetzner `178.105.63.154`. `ssh -i ~/.ssh/rig_hetzner root@178.105.63.154`.
- **Docker stack:** `rig-postgres` (ankane/pgvector, PG16), `rig-backend` (FastAPI **+ all
  Celery workers + Beat** via `/start.sh` — no separate worker services), `rig-caddy`
  (serves static night-desk from `/root/rig/night-desk-dist`), `rig-frontend`, `rig-searxng`,
  `rig-freshrss`.
- **Query the DB:** `ssh … "docker exec -i rig-postgres psql -U rig -d rig -tA"` (heredoc SQL).
  Heavy scans over 875k rows time out — **set `SET statement_timeout='55s'`, use `collected_at`
  windows, avoid `length(full_text_scraped)` full scans.**
- **What's actually running:** `docker exec rig-backend ps -ef`. **Task routing:** `backend/celery_app.py`.
- Two API surfaces: main `backend/` (Supabase-JWT, serves night-desk), `products/osint/backend/v1`
  (the partner API — keys/scope/webhooks/cursor), `products/ask-rig` (RAG `/ask` `/chat`).

## 3. DATABASE REALITY — measured live 2026-07-05 (trust these)
**Volume/freshness:** 875,650 articles; ~20.9k/24h; **live to today**.

**`articles` real columns (key ones):** `id`(uuid), `source_id`, `url`, `title`,
`lead_text_original`, `lead_text_translated`, `full_text_scraped`, `full_text_translated`,
`language_detected`, `language_iso`, `published_at`, `collected_at`, `updated_at`,
`nlp_processed`, `substrate_processed_at`, `substrate_status`, `entities_extracted`(jsonb
**array** of `{name,type,confidence,prominence}`), `geo_primary`, `labse_embedding`,
`labse_embedding_v4`, `register_emotion`, `register_is_breaking`, `summary_*`, `topic_category`,
`importance*`, `nlp_confidence`, `body_quality`, `word_count`.

**Coverage (last 7d):** full_text 94.3% · nlp_processed 100% · substrate 100% · **language_iso
only 67.6%** (⚠ a third untagged) · translation: lead/gist 92%, full-body 33% (99% of non-EN
*have* a scraped body — the gap is the translator, not scraping).

**`updated_at` moves on only 0.95% of rows** — pipeline never bumps it (matters for any
change-feed/cursor). Enrichment writes to *related* tables, not back to `articles`.

**Sentiment — `article_stances`** (directed: `stance`, `intensity` 0–1, `actor`=**target**
entity [legacy naming], `article_id`). 1.04M rows. **~29% of articles have a stance**; 100%
have extracted entities; **70% have a dictionary-matched entity** → the stance stage is the
selective gate, not missing entities. `entity_dictionary` = 19,385 entities. `article_entity_mentions`
(matview: article_id, entity_id, canonical_name, entity_type, surface_forms, mention_rows).
`entity_mention_daily` (659k rows, per-entity daily counts, fresh to today).

**Geography — `article_districts`** (article_id, district_id, mention_count, confidence,
is_primary) + `districts` (`state_code`, gazetteer). **28,571 articles tagged (~3.3%), AP+TG
only, 59 districts.** Multi-tenant-ready via `state_code`; new state = seed gazetteer + local
sources. Powers the Map. Accuracy ~50–80% by language.

**Sources — `sources`:** 2,039 (tier1 502 / tier2 1,375 / tier3 162). `source_tier`,
`health_score` (collector success, NOT editorial credibility).

**Stories — `analytics.story_clusters_v8`** (348,407 rows, all `status='active'`). Real cols:
`story_id, article_count, source_count, independent_source_count, updated_at, topic,
event_type, primary_entities, languages, stance_distribution, sentiment, representative_title,
representative_quote, importance_score, is_multi_event`. **Median `article_count`=1 (mostly
singletons); only 7,723 are ≥3-independent-source ("surfaceable"); one 14,893-article mega
exists.** Method: LaBSE embeddings + graph (Louvain/igraph) + nightly repair; ~76% precision /
~80% hub-purity on the confident tier (from QA docs — re-verify). Also `analytics.story_facts_v8`
(33k facts, single-source flag), `story_sources_v8`. Consumed by `products/osint/backend/routers/chronicle_router.py`.

**Quotes/claims — `article_quotes`, `article_claims`.** Coverage 24h: quotes 21%, claims 31% (selective LLM extraction).

**Summaries:** `briefs` (per-user daily) + `narrative_drafts` (LLM story drafts).

**Credibility / misinformation — ABSENT** (no table). `cm_stance_scores` = political
ruling/opposition lean only, not false/misleading.

## 4. Pipeline notes
Substrate v3 extraction (`backend/tasks/substrate/`); LaBSE v4 embeddings (`labse_embedding_v4`);
entity extraction = **open spaCy, keep-all** (~7 entities/article — high recall, lower precision);
queues: collectors, social, youtube, documents, nlp, relevance, brief. `register_emotion` skews
negative (don't treat as sentiment). Clustering has an anti-mega guard (`SIZE_NET`) + a nightly
janitor repair job.

## 5. Known data-quality gaps (measured)
1. `updated_at` frozen (0.95%). 2. `language_iso` 32% missing. 3. Sentiment 29% (entity/stage-gated).
4. Districts regional-only (3.3%, AP+TG). 5. Clustering mostly singletons + occasional megas.
6. Credibility absent. (Translation full-body 33% is **not** a real gap — only summaries need translating.)

## 6. Working style
Plain English, concrete, **no fabrication**, verify-don't-assume, honest about quality/limits,
recommend don't survey. India/Telugu-states domain. The user thinks in "what's real vs what we
claim." OSINT product design uses an "Armoury"/night-desk aesthetic (separate concern).

## 7. OUT OF SCOPE here (handled in the other chat)
- Client white-label partner API build (`osint/v1`) — see `client-api-build-spec.md`.
- Sentiment-v2 (embedding-distilled multi-perspective) — being designed in the other chat.
Don't reopen these; this chat is for **other DB + OSINT-product topics.**
