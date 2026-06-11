# Spec: fix v3 multilingual summary loss — two-pass (translate → extract)

**Owner:** substrate session (`backend/tasks/substrate/run_corpus_pass.py`)
**Author:** ops session, 2026-06-05 (diagnosed live on prod)
**Priority:** high — ~16,600 articles have `extraction_version=3` but NULL summaries; non-English is hit hardest.

---

## 1. Problem (evidence)

`summary_snippet` / `summary_executive` are NULL on a large share of v3-complete articles. Live prod numbers (last 48h, `substrate_processed_at` set + `extraction_version>=3`):

| lang | summary coverage |
|---|---|
| en | 75% |
| te | 67% |
| hi | 66% |
| ta | 58% |
| ml | 49% |
| ja | **3%** |

Among ALL v3-done articles: only **71.4%** have a summary. So v3 *does* generate summaries (same pass writes `summary_*` + `extraction_version=3` together) — but the summary step is failing, disproportionately for non-English.

## 2. Root cause (confirmed in code)

Single-call design overloads the model's output budget for non-English:

- `GROQ_SYS_NON_ENGLISH` (≈ run_corpus_pass.py:587) appends to the base prompt: *translate the body to English, add `english_translation` (≤1500 chars), THEN extract all structured data.*
- So one response must emit: `english_translation` + `summaries{preview,snippet,executive}` + locations + events + quotes + claims + actor_stances + numbers + register — all in one JSON, within the model's ~8K context (input+output shared).
- Indic/CJK scripts are token-dense; the translation field alone eats ~600 output tokens.
- The output **overflows and truncates mid-JSON**.
- `groq_semantic` (≈:673) does `json.loads()` → fails on truncated JSON → strips fences, retries parse → still invalid → **returns `None`**.
- `process_one` (≈:810) `else`-branch (≈:888) then sets `summary_preview = summary_snippet = summary_executive = None` (and all structured fields) **but still stamps `extraction_version=3`**.

Net: article marked v3-done, everything blank. English mostly survives (no translation field → fits); non-English truncates → `None`.

## 3. Fix — two-pass (the chosen best-fit, not a fallback)

Eliminate the root cause: never make one call do translation + full extraction.

### New flow in `process_one`
```
body, lang, cap = _get_extraction_context(article)

if lang is non-English:
    # PASS 1 — translate only (tiny output, always fits)
    english_text = await groq_translate(body)          # NEW helper
    if not english_text:
        english_text = body          # fall through; pass 2 still tries
    extract_input = english_text
    english_translation = english_text[:8000]
else:
    extract_input = body
    english_translation = None

# PASS 2 — the STANDARD English extraction+summary prompt on clean English
semantic = await groq_semantic(extract_input, prompt=GROQ_SYS)   # always GROQ_SYS now
```

### Key changes
1. **Add `groq_translate(text) -> str|None`** — a thin call: system prompt "Translate to faithful English, preserve proper nouns transliterated, output ONLY the translation." Small `max_tokens` sized to the body. Retry once like `groq_semantic`.
2. **Pass 2 always uses `GROQ_SYS`** (the English prompt). Delete the `GROQ_SYS_NON_ENGLISH` branch — extraction no longer needs to translate, so its full output budget goes to summaries + structured fields. Non-English now rides the proven English-quality path.
3. **Persist `english_translation`** from Pass 1 (you already store this column; now it's a clean dedicated artifact, not squeezed into the extraction JSON).
4. **Body caps:** with translation removed from Pass 2, the per-script truncation caps (`MAX_BODY_FOR_GROQ_*`) can relax for Pass 2 (input is now English). Pass 1's cap governs translation input.

### Why this is the real fix
- Removes output-budget contention entirely → no truncation → JSON parses → real summaries.
- Non-English quality rises to English-grade for **every** field (summaries, claims, stances, register), not just summaries.
- Simplifies the pipeline: one extraction prompt (`GROQ_SYS`), one path.

## 4. Cost
- +1 LLM call **only for non-English** (~30% of 24h volume: te/hi/ml/ta/ja vs en).
- Pass 1 output is small (translation only). On Groq/Cerebras (fast, high TPD) the marginal cost is low.
- Net: modest compute increase for correct, consistent extraction across all languages.

## 5. Optional defensive layer (keep, don't rely on)
In `groq_semantic`, before returning `None` on a parse failure, attempt a **partial-JSON salvage** (parse the largest valid `{...}` prefix) so a borderline-truncated response still yields whatever fields completed. This is belt-and-braces on top of the two-pass fix, not a substitute.

## 6. Backlog (separate decision — do NOT blanket re-run)
`process_one` **re-fetches the URL** (`_fetch_html_browser` → trafilatura), so re-running v3 on the ~16.6k no-summary articles = 16.6k fresh HTTP fetches + LLM calls, and many URLs are now stale (→ new `fetch_failed`, losing the body you already have). Options, in order of safety:
1. **Frontend fallback now** (ops session can do on mc-frontend): card shows `summary_snippet || summary_preview || lead_text_translated` — instant, free, no blank cards, no data mutation. (Recommended immediate mitigation while this spec is implemented.)
2. **Targeted re-run, capped + off-peak**, only on recent high-value sources, AFTER this fix ships — and ideally re-summarize from the *stored* `full_text_scraped`/`english_translation` instead of re-fetching (consider a `--reuse-body` path in `run()` that skips the fetch when a good body already exists).

## 7. Validation after implementing
- Run the two-pass on a sample of 50 Telugu + 20 Japanese articles; confirm `summaries.snippet` non-null ≥ ~90%.
- Re-check coverage by language — expect te/hi/ml to climb toward the en level (~75%+), ja off the floor.
- Confirm structured fields (claims/stances) also improve (they were truncation victims too).

## 8. Exact code anchors (run_corpus_pass.py, approx lines as of 2026-06-05)
- `GROQ_SYS` ≈ 551 ; `GROQ_SYS_NON_ENGLISH` ≈ 587 (to be removed)
- `MAX_BODY_FOR_GROQ_ENGLISH = 2400` ≈ 605 (+ per-script caps below it)
- `_get_extraction_context` ≈ 648
- `groq_semantic` ≈ 673 (add `prompt=` param; add salvage)
- `process_one` ≈ 810 ; summary mapping ≈ 870 ; `None` else-branch ≈ 888
- `_update_article` ≈ 974 (already accepts summary_* + english_translation params)
- `run()` batch entry ≈ 1402 ; SELECT `ORDER BY collected_at DESC LIMIT :lim` ≈ 1421 (add `--reuse-body` for the safe backlog path)
