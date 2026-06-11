# 02 - Substrate Pipeline (v3 Extraction)

> **TL;DR.** Every article runs through one structured-JSON LLM call
> that emits 6 child-table payloads (claims, quotes, locations, events,
> numbers, stances) plus byline / tweet fields on the article row.
> Production prompt: **Prompt G + compressed D1 SPO addendum**. The D1
> fix (2026-05-27) collapsed 4 verbose worked examples into 1 minimal
> example with explicit Subject-Predicate-Object schema → predicate/
> object fill rate went **14% → 99%**. Drain progress tracked by
> `articles.extraction_version`: `0`/null = legacy, `3` = current.

---

## What `extraction_version` means

`articles.extraction_version` is an **INTEGER** column.

| Value | Meaning |
|-------|---------|
| `0` or NULL | Legacy / not yet processed. |
| `1`, `2` | Old prompts (pre-D1, pre-state-vs-city fix). |
| `3` | **Current** — Prompt G + D1 SPO addendum. 6 child tables populated. 99% field fill rate. |

Progress probe:

```sql
SELECT extraction_version, substrate_status, COUNT(*)
  FROM articles
 GROUP BY 1, 2
 ORDER BY 1 DESC, 2;
```

`substrate_status` carries the lifecycle: `pending` (queued for
extraction), `processing` (claimed by a drain via atomic SKIP LOCKED),
`ok` (success), `extract_failed` (parse failed after retry),
`fetch_failed` (couldn't get the article body), `junk` (filtered
short/empty content).

---

## The v3 prompt — Prompt G + D1 SPO addendum

Lives in `backend/tasks/substrate/run_corpus_pass.py` as the constant
`GROQ_SYS` (and `GROQ_SYS_NON_ENGLISH` for translation+extraction
combined). Structured into these blocks:

1. **Role + JSON-only contract.** "You are a JSON extractor. Emit only
   valid JSON. No prose."
2. **Schema definition.** Lists every emitted field with type,
   nullability, max-cardinality (locations max 5; events max 6).
3. **Article-type vocabulary.** Closed set of 13 types: `news, opinion,
   analysis, explainer, listicle, horoscope, recipe, live_blog,
   photo_essay, interview, press_release, sports_result, other`.
4. **Register vocabulary.** Closed sets for `register_style`
   (factual / analytical / polemical / sensational / etc.) and
   `register_emotion` (alarm / approval / concerned / neutral / etc.).
5. **Location rules block** (3 sub-rules — see below).
6. **D1 SPO claim addendum** (NEW 2026-05-27). Every claim MUST be
   decomposed into `subject_text + predicate + object_text`. ONE
   compressed worked example replaces the previous 4. Compression
   freed token budget that was blowing Ollama's response cap.
7. **EVENT DATE RULE addendum.** Every emitted event must carry a
   `date` field — either real `YYYY-MM-DD` or explicit `null`. Stops
   model from skipping date inference on dated events.
8. **(Pending D8)** ARTICLE PUBLISHED anchor — will inject
   `article.published_at` + today's date as ground truth to stop LLM
   from defaulting event years to its training cutoff.

### The location-rules block (most-tweaked section)

Three sub-rules:
- **India city aggression.** If the body names any specific district/
  town/city/mandal/constituency in India, the `city` field MUST be
  populated. Country always `"India"`.
- **India anchor list.** Hard-coded list of disambiguators (Hyderabad,
  Khammam, Bengaluru, Mumbai, …). Around line 520 of
  `run_corpus_pass.py`.
- **State-vs-city decision tree.** A state-cabinet meeting in
  Hyderabad is a *Telangana* story (region=Telangana, city=null). A
  road crash at a named Hyderabad landmark is a city story (region=
  Telangana, city=Hyderabad). National-level only gets `city="New
  Delhi"` if the body specifically anchors there.

---

## The 6 v3 child tables

All foreign-keyed to `articles.id`. Migrations 063-075.

| Table | Migration | Purpose | Recent changes |
|---|---|---|---|
| `article_claims` | 043 + D1 SPO (2026-05-27) | Subject-Predicate-Object factual/opinion claims | Predicate/object_text now 99% filled (was 14% pre-D1) |
| `article_quotes` | 043 + 049 (translation) + 073 | Quoted speech: `text`, `speaker`, `speaker_role`, `context` | English-translation column, context/unknown_locations columns |
| `article_locations` | 066 + 070 + **074** | `country`, `region`, `city`, `is_primary`, **`location_scope`** | Migration 074 derives scope (city/state/country/continent) from existing columns |
| `article_events` | 067 + **072** | Discrete events: `event_date`, `event_description`, `event_type`, `actors[]`, `is_future`, **`effective_event_date`** | Migration 072 adds smart year-fix |
| `article_numbers` | 069 + **073** | Numeric facts: `value`, `unit` (normalized), `context` | Migration 073 normalized 11 unit duplicates (`year`/`years`, `dollars`/`USD`, etc.) |
| `article_stances` | 070 (polish) | Position-taking: `actor`, `target`, `stance`, `intensity` | — |

Sibling enrichment tables:
- `article_links` (064) — links extracted from body
- `article_media` (065) — embedded images / video URLs
- `article_tweets` (071) — embedded tweet IDs
- `articles.byline / author_name` (072 + D28 refinement) — author info
- **`articles.source_country`** (**075**, 2026-05-28) — ISO 3166 code
  auto-populated from `sources.country` via trigger

---

## The drain script

Single driver now (legacy `semantic_repass.py` deprecated):

**`backend/tasks/substrate/run_corpus_pass.py`** — pulls rows from
`articles` where `substrate_status='pending'`, runs Prompt G via
unified pool, parses JSON, inserts to child tables transactionally,
sets `substrate_status='ok'` + `extraction_version=3`.

### Atomic claim (D19, 2026-05-28)

Multiple drain processes can run in parallel without double-processing.
The fetch SQL is an UPDATE...RETURNING with `FOR UPDATE SKIP LOCKED`:

```sql
UPDATE articles
   SET substrate_status = 'processing'
 WHERE id IN (
   SELECT id FROM articles
    WHERE substrate_processed_at IS NULL AND url IS NOT NULL
      AND (substrate_status IS NULL OR substrate_status = 'pending')
    ORDER BY collected_at DESC
    LIMIT :batch
    FOR UPDATE SKIP LOCKED
 )
RETURNING id::text AS id, title, url
```

Each drain atomically claims a distinct batch. Orphaned 'processing'
rows from a hard-killed drain are recovered by `UPDATE articles SET
substrate_status='pending' WHERE substrate_status='processing' AND
substrate_processed_at IS NULL`.

### 2-attempt retry in groq_semantic (D15)

LLM call + JSON parse wrapped in 2-attempt loop. On parse-fail attempt
1, log INFO and re-loop (pool naturally rotates slot). On attempt 2,
log WARNING and return None.

**Net effect:** article-loss rate from ~25% (D17 era) → ~2% today.

### Other substrate-folder files

- `byline_periodic_task.py` — byline scraper (currently 14% coverage,
  target 80%, P1 todo)
- `backfill_bylines.py` — one-shot byline backfill driver
- `backfill_tweets.py`, `enrich_tweets.py`, `tweet_periodic_task.py` —
  tweet enrichment trio
- `eval_prompts.py` — historical eval harness used for A-through-G

---

## Unified LLM pool (substrate's view)

Calls go through `backend/nlp/groq_client.py`. Full details in
`05-llm-infrastructure.md`. Substrate-relevant essentials:

- **4 provider types in pool** (as of 2026-05-28): 8 local Ollama
  slots + (optional 8 lmstudio slots if `LMSTUDIO_BASE_URL` set) + 21
  Groq keys + 27 Cerebras keys.
- **Cerebras model in use:** `zai-glm-4.7` with `reasoning_effort:
  "none"`. Replaces deprecated `qwen-3-235b-a22b-instruct-2507`.
- **Groq model in use for substrate:** `qwen/qwen3-32b`.
- **Ollama model:** `qwen3:14b` (default) or `qwen3:30b-a3b` via
  `OLLAMA_MODEL` env var. Trijya-7 holds both warm.

### Routing env vars relevant to substrate

| Env var | Default | Effect on substrate |
|---|---|---|
| `LOCAL_LLM_ENABLED` | `1` | If `0`, Ollama lane removed. |
| `LOCAL_LLM_PRIMARY` | `1` | Prefer local first; cloud is fallback. |
| `LLM_LOCAL_ONLY` | `0` | If `1`, ONLY local lanes. Watchdog flips this when Cerebras TPD is near exhaustion. |
| `OLLAMA_CLIENT_SLOTS` | `8` | Number of local slots in our pool. |
| `LMSTUDIO_BASE_URL` | empty | If set, adds llama.cpp/LMStudio slots. Currently DISABLED. |

### max_tokens calibration

`MAX_TOKENS_ENGLISH = 3000` (was 5000 pre-D18). Reduction allowed by
zai-glm-4.7's reasoning_effort=none + qwen3-32b's natural conciseness
(typical output ~800-2,500 tokens). Helped Groq's per-org TPM
consumption (~5K → 3K reservation per call).

---

## D1 quality stats (last 6h sample, 2026-05-28)

For 8,156 articles processed substrate v3 successfully:

| Field | Fill rate |
|---|---|
| summary_preview / snippet / executive | **100%** |
| primary_subject | 100% |
| article_type | 100% |
| register_style / register_emotion | 99.99% |
| author_name | 100% |
| Claims with all 3 SPO fields | **99% (was 14% pre-D1)** |
| Locations populated | 99% (avg 2.57/article) |
| Events populated | 96% |
| Numbers populated | 74% |
| Quotes populated | 59% (lower because briefs/listicles have none) |
| `parse_a2` (genuine failures after retry) | **0** |

Total processed today (2026-05-28): ~30,000 articles. Failure rate:
0.28%. **No quality regressions vs pre-D1.** SPO completeness jump is
the biggest visible improvement.

---

## Known bugs / gotchas in the substrate pipeline

1. **`semantic_repass.py` ignored `LOCAL_LLM_PRIMARY`** — historical
   path that the drain no longer uses. New drain
   (`run_corpus_pass.py`) routes through unified pool entry-point that
   honours all env flags. Audit todo still open to verify nothing
   else bypasses. See known-issues O1.

2. **Qwen3 reasoning mode silently ate token budget** (resolved 2026-
   05). The OpenAI-compat shim `/v1/chat/completions` returned HTTP
   200 with `content=""` because reasoning tokens were routed to a
   hidden field. Native `/api/chat` with `think:false` is what we use
   today.

3. **zai-glm-4.7 has the SAME reasoning trap** (resolved D17, 2026-05-
   28). Without `reasoning_effort:"none"`, the response has no
   `content` key at all — only `reasoning` and `role`. Cerebras
   request body MUST include the flag for any model starting with
   `zai-glm`.

4. **Cerebras TPD blow-out**. Drain throughput controller knows per-
   minute RPM/TPM but not daily TPD. Heavy backfill exhausts the 27M
   daily budget in ~5h. Watchdog flips to LOCAL_ONLY at <5% remaining.
   Proper fix (TPD-aware controller) is P2 todo.

5. **D1 reset cron + corpus-pass disconnect** (open, D13 todo). Daily
   cron at 00:05 UTC resets `substrate_status='pending'` but doesn't
   chain into `run_corpus_pass`. Operator must manually invoke. Fix
   pending: bake into image + chain commands in cron.

6. **`event_date` year-bias resolved retroactively** (D7 / migration
   072). LLM defaulted event years to 2024 (training-cutoff) when
   articles didn't state year. Migration 072 added
   `effective_event_date` derived via 4-tier rule. Proactive fix (D8
   — bake `article.published_at` into prompt) still pending.

7. **`location_scope` defaulted to 'country' for everything** (D11 /
   migration 074, resolved). Derived from existing columns:
   city > state > country > continent > unknown.

8. **Newsroom cold-start deadlock** (open). `process_broadcast` hangs
   reliably as first task after worker restart (asyncio Lock + Celery
   prefork interaction). Workaround: warm with ping tasks before
   invoking. Root cause suspected in `groq_manager` module-level Lock.

---

## See also

- `05-llm-infrastructure.md` — pool internals, provider failover,
  reasoning_effort details.
- `06-operations-runbook.md` — drain commands, monitoring.
- `07-known-issues.md` — current open issues with substrate.
- `09-todos-prioritized.md` — D8 (publish_at anchor), D13 (D1 cron
  fix), other substrate P1 work.
- `11-session-2026-05-28-learnings.md` — full D1-D26 narrative
  including SPO fix details.
- `scripts/migrations/070_*.sql` through `075_*.sql` — all
  substrate-related migrations from this session.
