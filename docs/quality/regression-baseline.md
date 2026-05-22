# Gold-set regression — operator manual

The gold set (`docs/quality/gold_set_v1.jsonl`) is the immutable regression
baseline produced by the Phase-4 LLM-judge audit. 200 articles, 20+
sources, 5 languages, every field scored ≥ 8 by the judge with
confidence ≥ 0.85.

This file is **never edited by hand**. To rebuild it you must re-run the
full audit pipeline and call `scripts/audit/gold_set_freeze.py` against a
fresh judge run.

## Nightly task

`tasks.quality.gold_regression` (queue: `nlp`) runs at 21:30 UTC / 03:00
IST via Celery beat (`backend/celery_app.py` → `beat_schedule`). Per run:

1. Loads every row from `gold_set_v1.jsonl`.
2. Re-fetches the article from Postgres by `article_id`.
3. Compares: `primary_subject`, `summary_executive` length (±30%),
   `extraction_version`, `substrate_status`.
4. Writes a per-day summary to `docs/quality/regression_YYYY-MM-DD.json`.

The `/observe` Quality Monitor panel reads the most recent regression
file and surfaces `drift.subject_changed`, `drift.extraction_version_changed`,
etc. as live gauges.

## Interpreting deltas

| Drift counter | Why it might fire | Action |
|---|---|---|
| `article_missing` | Article hard-deleted from DB | Investigate — gold rows are reference data; deletion is a red flag. |
| `substrate_no_longer_ok` | Article re-extracted and failed | Inspect `articles.substrate_error` on that row. |
| `extraction_version_changed` | New v3 extraction shipped — expected. | None unless > 90% of gold drifted in one night (would suggest a mass re-run). |
| `subject_changed` | Different `primary_subject` than at freeze time | If > 5% in one night, the extraction prompt likely changed; re-run audit Phase 1+2 to validate. |
| `summary_len_delta_30pct` | Summary text length changed materially | Usually paired with `extraction_version_changed`. Spot-check 5 examples. |

## Manual trigger

```bash
# Inside the rig-backend container:
docker exec rig-backend python /app/scripts/audit/gold_regression.py \
  --gold /app/docs/quality/gold_set_v1.jsonl \
  --out /tmp/gold_regression_manual.json

# Or via Celery (queues to the nlp worker, ~3 min wall time):
docker exec rig-backend celery -A backend.celery_app:app call \
  tasks.quality.gold_regression
```

## Day-0 expectation

The verification gate from Phase 7 of the data-quality plan is:

> **Day-0 gold baseline: 200/200 match.**

If any drift counter is non-zero on day 0, the gold selection logic in
`gold_set_freeze.py` produced inconsistent rows — do NOT merge until
fixed.

After day 0, expect a small monotonic rise in `extraction_version_changed`
as the v3 extractor re-processes articles. The other counters should
stay at zero except after deliberate prompt changes.
