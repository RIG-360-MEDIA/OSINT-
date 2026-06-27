# RIG DB — answers to the read-only app builder's field audit (2026-06-19)

Answered by the DB chat against the LIVE Hetzner `rig` database (verified with `count(*)` as the `rig`
role where it mattered). "VERIFIED" = I ran it today. "KNOWN" = from this session's work / project memory.
"UNKNOWN" = say so, don't guess.

---

## §0 TOP-PRIORITY

**0.1 — Is this the full production dataset? YES, and your "empty" pillars are NOT empty.** ⚠️ Biggest correction.
Real `count(*)` today (as `rig`): `cm_stance_scores`=**108,115**, `cm_lead_headlines`=**13,835**, `cm_issue_evidence`≈5,576, `cm_spokesperson_quotes`≈4,918, `cm_action_queue`≈726, `cm_issues`≈296; `social_posts`=**6,890**, `social_events`≈854, `social_monitors`≈297, `social_sentiment_daily`≈386; `govt_documents`=**392**, `govt_collection_runs`≈1,997, `govt_document_chunks`≈1,076; `districts`=**59**, `assembly_constituencies`=**29**; `dossier_finding`=**421**.
There is **no RLS** on these and `analytics_user` **has SELECT** (`has_table_privilege` = true). So your 0-rows reading is an **environment/connection artifact** — you were almost certainly pointed at a *different database or host*, not this `rig` DB. **Action: re-confirm your DSN points at the Hetzner `rig` DB and re-run `count(*)`.** The data is here.
- **Genuinely empty / never-analyzed (reltuples = -1, treat as planned-not-started):** `mandi_prices`, `weather_warnings`, `alerts`, `notification_*`, `user_watchlist`, `narrative_*`. Confirm with `count(*)`; these look unbuilt.

**0.2 — Cross-pillar embeddings: NOT comparable.** VERIFIED: `clippings.labse_embedding` and `youtube_clips_v2.labse_embedding` have **no recipe column** and were **NOT part of the v4 campaign** (which only re-embedded `articles` → `labse_embedding_v4`, recipe `v4-tr-title-1024`). Clippings embedded≈11,822, youtube≈4,994. So article-v4 ↔ clipping/clip cosine is a **recipe mismatch** — your "loose, noisy cross-pillar matches" are exactly that, not sparse data. **Do NOT trust cross-pillar cosine until clippings/youtube are re-embedded with v4.** No such re-embed is scheduled that I can confirm (UNKNOWN/none).

**0.3 — LIVE clustering = `analytics.story_clusters_v8`** (VERIFIED ≈200,183 cluster rows; this is the keeper we actively maintain). The auditor's "`story_clusters` (34,599)" is now **`story_clusters_archive`** (old, pre-swap) and `story_clusters_old`≈37,982 (rollback). `public.event_clusters` you saw is **`event_clusters_archive`** (6,859, archived product layer). **Two-layer model:** `story_clusters_v8` (event atoms, the live keeper) → a product/surfacing layer. `_v8copy`/`_v8shadow*`/`_fwdrun` are scratch/validation — ignore. Status: v8 = **promoted/live**; v8 is actively written by the graph forward loop (every 30 min) + nightly reconcile.

**0.4 — `v4-tr-title-1024` recipe.** KNOWN: model = `sentence-transformers/LaBSE` (VERIFIED `embedding_model`), input = **translated title** ("tr-title"). The vector is pgvector with an HNSW index on `labse_embedding_v4`, cosine ops (`<=>`), `hnsw.ef_search` set at query time (we use 120). **UNKNOWN/verify yourself:** the exact meaning of "1024" (LaBSE is natively 768-dim — "1024" is likely a recipe/version tag, NOT the dim; check `vector_dims(labse_embedding_v4)`), whether it's L2-normalized (assume cosine-ready since we use `<=>`), and exact HNSW `m`/`ef_construction`.

**0.5 — Stance direction: `actor` = the TARGET being talked about (directed sentiment).** KNOWN/CONFIRMED (your assumption is correct). This is a known footgun: naive scoring read the wrong rows. `intensity` = magnitude of the stance (0–1ish); treat as relative, not calibrated.

**0.6 — Freshness & frozen.** VERIFIED ~**11,773 articles/day** recently (range ~5–12K/day). v4 embed coverage 336,048/353,764 = **95%**. KNOWN frozen/broken (per known-issues; re-verify current state): **entity extraction froze ~06-11** (a deleted module `backend.nlp.cm` that `nlp_processor` still imported — fix = optional import + backlog reset), **`thread_id` froze ~05-25** (separate), **`quote_text_en` essentially never populated** (VERIFIED only **202** rows have it). Matviews (`article_entity_mentions`, `mv_cm_*`, `mv_district_*`) refresh via cron every **30 min** (`/etc/cron.d/rig-matview-refresh`).

---

## §A Embeddings
- **A.1/A.3/K.2:** Use `labse_embedding_v4` ONLY. Legacy `labse_embedding` is **recipe-mixed (half built with the wrong recipe)** — do not use for similarity. The ~18K (now ~5%) missing v4 are low-value (junk/fetch_failed) or backfill tail. CONFIRMED.
- **A.2:** legacy `labse_embedding` + `labse_embedding_v0_backup` → safe to ignore (backup, likely droppable). No live feature should depend on them.
- **A.4:** `embedding_model`/`embedding_revision`/`embedded_at` = version tracking. The 572 rows with revision `-`/git-hash are pre-lock stragglers; the canonical ≈335,476 are `LaBSE | v4-tr-title-1024`.
- **A.5:** `analytics.embed_ab*` = the embedding A/B experiment that selected v4. Scratch now — ignore.
- **A.6:** `fts` tsvector — UNKNOWN exact config (verify `pg_get_indexdef`); likely English/simple config on title+lead. For regional-language hybrid search, treat as weak — rely on v4 vectors + translated text.
- **A.7 (critical for you):** there is **no public query-embedding endpoint** I can confirm. To embed a user query with the exact recipe you must run `sentence-transformers/LaBSE` on the **translated** query string yourself (translate query → LaBSE → cosine vs `labse_embedding_v4`). Reproduce `v4-tr-title-1024` precisely or vectors won't align. (Ask the pipeline owner for the `embed_fill` recipe code — it's the source of truth.)

## §B articles (key ones; rest = KNOWN/standard)
- **B.1/K.1:** `substrate_status='ok'` = usable; clean set ≈ `substrate_status='ok' AND NOT is_duplicate`. `ok` ≠ `nlp_processed` (nlp_processed can lag/flag without full substrate). CONFIRMED working-set assumption.
- **B.4/K.5:** rely on `title` + `lead_text_translated` (English). `full_text_translated` ~17.5% = on-demand/sparse → don't depend on it. CONFIRMED.
- **B.5:** `topic_category_orig` = pre-rollup label; `topic_fine` rolls up → `topic_category`. ~21% OTHER = a real backlog being rescued (topic_fill task), not all unclassifiable. (See [[project_worldwide_build]] §2.)
- **B.7/K.4:** `register_emotion` measures **event-emotion (e.g. "alarm"), NOT hostility** — do NOT use it as a hostility/negativity signal; use `article_stances`. CONFIRMED.
- **B.12:** dedup `is_duplicate`/`duplicate_of` — reasonably trustworthy; `duplicate_of` should be set when `is_duplicate`. Verify a sample.
- **B.13:** `thread_id` = social-thread link; **frozen ~05-25** — treat as stale.
- **B.9/K.8:** `narrative_frame` (0%), `content_type` (always 'article'), `geo_secondary` → dead/ignore. CONFIRMED.

## §C substrate
- **C.1:** extractor = local spaCy + LLM (qwen-class) on the **English translation**; confidence is **not calibrated** — treat as ordinal.
- **C.3/K.6:** stances — `actor` = TARGET; canonical `stance` set is small (support/oppose/neutral-ish); ~45% have `actor_entity_id` (free-text actors resolvable later). CONFIRMED.
- **C.5:** `quote_text_en` translation **not happening** (202 rows) — assume absent. `char_offset` index the **translated** text (extraction runs on English). `is_direct` = direct quote flag (reasonably reliable).
- **C.6:** numbers `unit` mixing currency/percent/count with date/year/runs = **by design-ish but messy** (units come from extraction, not a controlled set) — filter to the unit class you need.

## §D entities
- **D.2/K.7:** aliases are **English/Latin only**; regional-language mentions are linked via **translate-then-extract** (extraction runs on the English translation). No native-script matching. CONFIRMED.
- **D.3:** `article_entity_mentions` is a **matview** (refresh ~30 min cron). Surface forms are Latin. The inline `entities_extracted` jsonb `{prominence, confidence}` exists but is **frozen since ~06-11** (entity-extraction break) → stale for recent articles. Use the matview for the entity feed (K.3 CONFIRMED).
- **D.4:** `entity_lookup` (9 Australian politicians) = **dead test stub** — ignore. CONFIRMED.
- **D.7:** `redirected_to` — always follow to canonical; chains are short (resolve transitively).
- **D.8:** `entity_aliases` (0), `entity_match_index` (0) = empty/scratch; `entity_merge_map_*`/`entity_dict_meta` = curation support. Verify before use.
- **D.5 disambiguation:** entity dictionary + alias matching; **no strong contextual disambiguation** — wrong-entity bleed (Modi person vs Modinagar town) is a real risk; use entity_type + co-occurring entities to guard.

## §E clustering (KNOWN — this is our area)
- **E.2:** `attach_score` = edge/merge confidence of the member; `is_representative` = the cluster's lead article (highest-degree/centroid); `is_canonical`/`provisional` = lifecycle flags; representative chosen by centrality.
- **E.3:** `is_template_family` = **spam/template piles** (recipes, horoscopes, listicles, scorecards) — exclude for UX. `importance_score` is the engine's raw score (the front page uses its OWN recency-gated ranking, not this). `languages` histogram = reliable for cross-language framing.
- **E.10 (critical):** clippings & youtube are **clustered SEPARATELY** from articles (and cross-pillar cosine is unreliable, see 0.2) — there is **no joint article+clipping+clip event clustering** today.
- **E.7:** `story_clusters_old`, `analytics._*` (`_cand_pairs`, `_win`, `_sc`, `_v9_*`, `_fwd*`, `_reconcile_snap_*`) = scratch/rollback — ignore.
- **E.5/E.6:** ~47% clustered; singleton tail is expected (single-source events). Story enrichment (`story_facts_v8`/timeline/etc.) covers only the **surfaceable** set (`NOT is_template_family AND indep_src>=3`) and only when the **extraction phase** runs — it lags new clusters. You CAN derive a timeline from member `published_at` for any cluster.

## §F users / personalization
- **F.1:** `analytics.users` (VERIFIED **6** rows) is the live night-desk auth; `public.users`(3)/`user_profiles`(empty) is a **second, mostly-dead** system. **There are TWO user systems with ~no overlap** — `analytics.users` is canonical for night-desk. (Known 2-system split.)
- **F.2:** `user_article_relevance` = **1 distinct user** (VERIFIED; 317K rows = 1 user × corpus). Scoring is **batch per user** (relevance-v3); `score_stage1` = cheap prefilter, `score_final` = full; `relevance_explanation` = LLM-written. Only wired for 1 user so far.
- **F.4:** same scorer extended to `user_cutting_relevance`(≈6,895) and `user_clip_relevance`(≈4,448) — both populated.
- **F.6:** `user_story_assignments` = the admin-pushed **Chronicle** feature.

## §G clippings / youtube
- **G.1/G.2:** `clippings` is LIVE (newspaper PDFs, embedded-text-layer anchored, OCR fallback); `text_source` = text/layout/none anchoring method; `newspaper_clippings`/`editions`/`sources`(0) = deprecated. Embedding recipe ≠ v4 (see 0.2).
- **G.5/G.6:** `youtube_clips_v2` LIVE; `youtube_clips`(v1) legacy. `pending_youtube_videos`(≈7,619) = fetch backlog (relay-driven) — not needed by a read app.

## §H/§I freshness & empties
- **H/I:** ingestion ~12K articles/day. **Pillars are populated** (§0.1) — the political-intel (cm_*), social, and govt-docs pipelines are ALIVE. `govt_documents`=392 (not 15 — that stale number is wrong for this DB). Genuinely-unbuilt: mandi/weather/alerts/notifications/watchlist/narrative.

## §J access / scale
- **J.1:** `analytics_user` is read-only on this DB; for a new app prefer a dedicated SELECT-only role. (Memory: a `mc_readonly` pattern exists.)
- **J.2:** Yes — create your **own writable schema** on this server for app/user state; NEVER write the corpus. (Code is bind-mounted; DB is shared — coordinate.)
- **J.3:** This is the **LIVE production box (15 GB RAM, shared with Celery + the product)**. HNSW at app scale is OK but heavy concurrent vector+hybrid load CAN impact the product. **No read-replica exists** — throttle, cache, and avoid scans. Strongly consider a replica before app traffic.
- **J.4:** `article_links`(12M)=extracted hyperlinks, `article_media`(3.8M)=images/media refs, `article_tweets`(12.7K)=embedded tweets. Not needed for a basic read product.

## §K confirm/correct
K.1 ✅ correct (`ok AND NOT is_duplicate`). K.2 ✅ v4 only. K.3 ✅ matview for entities (but note it's stale since the 06-11 freeze). K.4 ✅ register_emotion ≠ hostility. K.5 ✅ title+lead_translated. K.6 ✅ actor = TARGET. K.7 ✅ translate-then-extract. K.8 ✅ dead columns.

## Things you didn't ask but should know
- **The corpus is 353,764 articles (not 293K)** — your audit is on a stale/partial snapshot; another reason to re-confirm your connection (§0.1).
- **Clustering is being actively rebuilt** (graph forward loop live ~85% intra-precision; old v7 clusters being superseded). Cluster IDs in `_v8` are stable+additive but a full replay to a new keeper is planned — don't hard-code cluster_ids long-term.
- **Content generation** lives in `analytics.story_generated_v8` (headline/deck/body/topic per surfaceable cluster) — if you want pre-written article text, read that, gated on `status='PUBLISHABLE'`.
