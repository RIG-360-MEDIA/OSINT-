# YouTube Clips Pipeline — Design (aligned to article/substrate system)

> Corrects the earlier rushed design. The core mistake was treating this as a
> Telangana-specific system with hardcoded entities and bespoke LLM calls. It
> is a **generic multi-region framework**. Clips must flow through the SAME
> infrastructure as articles: the unified LLM pool, the entity_dictionary /
> entity_lookup resolution, and the substrate-style structured extraction.

---

## 1. What the article system actually is (evidence)

### Generic, not Telangana-specific
- `entity_dictionary` has `country CHAR(2)` / full-name country, `state`, `party`,
  `source` (`seed:us_v1`, `llm_extracted`, `wikidata`). Entities are **data-driven**.
- `article_locations` stores `country` (full English name — "India", "United
  States", NEVER ISO), `region`, `city`, `location_scope`. Generic.
- Topic taxonomy (`nlp_topic.py`): 15 coarse / 25 fine buckets — globally
  applicable (POLITICS, GOVERNANCE, BUSINESS, INTERNATIONAL, …).
- Telangana is only the **current seed deployment** (district gazetteer + entity
  seeds + prompt location-anchor hints). The schema is multi-tenant.

### LLM infrastructure (`backend/nlp/groq_client.py`) — REUSE, don't reinvent
- Entry points: `call_groq()`, `extract_json()`, `classify()`, `translate()`, `generate()`.
- 4-provider **unified pool**: 8 local Ollama slots (Trijya-7 RTX 4090,
  `qwen3:14b`/`qwen3:30b-a3b`) → 21 Groq keys (`qwen/qwen3-32b`) → 27 Cerebras
  keys (`zai-glm-4.7`, `reasoning_effort:"none"`). `LOCAL_LLM_PRIMARY=1` → local
  is preferred, cloud is overflow → **clip extraction is essentially free on the GPU**.
- Per-key/slot cooldown 15s, 300s cap. Token bucket 4 req/s. `/no_think` everywhere.
- task_types → `TOKEN_LIMITS`: classification 50, translation 500,
  profile_extraction 1000, **transcript_analysis 1500**, relevance_explanation 200,
  brief_generation 4000, rag_response 2048. Temps: classification 0.0, translation
  0.1, generation 0.3.
- A `transcript_analysis` task_type **already exists** — use it.

### Substrate v3 extraction (`backend/tasks/substrate/run_corpus_pass.py`)
- ONE structured-JSON call per article (`GROQ_SYS` = Prompt G + D1 SPO addendum)
  emits: `article_type`, `primary_subject`, `summaries{preview,snippet,executive}`,
  `locations[]` (country/region/city/is_primary), `events[]`, `quotes[]`
  (speaker/text/context/is_verbatim), `actor_stances[]` (actor/stance/intensity),
  `claims[]` (**SPO**: subject/predicate/object/text/claimant/type/verifiable),
  `numbers[]`, `register{rhetorical_style,primary_emotion,is_breaking}`.
- `GROQ_SYS_NON_ENGLISH` = same + `english_translation` field (≤1500 chars).
- Called via `call_groq(system=GROQ_SYS, user="TITLE: …\n\nBODY:\n…", model=FAST_MODEL,
  task_type="profile_extraction", json_response=True, max_tokens_override=3000/3500)`.
- 6 child tables: `article_claims`, `article_quotes`, `article_locations`,
  `article_events`, `article_numbers`, `article_stances`. + `entities_extracted` JSONB.
- Lifecycle: `substrate_status` (pending→processing→ok/extract_failed/fetch_failed/junk),
  `extraction_version=3`. Atomic claim via `UPDATE…RETURNING FOR UPDATE SKIP LOCKED`.
  2-attempt retry + robust JSON parse (strip fences, isolate outer `{}`).

### Entity resolution (generic, table-driven) — NOT a hardcoded ALIAS_MAP
- `entity_lookup(name_norm PK, entity_id)` — `name_norm = lower(trim(name))`.
- `refresh_entity_lookup()` loads canonical names + **unambiguous** aliases only
  (ambiguous like "Congress" excluded).
- `article_entity_mentions` matview joins `entities_extracted` →
  `entity_lookup.name_norm` → `entity_dictionary` → (canonical_name, type, country).

### Monitoring model = **(a) GLOBAL ingestion + uniform view** (for feed content)
- Ingest scores against the **union of `user_watched_entities`** across all users
  (`SELECT DISTINCT canonical_name FROM user_watched_entities`). One global pass.
- Feed reads filter on `relevance_score >= 0.3` — **no user_id in the query**;
  everyone sees the same pre-scored corpus.
- Per-user scoring (`govt_relevance.py`, two-stage rules+LLM, weights:
  entity .40 / geo .25 / topic .20 / intrinsic .15) is applied at the **brief /
  govt-docs** layer, not the core feed. Clips should follow the feed model.

---

## 2. Corrected YouTube clips design

**Principle: a clip is an article whose body is a transcript span.** Reuse the
substrate prompt + child tables; the only YouTube-specific layer is
time-anchoring and chunking.

### Tables (migration 107)
- `pending_youtube_videos` — already exists (discovery→transcript queue, status
  lifecycle mirrors substrate). Keep.
- `youtube_clips_v2` — already exists. Add substrate-parity enrichment via child
  tables rather than flat columns, so clips feed the SAME analytics as articles:
  - `youtube_clip_claims` (SPO, mirrors article_claims)
  - `youtube_clip_quotes`
  - `youtube_clip_stances` (actor/target/stance/intensity)
  - `youtube_clip_locations` (country/region/city — generic, full country names)
  - keep on-row: `matched_entity`, `clip_start/end_seconds`, `embed_url`,
    `transcript_segment`, `transcript_translated`, `topic_category`/`topic_fine`,
    `register_*`, `labse_embedding`, `relevance_score`, `substrate_status`,
    `extraction_version`.
  - `entities_extracted JSONB` on the clip → feed a `youtube_clip_entity_mentions`
    matview that joins `entity_lookup` exactly like articles. (No ALIAS_MAP.)

### Extraction = ONE call per chunk (transcript-adapted Prompt G)
- Chunk transcript (≤150s / ≤2200 chars, cap N). Per chunk, `call_groq(model=FAST_MODEL,
  task_type="transcript_analysis", json_response=True)`.
- System prompt = Prompt G adapted: same schema (claims SPO, quotes, stances,
  locations full-country, register, numbers, events) **plus** per emitted clip:
  `entity` (surface form — resolved in Python via entity_lookup, NOT enum),
  `start_phrase` / `end_phrase` (verbatim anchors → real timestamps in Python),
  `importance`. Non-English videos → append the `english_translation` block.
- Python: anchor→timestamps; resolve entity via `entity_lookup`; **filter to the
  global monitored set** (union of `user_watched_entities` + dictionary aliases) —
  this is what makes it generic (US user follows Biden → Biden clips from CNN).
  Dedup `(entity, start_sec)` keep highest importance; gate; LaBSE embed (batch).

### Per-day firing (mirror substrate drain + RSS cadence)
- **VOD (uploads):** RSS discovery every 30m → `pending_youtube_videos`. Transcript
  drain (via relay) `FOR UPDATE SKIP LOCKED` → `transcribed`. Extraction drain →
  clips + child tables → `extracted`/`ok`, `extraction_version=3`.
- **Live:** YouTube auto-captions appear only AFTER stream ends (~1-4h). Poll
  live-capable channels every 15m; for videos <4h old attempt transcript, retry in
  90m on `no_transcript`. True real-time (`yt-dlp --live-from-start`) is out of scope.
- All LLM calls ride the unified pool (local-primary) → cheap; relay handles the
  YouTube IP block for transcript fetch only.

### Relevance
- Score clips at ingest globally against `user_watched_entities` union (feed model),
  store `relevance_score`; reuse the `_W_ENTITY/_W_GEO/_W_TOPIC/_W_INTRINSIC` math.

---

## 3. Concrete corrections vs the earlier rushed design

| Earlier (wrong) | Corrected |
|---|---|
| Hardcoded 11 Telangana entities | Global monitored set from `user_watched_entities` + `entity_dictionary` aliases (generic, any country) |
| Own raw Groq HTTP + hardcoded keys | `call_groq()`/`extract_json()` unified pool (local→Cerebras→Groq), `task_type="transcript_analysis"` |
| Bespoke ALIAS_MAP | `entity_lookup` table resolution + matview |
| Invented topic enum (ELECTION/IRRIGATION…) | Generic 15/25 `nlp_topic` taxonomy |
| `geo_tags TEXT[]` | `*_locations` child table: country(full name)/region/city |
| Flat stance/claim_type columns | Substrate-parity child tables: claims (SPO), quotes, stances, locations |
| Invented per-day logic | Substrate drain pattern: `FOR UPDATE SKIP LOCKED`, `substrate_status`, `extraction_version`, 2-attempt retry |
| `quality_check_standalone.py` shape | Keep its anchor-timestamp + chunking ideas only; route extraction through prod infra |
