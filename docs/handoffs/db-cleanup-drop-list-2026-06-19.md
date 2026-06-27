# RIG DB cleanup — verified drop list (2026-06-19)

## ✅ EXECUTED 2026-06-19 (owner said "do it") — outcome
**Backup taken first:** `/root/backups/pillars_drop_20260619.sql` (186 MB, all pillar data) →
restore with `psql -U rig -d rig -f /root/backups/pillars_drop_20260619.sql`. Fully reversible.

**DROPPED (verified gone, no live consumer):**
- Pillars: all `cm_*`, `social_*`, `govt_*`, `dossier_*`/`entity_dossier`, `narrative_*`, `story_threads`.
- Scratch: ~40 `analytics._*` experiment tables, 18 dated `public.*_bak/_backup` tables, 16 empty
  abandoned-feature tables, 19 story `_old`/`_archive`(enrichment)/`_v8copy`/`_v8shadow`/`_fwdrun` tables.
- Harmless collateral (CASCADE, 0 references): `mv_cm_*` matviews, views `worldwide_candidates` + `articles_to_dedup`.

**PROTECTED before dropping:** reassigned `story_facts_id_seq` / `story_quotes_id_seq` `OWNED BY` the LIVE
`story_facts_v8` / `story_quotes_v8` (the archive tables owned them — would have broken keeper inserts).

**FIXED:** `/etc/cron.d/rig-matview-refresh` — removed the 3 dead `mv_cm_*` refresh statements.

**KEPT (live FK refs — NOT safe to drop):**
- `analytics.story_clusters_archive` (34,599) — Chronicle FKs to it (`user_story_assignments`×2, `chronicle_cache`×1).
- `public.event_clusters_archive` — `article_events.event_cluster_id` FKs to it (398 rows).
- `mandi_prices`, `weather_warnings` — feed the live `mv_district_*` matviews.

**⚠️ DISCOVERED (pre-existing, NOT caused by cleanup):** `chronicle_router.py` queries `analytics.story_clusters`
/ `story_facts` / `story_timeline` / `story_quotes` / `story_stance` / `story_cluster_members` (UNSUFFIXED) —
**none of those exist**. The keeper was renamed to `story_clusters_archive` in a prior session and the router
never repointed. Chronicle is likely broken now → fix = repoint chronicle_router.py to the live `_v8` keeper
(+ migrate the 2 assignments / 1 cache row from archive story_ids to `_v8`). Separate task.

**Mistakes made + recovered:** (1) first scratch batch used `ON_ERROR_STOP` + `DROP TABLE` on a matview →
aborted whole txn → rolled back cleanly (no harm), re-ran per-statement. (2) broad `CASCADE` nearly hit live
objects → caught by the rollback, then protected sequences + deferred FK-bearing tables. **Nothing live broken.**

DB size after: **23 GB** (space frees as Postgres releases the table files).

---

**Original review list below (the plan). I did NOT drop the KEPT items above.** Take a `pg_dump` backup first.

## ⚠️ Read this first — why the "empty tables" audit was wrong
The field audit (and Postgres' own `reltuples`/`n_live_tup`) reported many tables as **0 rows** that are
actually **populated** — because those tables were **never `ANALYZE`d**, so the estimate defaults to 0.
I re-checked with real `count(*)`:
- `cm_stance_scores` = **108,115** · `cm_lead_headlines` = **13,835** · `cm_issue_evidence` = **5,810** · `cm_issues` = 296
- `social_posts` = **6,890** · `social_clusters` = 28 · `govt_documents` = **392** · `govt_document_chunks` = 1,148 · `govt_collection_runs` = 2,076
- `dossier_finding` = 421 · `entity_match_index` = **65,144** · `assembly_constituencies` = 29 · `analyst_sessions` = 192 · `user_watched_entities` = 466

**So the cm / social / govt / dossier pillars are NOT useless — they are real, populated data.** The "wrong
context" problem is **lack of documentation of what's live**, not junk data. **Do NOT drop those.** Dropping
them would delete real pillars. The genuine clutter is **scratch/backup/old tables**, below.

---

## TIER 1 — SAFE to drop (scratch / backup / dated / superseded). Big win, low risk.
These are backups, migration scratch, experiment leftovers, and superseded keeper generations. Confirm the
live version exists (it does: `story_*_v8` is the live keeper) and you don't need the rollback window, then drop.

### 1a. Dated backups (migration/experiment snapshots — pure clutter)
```
public.entities_extracted_bak_20260602            public.entity_dictionary_bak_20260602
public.entity_dictionary_bak_20260606             public.entity_dictionary_pre078_backup
public.entity_dictionary_pre079_backup            public.entity_dictionary_type_backup_20260528
public.article_locations_scope_backup_20260528    public.article_numbers_unit_backup_20260528
public.article_events_eed_backup_20260528         public.articles_embed_backup_20260523
public.articles_lang_backup_20260523              public.article_events_is_future_backup_20260523
public._backup_pre_category_a                      public._bak_articles_cols_20260526
public._bak_articles_dropped_cols_20260525t210851z public.dateline_backfill_20260606
public.entity_merge_map_20260606                   public._uk_sources_bak_20260618
analytics.entity_image_bak_20260609                analytics._b1_ime_bak_20260617
analytics.ubp_bak_amitshah_20260606                analytics._phantom_bak_clusters_20260617
analytics._phantom_bak2_20260617                   analytics._phantom_bak_gen_20260617
```

### 1b. Superseded keeper generations (OLD/ARCHIVE) — ⚠️ these were the keeper-swap ROLLBACK (Jun 2–3, ~2.5wk old)
Confirm you don't need to roll back the clustering swap, THEN drop:
```
analytics.story_clusters_old        analytics.story_clusters_archive
analytics.story_cluster_members_old analytics.story_cluster_members_archive
analytics.story_edges_old           analytics.story_edges_archive
analytics.story_quotes_archive      analytics.story_sources_archive
analytics.story_facts_archive       analytics.story_timeline_archive
analytics.story_geo_archive         analytics.story_stance_archive
analytics.story_enrichment_status_archive   public.event_clusters_archive
```

### 1c. This-session validation scratch (mine — safe to drop now)
```
analytics.story_clusters_v8copy            analytics.story_cluster_members_v8copy
analytics.story_clusters_v8shadow          analytics.story_clusters_v8shadow4
analytics.story_clusters_fwdrun            analytics.story_cluster_members_fwdrun
analytics.story_edges_fwdrun               analytics._reconcile_snap_1781845380
analytics._reconcile_snap_1781838692       analytics._gi_cand   analytics._gi_testset
analytics._v9_cand   analytics._v9_members   analytics._v9_members_pure
analytics._fwd_target   analytics._fwd_attach   analytics._fwd_generic
```

### 1d. Older clustering/eval scratch (analytics._* temp + experiment tables)
```
analytics._cand_pairs  analytics._rs_cand  analytics._win  analytics._sc  analytics._scl
analytics._clust  analytics._edge_stage  analytics._fixture_ids  analytics._eval_pairs
analytics._eval_tpl  analytics._fm_pairs  analytics._fm9  analytics._src_activate
analytics._mergeback_edges  analytics._mergeback_comp
analytics.embed_ab  analytics.embed_ab_sample  analytics.embed_ab_variants
analytics.pair_scores  analytics.pair_scores_watermark
analytics.hard_neg_candidates  analytics.hard_neg_candidates_v2  analytics.hard_neg_candidates_v3
analytics.dedup_val  analytics.dup_golden  analytics.dup_golden_v2  analytics.dup_overrides
```

## TIER 2 — EMPTY non-pillar tables (count(*)=0). Drop ONLY if the feature is abandoned (your call per-row).
These are genuinely empty AND not a populated pillar. Some may be **planned features** (dropping loses the
schema) or **app-referenced** (dropping breaks the next write). Decide per feature:
```
public.alerts                  public.notification_rules        public.notification_events
public.user_watchlist          public.user_breaking_now (1 row) public.audit_decisions
public.collections             public.collection_articles       public.mc_snapshots
public.mandi_prices            public.weather_warnings          public.newsroom_breaking_clusters
public.newsroom_briefs (2)     public.newsroom_channel_live_digest  public.newsroom_vod_caption_cache
public.narrative_clusters      public.narrative_cluster_members public.narrative_drafts
public.social_cluster_posts(?) public.brief_quality_scores
analytics.invites (1)  analytics.replay_clock (1)  analytics.article_signals_mv  analytics.dup_golden*(scratch)
```
(`narrative_*` = the abandoned old content-gen stage; `mandi/weather/alerts/notification/watchlist` = planned-
but-unbuilt district/alert features — safe to drop if you're not building them soon.)

## TIER 3 — FROZEN pillars (populated, but **0 writes in 14 days** = pipeline stopped). YOUR CALL.
Usage window = postmaster uptime **14 days**. These tables have rows but have NOT been written in ≥14 days,
and most are **barely read** (reads/14d shown) → stale data that feeds wrong/old context (your exact complaint).
**Decide per pillar: ABANDONED → drop; BROKEN-but-will-resume → keep + fix the pipeline** (several froze around
the same time as the 06-11 entity-extraction break — likely broken, not deliberately retired).

| Pillar / table | rows | reads/14d | verdict |
|---|---|---|---|
| `cm_stance_scores` | 108K | 660K | heavily read **only by `mv_cm_*` refresh** — check if anything reads those matviews; frozen |
| `cm_lead_headlines` | 14K | 20 | frozen + barely read → strong declutter candidate |
| `cm_issue_evidence` | 5.8K | 792 | frozen; some reads |
| `cm_issues / cm_spokesperson_quotes / cm_action_queue / cm_coalitions / cm_political_handles / cm_promises / cm_risk_calendar / cm_counter_narratives / cm_dissent_signals / cm_analysis_drafts` | small | ~19–20 | frozen + ~unread → declutter candidates |
| `social_posts` | 6.9K | 100 | frozen; lightly read |
| `social_events / social_monitors / social_sentiment_daily / social_entity_baselines / social_summaries / social_clusters / social_cluster_posts / social_topic_seeds / social_geo_seeds / social_topics / social_post_districts` | mixed | ~19–77 | frozen + ~unread → declutter candidates |
| `govt_documents` | 392 | 2,218 | frozen; read — documents pillar (you said this once had ~15 rows — it's 392 here) |
| `govt_document_chunks / govt_collection_runs / govt_document_sources` | 1.1K/2K/50 | ~20–254 | frozen |
| `dossier_finding / dossier_cache / dossier_audit_log` | 421/22/8 | ~20 | frozen + ~unread |
| `narrative_clusters / narrative_cluster_members / narrative_drafts` | 0 | ~22 | empty + dead (old content-gen stage) → drop (also in Tier 2) |

**How to decide quickly:** for each, ask "is there a live product page that reads it THIS week?" If no (and
writes=0), it's stale clutter. The cm_* matview chain (`mv_cm_*`) is the one to actually trace — if those
matviews aren't read by a live API, the whole CM pillar (108K stance rows included) is orphaned and droppable.

### CONSUMER CHECK (grep of live API `products/osint/backend` vs ingest `backend`) — 2026-06-19
**No live night-desk API reads ANY of these (live-API refs = 0). They're only touched by FROZEN ingest code.**
So they're safe to drop *from the product's view* — but dropping a table that ingest code references means you
are **abandoning that pipeline** (remove/disable the collector code too, or it errors if restarted).
- `cm_lead_headlines` → **0 refs anywhere** = truly orphaned → **drop outright.**
- `dossier_finding` → **0 refs anywhere** = truly orphaned → **drop outright.**
- `cm_stance_scores`,`cm_issue_evidence` → live-API 0, ingest 1 → drop IF abandoning the **CM political-intel** pipeline.
- `social_*` (social_posts ref'd in 15 backend files) → live-API 0 → drop IF abandoning the **Signals** pipeline.
- `govt_*` (govt_documents ref'd in 22 backend files) → live-API 0 → drop IF abandoning the **Documents** pipeline.
- `narrative_*` → empty + dead → drop.
**cm = "political intelligence" pillar:** `cm_stance_scores`=actors' stance on issues (feeds mv_cm_voice_share/
heatmap/exploitation-index); `cm_lead_headlines`=curated headlines per issue; `cm_issue_evidence`=article
citations per issue. Powered a political dashboard that the live night-desk does NOT serve.

### story_threads — SAFE TO DROP (corrected 2026-06-19)
Earlier I flagged it "live-served" based on a grep file-match — **that was wrong.** The live API's only mentions
are **comments**, and `stories.py:674` explicitly says the endpoint *"deliberately does NOT use the story_threads
engine."* So **no live code queries it**; the ~274/day reads are background/cron/audit. It's frozen (newest
2026-05-25) + blobby (29,798-article thread) + only the **frozen ingest thread-builder** writes it. → **Drop it.**
Its "part" is the `articles.thread_id` column (frozen) — leave that column (dropping a column off the live
`articles` table is riskier and it's harmless empty/frozen), or drop it later in a low-traffic window.
(If you DO want the "whole-saga" feature later, it's a fresh REBUILD on the clean event clusters anyway — the
current 7,409 blobby threads have no salvage value.)

## ❌ DO NOT DROP — genuinely LIVE + used (rows + reads + recent writes in the 14d window)
(cm_/social_/govt_/dossier_ moved to TIER 3 above — they're populated but FROZEN, so they're a *judgement
call*, not "keep". Below are the ones with real, recent activity.)
```
LIVE clustering (written today):  analytics.story_clusters_v8 / story_cluster_members_v8 / story_edges_v8 /
                  story_facts_v8 + story_timeline/sources/quotes/geo/stance/enrichment_status _v8 + story_generated_v8
Entity/reference (heavily read):  public.districts (87M reads) · entity_dictionary (14M reads, written 06-06) ·
                  entity_lookup (15M reads — NOT a dead stub; my earlier call was WRONG, re-investigate) ·
                  entity_mention_daily (5.3M reads, WRITTEN TODAY) · entity_match_index (65K rows, 2.6K reads) ·
                  entity_dict_meta · entity_image · article_entity_mentions (mv)
Users/personalize (active):       analytics.users(6) · user_article_relevance(317K) · user_clip_relevance ·
                  user_cutting_relevance · user_watched_entities(466) · public.analyst_sessions(192) · user_brief_prefs
Corpus (the substrate):           articles · clippings · youtube_clips_v2 · article_claims/stances/quotes/numbers ·
                  article_links/media/tweets · article_events
```
**Correction to the audit doc:** `entity_lookup` is **15M reads in 14 days** → it is on a hot path, NOT a dead
9-row test stub. Do not drop; figure out what reads it (it may be a critical lookup the app depends on).

---

## CONSOLIDATED DROP SCRIPT (owner-approved 2026-06-19) — run AFTER a backup. I did NOT run this.
Owner decision: drop `story_threads` + the frozen CM / Signals / Documents / dossier pillars + orphans + scratch.
**Consequence:** the frozen ingest pipelines that write these (social/govt/CM collectors, thread-builder) will
**error if ever restarted** — so disable/remove those Celery tasks too (they're frozen now, so no live break).
None of these are read by the live night-desk API (verified by grep of `products/osint/backend`).

```sql
-- 0) BACKUP FIRST (one dump of everything you're about to drop):
--    pg_dump -U rig -d rig -t 'public.cm_*' -t 'public.social_*' -t 'public.govt_*' -t 'public.dossier_*' \
--      -t 'public.narrative_*' -t 'public.story_threads' -t 'analytics._*' -t 'analytics.*_old' \
--      -t 'analytics.*_archive' -t 'analytics.*_v8copy' -t 'analytics.*shadow*' -t 'public.*_bak*' \
--      -t 'public.*_backup*' -f /root/backups/drop_20260619.sql

BEGIN;
-- pillars (owner-approved; not live-served)
DROP TABLE IF EXISTS public.cm_stance_scores, public.cm_lead_headlines, public.cm_issue_evidence,
  public.cm_issues, public.cm_spokesperson_quotes, public.cm_action_queue, public.cm_coalitions,
  public.cm_political_handles, public.cm_promises, public.cm_risk_calendar, public.cm_counter_narratives,
  public.cm_dissent_signals, public.cm_analysis_drafts CASCADE;
DROP TABLE IF EXISTS public.social_posts, public.social_events, public.social_monitors,
  public.social_sentiment_daily, public.social_entity_baselines, public.social_summaries, public.social_clusters,
  public.social_cluster_posts, public.social_topic_seeds, public.social_geo_seeds, public.social_topics,
  public.social_post_districts CASCADE;
DROP TABLE IF EXISTS public.govt_documents, public.govt_document_chunks, public.govt_collection_runs,
  public.govt_document_sources CASCADE;
DROP TABLE IF EXISTS public.dossier_finding, public.dossier_cache, public.dossier_audit_log,
  public.entity_dossier CASCADE;
DROP TABLE IF EXISTS public.narrative_clusters, public.narrative_cluster_members, public.narrative_drafts CASCADE;
DROP TABLE IF EXISTS public.story_threads CASCADE;   -- frozen, blobby, not live-served
COMMIT;

-- Tier-1 scratch/backup/old/archive (run after confirming clustering rollback window is closed):
BEGIN;
DROP TABLE IF EXISTS
  analytics.story_clusters_old, analytics.story_cluster_members_old, analytics.story_edges_old,
  analytics.story_clusters_archive, analytics.story_cluster_members_archive, analytics.story_edges_archive,
  analytics.story_quotes_archive, analytics.story_sources_archive, analytics.story_facts_archive,
  analytics.story_timeline_archive, analytics.story_geo_archive, analytics.story_stance_archive,
  analytics.story_enrichment_status_archive, public.event_clusters_archive,
  analytics.story_clusters_v8copy, analytics.story_cluster_members_v8copy, analytics.story_clusters_v8shadow,
  analytics.story_clusters_v8shadow4, analytics.story_clusters_fwdrun, analytics.story_cluster_members_fwdrun,
  analytics.story_edges_fwdrun, analytics._cand_pairs, analytics._rs_cand, analytics._win, analytics._sc,
  analytics._scl, analytics._clust, analytics._edge_stage, analytics._fixture_ids, analytics._eval_pairs,
  analytics._eval_tpl, analytics._fm_pairs, analytics._fm9, analytics._src_activate, analytics._mergeback_edges,
  analytics._mergeback_comp, analytics._gi_cand, analytics._gi_testset, analytics._v9_cand, analytics._v9_members,
  analytics._v9_members_pure, analytics._fwd_target, analytics._fwd_attach, analytics._fwd_generic,
  analytics.embed_ab, analytics.embed_ab_sample, analytics.embed_ab_variants, analytics.pair_scores,
  analytics.pair_scores_watermark, analytics.hard_neg_candidates, analytics.hard_neg_candidates_v2,
  analytics.hard_neg_candidates_v3, analytics.dedup_val, analytics.dup_golden, analytics.dup_golden_v2,
  analytics.dup_overrides, analytics.entity_image_bak_20260609, analytics._b1_ime_bak_20260617,
  analytics.ubp_bak_amitshah_20260606, analytics._phantom_bak_clusters_20260617, analytics._phantom_bak2_20260617,
  analytics._phantom_bak_gen_20260617
  CASCADE;
DROP TABLE IF EXISTS analytics._reconcile_snap_1781845380, analytics._reconcile_snap_1781838692 CASCADE;
-- public scratch/backups:
DROP TABLE IF EXISTS public.entities_extracted_bak_20260602, public.entity_dictionary_bak_20260602,
  public.entity_dictionary_bak_20260606, public.entity_dictionary_pre078_backup,
  public.entity_dictionary_pre079_backup, public.entity_dictionary_type_backup_20260528,
  public.article_locations_scope_backup_20260528, public.article_numbers_unit_backup_20260528,
  public.article_events_eed_backup_20260528, public.articles_embed_backup_20260523,
  public.articles_lang_backup_20260523, public.article_events_is_future_backup_20260523,
  public._backup_pre_category_a, public._bak_articles_cols_20260526,
  public._bak_articles_dropped_cols_20260525t210851z, public.dateline_backfill_20260606,
  public.entity_merge_map_20260606, public._uk_sources_bak_20260618 CASCADE;
-- empty abandoned features (optional):
DROP TABLE IF EXISTS public.alerts, public.notification_rules, public.notification_events, public.user_watchlist,
  public.user_breaking_now, public.audit_decisions, public.collections, public.collection_articles,
  public.mc_snapshots, public.mandi_prices, public.weather_warnings, public.newsroom_breaking_clusters,
  public.newsroom_briefs, public.newsroom_channel_live_digest, public.newsroom_vod_caption_cache,
  analytics.invites, analytics.replay_clock, analytics.article_signals_mv CASCADE;
COMMIT;

ANALYZE;   -- so pg_class/reltuples stop reporting live tables as 0 rows (root cause of the bad audit)
```
**After dropping:** also disable the now-dead Celery tasks (CM `tasks.cm.*`, social collectors, govt collectors,
the thread-builder) so Beat doesn't try to write vanished tables. And re-point any `mv_cm_*` matviews / consumers.

## How to drop safely (after review)
1. **Backup first:** `pg_dump -U rig -d rig -t '<table>' -f /root/backups/<table>.sql` (or dump all Tier-1 at once).
2. Drop in a transaction so a FK surprise rolls back:
   `BEGIN; DROP TABLE IF EXISTS analytics._cand_pairs CASCADE; ... COMMIT;`
3. **Run Tier 1 first** (pure clutter). Hold Tier 2 until you confirm each feature is abandoned.
4. After dropping, `ANALYZE;` so future stats are accurate (this whole mess came from un-analyzed tables).

## Root-cause fix for the "wrong context" problem
Dropping scratch helps, but the real fix is **documentation + accurate stats**:
- Run `ANALYZE` across the DB so `count`/`reltuples` stop lying (then audits won't see live tables as "empty").
- Keep the `db-audit-answers-2026-06-19.md` (what's live vs stale) next to the schema so future readers don't
  treat populated-but-undocumented pillars (cm/social/govt) as junk.
