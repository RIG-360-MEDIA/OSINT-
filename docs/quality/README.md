# V3 Data Quality Audit

> Six-layer audit harness that catches field-level bugs across the v3 substrate
> corpus (~165K events / ~82K articles / ~50 LLM-derived fields). Each layer
> targets a different bug category. Layers chain via `scripts/audit/run_audit.py`.

## Architecture

```
docs/quality/
├── README.md                          ← this file
├── v3-deep-audit-YYYY-MM-DD.md        ← generated per run
├── audit_run_YYYYMMDD.json            ← machine-readable summary per run
├── gold_set_v1.jsonl                  ← Phase 4 frozen 200-article baseline
└── regression-baseline.md             ← Phase 7 operator manual
```

## The six layers

| Layer | What it catches | Cost | Phase |
|---|---|---|---|
| **1. SQL sanity** | Year drift, truncation cliffs, NULL leakage, FK orphans, language mis-tags | Cheap (~5 min) | 1 |
| **2. Content grounding** | Hallucinated entities/quotes/numbers (does the value appear in article body?) | Moderate (~30 min) | 2 |
| **3. Distribution anomalies** | Per-source quality regression, per-day drift, extraction-version comparisons | Cheap (~10 min) | 2 |
| **4. Cross-source agreement** | Same-event articles disagreeing on date/actor/numbers | Moderate (~15 min) | 3 |
| **5. LLM-as-judge** | Semantic errors LLM-judge can detect that rules cannot (5K stratified sample) | Expensive (~30 min - 2 hr) | 4 |
| **6. Synthetic probes** | Systematic biases (training-cutoff year defaults, actor-name shortening) | Cheap (~30 min) | 3 |

## How to run

```bash
# Inside rig-backend container (uses backend/nlp/groq_client.py via wrapper)
python3 scripts/audit/run_audit.py --layer 1     # SQL sanity only
python3 scripts/audit/run_audit.py --full        # all six layers
python3 scripts/audit/run_audit.py --layer 5 --resume  # resumeable LLM judge

# Output appears at docs/quality/v3-deep-audit-YYYY-MM-DD.md
```

## Verification gates per layer

Each layer has a STOP condition. If any gate trips, the audit halts; the
remaining layers do not run. Specific thresholds live in
`scripts/audit/run_audit.py` constants:

- Layer 1: FK orphans > 0.5% on any table → STOP
- Layer 2: any LLM-derived table < 50% grounding → STOP, file in `docs/qa/`
- Layer 3: > 50 outlier articles per source → flag for inspection (not STOP)
- Layer 4: cluster Jaccard median < 0.4 → STOP
- Layer 5: judge-vs-synthetic concordance < 80% → STOP (do not freeze gold set)
- Layer 6: < 5 of 10 synthetic probes pass → STOP

## Pre-conditions (already shipped)

- **Migration 053[a-d]** applied. Adds `article_events.effective_event_date`
  with Option-4 publish-year clamp. Original `event_date` preserved.
- 6,712 active `event_clusters` populated from the May 2026 validation run.
- 60,973 `extraction_version=3` articles + 7,000+ pending drained.

## What this audit does NOT do

- Does NOT modify v3 extracted fields (read-only on `articles`, `article_events`,
  etc.). The only writes are to: `audit_decisions` (new table, Phase 5) and
  `article_events.effective_event_date` (one-time Phase 0 clamp).
- Does NOT call the v3 extraction pipeline. LLM-judge re-asks the LLM to
  EVALUATE existing extractions, not to re-extract.
- Does NOT touch `backend/tasks/substrate/*`, `backend/nlp/groq_client.py`,
  or the drain watchdog.

## Audit cadence

- **One-time exhaustive run** during the data-quality sprint (this work).
- **Nightly regression** against `gold_set_v1.jsonl` (Phase 7).
- **Monthly full audit** going forward (suggested) to catch slow drift.

## Where to find findings

After each run, a markdown report is generated at
`docs/quality/v3-deep-audit-YYYY-MM-DD.md` with three sections:
1. **Critical findings** (per-field bugs with prevalence %)
2. **Per-source health scorecard**
3. **Per-field health gauges + LLM-judge summary**

Operators read this. Engineers debug from the JSON sidecar
(`audit_run_YYYYMMDD.json`).
