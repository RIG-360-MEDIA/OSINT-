# Source-Side Fixes — Stop the bleeding for NEW articles

**Context:** T1/T2/T3/T4 fix the legacy corpus. But the ingest + substrate pipeline still has the original bugs baked in — new articles arriving today still inherit some of them. This plan adds source-side fixes so new articles auto-clean at ingest, no future backfill needed.

**Side benefit:** the source-side fixes that require new prompts force a re-extraction pass on the legacy data too (folding T4's pattern). One pass = both fix + apply.

**Validation principle for every task:** new-article quality must match or exceed backfilled-article quality, measured by the audit metrics.

---

## T9 — Fix event_date drift in substrate prompt

**Files touched:** `backend/tasks/substrate/eval_prompt_G.py` (or wherever event extraction prompt lives — needs lookup before edit)

**Bug:** Prompt confuses publish date with event date. Multi-source clusters agree on date only 26.7% of the time. Sports results worst — 13.3% agreement.

**Prompt diff (sketch):**
```
OLD: "extract event_date from the article"
NEW: "event_date is the calendar date on which the event ITSELF happened — NOT
      the date this article was published. If the article reports an event from
      last week, use last week's date. If the article describes a future event
      scheduled for next month, use next month's date. If unclear, omit the
      event_date field entirely. Never use today's date as a default."
```

**Pre-flight:**
- 30-article side-by-side test (OLD vs NEW prompt) before mass-deploy.
- Verify event_date diversity (multi-source clusters should now have ≥70% perfect date agreement on the test set).

**Re-extraction:**
- Trigger `extract_events_for_article` with `force=True` for all 165,791 events in article_events.
- Resumable, checkpointed. Estimated ~30-60h on free-tier pool.

**Gate:**
- Cross-source date agreement: 26.7% → ≥70% on multi-source clusters.
- Spot-check 20 sports-result clusters — ≥18 must have all sources on the same date.

---

## T10 — Force full disambiguating names

**Files touched:** `backend/tasks/coverage/claims_quotes_task.py` + the events extraction prompt.

**Bug:** LLM writes just "Modi" when the article is about Lalit Modi or Sushil Modi → downstream search returns all 3 mashed together.

**Prompt diff (sketch):**
```
ADD: "When extracting subjects, speakers, and actors, use the FULL disambiguating
      name based on article context. Examples:
        - 'IPL chairman Modi' → 'Lalit Modi' (NOT 'Modi')
        - 'PM Modi' or 'Prime Minister Modi' → 'Narendra Modi'
        - 'former Bihar deputy CM Modi' → 'Sushil Modi'
      Never use just a family name when context makes the full name clear.
      For ambiguous bare names (e.g., 'Singh', 'Rao' alone), prefer to OMIT
      rather than guess."
```

**Re-extraction:**
- Folded into T9's pass (same prompt file gets both edits, one re-extract on events + claims).

**Gate:**
- Spot-check 100 articles where the name is ambiguous in context. ≥80 must have the disambiguated full name.

---

## T11 — Language detector in the INGEST pipeline (not just the LLM)

**Files touched:** wherever `articles.language_detected` is set during initial ingestion.

**Bug:** Telugu sources (TV9 Telugu, Namasthe Telangana, etc.) have `language_detected='en'` hardcoded — the detector never ran on title.

**Code diff (sketch):**
```python
# After ingest sets language_detected, run a Unicode-script override:
SCRIPT_OVERRIDE = {
    re.compile(r"[ఀ-౿]"): "te",
    re.compile(r"[ऀ-ॿ]"): "hi",
    re.compile(r"[ঀ-৿]"): "bn",
    # ... (the regex map from T2_fix_language_mistags.py)
}
for pat, lang in SCRIPT_OVERRIDE.items():
    if len(pat.findall(title)) >= 3:
        article.language_detected = lang
        break
```

**Re-extraction:** Not needed — this is a daily auto-classifier on new ingests.

**Gate:**
- 0 mistagged articles among new ingests over a 24h window.
- T14 monitors continuously.

---

## T12 — `is_future` post-processor (compute from dates)

**Files touched:** wherever `article_events.is_future` is set, OR add a post-step in the events extraction task.

**Bug:** LLM sets `is_future=TRUE` based on tense ("will happen") instead of comparing event_date to publish date.

**Code diff (sketch):**
```python
# After event extraction, override is_future from dates:
if event.effective_event_date and article.published_at:
    event.is_future = event.effective_event_date > article.published_at.date()
```

**Re-extraction:** Not needed — T1 already fixed legacy rows. This stops future bleeding.

**Gate:** 0 new is_future contradictions in next 7 days.

---

## T13 — Soften summary truncation cliff (lower priority)

**Files touched:** the summarizer prompt (writes `summary_executive`).

**Bug:** Prompt says "summarize in ≤ 500 chars" → LLM hits 500 exactly. 152 articles affected.

**Prompt diff:**
```
OLD: "summarize in ≤ 500 characters"
NEW: "summarize in 200-450 characters; do not pad to a length"
```

**Re-extraction:** Optional — only 152 rows affected, can skip or fold into T9's pass.

**Gate:** 0 new articles at exactly 500/1000 char cliff.

---

## T14 — Daily quality-comparison job

**New file:** `backend/tasks/quality_comparison_task.py`
**Schedule:** Celery beat 03:30 IST (after gold regression at 03:00).

**What it does:**
1. Snapshot last-24h-new-articles' quality metrics:
   - Placeholder claims pct
   - Language mistag count
   - is_future contradiction count
   - event_date diversity in multi-source clusters
   - Summary length distribution (any cliffs?)
   - LaBSE collision count
2. Compare against the backfilled-articles baseline (recorded once T4 completes).
3. Write to `docs/quality/new-vs-baseline-YYYY-MM-DD.json`.
4. Surface in `/observe` Quality Monitor as a "New article quality" gauge.
5. Alert (via `audit_decisions` queue) if any metric regresses > 2x baseline.

**Gate:** New-article metrics within 20% of baseline on day 1, < 5% within 30 days.

---

## T15 — Validate LaBSE embedding input

**Files touched:** `backend/nlp/nlp_embedding.py` caller.

**Bug:** 800+ articles share identical embeddings → suggests the embedder was fed boilerplate ("read more", a templated header, etc.) instead of body text.

**Code diff (sketch):**
```python
# In whatever calls generate_embedding(), assert the input isn't a known
# boilerplate string and has ≥ 100 chars of real article text.
def safe_embed_input(article) -> str | None:
    text = article.lead_text_translated or article.full_text_scraped or article.summary_executive
    if not text or len(text) < 100: return None
    # Reject if first 200 chars match known boilerplate fingerprints
    BOILERPLATE_PREFIXES = {"Share this article", "Click here to read", ...}
    if any(text.strip().startswith(p) for p in BOILERPLATE_PREFIXES):
        text = text[200:]  # skip the boilerplate
    return text
```

**Re-extraction:** T3 already fixed the top 6 collision groups. Smaller groups left untouched.

**Gate:** No new collision signature with ≥ 5 articles forms within 30 days of deployment.

---

## Execution order

```
WHILE T4 RUNS (24-48h)
  → draft T9 prompt + side-by-side test it (offline, 30 articles)
  → draft T10 prompt + side-by-side test it
  → draft T11/T12/T13/T14/T15 diffs

T4 COMPLETES → record backfilled-article baseline metrics

THEN, with green light:
  T11, T12, T15 — ingest-pipeline fixes (no re-extraction, just deploy)
  T9 + T10 — substrate prompt edits (combined re-extraction pass, 30-60h)
  T13 — summarizer prompt edit (optional, low value)
  T14 — daily comparison job (wires up Celery beat)
```

## Single sentence summary

**T9-T15 stop the source-side bleeding so new articles auto-clean at ingest; T14 watches continuously so any regression is caught within 24h.**
