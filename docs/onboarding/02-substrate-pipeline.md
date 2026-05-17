# 02 - Substrate Pipeline (v3 Extraction)

> **TL;DR.** Every article runs through one structured-JSON LLM call
> that emits 6 child-table payloads (quotes, claims, stances, numbers,
> events, locations) plus byline / tweet fields on the article row.
> The current production prompt is **Prompt G** (= prompt C base +
> the "EVENT DATE RULE" addendum). It is the winner of a 7-variant
> head-to-head eval done 2026-05-15/16. Drain progress is tracked by
> `extraction_version` on each article row: `v1` = legacy /
> not-yet-processed, `v2` = old prompt, `v3` = current (Prompt G).

## What `extraction_version` means

`articles.extraction_version` is a single-character column. The drain
walks rows from oldest version forward.

| Value | Meaning                                                                 |
|-------|-------------------------------------------------------------------------|
| `v1`  | Legacy. No substrate extraction. ~23K rows remaining as of 2026-05-16.  |
| `v2`  | Old prompt (before the state-vs-city fix and the EVENT DATE addendum). |
| `v3`  | **Current.** Prompt G output. 6 child tables populated.                |

Progress probe:

```sql
SELECT extraction_version, COUNT(*) FROM articles
GROUP BY 1 ORDER BY 1;
```

## The v3 prompt — Prompt G

Lives in `backend/tasks/substrate/run_corpus_pass.py` as the
constant `GROQ_SYS`. The eval harness for the 7-variant run is in
`backend/tasks/substrate/eval_prompts.py` (and the historical
`eval_prompt_F.py` / `eval_prompt_G` at repo root).

Prompt G is structured into these blocks (read the source for the
exact wording — what follows is a faithful summary):

1. **Role + JSON-only contract.** "You are a JSON extractor. Emit
   only valid JSON. No prose."
2. **Schema definition.** Lists every emitted field, each with type,
   nullability, and max-cardinality (e.g. locations: max 5; events:
   max 6). Quotes get speaker + context; claims get claim_type;
   stances get target + stance + intensity; events get a `date`
   field; locations get country/region/city/is_primary.
3. **Article-type vocabulary.** Closed set of 12 types:
   `news, opinion, analysis, explainer, listicle, horoscope, recipe,
   live_blog, photo_essay, interview, press_release, sports_result,
   other`. Anything that doesn't fit goes to `other`.
4. **Location rules block.** The most important section. Three
   sub-rules:
   - **India city aggression.** If the body names any specific
     district/town/city/mandal/constituency in India, the `city`
     field MUST be populated. Country must always be `"India"`.
   - **India anchor list.** Hard-coded list of known places
     (Hyderabad, Khammam, Bengaluru, Mumbai, …) to disambiguate
     against. Lives ~lines 520-530 of `run_corpus_pass.py`.
   - **State-vs-city decision tree.** A state-cabinet meeting in
     Hyderabad is a *Telangana* story, not a *Hyderabad* story
     (region=Telangana, city=null). A road crash at a named
     Hyderabad landmark is a city story (region=Telangana,
     city=Hyderabad). National-level (centre govt, Lok Sabha,
     Supreme Court) only gets `city="New Delhi"` if the body
     specifically anchors there.
5. **Few-shot location examples.** Two or three concrete worked
   examples — a state policy, a city incident, a national-level
   statement — showing the desired output shape.
6. **EVENT DATE RULE addendum** (the difference between Prompt C and
   Prompt G). Forces every emitted event to carry a `date` field —
   either a real `YYYY-MM-DD` or explicit `null`. Stops the model
   from skipping date inference on dated events.

## The 6 v3 child tables

All foreign-keyed to `articles.id`. Migrations 063-073.

| Table                | Migration | Purpose                                                                                   |
|----------------------|-----------|-------------------------------------------------------------------------------------------|
| `article_quotes`     | 043 + 049 (translation) + 073 (context, unknown_locations) | Quoted speech: `text`, `speaker`, `speaker_role`, `context`, `source_lang`. |
| `article_claims`     | 043       | Factual / opinion claims: `claim_text`, `claim_type`, `speaker`.                          |
| `article_stances`    | 070 (polish) | Position-taking: `actor`, `target`, `stance`, `intensity`.                                |
| `article_numbers`    | 069       | Numeric facts: `value`, `unit`, `context`.                                                |
| `article_events`     | 067       | Discrete events: `date`, `description`, `event_type`, `actors[]` (max 6).                 |
| `article_locations`  | 066 + 070 | Geo: `country`, `region`, `city`, `is_primary` (max 5).                                   |

Sibling enrichment tables (also v3-era):

- `article_links` (064) — links extracted from body, with anchor text.
- `article_media` (065) — embedded images / video URLs with captions.
- `article_tweets` (071) — embedded tweet IDs + text snapshot.
- `articles.byline_*` columns (072) — author name, handle, role, photo URL.

The unknown-locations column (073) is for the case where the model
emits a place name it cannot confidently country-tag — kept as raw
strings for human review later.

## The drain script

Two related files in `backend/tasks/substrate/`:

- `run_corpus_pass.py` — the main driver. Pulls rows from `articles`
  where `extraction_version != 'v3'`, runs Prompt G, parses JSON,
  inserts to child tables transactionally, sets
  `articles.extraction_version='v3'`.
- `semantic_repass.py` — a similar driver used for the "drain backlog"
  job. Uses the unified LLM pool but, **critically, has its own
  manual provider list construction** that pre-2026-05-15 did NOT
  honour `LOCAL_LLM_PRIMARY`. The current workaround is
  `LLM_LOCAL_ONLY=1`, which is enforced at the unified-pool
  entrypoint and therefore propagates. See known-issues #6.

Other substrate-folder files:
- `byline_periodic_task.py` — the byline scraper, ~14% coverage target
  → 80% (P1 todo).
- `backfill_bylines.py` — one-shot byline backfill driver.
- `backfill_tweets.py`, `enrich_tweets.py`, `tweet_periodic_task.py` —
  tweet enrichment trio.
- `eval_prompts.py` — the historical eval harness used for A-through-G.

## Unified LLM pool (overview)

The substrate calls go through `backend/nlp/groq_client.py`. Despite
the filename, this module manages three providers:

- **24 Groq keys** (round-robin, key-level cooldown on 429). Models:
  `llama-3.1-8b-instant` (fast) and `llama-3.3-70b-versatile`
  (quality).
- **27 Cerebras keys** (round-robin, daily-budget aware). Model:
  `llama-3.3-70b`.
- **1 Ollama slot** on TRIJYA-7. Model: `qwen3:30b-a3b`.

Routing is gated by env flags read at module import:

| Env var                        | Default | Effect                                                                                          |
|--------------------------------|---------|-------------------------------------------------------------------------------------------------|
| `LOCAL_LLM_ENABLED`            | `1`     | If `0`, the Ollama lane is removed entirely.                                                    |
| `LOCAL_LLM_PRIMARY`            | `0`     | If `1`, Ollama is tried first; cloud is fallback.                                                |
| `LOCAL_LLM_MAX_CONCURRENT`     | (env)   | Limits inflight Ollama calls (matches `OLLAMA_NUM_PARALLEL`).                                   |
| `LLM_LOCAL_ONLY`               | `0`     | If `1`, returns ONLY the Ollama slot. Used by the drain when cloud quota is exhausted.          |

A cooldown timer is attached to each Groq / Cerebras key. On HTTP
429 the key gets a cooldown stamp; round-robin skips cooled keys
until reset (daily for Cerebras at 00:05 UTC, per-minute for Groq).
If all keys cool simultaneously, `GroqQuotaExhausted` is raised and
the pool returns a structured error the substrate driver knows to
handle.

A separate Cloudflare-WAF dodge: the Groq SDK's default User-Agent
got blocked with error `1010` (403). The pool overrides with a real
browser UA. Without this every Groq call 403s and the pool logs
phantom rate-limit errors.

## Known bugs / gotchas in the substrate pipeline

1. **`semantic_repass.py` ignores `LOCAL_LLM_PRIMARY`** — only
   `LLM_LOCAL_ONLY=1` forces the Ollama path because the unified-pool
   entry-point honours it. The audit todo to find every manual
   provider-list construction is still open. See known-issues #6.
2. **Qwen3 reasoning mode silently ate the token budget.** First
   integration via Ollama's OpenAI-compat endpoint
   `/v1/chat/completions` returned HTTP 200 with `content=""` because
   reasoning tokens were routed to a hidden `reasoning` field. Fix:
   call the native `/api/chat` and pass `think: false` in the body.
   The OpenAI-compat shim ignored `/no_think` prefixed to the system
   prompt; native endpoint honours `think: false`. See mistakes.md
   incident #13.
3. **Cerebras TPD blow-out.** The drain throughput controller knew
   per-minute RPM/TPM but not the daily TPD budget. One run consumed
   26.87M of 27M tokens in 8 hours (99.5%), stalling the next 16
   hours. Workaround: watchdog flips to `LOCAL_ONLY` at high
   Cerebras consumption. Proper fix: TPD-aware back-pressure
   controller, pending.
4. **Newsroom cold-start deadlock.** `process_broadcast` hangs
   reliably as the *first* task after a worker restart due to an
   asyncio Lock + Celery prefork interaction. Workaround: warm
   the worker with a few ping tasks before invoking. Root-cause fix
   is suspected in a module-level Lock in `groq_manager` —
   investigation open.

## v3 quality stats (post-drain, 2026-05-16)

- 1.4 quotes per article (median).
- 3.2 claims per article (median).
- 80% of claims rated factual by spot-check.
- 0% null-subject claims (a v2 failure mode that Prompt G killed).
- 37% byline coverage (target: 80% — P1 todo).
- ~23K v1 rows remaining; drain ETA dependent on quota and watchdog
  mode.
