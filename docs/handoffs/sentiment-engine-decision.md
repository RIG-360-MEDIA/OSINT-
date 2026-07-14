# Sentiment Engine v2 — Decision Record & Handoff

**Date:** 2026-07-05  ·  **Status:** engine chosen & frozen; harness built; blocked on gold
**Code:** [`backend/sentiment/`](../../backend/sentiment/)  ·  **Spec:** [`backend/sentiment/README.md`](../../backend/sentiment/README.md)

---

## 1. The problem

The old sentiment stage (`analytics.article_stances`, dict-gated) covered only **~29%**
of articles and produced a single blurred "stance toward actor" label. Goal: score
**every** (article, entity) pair, reliably and cheaply, and support arbitrary read-time
perspectives ("from India's / Windlass's perspective").

## 2. The single most important finding

**"Sentiment" is undefined until you name the perspective, and it is TWO questions:**

| Field | Question | Powers |
|-------|----------|--------|
| **stance** | Does the *article* praise / criticise X? (tone) | Signal Room, "who's under fire" |
| **impact** | Are the *events* good / bad for X? (consequence) | "from X's perspective" feature |

On **25 of 40** sample articles these two DIFFER (e.g. "Beverages Corp fined" =
stance neutral, impact negative). **Never merge them into one column or one accuracy
number.** This is the core architectural decision.

## 3. What we tried (RTX 4090, scored vs a 40-pair hand gold)

| Approach | Trained on our labels? | Result | Verdict |
|----------|------------------------|--------|---------|
| Off-the-shelf multilingual sentiment | no | 36% | wrong task (reads mood, not entity) |
| **NLI zero-shot** (Engine B) | no | 42.5% | dead — can't focus on the entity, no neutral |
| Distil from LaBSE embedding | yes | 55% | blurred whole-article vector |
| Fine-tuned DistilBERT | yes | 52.7% | no target as input |
| Target-aware XLM-R | yes | 59% | memorised our label noise |
| Old production labeler | it *is* the labeler | 62.5% | baseline |
| **Instruct LLM, two-field** (Engine A) | **no** | **65% → stance 80 / impact 60** | ✅ chosen |

Every "judge the text objectively" method clustered at 36–44%; only label-trained
models reached 52–59%. That gap proved the metric was measuring *agreement with our
noisy labels*, not correctness. An instruct LLM, scored against a clean hand key,
beats the production labeler **with zero training** and is the only approach that
produces per-perspective output.

## 4. Decisions & rationale

1. **Engine = Qwen2.5-7B-Instruct, two-field, guided JSON.** Frozen.
2. **Two independent fields**, never one merged "sentiment" (§2).
3. **Guided/schema-constrained decoding** (vLLM/xgrammar). Raw prompting = 66.7% valid
   JSON; guided = **100%**. Parse-failure class eliminated by design.
4. **7B, not 32B.** 32B (4-bit) scored *lower* (stance 70 / impact 50) — within the
   ±15% noise band of a 40-row key. Bigger did not help; 7B is cheaper and ≥ on every
   field. **Do not use 32B for bulk.** *Scope caveat:* this was a **local 4-bit
   bitsandbytes copy on TRIJYA-7's 4090** (HF, `~/senv`), NOT the pool's full-precision
   32B node — so it rules out *4-bit-32B*, and the 40-row key couldn't resolve a
   full-precision difference anyway. Re-test on the pool 32B only after the bigger gold.
5. **Stopped tuning.** Cleaning the gold → no change; better prompt → no change on the
   blurred key; bigger model → moved down. That is the signature of a **saturated
   measurement**. Further tuning against 40 one-annotator rows is noise-chasing.

## 5. Current numbers (honest)

```
Stance (tone)          ~80%   near human-agreement ceiling — production-ready
Impact (consequence)   ~60%   real, robust to gold-cleaning — genuinely the hard field
Valid JSON (guided)    100%
Throughput             batched-HF floor 3.08 art/s; vLLM ~est 2-3x;
                       pool of 4 GPUs ~8h backfill; ~15 min/day incremental
```
Stance ~80% is near the ceiling (two humans agree only ~75–85% on sentiment).

## 6. Why impact is stuck at ~60% (failure patterns)

1. **Won't say `not_relevant`** for incidental subjects (Coroner, Blinken, Spurs) —
   biggest & most fixable slice (~+10 pts from a `not_relevant` few-shot).
2. **Over-reads intensity** from a charged context (active subject → positive; grim
   topic → negative) when nothing material changed.
3. **Misses implicit consequences** (Haiti lost 3-0 → read neutral).
Much of the residual is the *irreducible subjectivity* of "does this matter for them" —
the neutral boundary is fuzzier for impact than for tone.

## 7. What's built

`backend/sentiment/`: `schema.sql` (results/gold/audit/run-stats), `engine.py` (prompt +
schema + `score_entity` + ordinal/confidence helpers), `bench_gold.py` (regression gate,
now reports impact exact / tolerant / MAE / high-confidence), `judge_audit.py` (32B
LLM-judge sampler), `gold_build.py` (+ `gold_seed_human.csv`, 40 dual-labeled human rows).

Quality tracking = 4 layers: frozen gold gate, LLM-judge audit, confidence/divergence,
distribution monitors. **No fabricated eval data:** model labels are `silver`,
`verified=false`, excluded from the gate until a human signs off.

## 8. THE blocker & next steps (in order)

1. **Build the ≥200-pair, 2-annotator gold** (dual-labeled stance + impact). *Everything
   else depends on this.* The 40-row single-annotator key is exhausted — it cannot
   resolve differences at the 10-point level. Use `gold_build.py --silver` → human review.
2. Then, and only then, run the queued impact experiments (scaffolded, not yet measured):
   - `not_relevant` few-shot prompt (biggest lever).
   - **confidence gating** (`impact_confidence` field) — surface trusted calls, route
     low-confidence to review/32B.
   - **ordinal-tolerant scoring** (off-by-one = near-miss; MAE) — stop penalising the
     neutral-boundary fuzz.
3. Ship the pipeline: apply `schema.sql`, wire `engine.py` to a `guided_json` pool
   endpoint, verify table/column names (`public.articles`, `analytics.article_stances`),
   backfill on the pool, run `bench_gold.py` as the gate.

## 9. One-line summary

**Ship 7B two-field with guided JSON: stance is solved (~80%), impact is real but hard
(~60%); the next gain is blocked not on models but on a bigger multi-annotator gold —
stop tuning against 40 rows.**
