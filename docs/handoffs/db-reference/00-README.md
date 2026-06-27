# RIG Surveillance — Database Reference (RAG knowledge base)

Authoritative field-level reference for the live PostgreSQL database (Hetzner `rig-postgres`,
Postgres 16 + pgvector). Generated 2026-06-19 from the **live schema** (`pg_class`/`pg_attribute`),
the `COMMENT ON` metadata, the `scripts/migrations/*.sql` files, and **real sampled values** from
production. Nothing here is invented; inferences are marked "(inferred)".

> Scope: 134 relations (tables + views + matviews), 1,325 columns, across two schemas (`public`,
> `analytics`). The dead/frozen pillars (`cm_*`, `social_*`, `govt_*`, `dossier_*`, `narrative_*`,
> `story_threads`) were dropped 2026-06-19 and are **not** in this reference — see
> [../db-cleanup-drop-list-2026-06-19.md](../db-cleanup-drop-list-2026-06-19.md).

## How to read this reference
Each table is documented as: status label, row count + size, purpose, who populates it, who reads it,
freshness, then a **column-by-column** table (type / nullable / default / meaning & example values),
then its **joins** (FKs) and **notes** (gotchas). Status labels:
- **[LIVE]** — rows present and written recently (actively maintained).
- **[FROZEN since DATE]** — rows present but no writes since DATE (pipeline stopped/stalled; data is stale).
- **[EMPTY/PLANNED]** — 0 rows; schema exists but the feature/collector was never activated.

## The reference set (read in this order)
| File | Domain |
|---|---|
| [05-relationships-and-joins.md](05-relationships-and-joins.md) | FK graph + common join recipes |
| [10-corpus-and-substrate.md](10-corpus-and-substrate.md) | `articles`, `sources`, and the v3 NLP substrate (claims/stances/quotes/numbers/events/links/media/locations/tweets) |
| [20-entities.md](20-entities.md) | Entity dictionary + the surface-form→canonical resolution chain + mention matviews |
| [30-clustering-stories.md](30-clustering-stories.md) | The `story_*_v8` clustering keeper, enrichment, LLM generation, the nightly janitor, Chronicle |
| [40-youtube-newsroom.md](40-youtube-newsroom.md) | YouTube clips pillar (`youtube_clips_v2` vs legacy) + the Newsroom redesign |
| [50-clippings-districts.md](50-clippings-districts.md) | Newspaper cuttings pillar + the district / CM-v2 atlas (collectors + matviews) |
| [60-users.md](60-users.md) | The two user systems, RBAC, impersonation, per-user relevance, the Analyst RAG |
| [70-briefs-caches-infra.md](70-briefs-caches-infra.md) | Brief pillar, coverage caches, topic vocabulary, freshness views, Celery/Kombu plumbing |
| [90-known-issues-and-data-health.md](90-known-issues-and-data-health.md) | Stale pipelines, broken features, and query traps (READ THIS before trusting a table) |

## What the system is
RIG Surveillance is a Telangana-focused political-intelligence / OSINT aggregator. A FastAPI service +
Celery workers ingest content across pillars, run a uniform NLP "substrate" extraction over every item,
resolve entities, cluster items into events/stories, score per-user relevance, and serve a Next.js/Vite
"night-desk" frontend plus a per-user RAG "Analyst".

## Pillars → primary tables
| Pillar | Raw item table | Substrate (per item) | Entity matview |
|---|---|---|---|
| **Articles** (RSS/HTML) | `articles` | `article_claims`/`_stances`/`_quotes`/`_numbers`/`_events`/`_locations`/`_links`/`_media`/`_tweets` | `article_entity_mentions` |
| **Cuttings** (newspapers) | `clippings` | `clipping_claims`/`_events`/`_locations`/`_numbers`/`_quotes`/`_stances` | `clipping_entity_mentions` |
| **Clips** (YouTube) | `youtube_clips_v2` | `youtube_clip_claims`/`_locations`/`_quotes`/`_stances` | `youtube_clip_entity_mentions` |
| **Stories/Events** | `story_clusters_v8` (+ `story_cluster_members_v8`, `story_edges_v8`) | `story_facts_v8`/`_quotes_v8`/`_timeline_v8`/`_geo_v8`/`_sources_v8`/`_stance_v8` | (via member articles) |
| **Brief** | `briefs` | — | — |
| **Analyst** (RAG) | `analyst_sessions` / `analyst_turns` | (retrieves over the corpus) | — |
| **Districts/CM-atlas** | `districts` + `article_districts` | `mv_district_*` matviews | — |

## Cross-cutting concepts (the mental model)
1. **The substrate pattern.** Every raw item (article / clipping / clip) is decomposed into the SAME
   child shapes — claims, quotes, stances, numbers, events, locations — each FK'd back to its parent by
   `<item>_id`. To get "everything extracted from item X," join the parent to its `*_claims/_quotes/...`
   children. The three pillars are deliberately parallel so logic ports across them.
2. **Entity resolution chain.** spaCy writes surface forms into `articles.entities_extracted` →
   `entity_lookup` maps a normalized surface form to a canonical `entity_id` → `entity_dictionary` holds
   the canonical entity → the matview `article_entity_mentions` is the **shared, alias-resolved surface
   every product joins to** (mirrored per pillar as `clipping_entity_mentions` / `youtube_clip_entity_mentions`,
   kept separate so CM/article metrics stay article-only). See [20-entities.md](20-entities.md).
3. **Embeddings.** The article vector column family lives on `articles`; the locked recipe is
   **`labse_embedding_v4`** = `sentence-transformers/LaBSE | v4-tr-title-1024` (translated-title input).
   The legacy `labse_embedding` column is **recipe-mixed** (two incompatible recipes) — filter by the
   recipe/revision before any cosine search. Clipping/clip embeddings are NOT on the v4 recipe → treat
   cross-pillar cosine as unreliable.
4. **Clustering.** The LIVE keeper is `story_clusters_v8` + `story_cluster_members_v8` + `story_edges_v8`
   (graph-rebuilt, ~200k clusters, ~80% same-event precision on surfaceable clusters). Enrichment and
   LLM generation hang off `story_id`. A nightly reversible janitor (`story_repair_log_v8`) splits/merges.
5. **Personalization.** `user_article_relevance` / `user_clip_relevance` / `user_cutting_relevance` /
   `user_govt_doc_relevance` hold per-(user, item) scores from the v3 scorer (`score_stage1`,
   `score_final` — NOT `score`).
6. **Two user systems (do not conflate).** `analytics.users` (night-desk product, RBAC via
   `is_super_admin`) and `public.users` + `public.user_profiles` (a separate/older system) share **zero
   FKs and zero ID overlap**. Most `public.user_*` tables FK to `public.users`.

## Conventions
- **Schemas:** `public` = ingestion/corpus + product tables; `analytics` = the clustering keeper, caches,
  and the night-desk user/RBAC system. (Read-only role `analytics_user` exists for the night-desk.)
- **PKs:** mostly UUID (`gen_random_uuid()`); some product tables use BIGSERIAL; a few small vocab tables
  are keyed by a text `name` (`topic_categories`) — see each table.
- **`_v8` suffix** = the current clustering generation. `_archive`/`_old` = prior generations (the
  pre-v8 ones were dropped; `story_clusters_archive` is KEPT because Chronicle still FKs to it).
- **Matviews** are refreshed every 30 min by `/etc/cron.d/rig-matview-refresh`
  (`article_entity_mentions`, `clipping_entity_mentions`, `mv_district_*`). They are invisible to
  `information_schema.tables` — query `pg_matviews`.
- **Row-count caveat:** `reltuples`/`n_live_tup` are estimates that read 0 for never-`ANALYZE`d tables.
  All counts here were taken from real `count(*)` or post-`ANALYZE` estimates.

## Access (for whoever maintains this)
`ssh -i ~/.ssh/rig_hetzner root@178.105.63.154` → `docker exec -i rig-postgres psql -U rig -d rig`.
Backend code is bind-mounted `/root/rig` → `/app` (FastAPI live API = `products/osint/backend`;
ingestion = `backend/`). Migrations: `scripts/migrations/NNN_*.sql`.
