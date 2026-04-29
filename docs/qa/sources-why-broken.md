# Why some govt sources work and others give nothing / wrong data

This is the diagnosis pass for "47 adapters registered, but most return empty or junk." Every claim below cites the file:line that proves it.

## The five reasons, in order of impact

### 1. `published_at` is **ALWAYS `None`** for every adapter (47/47)

Every adapter — without exception — emits rows shaped:
```python
{"url": ..., "title": ..., "published_at": None, "type": ...}
```
Confirmed in `central_regulators.py` (line 14 docstring + lines 149, 198), `govt_collector.py` (lines 203, 250, 300), and the same pattern repeats in every family file.

**Consequence:** the system has **no idea when any document was actually published.** All ranking and filtering downstream falls back to `collected_at` (the timestamp of the scrape itself). That's why the feed looks "wrong":
- A 2018 RBI master direction scraped today looks newer than a 2024 court order scraped yesterday.
- The frontend's "30 day" window is measured from `collected_at`, not the doc's actual date — so re-scraping an old PDF makes it pop to the top.
- The `intrinsic_importance` score has no recency input → ancient circulars rank above today's gazette.

**Fix:** every adapter must parse a date from the listing page (it's there — RBI publishes dated rows, court orders embed the date in the title, NCLT shows it in the table) and write a real `published_at`.

---

### 2. `since_days` is accepted but **never used** by any adapter

Every adapter signature is `(portal_url, document_type, since_days: int = 2)`. The collector passes `since_days=2` (line 450 of [govt_collector.py](../../backend/collectors/govt_collector.py)). But none of the 47 adapters actually filter by it — they just scrape the entire visible index.

**Consequence:** every nightly run re-scrapes the *same* historical PDFs already on the index page. Output volume is bounded only by `_PER_PORTAL_CAP` (15 per portal, hard-coded in [govt_collector.py](../../backend/collectors/govt_collector.py) — see defect D-19), not by recency. The "daily delta" promised by the task name is a fiction; it's a daily *snapshot* of "whatever fits on page 1 of the portal."

**Fix:** combine with #1 — once `published_at` is real, gate `published_at >= NOW() - since_days days` inside each adapter. Or skip via `_dedup_url` against the DB.

---

### 3. Ten adapters require Playwright; if Playwright fails or is missing, they silently return `[]`

Adapters that need a real browser to render JS:
- `scrape_sebi` — [central_regulators.py:289](../../backend/collectors/sources/central_regulators.py)
- `scrape_cerc` — [central_regulators.py:456](../../backend/collectors/sources/central_regulators.py)
- `scrape_pngrb` — [central_regulators.py:498](../../backend/collectors/sources/central_regulators.py)
- `scrape_sci_judgments` — [courts.py:109](../../backend/collectors/sources/courts.py)
- `scrape_ngt` — [courts.py:279](../../backend/collectors/sources/courts.py)
- `scrape_committee_reports` — [parliament.py:132](../../backend/collectors/sources/parliament.py)
- `scrape_mca_notifications` — [ip_permits.py:220](../../backend/collectors/sources/ip_permits.py)
- `scrape_adb_india` — [international.py:149](../../backend/collectors/sources/international.py)
- `scrape_imf_india` — [international.py:192](../../backend/collectors/sources/international.py)
- `scrape_un_india` — [international.py:235](../../backend/collectors/sources/international.py)

The pattern (e.g. SEBI lines 293–325) is:
```python
try:
    html = await render_html(portal_url, wait_for_selector="...", timeout_ms=30000)
    if not html:
        return docs   # silent empty
    ...
except Exception as exc:  # noqa: BLE001
    logger.warning("SEBI scrape failed for %s: %s", portal_url, exc)
    return []         # silent empty
```

**Consequence:** if the worker container doesn't have Playwright browsers installed, **all 10 adapters return `[]`** — that's 10 of the 47 sources (21%) producing nothing, with only a `WARNING` line in the log. SEBI, Supreme Court, NGT, MCA, IMF, UN, ADB — major coverage. They'll appear "registered and active" in the source health table while delivering zero rows.

Same pattern when the wait-for-selector times out (page slow, layout changed, anti-bot wall) — empty result, no surfacing.

**Fix:** verify Playwright is provisioned (`playwright install chromium`); add a startup self-check that fails the worker boot if `render_html` of a known-good page returns empty; emit metrics on per-adapter empty-result rate so Slack can ping when SEBI suddenly returns 0 for 3 days.

---

### 4. `scrape_ecourts_stub` is **declared as a stub** that always returns `[]`

[courts.py:309–327](../../backend/collectors/sources/courts.py):
```python
@register_source("ecourts.gov.in")
async def scrape_ecourts_stub(...):
    """eCourts — STUB.
    The eCourts portal exposes case status only via per-case search forms
    ... It is not crawlable as a flat document list. Wired up here so
    the registry lookup matches and we don't accidentally fall through to
    the generic scraper, but always returns [].
    """
    logger.info("ecourts requires per-case query — not implemented in v1")
    return []
```

**Consequence:** eCourts is in the 47-adapter count but is intentionally non-functional. It's correctly named `_stub`, but it inflates the inventory.

**Fix:** either implement the per-case query path (CAPTCHA + state cascade — non-trivial) or remove it from the registry until v2.

---

### 5. Selector-only filters → "wrong things" make it through

Each adapter passes an `href_filter` lambda (e.g. SEBI lines 305–315) that whitelists URLs by substring (`.pdf`, `/sebi_data/`, `intmid=`). If the portal redesigns its URL scheme, two things happen:
- **False negatives:** real PDFs get dropped because the new path doesn't match. Adapter returns 0.
- **False positives:** unrelated content slips through (e.g. RBI's `BS_PressReleaseDisplay` matches the press release index, header banners, login pages, generic site nav). The `_is_junk_title` heuristic removes the most obvious junk ("Click here", "PDF") but doesn't filter by document semantics.

The collector logs `dropped %d junk` (e.g. line 268, line 318, line 360) — that counter is the only signal that the selector is over-broad. **Nobody reads it.**

**Consequence:** when a portal renames an upload directory, the adapter goes silently quiet. When it adds a new nav link that matches the filter, you get nav-bar entries in the feed.

**Fix:** persist `dropped_junk_count` per run into `govt_collection_runs`; alert when junk-rate >50% or doc-rate drops to 0 for 3 consecutive runs.

---

## The single combined symptom

Most of what the user sees as "wrong" is the compound of #1+#2+#3:
- ~21% of adapters silently empty due to Playwright (#3).
- 100% of adapters lying about dates (#1).
- 0% of adapters honoring "since_days" (#2).

Net effect: **the feed shows whatever happens to be on the front page of each portal today, mixed with stale re-scrapes from previous nights, all stamped with `collected_at` and ranked as if they're current.** That's the "wrong things" surfacing.

## How to triage in one query

```sql
-- Run after a nightly collection. Anything in this list is silently dead.
SELECT
  s.name,
  s.portal_url,
  s.last_scraped_at,
  s.consecutive_failures,
  COALESCE(d30.docs_30d, 0) AS docs_30d
FROM govt_document_sources s
LEFT JOIN (
  SELECT source_id, COUNT(*) AS docs_30d
  FROM govt_documents
  WHERE collected_at > NOW() - INTERVAL '30 days'
  GROUP BY source_id
) d30 ON d30.source_id = s.id
WHERE s.is_active
  AND COALESCE(d30.docs_30d, 0) = 0
ORDER BY s.last_scraped_at NULLS FIRST;
```

Adapters returning 0 docs in 30 days while marked active → either Playwright down (#3), selector drifted (#5), or stub (#4).

```sql
-- And to expose lie #1: how many docs have a real published_at?
SELECT
  COUNT(*) FILTER (WHERE published_at IS NULL) AS no_date,
  COUNT(*) FILTER (WHERE published_at IS NOT NULL) AS has_date,
  ROUND(100.0 * COUNT(*) FILTER (WHERE published_at IS NOT NULL)
        / NULLIF(COUNT(*), 0), 1) AS pct_with_date
FROM govt_documents;
```
Expect: `pct_with_date ≈ 0.0%`.

## Defects to add to documents-defects.md

| ID | Sev | Issue | Where |
|---|---|---|---|
| D-22 | **P0** | Every adapter returns `published_at: None`. No real document dates anywhere → ranking and recency are fictional. | Every file in `backend/collectors/sources/` + legacy paths in `govt_collector.py` lines 203, 250, 300 |
| D-23 | **P0** | `since_days` accepted but never honoured by any adapter → daily runs re-scrape historical docs, no real delta. | Same files |
| D-24 | **P1** | 10 Playwright-dependent adapters (SEBI, SCI, NGT, MCA, ADB, IMF, UN, CERC, PNGRB, committee_reports) silently return `[]` on browser failure or selector timeout. | listed above |
| D-25 | P1 | `scrape_ecourts_stub` is a wired-up no-op; inflates source count without contributing data. | [courts.py:309](../../backend/collectors/sources/courts.py) |
| D-26 | P2 | Per-adapter `dropped_junk_count` is logged but not persisted → silent selector drift. | Each adapter, e.g. [central_regulators.py:268](../../backend/collectors/sources/central_regulators.py) |
