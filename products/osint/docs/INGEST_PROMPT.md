# DB-Chat Prompt — add + verify + activate new sources (safe)

Paste the block below into the DB chat. It adds the ~201 new sources from
`products/osint/docs/sources_to_add.csv`, discovers their feeds, verifies each,
and activates them in staggered batches **without breaking live ingestion**.

---

You are a careful data/ops engineer with WRITE access to the rig-surveillance Postgres
(`rig-postgres`, db `rig`, role `rig`). Your job: add new news sources from a CSV into the
`public.sources` table, discover each one's feed, verify it works, and activate them in
small safe batches **without breaking the running ingestion system**.

## INPUT
- CSV: `products/osint/docs/sources_to_add.csv`
- Columns: `name,url,source_type,language,country_iso,geo_state,reach_tier,category,access_status,note,group`
- ~201 rows, already deduped against current `sources` and access-validated (`access_status=LIVE`,
  except 1 `VERIFY` override = The Guardian). `url` is the homepage (feeds must be discovered).

## TARGET TABLE: `public.sources`
`id uuid (default), name, domain, rss_url, source_type, source_tier int, language, geo_states text[],
topics text[], health_score numeric, consecutive_failures int, is_active bool, last_collected_at, created_at, country`

## HARD SAFETY RULES — do not violate
1. Use the WRITABLE role (`docker exec rig-postgres psql -U rig -d rig`). **`analytics_user` is read-only — never use it for writes.**
2. **Do NOT restart `rig-backend`** — it runs the Celery workers + Beat + FastAPI; a restart triggers the known NEWSROOM cold-start deadlock and disrupts ingestion.
3. **Do NOT edit docker-compose or Celery Beat** — duplicate Beat = double-fired periodic tasks (known foot-gun).
4. **Do NOT call yt-dlp / YouTube** (IP-reputation).
5. **Idempotent** — re-running must not duplicate. Check the domain exists before inserting (pre-SELECT or `ON CONFLICT (domain) DO NOTHING`).
6. **Insert every row `is_active = FALSE` first.** NEVER bulk-activate. Activate only AFTER per-source verification, in batches (Step 5).

## STEP 1 — load + dedup
Read the CSV. For each row, compute the registrable domain from `url`. Skip if a `sources` row with
that domain (or matching `rss_url` host) already exists. (CSV is pre-deduped; re-check for idempotency.)

## STEP 2 — feed discovery (per row)
Find the RSS/Atom feed for each homepage:
- GET the homepage (User-Agent `Mozilla/5.0`, follow redirects, 12s timeout).
- Parse for `<link rel="alternate" type="application/rss+xml"|"application/atom+xml" href=...>`.
- Else try common paths: `/feed`, `/feed/`, `/rss`, `/rss.xml`, `/atom.xml`, `/feeds/posts/default?alt=rss`, `/?feed=rss2`.
- Feed found → `source_type='rss'`, `rss_url=<feed>`.
- No feed but page has clean article links → `source_type='scrape'`, `rss_url=NULL` (keep domain).
  *(The 4 `group=Lite` rows are publisher text endpoints — keep `source_type='scrape'`.)*
- Nothing works → leave inactive, set `consecutive_failures=1`, record the reason.

## STEP 3 — verify (per row, BEFORE activating)
- RSS: feed must be HTTP 200 **and** parse to ≥1 item with title+link. Reject 403/404/empty/geo-block.
- Scrape: homepage HTTP 200 **and** ≥5 article-like links.
- `access_status='VERIFY'` rows (Guardian override): re-check live; proceed only on 200.
- Record a per-row `verified` boolean + failure reason.

## STEP 4 — insert (ALL rows, `is_active=FALSE`)
Field mapping:
- `name` ← name
- `domain` ← registrable host of `url`
- `rss_url` ← discovered feed (or NULL)
- `source_type` ← discovered (`rss`/`scrape`)
- `source_tier` ← `int(reach_tier)`
- `language` ← language
- `country` ← country_iso
- `geo_states` ← `country_iso='IN' AND geo_state<>'' ? ARRAY[geo_state] : NULL`
- `topics` ← `ARRAY[category]`
- `health_score` ← 1.0 · `consecutive_failures` ← 0 · `is_active` ← FALSE · `created_at` ← now()

Insert in one transaction; report inserted count.

## STEP 5 — staggered activation (this is what protects the system)
- Activate ONLY `verified` rows, in **batches of 25**.
- Per batch: `UPDATE sources SET is_active=TRUE` for those 25 → then **pause and watch load** before the next batch:
  - `collectors` worker is **concurrency 1**, `nlp` worker is **concurrency 4** — they fall behind if flooded.
  - Check backlog: `SELECT count(*) FROM articles WHERE collected_at > now()-interval '1 hour'` and/or
    `docker exec rig-backend celery -A celery_app inspect active` (queue depth).
  - Proceed to the next batch only when the previous batch's sources are being picked up **and** the
    nlp backlog is draining (not growing).
- **Stop and report** if any batch spikes failures or the backlog grows unbounded.

## STEP 6 — report
Print: total in CSV · skipped-as-dupes · feeds discovered (rss vs scrape) · verified · inserted ·
activated · and a list of any that **failed verification with the HTTP reason** so they can be fixed manually.

## NOTES
- **Cap per-source volume** if the collector supports a per-run item limit — a few firehose feeds
  (Ghana/Nigeria) once made up ~14% of the corpus from 3–4 sources. A modest per-source cap keeps any
  single new feed from dominating.
- Leave the ~17 India `(national)` rows with `geo_states=NULL` (Hindi-belt multi-state dailies);
  article-level geo tagging handles their coverage.
- Touch existing rows only via the Step-5 activation `UPDATE`s.
