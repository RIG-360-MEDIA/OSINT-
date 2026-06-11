# Data-Fix Execution Plan — `/brief` Readiness

Each task ships with: pre-flight check → execution → validation gate → /observe metric → rollback. **No task is marked done unless its gate passes.**

---

## Cheap data fixes (Group A — run first, all in parallel)

### Task 1 — Fix `is_future` contradictions (7,825 rows)
**Pre-flight:** verify column types + count current contradictions.
**Execution:** single SQL UPDATE setting `is_future = (effective_event_date > published_at::date)`.
**Gate:** post-UPDATE count of `is_future=TRUE AND effective_event_date < published_at::date - INTERVAL '60 days'` must drop from **7,825 → 0** (±5).
**Rollback:** save backup of `(id, is_future)` pairs before UPDATE; one SQL restore on failure.
**Observe metric:** `is_future_contradictions` counter in audit_run_*.json.

### Task 2 — Language re-detect on mistagged articles (9,346 rows)
**Pre-flight:** verify cld3 / fasttext available inside container.
**Execution:** Python script. For each `articles` row where `language_detected='en'` AND title regex matches `[ఀ-౿ऀ-ॿঀ-৿]`, run lang detector on title. UPDATE `language_detected`.
**Gate:** post-UPDATE count where `language_detected='en' AND title ~ '[ఀ-౿]'` drops to **0** for 100% Telugu sources (TV9 Telugu, Namasthe Telangana, NTV Telugu, HMTV, Mana Telangana).
**Rollback:** backup table `articles_lang_backup` before UPDATE.
**Observe metric:** Source Scorecard "languages" column distribution.

### Task 3 — Re-embed LaBSE collision groups (~437 + 4 smaller groups)
**Pre-flight:** confirm Ollama LaBSE model responsive; identify the 5 worst collision signatures.
**Execution:** for each article in top 5 collision groups, re-embed from `lead_text_translated` via Ollama; UPDATE `labse_embedding`.
**Gate:** post-embed, the worst signature's row count drops from 437 → ≤ 5 (any remaining collisions are legitimate near-duplicates).
**Rollback:** none needed — embedding overwrites are idempotent.
**Observe metric:** `labse_collisions` in known_bug_probes audit section.

### Task 4 — Placeholder-claim backfill (64,362 articles, ~24-48h)
**Pre-flight:** smoke test on 100 articles (already done — passed with 9.0 median judge score).
**Execution:** `scripts/backfill/refill_placeholder_claims.py` running on unified pool, detached.
**Gate (live):** `/observe` Quality Monitor `claims_placeholder_pct` drops from **74.2% → ≤ 1%**. LLM-judge median of 50 backfilled articles ≥ 8.
**Rollback:** state file is the rollback log; can replay/undo specific articles.
**Observe metric:** Quality Monitor live panel updates in real time.

---

## Medium build (Group B — run AFTER Group A done)

### Task 5 — Importance-score algorithm for events/clusters
**Pre-flight:** confirm clean event_clusters + clean article_claims.subject_text (Group A done).
**Execution:**
  - Add `importance_score real` column to `event_clusters`.
  - Formula: `(0.4 * log(source_count+1)) + (0.3 * log(article_count+1)) + (0.2 * novelty_score) + (0.1 * velocity_score)` where:
    - novelty_score = `1 - exp(-days_since_first_seen/3)` (high for fresh stories)
    - velocity_score = `articles_in_last_6h / max(articles_in_prior_18h, 1)`
  - Daily Celery task refreshes the score.
**Gate:** human spot-check the top 20 cluster headlines — at least 16/20 must be subjectively "actually important news today" (auditor reviews).
**Observe metric:** new "Top Importance" sub-panel on Story Pulse.

### Task 6 — Daily mention-aggregation task
**Pre-flight:** clean subject_text + speaker_name.
**Execution:**
  - New table `entity_mention_daily (entity_text, date, n_mentions, n_sources, n_quotes)`.
  - Celery task runs hourly, aggregates last 24h of claims/quotes/stances by `LOWER(subject_text)` etc.
  - 7-day rolling baseline stored alongside.
**Gate:** test query "top 50 entities last 24h" returns recognizable names; no entity has count > 80% of total (would suggest a placeholder remnant).
**Observe metric:** new "Trending Entities" panel.

### Task 7 — Watchlist matcher cron
**Pre-flight:** Task 6 done (uses the aggregation table).
**Execution:**
  - Hourly cron compares `user_watched_entities.entity_text` against `entity_mention_daily`.
  - Writes `user_notifications` rows.
**Gate:** seed a test user with watched entities ["Revanth Reddy", "Modi"]. Verify within 1 hour that notifications appear for both.
**Rollback:** TRUNCATE user_notifications; remove cron.
**Observe metric:** notification-delivery latency on dashboard.

### Task 8 — Contradiction-detection pipeline
**Pre-flight:** confirm `article_contradictions` table schema; identify why current pipeline produces only 1 row.
**Execution:**
  - Diagnose existing contradictions task (likely runs but extractor misses cases).
  - Build a daily job: for each multi-source event_cluster, run an LLM "do these two article snippets disagree?" prompt on pairs.
  - Write disagreements to `article_contradictions`.
**Gate:** ≥ 50 contradictions in last 7 days (vs current 1). Each must have valid `event_cluster_id`. Spot-check 20 — ≥ 15 must be genuine disagreements (not paraphrase variation).
**Observe metric:** new "Contradictions" panel.

---

## Per-task discipline

Every task follows this loop:
1. **Pre-flight:** confirm dependencies + take backup
2. **Run** the change
3. **Validate** against the gate
4. **Update /observe** so the metric is visible
5. **Stop and report to user.** Get green light before next task.

If a gate fails → roll back, diagnose, re-plan that task.
