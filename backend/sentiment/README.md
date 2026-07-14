# Sentiment Engine v2 — two-field, per-entity, perspective-aware

Replaces the dict-gated `article_stances` stage (which only covered ~29% of
articles). This engine scores **every** (article, entity) pair on **two
independent fields**, and can answer arbitrary read-time perspectives
("from India's perspective", "from Windlass's perspective").

## Why two fields (read this first)

"Sentiment" is undefined until you name the perspective. One article gives two
different answers:

| Field | Question | "Windlass wins army contract" → Cold Steel |
|-------|----------|--------------------------------------------|
| **stance** | Does the *article* praise / criticise X? | neutral (barely mentioned) |
| **impact** | Are the *events* good / bad for X? | negative (they lost the deal) |

Never collapse these into one "sentiment" column. `stance` powers the Signal
Room / "who's under fire" views; `impact` powers the "from X's perspective"
feature. See `schema.sql` for the storage split.

## How it was chosen (evidence)

Eight experiments on an RTX 4090, scored against a hand-labeled 40-pair gold key:

| Approach | Trained on our labels? | Accuracy vs gold |
|----------|------------------------|------------------|
| NLI zero-shot (Engine B) | no | **42.5%** (dead — can't focus on entity) |
| Fine-tuned DistilBERT / XLM-R | yes | 53–59% (memorised label noise) |
| Old production labeler | it *is* the labeler | 62.5% |
| **Instruct LLM, two-field (Engine A)** | **no** | **65.0%** ✅ |

Engine A beats the current production labeler with **zero training**, and is the
only approach that produces per-perspective output. ~65% is near the practical
ceiling: two careful human annotators only agree ~75–85% on sentiment.

## Guaranteed valid output

Decoding is **schema-constrained** (`SENTIMENT_SCHEMA` in `engine.py`, enforced
via vLLM/xgrammar `guided_json`). Measured: raw prompting = 66.7% valid JSON;
guided = **100.0%** (120/120). The parse-failure class is eliminated by design.

## Throughput

Per-article LLM call (scores all the article's entities at once).

| Path | art/s (1×4090) | 875k backfill |
|------|----------------|---------------|
| batched HF (measured floor) | 3.08 | ~79 h |
| vLLM (est. 2–3×) | ~7–9 | ~30 h |
| **vLLM across 4-GPU pool** | **~30** | **~8 h (overnight)** |

Ongoing incremental (~20k new articles/day): **~15–20 min/day** — folds into the
pipeline. Re-benchmark on the real pool nodes at deploy time to replace the
estimate with a measured number.

## Files

| File | Purpose |
|------|---------|
| `schema.sql` | Tables: results, gold, audit, run-stats. Idempotent. |
| `engine.py` | Prompt + schema + `score_entity()`. Single source of truth. |
| `bench_gold.py` | Regression gate vs **verified** gold. Run before every backfill. |
| `judge_audit.py` | Samples production rows, re-scores with a stronger model, logs agreement. |
| `gold_build.py` | Seeds the 40 human-gold; grows to ~200 via silver (human-reviewed). |
| `gold_seed_human.csv` | The 40 hand-verified dual-label pairs (held-out gold). |
| `gold_candidates_silver.csv` | 200 fresh rows, 7B-prelabeled (stance/impact/confidence) + blank `human_*` columns for review. |

## Gold expansion workflow (to reach the ≥200 verified gold)

1. **`gold_seed_human.csv`** — 40 dual-labeled rows, already human-verified (held out).
2. **`gold_candidates_silver.csv`** — 200 fresh rows the 7B pre-labeled. Distribution:
   stance 147 neu / 35 pos / 18 neg; impact 92 neg / 67 pos / 41 neu; 21% low-confidence.
   These are **SILVER — model predictions, not gold.**
3. **Human review**: open the CSV, fill `human_stance` / `human_impact` (correct the silver
   where wrong). Ideally two reviewers; disagreements resolve the fuzzy neutral boundary.
4. **`python -m backend.sentiment.gold_build --load-reviewed`** — human-filled rows load as
   VERIFIED gold; unreviewed stay silver. **Loading silver unreviewed would be circular**
   (scoring the model against its own labels) — the gate uses `verified=true` only.

## Quality tracking (4 layers)

1. **Frozen gold gate** (`bench_gold.py`) — halts rollout if stance acc < 0.60.
2. **LLM-judge audit** (`judge_audit.py`) — continuous ~0.2% sample re-scored by a
   32B judge; alerts if agreement < 0.75.
3. **Confidence / divergence** — `stance != impact` is *signal*, kept; low-confidence
   rows can be routed to the 32B for a second pass.
4. **Distribution monitors** (`sentiment_run_stats`) — per-node class balance,
   parse-ok %, throughput. A node drifting all-negative or high parse-fail =
   quarantine.

**No fabricated eval data:** model-labeled rows are `source='silver'`,
`verified=false`, and are excluded from the gate until a human flips `verified`.
Only the 40 human rows (and whatever silver a human later signs off) count as gold.

## Impact is the hard field — measured ~60% (stance is ~80%)

Judging *consequences* is genuinely harder and more subjective than judging *tone*.
Known 7B failure patterns (measured): (1) won't say `not_relevant` for incidental
subjects, (2) over-reads intensity from a charged context, (3) misses implicit
outcomes (a sports loss, a show of support). A bigger model did **not** help — 32B
scored lower on the 40-row key, which is within its ±15% noise band. **Do not tune
against 40 one-annotator rows; build the multi-annotator gold first.**

### Next impact experiment — confidence + ordinal-tolerant scoring (scaffolded, not yet measured)

Impact is an **ordinal** quantity (harm↔benefit), not 3 hard boxes. Adding hard
"lean-positive/lean-negative" classes would *lower* exact-match accuracy and make the
gold harder to annotate. Instead:

- **Confidence field** — the model now emits `impact_confidence` (0–1) and is told to
  score borderline calls low. `bench_gold.py` reports accuracy on the high-confidence
  slice (`--conf>=0.7`) so you can surface only trusted calls and route the rest to
  review / the 32B. (`engine.py::SENTIMENT_SCHEMA`, `SentimentResult.impact_confidence`.)
- **Ordinal-tolerant scoring** — `bench_gold.py` now reports impact three ways:
  `exact`, `tolerant` (off-by-one counts, so neutral-vs-negative is a near-miss not a
  full miss), and `MAE`. `not_relevant` is off-axis and scored exact-only
  (`engine.py::impact_distance`). Tolerant scoring stops penalising the genuine
  neutral-boundary fuzz and gives a truer picture of impact quality.

**Run once the ≥200-pair, 2-annotator gold exists** — not against the current 40-row
key (which cannot resolve differences this small).

### Directional findings so far (measured on 40 rows — treat as suggestive, not final)

- **Ordinal-tolerant reframes impact**: exact ~55%, but **tolerant (±1) ~85–88%, MAE
  ~0.37** across two runs. Impact is almost never a *sign flip* — it wobbles on the
  neutral boundary. Report tolerant + MAE, not just exact.
- **Confidence RANKS but isn't calibrated.** Both self-reported and **logprob** confidence
  are over-confident (nearly all rows score high), so a fixed threshold (≥0.7) passes
  everything. But *ranking* works: least-confident half ~40% vs most-confident half ~70%.
  → Use confidence for **relative routing** ("send the least-confident 25% to review/32B"),
  not absolute publish gates. Prefer **logprob** confidence (no self-rating; principled).
  Needs temperature/Platt scaling on the bigger gold to become an absolute gate.

## Model tiering

- **Backfill / bulk**: `qwen2.5-7b-instruct` (validated ≥ production, fast).
- **On-demand perspective queries + audit judge**: `qwen2.5-32b-instruct`.

## Integration TODO (confirm against live infra before wiring)

- `ANALYTICS_DSN` / `LLM_BASE_URL` env — align with existing pool + DB config.
- `gold_build.sample_pairs` / `judge_audit.fetch_text` reference
  `public.articles(title, body)` and `analytics.article_stances(actor)` — verify
  column names against the live DB.
- Point the pool client at a vLLM endpoint that supports `guided_json`.
