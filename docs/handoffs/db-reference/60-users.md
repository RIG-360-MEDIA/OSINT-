# 60 — Users, RBAC, Personalization & Analyst

## Overview (read first)

There are **two completely separate user systems** in this database with ~0 row overlap:

1. **`analytics.users` + `analytics.orgs`** — the night-desk / analytics product. Users here are staff accounts managed by invite; authorization is based on `is_super_admin` (boolean flag, no role column). Brief personalization lives in `analytics.user_brief_prefs`. The seeded super-admin is `pranavsinghpuri09@gmail.com`.

2. **`public.users` + `public.user_profiles`** — an older onboarding-style system. Only 3 rows live. `public.users.role` is `'user' | 'super_admin'` (text CHECK constraint). RBAC page-grants (`user_page_access`), impersonation audit (`impersonation_sessions`/`impersonation_actions`), and all per-user personalization tables (relevance scores, cards, analyst sessions) hang off `public.users`.

The two systems **do not share IDs**. Code that queries `analytics.users` cannot join to `public.user_profiles` without an explicit cross-schema lookup, and no FK connects them.

**Relevance model (v3 scorer):** per-user relevance rows exist for articles (323 k rows, 131 MB), clips (2.6 k), cuttings (6.9 k), and govt docs (274). Every row carries `score_stage1` (pre-geo), `score_final` (post geo-multiplier), `relevance_tier` (int bucket), `sentiment_for_user`, `geo_multiplier_applied`, and `matched_entity_names`. Scores are written by the `relevance` Celery queue.

---

## analytics.orgs — [LIVE] (~6 rows, 48 kB)

**Purpose:** Organisation groupings for analytics-product users.
**Populated by:** manual seeding / admin UI.
**Read by:** `analytics.users` FK, night-desk auth middleware.
**Freshness:** Small reference table; rows are stable.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| name | text | NO | — | Human name, e.g. `"RIG Newsroom"` |
| role_template | text | NO | — | Template name applied to new org members (inferred: org-level default role label) |
| notes | text | YES | — | Free-form admin notes |
| created_at | timestamptz | NO | now() | Row creation time |
| updated_at | timestamptz | NO | now() | Last modification time |

**Joins:** `analytics.users.org_id → analytics.orgs.id`

**Notes:** No `plan` or `slug` column exists (live-verified). `role_template` is a text label, not a FK to a roles table.

---

## analytics.users — [LIVE] (~6 rows, 80 kB)

**Purpose:** Staff/analyst accounts for the night-desk product. Separate from `public.users`.
**Populated by:** Admin invite flow; rows inserted by onboarding API.
**Read by:** Night-desk auth middleware, brief generation, `analytics.user_brief_prefs`.
**Freshness:** Stable reference; 6 accounts as of 2026-06-19.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NO | — | PK (no default — supplied by caller) |
| org_id | uuid | YES | — | FK → `analytics.orgs.id`; NULL = no org |
| email | text | NO | — | User e-mail address (do not dump values) |
| full_name | text | YES | — | Display name, e.g. `"Pranav Singh"` |
| designation | text | YES | — | Job title, e.g. `"Editor"` |
| is_super_admin | boolean | NO | false | True = platform super-admin; the seeded super-admin is `pranavsinghpuri09@gmail.com` |
| invited_by | uuid | YES | — | Self-referential FK → `analytics.users.id`; NULL for the first account |
| onboarded_at | timestamptz | YES | — | Timestamp when onboarding wizard completed |
| last_login_at | timestamptz | YES | — | Last successful login |
| created_at | timestamptz | NO | now() | Row creation time |
| updated_at | timestamptz | NO | now() | Last modification time |

**Joins:**
- `analytics.users.org_id → analytics.orgs.id`
- `analytics.users.invited_by → analytics.users.id` (self-referential)
- `analytics.user_brief_prefs.user_id → analytics.users.id`

**Notes:** There is **no `role` text column** here (live-verified — the error `column "role" does not exist` confirms it). Authorization is purely `is_super_admin`. Do NOT confuse with `public.users.role`.

---

## analytics.user_brief_prefs — [LIVE] (~5 rows, 328 kB)

**Purpose:** Per-user personalization preferences for the daily intelligence brief.
**Populated by:** Brief onboarding wizard (night-desk product).
**Read by:** Brief generation Celery task, brief API router.
**Freshness:** Updated whenever user changes preferences.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| user_id | uuid | NO | — | PK + FK → `analytics.users.id` |
| primary_subject_id | uuid | YES | — | Entity UUID the user primarily tracks (e.g. a politician's entity ID) |
| primary_subject_meta | jsonb | YES | — | Cached entity metadata for the primary subject (name, type, party, state) |
| watchlist | jsonb | NO | `'{}'` | List of watched entity UUIDs + metadata; structure: `{entity_ids: [...], entity_meta: [{id, name, type, party, ...}], auto_adjacents: bool}` |
| regions | jsonb | NO | `'{}'` | Geographic filter: `{states: ["Tamil Nadu"], countries: ["IN","PK"], districts: []}` |
| topics | jsonb | NO | `'{}'` | Topic include/exclude: `{include: ["SECURITY"], exclude: ["BUSINESS"]}` |
| languages | jsonb | NO | `'{}'` | Language preferences: `{read: ["en","kn"]}` |
| sources | jsonb | NO | `'{}'` | Source-level filter preferences |
| stance | jsonb | NO | `'{}'` | Editorial stance preferences |
| events | jsonb | NO | `'{}'` | Named-event tracking preferences |
| delivery | jsonb | NO | `'{}'` | Delivery schedule preferences (time, channel) |
| personality | jsonb | NO | `'{}'` | Brief personality / tone preferences |
| updated_at | timestamptz | NO | now() | Last preference update |

**Joins:** `analytics.user_brief_prefs.user_id → analytics.users.id`

**Notes:** All JSONB columns default to `{}` so the application always receives a valid object even for fresh accounts. `primary_subject_id` is an entity UUID from `public.entities` (inferred — no FK defined).

---

## public.users — [LIVE] (~3 rows, 96 kB)

**Purpose:** The older public-facing user system. Drives RBAC, impersonation, relevance scoring, cards, and the analyst chat.
**Populated by:** Supabase signup + onboarding confirm endpoint.
**Read by:** All public-schema personalization tables; impersonation; analyst.
**Freshness:** Only 3 rows live — this system is lightly used vs the analytics system.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| email | text | NO | — | User e-mail address (do not dump values) |
| role | text | NO | `'user'` | CHECK: `'user'` or `'super_admin'`; seeded super-admin is `pranavsinghpuri09@gmail.com` |
| created_at | timestamptz | YES | now() | Account creation time |

**Joins:**
- `public.user_profiles.user_id → public.users.id`
- `public.user_page_access.user_id → public.users.id`
- `public.impersonation_sessions.admin_id / target_user_id → public.users.id`
- `public.user_article_relevance.user_id → public.users.id` (and the other relevance tables)
- `public.analyst_sessions.user_id → public.users.id`
- `public.user_cards.user_id → public.users.id`
- `public.briefs.user_id → public.users.id`
- `public.user_entities.user_id → public.users.id`

**Notes:** No `password_hash` column — authentication is delegated to Supabase Auth. There is **no `is_active` column** (live-verified).

---

## public.user_profiles — [LIVE] (~1 row, 48 kB)

**Purpose:** Extended profile for `public.users` — geographic context, role description, and brief delivery preferences used by the v3 relevance scorer and brief system.
**Populated by:** Onboarding wizard (`/api/onboarding/confirm`).
**Read by:** Relevance scorer (geo weighting), brief generation.
**Freshness:** 1 row — very sparse population.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK (separate from user_id) |
| user_id | uuid | NO | — | FK → `public.users.id`; UNIQUE |
| raw_description | text | NO | — | Free-text user description of their role/focus |
| role_type | text | NO | — | Structured role category, e.g. `"journalist"`, `"analyst"` |
| organisation | text | YES | — | Employer / organisation name |
| geo_primary | text | NO | `''` | Primary geography of interest, e.g. `"Telangana"` |
| geo_secondary | text[] | YES | `'{}'` | Additional geographies of interest |
| signal_priorities | jsonb | NO | `'{}'` | Priority signals for feed ranking (inferred: topic/entity priority weights) |
| language_preferences | text[] | YES | `'{en}'` | Preferred content languages |
| brief_time | time | YES | `'06:00:00'` | Daily brief delivery time (local) |
| brief_timezone | text | YES | `'Asia/Kolkata'` | Timezone for brief delivery |
| role_context | text | NO | `''` | Additional context about the user's role (used in brief prompts) |
| created_at | timestamptz | YES | now() | Row creation time |
| updated_at | timestamptz | YES | now() | Last update time |

**Joins:** `public.user_profiles.user_id → public.users.id`

**Notes:** Despite being the primary personalization source for the v3 scorer, only 1 row exists — indicating most `public.users` have not completed the onboarding wizard.

---

## public.user_article_relevance — [LIVE] (~323,635 rows, 131 MB)

**Purpose:** Per-user relevance scores for articles. The dominant relevance table by volume — the v3 scorer writes one row per (user, article) pair.
**Populated by:** `worker-relevance` Celery queue, `tasks/relevance` module.
**Read by:** `/coverage` feed ranking, Entity page cross-pillar ranking.
**Freshness:** Continuously scored; freshest rows near `now()`.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| user_id | uuid | NO | — | FK → `public.users.id` |
| article_id | uuid | NO | — | FK → `public.articles.id` |
| score_stage1 | float8 | NO | 0.0 | Pre-geo score: canon + recency + mute components |
| score_final | float8 | NO | 0.0 | Post-geo score: `score_stage1 × geo_multiplier_applied` |
| relevance_tier | int | NO | 0 | Integer bucket (0=lowest); used for feed pagination |
| relevance_explanation | text | YES | — | Human-readable explanation of score factors |
| sentiment_for_user | text | YES | — | Sentiment of article toward user's tracked entities |
| geo_multiplier_applied | float8 | YES | — | Geo-weight factor applied; NULL means no geo boost/penalty |
| matched_entity_names | text[] | YES | `'{}'` | Entities from user's watchlist that matched in this article |
| scored_at | timestamptz | YES | now() | When the score was computed |

**Joins:**
- `user_article_relevance.user_id → public.users.id`
- `user_article_relevance.article_id → public.articles.id`

**Notes:** UNIQUE on `(user_id, article_id)`. Indexed on `(user_id, score_final DESC)` and `(user_id, relevance_tier)` for feed queries. 131 MB is the largest personalization table. The column is `score_stage1`/`score_final`, NOT `score` (a common mistake — the live sample confirmed `column "score" does not exist`).

---

## public.user_clip_relevance — [LIVE] (~2,604 rows, 2.99 MB)

**Purpose:** Per-user relevance scores for YouTube clips. Mirrors `user_article_relevance` structure; created in migration 114.
**Populated by:** `worker-relevance` queue, event-driven after clip enrichment.
**Read by:** `/clips` feed ranking, cross-pillar Entity page.
**Freshness:** Event-driven; clips scored after enrichment completes.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| user_id | uuid | NO | — | FK → `public.users.id` |
| clip_id | bigint | NO | — | FK → `public.youtube_clips_v2.id` |
| score_stage1 | real | YES | — | Pre-geo relevance score |
| score_final | real | YES | — | Post-geo relevance score |
| relevance_tier | smallint | YES | — | Tier bucket for pagination |
| relevance_explanation | text | YES | — | Score explanation text |
| sentiment_for_user | text | YES | — | Sentiment toward user's entities |
| geo_multiplier_applied | real | YES | — | Geo boost/penalty factor |
| matched_entity_names | text[] | YES | — | Matched watchlist entity names |
| scored_at | timestamptz | NO | now() | Score computation timestamp |

**Joins:**
- `user_clip_relevance.user_id → public.users.id`
- `user_clip_relevance.clip_id → public.youtube_clips_v2.id`

**Notes:** UNIQUE on `(user_id, clip_id)`. Uses `real` (float4) instead of `float8` unlike `user_article_relevance` — slightly lower precision. Indexed on `(user_id, relevance_tier)` and `(user_id, score_final DESC)`.

---

## public.user_cutting_relevance — [LIVE] (~6,895 rows, 3.15 MB)

**Purpose:** Per-user relevance scores for newspaper clippings. Mirrors clip/article relevance; created in migration 114.
**Populated by:** `worker-relevance` queue, event-driven after clipping enrichment.
**Read by:** `/cuttings` feed ranking, cross-pillar Entity page.
**Freshness:** Event-driven; coverage noted as "weak/geo-over-surface" in MEMORY.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| user_id | uuid | NO | — | FK → `public.users.id` |
| clipping_id | uuid | NO | — | FK → `public.clippings.id` |
| score_stage1 | real | YES | — | Pre-geo relevance score |
| score_final | real | YES | — | Post-geo relevance score |
| relevance_tier | smallint | YES | — | Tier bucket |
| relevance_explanation | text | YES | — | Score explanation |
| sentiment_for_user | text | YES | — | Sentiment toward user's entities |
| geo_multiplier_applied | real | YES | — | Geo boost/penalty factor |
| matched_entity_names | text[] | YES | — | Matched watchlist entity names |
| scored_at | timestamptz | NO | now() | Score computation timestamp |

**Joins:**
- `user_cutting_relevance.user_id → public.users.id`
- `user_cutting_relevance.clipping_id → public.clippings.id`

**Notes:** UNIQUE on `(user_id, clipping_id)`. Cuttings relevance noted as weaker than clips/articles due to geo-over-surfacing (MEMORY: relevance_v3_cross_pillar). Indexed on `(user_id, relevance_tier)` and `(user_id, score_final DESC)`.

---

## public.user_govt_doc_relevance — [LIVE] (~274 rows, 288 kB)

**Purpose:** Per-user relevance scores for government PDF documents.
**Populated by:** `worker-relevance` queue.
**Read by:** `/documents` feed ranking.
**Freshness:** 274 rows — sparse; govt-docs pillar has limited ingest.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| user_id | uuid | NO | — | FK → `public.users.id` |
| doc_id | uuid | NO | — | FK → `public.govt_documents.id` |
| score_stage1 | float8 | NO | 0.0 | Pre-geo relevance score |
| score_final | float8 | YES | — | Post-geo relevance score |
| relevance_explanation | text | YES | — | Score explanation |
| urgency | text | YES | — | Urgency label derived from document metadata (inferred: e.g. `"high"`, `"low"`) |
| sentiment_for_user | text | YES | — | Sentiment toward user's entities |
| matched_entity_names | text[] | YES | — | Matched watchlist entity names |
| geo_match_strength | float8 | YES | 0.0 | Raw geo match score before normalization |
| computed_at | timestamptz | YES | now() | Score computation timestamp |

**Joins:**
- `user_govt_doc_relevance.user_id → public.users.id`
- `user_govt_doc_relevance.doc_id → public.govt_documents.id` (inferred FK name)

**Notes:** Uses `computed_at` (not `scored_at`) and adds `urgency` + `geo_match_strength` columns not present in the other relevance tables. `score_stage1` is NOT NULL with default 0.0, unlike clips/cuttings where it is nullable.

---

## public.user_cards — [LIVE] (~6 rows, 80 kB)

**Purpose:** Per-user custom tracker cards on `/coverage/articles`. Each card defines a set of filters (entities, topics, geo) to track; cards with the same `definition_hash` share one LLM summary.
**Populated by:** User action in the coverage UI; `tasks.spawn_sub_cards` Celery task for parent→child expansion.
**Read by:** `/coverage` card panel, `user_card_summaries` lookup.
**Freshness:** 6 rows — feature lightly used.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| user_id | uuid | NO | — | FK → `public.users.id` |
| label | text | NO | — | User-facing card title, e.g. `"Revanth Reddy threats"` |
| definition_hash | text | NO | — | SHA-256 of normalized filter config; links to `user_card_summaries` |
| entity_refs | jsonb | NO | `'[]'` | Array of entity objects; max 10 (CHECK constraint) |
| topic_filters | jsonb | NO | `'[]'` | Topic filter array |
| geo_filter | jsonb | NO | `'[]'` | Geographic filter array |
| user_intent | text | YES | — | Free-text intent typed by user; fed into summary prompt |
| created_at | timestamptz | NO | now() | Card creation time |
| last_refreshed_at | timestamptz | YES | — | Last time summary was regenerated |
| parent_card_id | uuid | YES | — | Self-FK → `user_cards.id`; NULL for user-created parents, UUID for spawned sub-cards |
| sub_card_angle | text | YES | — | Short angle label for sub-cards (e.g. `"Threats to Revanth"`); NULL on parents |
| sub_cards_spawned | boolean | NO | false | TRUE once `spawn_sub_cards` has finished; prevents re-spawning |

**Joins:**
- `user_cards.user_id → public.users.id`
- `user_cards.parent_card_id → user_cards.id` (self-referential)
- `user_cards.definition_hash → user_card_summaries.definition_hash`

**Notes:** The `entity_refs` cap of 10 is enforced by `CONSTRAINT user_cards_entity_cap_chk`. Multiple users with identical filter definitions share one `user_card_summaries` row — the deduplication key is `definition_hash`.

---

## public.user_card_summaries — [LIVE] (~6 rows, 120 kB)

**Purpose:** LLM-generated 4-section summaries shared across all users whose cards share the same `definition_hash`. One row per unique card definition, not per user.
**Populated by:** Daily Celery task (card summary generation, using `llama-3.1-8b-instant` by default).
**Read by:** Coverage card panel UI.
**Freshness:** Regenerated daily or on `last_refreshed_at` trigger.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| definition_hash | text | NO | — | PK; SHA-256 of the card definition |
| sections | jsonb | NO | — | 4-section summary: `{state, whats_new: [...], why_matters, watch_for: [...]}` |
| citations | jsonb | NO | `'[]'` | Ordered array of article IDs that fed the summary |
| generated_at | timestamptz | NO | now() | When the LLM summary was generated |
| generated_by_model | text | NO | `'llama-3.1-8b-instant'` | Model used; default may change as pool evolves |
| sample_size | integer | NO | 0 | Number of articles sampled for this summary |

**Joins:** `user_card_summaries.definition_hash → user_cards.definition_hash`

**Notes:** This table has no `user_id` — it is intentionally user-agnostic. Any user with a matching `definition_hash` sees the same summary. This is the deduplication mechanism to avoid redundant LLM calls.

---

## public.user_page_access — [LIVE] (~16 rows, 48 kB)

**Purpose:** Per-user page allowlist for RBAC. Controls which pillar pages a user can access. Created in migration 031.
**Populated by:** Admin grant action; backfilled for all existing users by migration 031; new users get defaults via `/api/onboarding/confirm`.
**Read by:** Auth middleware on each page request.
**Freshness:** 16 rows across 3 users — one full default grant set each.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| user_id | uuid | NO | — | PK part + FK → `public.users.id` ON DELETE CASCADE |
| page_slug | text | NO | — | PK part; page identifier: `'coverage'`, `'clips'`, `'cuttings'`, `'threads'`, `'signals'`, `'documents'`, `'brief'`, `'analyst'`, `'worldmonitor'` |
| granted_by | uuid | YES | — | FK → `public.users.id` ON DELETE SET NULL; NULL = system default |
| granted_at | timestamptz | NO | now() | Grant timestamp |

**Joins:**
- `user_page_access.user_id → public.users.id`
- `user_page_access.granted_by → public.users.id`

**Notes:** Primary key is `(user_id, page_slug)` composite. Column is named `page_slug`, NOT `page_key` (live-verified). Known slugs as of migration 031: `coverage`, `clips`, `cuttings`, `threads`, `signals`, `documents`, `brief`, `analyst`, `worldmonitor`.

---

## public.impersonation_sessions — [LIVE] (~26 rows, 80 kB)

**Purpose:** Audit log of super-admin "view as user" sessions. One row per impersonation session opened by an admin. Created in migration 031.
**Populated by:** Super-admin "impersonate" action in UI.
**Read by:** Admin audit panel; impersonation middleware.
**Freshness:** 26 sessions recorded; actively used for admin debugging.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| admin_id | uuid | NO | — | FK → `public.users.id` ON DELETE CASCADE; the super-admin who initiated |
| target_user_id | uuid | NO | — | FK → `public.users.id` ON DELETE CASCADE; the user being impersonated |
| started_at | timestamptz | NO | now() | Session start time |
| ended_at | timestamptz | YES | — | Session end time; NULL = session still open |
| reason | text | YES | — | Admin-provided reason for impersonation |

**Joins:**
- `impersonation_sessions.admin_id → public.users.id`
- `impersonation_sessions.target_user_id → public.users.id`
- `impersonation_actions.session_id → impersonation_sessions.id`

**Notes:** Partial index on `(admin_id) WHERE ended_at IS NULL` for fast "active sessions" lookup. A session is "open" while `ended_at IS NULL`.

---

## public.impersonation_actions — [LIVE] (~3,614 rows, 864 kB)

**Purpose:** Per-HTTP-request audit log inside an impersonation session. Every API call made while impersonating a user is recorded here.
**Populated by:** Impersonation middleware (logs every request during an active session).
**Read by:** Admin audit panel.
**Freshness:** 3,614 rows — the most populated RBAC table; impersonation is used heavily for debugging.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | bigint | NO | nextval(sequence) | PK (BIGSERIAL — high-volume) |
| session_id | uuid | NO | — | FK → `impersonation_sessions.id` ON DELETE CASCADE |
| method | text | NO | — | HTTP method: `'GET'`, `'POST'`, `'DELETE'`, etc. |
| path | text | NO | — | Request path, e.g. `'/api/articles?page=1'` |
| status_code | integer | YES | — | HTTP response status code; NULL if request did not complete |
| at | timestamptz | NO | now() | Request timestamp |

**Joins:** `impersonation_actions.session_id → impersonation_sessions.id`

**Notes:** Uses BIGSERIAL (not UUID) for the PK — appropriate for high-volume append-only audit data. Indexed on `(session_id)` and `(at)`. No `action_type` enum column — method + path together describe the action.

---

## public.analyst_sessions — [LIVE] (~192 rows, 96 kB)

**Purpose:** Container for a user's RAG Analyst chat session. One row per conversation thread on the `/analyst` page.
**Populated by:** Analyst chat API when a user starts a new conversation.
**Read by:** Analyst chat UI; `analyst_turns` lookup.
**Freshness:** 192 sessions; actively used.

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| user_id | uuid | NO | — | FK → `public.users.id` |
| room | text | NO | `'analyst'` | Room/context discriminator; default `'analyst'`; may distinguish different analyst sub-contexts |
| created_at | timestamptz | YES | now() | Session creation time |
| updated_at | timestamptz | YES | now() | Last turn time |

**Joins:**
- `analyst_sessions.user_id → public.users.id`
- `analyst_turns.session_id → analyst_sessions.id`

**Notes:** No `title` column (live-verified). The `room` column allows the same session infrastructure to be reused for different analyst contexts (e.g. a future "brief analyst" vs "corpus analyst").

---

## public.analyst_turns — [LIVE] (~163 rows, 432 kB)

**Purpose:** Individual Q&A turns within an analyst session. Each row is one user question + system answer with RAG metadata.
**Populated by:** Analyst RAG pipeline on each query.
**Read by:** Analyst chat UI (conversation replay), evaluation harness.
**Freshness:** 163 turns across 192 sessions (some sessions have 0 turns — opening without querying).

| column | type | nullable | default | meaning & example values |
|---|---|---|---|---|
| id | uuid | NO | gen_random_uuid() | PK |
| session_id | uuid | NO | — | FK → `analyst_sessions.id` |
| question | text | NO | — | User's question text |
| answer | text | NO | — | System's generated answer |
| evidence_count | integer | YES | 0 | Number of retrieved evidence chunks used |
| confidence | text | YES | — | Confidence label, e.g. `'high'`, `'medium'`, `'low'` |
| retrieval_ms | integer | YES | — | Retrieval latency in milliseconds |
| room | text | NO | `'analyst'` | Mirrors session room discriminator |
| created_at | timestamptz | YES | now() | Turn creation time |

**Joins:** `analyst_turns.session_id → analyst_sessions.id`

**Notes:** `evidence_count` and `retrieval_ms` enable latency / quality monitoring over time. `confidence` is a text label (not an enum or float) — values are LLM-generated and may vary. The `room` column is denormalized from the session for simpler queries.

---

## Cross-system reference: The Two User Systems

| Attribute | `analytics.users` | `public.users` |
|---|---|---|
| Purpose | Night-desk staff accounts | Older onboarding / public system |
| Row count | 6 | 3 |
| Auth | Supabase + `is_super_admin` bool | Supabase + `role` text CHECK |
| Role model | Boolean flag | `'user'` \| `'super_admin'` |
| Org grouping | `analytics.orgs` | None |
| Brief prefs | `analytics.user_brief_prefs` | `public.user_profiles` (partial) |
| RBAC | Not applicable | `public.user_page_access` |
| Impersonation | Not applicable | `public.impersonation_*` |
| Relevance scores | Not applicable | `public.user_*_relevance` |
| Analyst chat | Not applicable | `public.analyst_sessions/turns` |
| Cross-join FK | None | None — systems are isolated |

**There is no foreign key or shared ID space between the two systems.**
