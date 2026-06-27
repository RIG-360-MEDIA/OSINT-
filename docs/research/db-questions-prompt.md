# Prompt for the RIG Database Chat — open questions from the field audit

> Copy everything below the line into your database chat. It is written to be
> answered section by section. Where I state "I believe X — confirm or correct,"
> please verify against the real schema/pipeline/code.

---

You are the expert on the RIG Surveillance Postgres database (the multi-pillar
news/OSINT corpus on the Hetzner box: ~293K `articles`, `clippings`,
`youtube_clips_v2`, entity graph, structured substrate, story clustering, per-user
relevance). I am building a **new read-only application** on top of this database
and I have already run a live field-level audit as `analytics_user`. I now need
the *intent, provenance, quality, and known issues* behind the fields — the things
SELECT queries can't tell me.

**How to answer (please follow for every field/table):**
1. **Meaning** — what it represents, in one plain sentence.
2. **How it's produced** — which pipeline/task/model/prompt populates it, and when.
3. **Reliability** — quality, known issues, % you'd trust, calibration.
4. **Status** — live / deprecated / backfilling / safe-to-ignore.
5. **Consumer** — what currently reads/uses it (so I know if it's live or orphaned).
If you don't know something, say "unknown" rather than guessing. Correct any wrong
assumption I state. Group your answers under the same section letters/numbers below.

---

## §0. TOP-PRIORITY (make-or-break) questions — answer these first

0.1 **Is THIS database the full production dataset?** Many tables are empty (0 rows):
all `cm_*` (political intelligence), all `social_*` (signals), all `govt_*`
(documents), `districts`/`assembly_constituencies`/`mandi_prices`/`weather_*`,
`dossier_*`, `narrative_*`, `alerts`/`notification_*`/`user_watchlist`. Are these
**abandoned**, **planned-but-not-started**, or **populated in a different
database/environment** I'm not connected to? This decides whether whole feature
areas are possible.

0.2 **Cross-pillar embedding comparability.** `articles.labse_embedding_v4` uses
recipe `v4-tr-title-1024`. `clippings.labse_embedding` and
`youtube_clips_v2.labse_embedding` have no recorded recipe. **Are clippings/youtube
embedded with the SAME LaBSE recipe as articles v4, or a different one?** Can I
trust cosine similarity *across* pillars (article ↔ clipping ↔ clip)? Is there a
plan to re-embed clippings/youtube with v4? (My spot-check showed loose, noisy
cross-pillar matches — I need to know if that's recipe mismatch or just sparse data.)

0.3 **Which story-clustering generation is LIVE and wired to the product right
now** — `analytics.story_clusters` (34,599) or `analytics.story_clusters_v8`
(178,258)? What is v8's status (candidate / promoted / abandoned)? And how does
`analytics.story_clusters` relate to `public.event_clusters` (6,859) — two systems,
which does the product actually use?

0.4 **What exactly is the `v4-tr-title-1024` embedding recipe?** What input text is
embedded (translated title only? title+lead? full text?), what does "1024" mean
(the vector is 768-dim), and is the vector L2-normalized (cosine-ready)? What are
the HNSW index parameters (m, ef_construction) and which column is indexed?

0.5 **Stance direction.** In `article_stances`, is `actor` the **target being
talked about** or the **holder/speaker** of the stance? (I believe `actor` =
target, i.e. directed sentiment — confirm or correct.) What does `intensity`
range/mean?

0.6 **Freshness & what's frozen.** How many new articles land per day? Which
pipelines are currently **broken or frozen** (I've heard: entity extraction froze
~06-11, `thread_id` froze ~05-25, `quote_text_en` never populated) — what's the
current status of each? Which matviews refresh on a schedule, and how often?

---

## §A. Embeddings & semantic search
A.1 Why does `labse_embedding_v4` cover ~94% while legacy `labse_embedding` covers
~97.7%? What are the ~18K articles missing v4 — being backfilled, or permanently skipped?
A.2 Is legacy `labse_embedding` used by ANY live feature today, or fully superseded
by v4? Safe to ignore? Same for `labse_embedding_v0_backup` (will it be dropped)?
A.3 Confirm v4 is the only embedding I should use for similarity. Is the legacy
column truly "recipe-mixed" (half wrong recipe), as I was told?
A.4 What are `embedding_model`, `embedding_revision`, `embedded_at` for — version
tracking? What does revision `836121a0…` (a git hash, ~8K rows) vs `v4-tr-title-1024`
(~275K) mean?
A.5 What are the `analytics.embed_ab`, `embed_ab_sample`, `embed_ab_variants`
tables — an embedding A/B test? Which recipe won and why?
A.6 Is `fts` (tsvector, 100% populated) built from original or translated text,
and with which text-search config (English? simple? multi-language)? Does it index
regional-language articles usefully for hybrid search?
A.7 **Query embedding at runtime:** is there an embedding service / endpoint / SQL
function I can call to embed a user's *query string* with the EXACT `v4-tr-title-1024`
recipe, so query vectors match the indexed doc vectors? (Without this, semantic
search is impossible — I must reproduce the recipe precisely.)

## §B. `articles` — field meaning & quality
B.1 `substrate_status` values `ok / fetch_failed / junk / extract_failed /
processing / pending` — exact meaning of each. Is `ok` the correct filter for
"usable"? How does it differ from `nlp_processed=true`?
B.2 The "enriched cohort" (~208K rows that have summaries + register + primary_subject):
what decides if an article gets enriched? Will the remaining ~29% ever be enriched,
or are they permanently skipped (junk/fetch_failed)?
B.3 `summary_preview` vs `summary_snippet` vs `summary_executive` — intended
length/use of each tier? Always generated together? Which model writes them?
B.4 `lead_text_translated` / `full_text_translated` — always English? Which
translation model? Why is full-text translation only ~17.5% — on-demand or batch,
and is coverage increasing?
B.5 `topic_category` vs `topic_fine` vs `topic_category_orig` — what is `_orig`
(pre-rollup)? Is `topic_fine` a controlled vocabulary? Why is 21% of `topic_category`
= `OTHER` — genuinely unclassifiable, or a backlog being rescued?
B.6 `geo_primary` mixes country/state/city (India / Telangana / Hyderabad). Is
there a cleaner canonical geo? Is `geo_secondary` (100% non-null) truly defaulted/
unused, and what was it meant to be? Should I use `article_locations` instead?
B.7 The "register" model: what are `register_style` values, what does
`register_emotion` actually measure (event-emotion vs hostility?), and is
`register_is_breaking` reliable?
B.8 `primary_subject` — what is it (one-line subject? entity?) and how produced?
B.9 Confirm dead/ignore: `narrative_frame` (0%), `content_type` (always 'article'),
`geo_secondary`. Are these deprecated or pending?
B.10 `source_tier` — what are the tiers and how assigned? `article_type` vs
`article_type_orig` — meaning/values?
B.11 `body_quality`, `word_count`, `reading_minutes` — how computed; `body_quality`
scale? `nlp_confidence` — what does it score?
B.12 `is_duplicate` / `duplicate_of` — how is dedup decided; is `duplicate_of`
always set when `is_duplicate` is true? Is the dedup trustworthy?
B.13 `thread_id` — what is it (social thread link?); is it still maintained (I heard
it froze ~05-25)?
B.14 `published_at` ranges back to 2010 — are old dates real/imported, and are any
dates bogus or future-dated? `collected_at` vs `published_at` reliability?
B.15 `canonical_url` vs `url` — canonicalization/dedup role?

## §C. Structured substrate (stances / claims / quotes / numbers)
C.1 Which model/prompt extracts the substrate (qwen3-32b? local spaCy? something
else)? What do `extracted_by_model` values look like? Is confidence calibrated?
C.2 Is the plan to extract substrate for the WHOLE corpus, or only the ~50% 'ok'
cohort it currently covers?
C.3 **Stances:** meaning of `actor` / `stance` / `intensity` / `actor_entity_id`.
Why only ~45% have `actor_entity_id`? Canonical set of `stance` values? Can the
free-text actors be resolved later?
C.4 **Claims:** why only ~30% `subject_entity_id` resolved? Is `predicate` meant to
be free-text (134K distinct) or normalized? What is `confidence` based on? What is
the `embedding` column on claims used for (claim-level search)?
C.5 **Quotes:** is `quote_text_en` translation planned (currently ~0)? Will
`speaker_entity_id` (~39%) improve? Do `char_offset_start/end` index the original
or translated text? What does `is_direct` mean and is it reliable?
C.6 **Numbers:** intended canonical `unit` set? Units currently mix `currency/
percent/count` with `date/year/time` and `runs` — is that a bug or by design? What
are `context` and `position`? How often is `value` mis-parsed?

## §D. Entities
D.1 How is `entity_dictionary` curated — manual, automatic, or both? How are new
canonical entities added?
D.2 `aliases` appears to be **English/Latin only** (e.g. "PM Modi", "KCR") — no
native Telugu/Hindi script. **Confirm:** are regional-language mentions linked to
canonical entities via **translate-then-extract** (extraction runs on English
translation)? Is native-script matching done anywhere?
D.3 `article_entity_mentions` (matview): what is its **source query** and **refresh
cadence**? Are `surface_forms` always Latin? It exposes `mention_rows` but **no
prominence/confidence** — is there any prominence/salience signal anywhere (the
inline `entities_extracted` jsonb claims `{prominence, confidence}` — are those
reliable)?
D.4 Confirm `entity_lookup` (9 rows, all Australian politicians) is a **dead test
stub** — not used by any live path. Safe to ignore?
D.5 Entity **disambiguation**: how does the system separate "Narendra Modi" from
"Lalit Modi" / "Modi government" / "Modinagar" (a town)? Is there a confidence or
context mechanism I should use to avoid wrong-entity bleed?
D.6 `entity_type` values (person/organization/location/constituency/role) — is that
the complete set? Is `party` reliable (only ~18% filled — politicians only)?
D.7 `redirected_to` — entity merges: should I always follow it to the canonical
entity? How many are chained?
D.8 What are `entity_merge_map_*`, `entity_aliases` (0 rows), `entity_dict_meta`,
`entity_match_index` (0), `entity_image`? Which are live vs scratch/backup?
D.9 `entity_mention_daily` — schema and meaning (daily counts per entity?). Reliable
for trend/velocity ("heating up") features? Refresh cadence?
D.10 Only ~10,331 of 19,356 dictionary entities appear in articles — are the rest
seeded/expected/future, or junk?

## §E. Clustering / stories / events
E.1 (see 0.3) Live generation + relationship between `story_clusters`,
`story_clusters_v8`, `event_clusters`.
E.2 `story_cluster_members`: meaning of `attach_score`, `is_representative`,
`is_canonical`, `provisional`. How is the representative article chosen?
E.3 `story_clusters` fields: how are `stance_distribution`, `sentiment`,
`importance_score`, `title_cohesion`, `entity_core_cov`, `is_template_family`,
`languages` computed? Which are reliable for ranking/UX? (`is_template_family` =
spam/template piles?)
E.4 Is the `languages` per-cluster histogram reliable and complete? (I rely on it
for cross-language framing contrast.)
E.5 Only ~945 clusters have ≥3 articles; ~47% of articles are clustered. Is the
singleton/small-cluster tail expected? What decides if an article gets clustered
(only 'ok'? only v4-embedded?)?
E.6 Story enrichment (`story_timeline`/`facts`/`sources`/`quotes`/`geo`/`stance`)
covers only ~716 stories — is enrichment ongoing, and what triggers a story to be
enriched? Could I instead derive a timeline from member `published_at` for any
cluster?
E.7 Are `story_clusters_old` and the `analytics._*` tables (`_cand_pairs`, `_win`,
`_sc`, `_scl`, `_clust`, `_edge_stage`, `_fixture_ids`, etc.) scratch/rollback —
safe to ignore?
E.8 `story_edges` / `story_edges_v8` (the similarity graph) — what are they for; is
the graph reusable by my app?
E.9 Cluster `subject_country` / `subject_region` / `subject_locations` — reliability?
E.10 **Do clippings and youtube clips get clustered together WITH articles into the
same events, or are pillars clustered separately?** (Critical for cross-pillar.)
E.11 `article_events` (511K rows) — what is an "event" row, and how does it relate to
`event_clusters` / `story_clusters`? Is it a per-article extracted event that FEEDS
clustering, or a separate output? Are `article_contradictions` / `event_dissent`
(both empty) planned features?

## §F. Per-user / accounts / personalization
F.1 `analytics.users` (2 rows) — is this the live auth system for night-desk? Who
are the 2 users? Is `public.users`/`user_profiles` (empty) a dead parallel system,
and which is canonical going forward?
F.2 `user_article_relevance` is populated for only **1 user**. Is scoring on-demand
per user or batch? What triggers it? Explain the relevance-v3 fields end-to-end:
`score_stage1` vs `score_final`, `relevance_tier` values, who writes
`relevance_explanation` (LLM?), `sentiment_for_user`, `geo_multiplier_applied`,
`matched_entity_names`.
F.3 `user_brief_prefs` (`watchlist/regions/topics/languages/stance/events/sources/
personality/delivery`) — how is it set (an onboarding wizard?) and is it wired to
anything live?
F.4 `user_cutting_relevance` / `user_clip_relevance` — same scorer applied to
clippings/clips?
F.5 `analytics.orgs` (2) + `org_id` on users — is this a real multi-tenant model?
F.6 `user_story_assignments` (2) — is this the admin-pushed "Chronicle" feature?

## §G. Clippings & YouTube pillars
G.1 How are `clippings` collected (PDF OCR + embedded text layer)? What do
`text_source` (text/layout/none?) and `extraction_confidence` mean, and how
reliable? Which embedding recipe (see 0.2)?
G.2 Confirm `clippings` is the live table and `newspaper_clippings`/`editions`/
`sources` (0 rows) are the deprecated old tables.
G.3 Do clipping substrate tables (`clipping_claims`/`stances`/`quotes`/…) use the
SAME extractor and quality as articles?
G.4 `clip_source`, `edition_date` reliability; are `page_number`/`bbox` useful?
G.5 Confirm `youtube_clips_v2` is live and `youtube_clips` (971, v1) is legacy.
What is `transcript_source`/`transcript_language`, and how accurate are
`clip_start_seconds`/`clip_end_seconds`?
G.6 `pending_youtube_videos` (7,619) — is this the fetch backlog; relevant to my app?

## §H. Freshness / pipeline / operations
H.1 Daily ingestion volume per pillar (articles/clippings/clips)? Real-time enough
for "first-alert" / "heating up" features?
H.2 Which Celery tasks populate which fields, and which are actively running vs
frozen/deprecated right now?
H.3 Refresh cadence for matviews: `article_entity_mentions`, `entity_mention_daily`,
`mv_cm_*`, `mv_district_*`. Which are stale?
H.4 What is being backfilled at this moment (v4 embeddings, substrate, anything else)?

## §I. Empty-table intent (expand on 0.1)
I.1 For each empty pillar — political-intel (`cm_*`), social/signals (`social_*`),
govt-docs (`govt_*`), district reference data, dossiers, narratives, alerts/
watchlists — is it abandoned, planned, or living in another DB? If planned, is there
an ETA or a way to generate the data?
I.2 `govt_documents` — I heard production once had ~15 rows from a manual run; is
that this DB, and is the documents pipeline alive?

## §J. Access / safety / scale
J.1 Is `analytics_user` the right read-only role for a new app, or should I get a
dedicated SELECT-only role (e.g. `mc_readonly`)? Any connection/rate limits?
J.2 Can my new app create its **own writable schema/database on this server** for
user state, or must app state live on entirely separate infrastructure? (My app
will NEVER write to the corpus.)
J.3 Is running HNSW similarity + hybrid queries at app scale safe on this **live
production** box, or will it impact the existing product? Any read-replica?
J.4 What are `article_links` (12M), `article_media` (3.8M), and `article_tweets`
(12.7K) — what's in each, and do I need them for a read-only product?
J.5 Any PII / sensitive / legally-restricted data in the corpus or user tables I
should treat carefully?

## §K. Please CONFIRM or CORRECT these working assumptions
K.1 Clean working set = `substrate_status='ok' AND NOT is_duplicate` ≈ 200K.
K.2 Use `labse_embedding_v4`; never use legacy `labse_embedding` for similarity.
K.3 Use `article_entity_mentions` for entity feeds; `entities_extracted` jsonb and
`entity_lookup` are not the canonical path.
K.4 Use `article_stances` for sentiment/framing; `register_emotion` is NOT a
hostility signal.
K.5 English text to rely on = `title` + `lead_text_translated`; `full_text_translated`
is too sparse to depend on.
K.6 `article_stances.actor` is the TARGET (directed sentiment), not the speaker.
K.7 Regional-language entities are linked via translate-then-extract, not native-
script aliases.
K.8 Dead/ignore columns: `narrative_frame`, `content_type`, `geo_secondary`.

Please answer section by section, flag every assumption that's wrong, and note any
important field/table I failed to ask about that a read-only app builder should know.
