# 20 — Entities & Entity Resolution

> **Resolution chain (read this first):**
> spaCy extracts surface forms into `articles.entities_extracted` (a JSONB array of `{name, label}` objects).
> Each surface form is lower-cased + trimmed and looked up in `entity_lookup` (55 k rows, exact string match on `name_norm`).
> A match yields an `entity_id` pointing into `entity_dictionary` (the canonical vocabulary, 19 k rows, 5 types).
> `article_entity_mentions` is a materialised view that performs this JOIN at refresh time and exposes one row per `(article_id, entity_id)` pair — it is the **single join surface** every product should use for entity matching (1.3 M rows, refreshed by `refresh_article_entity_mentions()`).
> `entity_mention_daily` (320 k rows) aggregates mentions cross-pillar (articles + clippings + clips) into a daily time series for trending/dashboards. `user_watched_entities` maps users to specific entities with ally/opponent framing for personalised views. `analytics.entity_image` holds cached image URLs for entity profile pages.

---

### public.entity_dictionary — [LIVE] (~19,356 rows, 17 MB)

**Purpose:** Canonical entity vocabulary. One row per unique real-world entity. The authoritative source of `entity_id` used as FK across all entity-aware tables.
**Populated by:** Seed scripts (`source` = `seed:au_v1`, `seed:in_v1`, etc.), NLP enrichment tasks, and admin tooling. Migration 095 (2026-06-04) added `redirected_to` for duplicate merges.
**Read by:** `entity_lookup` (FK), `user_watched_entities`, `article_stances`, `article_claims`, `article_quotes`, `clipping_stances/claims/quotes`, `newsroom_entity_mentions`, `coverage_gaps_daily`, all product UI layers.
**Freshness:** Entry count per `entity_dict_meta`: 17,066 as of 2026-06-08.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NOT NULL | gen_random_uuid() | PK. Referenced by entity_lookup, user_watched_entities, etc. |
| canonical_name | text | NOT NULL | — | Display name. e.g. `K. Chandrashekar Rao`, `Narendra Modi`, `Telangana` |
| entity_type | text | NOT NULL | — | One of: `person` (11,104), `organization` (4,242), `location` (2,364), `constituency` (1,194), `role` (452) |
| aliases | text[] | nullable | `'{}'` | Embedded aliases array (denormalised copy; canonical list is in `entity_lookup` + `entity_aliases`). e.g. `{KCR, "Chandrashekar Rao"}` |
| state | text | nullable | — | Indian state code for political entities. e.g. `telangana`, `andhra_pradesh`. NULL for non-India or orgs. |
| party | text | nullable | — | Political party affiliation. e.g. `Labor`, `BJP`, `BRS`. NULL for non-political. |
| metadata | jsonb | nullable | `'{}'` | Free-form extra fields. Content varies by entity type. |
| created_at | timestamptz | nullable | now() | Row creation time. |
| country | char(2) | nullable | — | ISO-3166-1 alpha-2. e.g. `IN`, `AU`, `US`. Note: some seed rows have `IN` incorrectly (inferred from samples). |
| source | text | nullable | — | Provenance tag. e.g. `seed:au_v1`, `seed:in_v1`, `manual`. |
| redirected_to | uuid | nullable | — | If set, this row is a deprecated duplicate; canonical row is `redirected_to`. Added migration 095 (2026-06-04). Kept for reversibility — do not DELETE. Consumers must filter `WHERE redirected_to IS NULL` to avoid double-counting. Currently ~N rows redirected (verify with `SELECT count(*) FROM entity_dictionary WHERE redirected_to IS NOT NULL`). |

**Joins:**
- `entity_lookup.entity_id → entity_dictionary.id` (FK; many lookups per entity)
- `user_watched_entities.entity_id → entity_dictionary.id`
- `entity_aliases` joined on `canonical_name` (text join, not UUID)
- `entity_dict_meta` tracks version/count of this table separately

**Notes:**
- Filter `WHERE redirected_to IS NULL` in all consumer queries unless doing provenance tracing.
- `aliases` column is denormalised. The proper alias resolution path is through `entity_lookup`.
- `entity_type` values are lowercase plain strings (not an enum); add a CHECK constraint if stricter validation is needed.

---

### public.entity_lookup — [LIVE] (~55,064 rows, 7 MB)

**Purpose:** Fast exact-match lookup table. Maps any known surface form (normalised) to a canonical `entity_id`. This is the hot-path table — millions of reads per day.
**Populated by:** Seeding scripts that emit one row per alias per entity. Aliases from `entity_dictionary.aliases` + `entity_aliases` are both denormalised here.
**Read by:** `article_entity_mentions` matview (JOIN on `name_norm`), NLP enrichment pipeline during entity extraction.
**Freshness:** Reflects the seeded + admin-updated state. Count confirmed 55,064 live rows.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| name_norm | text | NOT NULL (PK) | — | Lower-cased, trimmed surface form. e.g. `narendra modi`, `kcr`, `కేసీఆర్` (Telugu scripts supported). Composite PK with entity_id (inferred). |
| entity_id | uuid | NOT NULL (PK) | — | FK → entity_dictionary.id. Multiple name_norm rows can map to the same entity_id (many-to-one). |

**Joins:**
- `entity_lookup.entity_id → entity_dictionary.id`
- Used in matview: `JOIN entity_lookup el ON el.name_norm = lower(trim(e.elem->>'name'))`

**Notes:**
- No `created_at` column. Bulk-loaded; not auditable for individual row insertion time.
- 55,064 rows for 19,356 entities ≈ 2.84 aliases per entity on average.
- This table has **no index column listed in schema files** beyond the PK — confirm with `\d entity_lookup` that a B-tree index on `name_norm` exists, as a seq-scan on 55 k rows during matview refresh would be slow.
- `redirected_to` entities in `entity_dictionary` still have rows here pointing to the old entity_id; consumers should join through `entity_dictionary` and filter `redirected_to IS NULL`.

---

### public.entity_aliases — [LIVE] (~14 rows, 80 kB)

**Purpose:** Small curated override table for high-ambiguity aliases requiring editorial notes. Distinct from the bulk `entity_lookup` — this table stores *why* an alias is assigned to a specific entity (disambiguation notes), particularly for Telangana political figures where name collisions are common.
**Populated by:** Manual editorial curation only.
**Read by:** Seeding/rebuild scripts that generate `entity_lookup`. Not read at query time by the live pipeline.
**Freshness:** Static; 14 rows as of last schema dump.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NOT NULL | gen_random_uuid() | PK. |
| canonical_name | text | NOT NULL | — | Must match `entity_dictionary.canonical_name` exactly. e.g. `K. Chandrashekar Rao`, `K.T. Rama Rao` |
| alias | text | NOT NULL | — | The alias string. e.g. `KCR`, `కేసీఆర్`, `KTR`, `కేటీఆర్`, `Tarakarama Rao` |
| notes | text | nullable | — | Disambiguation note. e.g. `"ex-CM, BRS founder. NOT KTR."`, `"son of KCR — NOT KCR himself"` |
| region | text | nullable | — | Geographic scope of the alias. e.g. `telangana` |
| created_at | timestamptz | nullable | now() | Row creation time. |

**Joins:**
- `canonical_name` text-joins to `entity_dictionary.canonical_name` (no UUID FK; fragile to renames).

**Notes:**
- All 14 current rows are Telangana political figures (KCR, KTR). Includes Telugu-script aliases.
- The `notes` field is critical for disambiguation: KCR ≠ KTR is explicitly recorded here.
- This table feeds the seeding pipeline; it is **not** queried in the live resolution hot path.

---

### public.entity_match_index — [LIVE] (~65,144 rows, 8.6 MB)

**Purpose:** String-match candidate index. Contains one row per `(entity_id, match_str)` pair used for fuzzy/candidate entity resolution — supporting a broader set of match strings than `entity_lookup`'s exact normalised forms. The migration file was not found locally; purpose inferred from table comment and column names.
**Populated by:** Seeding/entity-update pipeline (inferred — no migration file found on disk).
**Read by:** Entity matching/NER enrichment code that performs candidate lookup before exact resolution (inferred).
**Freshness:** 65,144 rows, 65,144 distinct entity IDs confirmed live.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| ent_id | uuid | nullable | — | FK → entity_dictionary.id (inferred). e.g. `b97c5226-ecac-4801-a8c2-c9336a66bb6e` (Anthony Albanese) |
| match_str | text | nullable | — | Candidate match string. e.g. `Anthony Albanese`, `Albanese` (broader than name_norm; may not be lower-cased — verify). |

**Joins:**
- `ent_id → entity_dictionary.id` (inferred FK, not declared in schema FKs file)

**Notes:**
- No migration SQL found in `scripts/migrations/` — likely created in `001_initial_schema.sql` or a migration not in the handoff dump.
- 65,144 rows vs 55,064 in `entity_lookup` suggests `entity_match_index` contains additional candidate forms not in the exact-match table.
- Column nullability `true` for both columns is unusual for a lookup table — verify that a compound unique index exists.
- **(inferred)** This table may support a pre-filter stage before exact `entity_lookup` resolution.

---

### public.entity_dict_meta — [LIVE] (1 row, 112 kB)

**Purpose:** Singleton version-tracking row for the entity dictionary. Allows consumers and monitoring to check whether `entity_dictionary` has been updated without scanning it.
**Populated by:** Entity seeding/update scripts that bump `version` and `entry_count` on each bulk load.
**Read by:** Monitoring, admin tooling, cache-invalidation logic (inferred).
**Freshness:** `last_updated_at` = 2026-06-08 22:32 UTC. `entry_count` = 17,066. `version` = 12,453 (note: `version` is an integer, not a semantic version — it may be a counter incremented per update batch).

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | integer | NOT NULL | 1 | PK, always = 1 (singleton). |
| version | integer | NOT NULL | 1 | Monotone counter incremented on each dictionary update. Current value: 12,453. |
| last_updated_at | timestamptz | nullable | now() | Timestamp of last bulk update. 2026-06-08 22:32:32 UTC. |
| entry_count | integer | nullable | 0 | Snapshot of entity count at last update. 17,066 (slightly lower than live 19,356 — indicates entities were added after the last meta update). |
| updated_by | text | nullable | `'system'` | Who triggered the update. Current: `system`. |

**Joins:** None. Standalone singleton.

**Notes:**
- `entry_count` (17,066) < live `entity_dictionary` count (19,356): ~2,290 entities added since the last meta refresh. Scripts should call a meta-update step after bulk inserts.
- `version` = 12,453 with `id` = 1 — `version` is a high-value integer counter, not a semantic version string.

---

### public.entity_mention_daily — [LIVE] (~320,554 rows, 97 MB)

**Purpose:** Per-entity per-day aggregated mention counts across all pillars. Powers `/brief` trending, watchlist matchers, per-entity dashboards, and Mission Control entity pages. Migration 113 extended this from articles-only to cross-pillar (articles + clippings + clips).
**Populated by:** `backend/tasks/entity_mention_task.py`, runs hourly. Draws from `article_claims.subject_text`, `article_quotes.speaker_name`, `article_stances.actor` (articles pillar) + `entities_extracted` across all three pillars (migration 113).
**Read by:** `/brief` trending endpoint, Mission Control entity page, watchlist matchers.
**Freshness:** min date 2026-04-16, max date 2026-06-19. Actively updated (confirmed today's date has rows).

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NOT NULL | gen_random_uuid() | PK. |
| entity_text | text | NOT NULL | — | LOWER()'d surface form (not an entity_id — text join only). e.g. `iran`, `donald trump`, `narendra modi` |
| date | date | NOT NULL | — | `collected_at::date` bucket. UNIQUE with entity_text. e.g. `2026-06-19` |
| n_claims | integer | NOT NULL | 0 | Count of `article_claims` rows where subject matches this entity/day. e.g. `iran` on 2026-06-19: 135 |
| n_quotes | integer | NOT NULL | 0 | Count of `article_quotes` rows where speaker matches. e.g. `donald trump`: 168 |
| n_stances | integer | NOT NULL | 0 | Count of `article_stances` rows where actor matches. e.g. `iran`: 189 |
| n_sources | integer | NOT NULL | 0 | Distinct source count for this entity/day. e.g. `iran`: 125 |
| n_mentions_total | integer | nullable | computed | **STORED GENERATED COLUMN** = `n_claims + n_quotes + n_stances`. e.g. `iran`: 324, `donald trump`: 638 |
| computed_at | timestamptz | NOT NULL | now() | When this row was last recalculated. |
| n_entities | integer | NOT NULL | 0 | Count of `entities_extracted` raw mentions across articles+clippings+clips (added migration 113). e.g. `iran`: 512, `united states`: 321. Rank by `n_mentions_total + n_entities`. |

**Joins:**
- `entity_text` text-joins to `entity_lookup.name_norm` or `entity_dictionary.canonical_name` (no FK — text only). This means entity renames do NOT auto-propagate here.

**Notes:**
- UNIQUE constraint on `(entity_text, date)` — upsert pattern used by the hourly task.
- `n_mentions_total` is a stored generated column (cannot be inserted directly). Index: `(date DESC, n_mentions_total DESC)`.
- Migration 113 added a second ranking index: `(date DESC, (n_claims+n_quotes+n_stances+n_entities) DESC)`.
- **No FK to entity_dictionary** — text-based join only. Entity merges/renames do not cascade here.
- `clipping_entity_mentions` and `youtube_clip_entity_mentions` tables do **not exist** as separate tables (confirmed by DB query returning no rows). Cross-pillar data flows into this table via `n_entities`, not separate mirror tables.

---

### public.user_entities — [LIVE] (~64 rows, 80 kB)

**Purpose:** Per-user personal entity watchlist with free-text context. Older/lighter alternative to `user_watched_entities` — stores user-defined entities that may not exist in `entity_dictionary` (uses `canonical_name` text, not UUID FK). Supports the Analyst/RAG persona context.
**Populated by:** User UI actions (entity watch configuration).
**Read by:** Analyst pillar, personalisation logic.
**Freshness:** 64 rows. Lightly used.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NOT NULL | gen_random_uuid() | PK. |
| user_id | uuid | NOT NULL | — | FK → users.id. |
| canonical_name | text | NOT NULL | — | Entity name as entered by user. May not match entity_dictionary exactly. |
| entity_type | text | NOT NULL | — | User-supplied type. Observed values: `topic` (36), `person` (12), `scheme` (6), `organisation` (6), `project` (2), `place` (2). Note: `organisation` spelling differs from `organization` in entity_dictionary. |
| aliases | text[] | nullable | `'{}'` | User-defined aliases for this entity. |
| why_watching | text | nullable | — | Free-text user note on why they're tracking this entity. |
| priority | integer | nullable | 5 | User-set priority weight (1–10 inferred). Default 5. |
| created_at | timestamptz | nullable | now() | Row creation time. |

**Joins:**
- `user_id → users.id`
- No FK to `entity_dictionary` — text only.

**Notes:**
- `entity_type` values include `topic`, `scheme`, `project` — broader than `entity_dictionary`'s 5 types.
- This table is largely superseded by `user_watched_entities` for entities that exist in the dictionary.

---

### public.user_watched_entities — [LIVE] (~466 rows, 200 kB)

**Purpose:** Per-user bucketed entity assignments for personalised framing (ally/opponent/neutral) and relevance scoring. The primary personalisation signal for article relevance, breaking-band alignment, journalist-bias, and home page competitor row. Created migration 068.
**Populated by:** User onboarding/settings UI (`source` = `manual`), auto-promotion on first entity surface (`auto_promote`), party-based auto-assignment (`auto_party`), geographic auto-assignment (`auto_geo`).
**Read by:** Relevance v3 scorer, night-desk home page, breaking band, journalist-bias alignment.
**Freshness:** 466 rows. Distribution: neutral 271, watched 116, ally 49, opponent 30. Actively populated.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| user_id | uuid | NOT NULL (PK) | — | FK → users.id (composite PK with entity_id). |
| entity_id | uuid | NOT NULL (PK) | — | FK → entity_dictionary.id ON DELETE CASCADE. |
| bucket | text | NOT NULL | — | CHECK: `ally` \| `opponent` \| `neutral` \| `watched` \| `passive`. `ally`/`opponent` = political framing; `watched` = locations/orgs/constituencies; `passive` = auto-promoted, awaiting user review. |
| weight | smallint | NOT NULL | 5 | Relative importance weight for relevance scoring. |
| source | text | nullable | — | `auto_party` \| `auto_geo` \| `manual` \| `auto_promote` |
| added_at | timestamptz | NOT NULL | now() | When the row was created. |

**Joins:**
- `user_id → users.id`
- `entity_id → entity_dictionary.id` (ON DELETE CASCADE)
- Indexes: `(user_id, bucket)` and `(entity_id)`

**Notes:**
- Composite PK `(user_id, entity_id)` — one bucket assignment per user per entity.
- `passive` bucket is the auto-promote staging area; UX should prompt users to classify passive entities.
- `neutral` (271) dominates because auto-assigned entities default to neutral until user acts.

---

### public.article_entity_mentions — [LIVE MATVIEW] (~1,307,767 rows, 292 MB)

**Purpose:** The canonical cross-reference between articles and resolved entities. Every product that needs "which entities appear in article X" or "which articles mention entity Y" should JOIN to this view. Resolves `articles.entities_extracted` JSONB surface forms through `entity_lookup` to `entity_dictionary`. **Not a regular table — a PostgreSQL materialised view.** Refreshed by calling `refresh_article_entity_mentions()`.
**Populated by:** `refresh_article_entity_mentions()` function (called by NLP pipeline after entity extraction, and by a 30-min matview refresh cron on Hetzner).
**Read by:** All product pages doing entity filtering; relevance scorer; article_stances join pipelines; analytics queries.
**Freshness:** 1.3 M rows. Refreshed on a 30-minute cron (`/etc/cron.d/rig-matview-refresh`). Stale window up to 30 min.

**Materialised view definition (verified from DB):**
```sql
SELECT a.id AS article_id,
       el.entity_id,
       ed.canonical_name,
       ed.entity_type,
       ed.country,
       array_agg(DISTINCT lower(trim(e.elem->>'name'))) AS surface_forms,
       count(*) AS mention_rows
FROM articles a
CROSS JOIN LATERAL jsonb_array_elements(a.entities_extracted) e(elem)
JOIN entity_lookup el ON el.name_norm = lower(trim(e.elem->>'name'))
JOIN entity_dictionary ed ON ed.id = el.entity_id
WHERE a.entities_extracted IS NOT NULL
  AND jsonb_typeof(a.entities_extracted) = 'array'
GROUP BY a.id, el.entity_id, ed.canonical_name, ed.entity_type, ed.country;
```

| column | type | nullable | meaning & example values |
|---|---|---|---|
| article_id | uuid | nullable | FK → articles.id. |
| entity_id | uuid | nullable | FK → entity_dictionary.id. |
| canonical_name | text | nullable | Denormalised from entity_dictionary. e.g. `Narendra Modi` |
| entity_type | text | nullable | Denormalised. e.g. `person`, `organization` |
| country | char(2) | nullable | Denormalised. e.g. `IN`, `US` |
| surface_forms | text[] | nullable | All distinct lower-cased surface forms that triggered this match in the article. e.g. `{modi, narendra modi}` |
| mention_rows | bigint | nullable | Count of JSONB array elements (entity mention occurrences) in the article that resolved to this entity. |

**Joins:**
- `article_id → articles.id`
- `entity_id → entity_dictionary.id`
- This is the **output** of the resolution chain, not an input.

**Notes:**
- Because this is a matview, it does NOT update on INSERT to `articles`. A refresh cycle is required.
- Articles with `entities_extracted IS NULL` or not a JSONB array are excluded.
- `redirected_to` entities in `entity_dictionary` may appear in this view if `entity_lookup` still points to the old entity_id. Refresh after redirect migrations.
- `clipping_entity_mentions` and `youtube_clip_entity_mentions` **do not exist** as separate tables (verified live). Cross-pillar entity signal flows through `entity_mention_daily.n_entities` instead. This matview is **articles-only**.

---

### analytics.entity_image — [LIVE] (~134 rows, 96 kB)

**Purpose:** Cached image URLs for entity profile cards on the night-desk UI. One row per entity. Images fetched from external sources and stored with attribution metadata. Lives in `analytics` schema (read-write for analytics role, read-only for analytics_user).
**Populated by:** Image-fetch pipeline (inferred — likely a one-time or periodic admin script).
**Read by:** Night-desk entity profile pages, Mission Control entity display.
**Freshness:** `max(fetched_at)` = 2026-06-09 00:50 UTC. 118 ok=true, 16 ok=false (broken/missing images).

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| entity_id | uuid | NOT NULL (PK) | — | FK → entity_dictionary.id. One row per entity. |
| image_url | text | nullable | — | Absolute URL to image. May be null if fetch failed. |
| attribution | text | nullable | — | Attribution text (e.g. `Wikimedia Commons`, photographer name). |
| source | text | nullable | — | Source system or URL domain. |
| ok | boolean | NOT NULL | true | Whether the image URL is still reachable. 118 true, 16 false. |
| fetched_at | timestamptz | NOT NULL | now() | When the image was fetched/verified. Last: 2026-06-09 00:50 UTC. |

**Joins:**
- `entity_id → entity_dictionary.id` (inferred; no FK declared in schema FKs file — verify with `\d analytics.entity_image`)

**Notes:**
- `ok = false` rows (16) should be treated as "no image available" by the UI.
- Coverage: 134 images for 19,356 entities = ~0.7% coverage. Most entities have no image.
- Schema: `analytics` — accessible via `analytics_user` role (read-only) and `analytics` role (read-write).

---

## Resolution Chain Summary

```
articles.entities_extracted (JSONB array: [{name: "Modi", label: "PERSON"}, ...])
         │
         │  lower(trim(elem->>'name'))
         ▼
entity_lookup (name_norm → entity_id)          ← exact string match, 55k rows
         │
         │  entity_id
         ▼
entity_dictionary (canonical_name, entity_type, state, party, ...)   ← 19k canonical entities
         │
         │  materialised at refresh time
         ▼
article_entity_mentions (MATVIEW, 1.3M rows)   ← the shared join surface for all products
         │
         ├── user_watched_entities (per-user ally/opponent/neutral buckets)
         │         └── personalised relevance scoring, night-desk home page
         │
         └── entity_mention_daily (hourly agg, cross-pillar, 320k rows)
                   └── /brief trending, Mission Control entity page, watchlist matchers
```

**Cross-pillar note:** `article_entity_mentions` is articles-only. Clippings and YouTube clips contribute to entity signal exclusively via `entity_mention_daily.n_entities` (migration 113). There are no `clipping_entity_mentions` or `youtube_clip_entity_mentions` tables.
