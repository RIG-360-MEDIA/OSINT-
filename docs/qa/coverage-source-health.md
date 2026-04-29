# Coverage — Source Health Matrix (2026-04-28)

Snapshot of `sources` filtered to `is_active=true`, joined against article ingest in the last 24 h / 7 d. Total active sources: **242** (RSS 184, scrape 15, api 43).

## Verdict distribution

| Verdict | Count | Meaning |
|---|---:|---|
| `OK` | **35** | At least one article ingested in the last 24 h |
| `IDLE_24H` | 136 | Quiet for 24 h, but produced articles in the last 7 d |
| `SILENT_7D` | **70** | No articles for 7+ days. Subdivides: api 43 · rss 17 · scrape 10 |
| `INVESTIGATE_HEALTH` | 1 | `health_score < 0.5` |
| `INVESTIGATE_FAILS` | 0 | `consecutive_failures ≥ 3` |

**Headline:** ~14 % of active sources actively producing in the last day. ~29 % have been silent for 7+ days. This is **not necessarily a bug** — many `api` sources (YouTube channels, social handles) are genuinely low-volume — but it does inflate the "242 active" count beyond what is operationally true.

## Investigate now

| Source | Domain | Type | Tier | Health | Last collected |
|---|---|---|---|---|---|
| The News International | thenews.com.pk | rss | 2 | 0.40 | 2026-04-25 |

## Top 25 producers (last 24 h)

| Source | Type | Tier | Articles 24 h |
|---|---|---:|---:|
| Dharitri | rss | 1 | 82 |
| Al Jazeera — Asia | rss | 2 | 71 |
| Ada Derana Sri Lanka | rss | 2 | 54 |
| Edex Live — Education | rss | 1 | 47 |
| Bar and Bench | rss | 1 | 38 |
| Hindu Business Line — Corporate | rss | 1 | 37 |
| Hindu Business Line — Economy | rss | 1 | 37 |
| Communications Today | rss | 1 | 35 |
| Economic Times — Economy | rss | 1 | 28 |
| Dawn — Defence | rss | 2 | 28 |
| Economic Times | rss | 1 | 24 |
| ESPNcricinfo | rss | 1 | 23 |
| BBC World News | rss | 2 | 23 |
| Deutsche Welle — English | rss | 2 | 21 |
| HT Education | rss | 1 | 12 |
| Cargo Talk India | rss | 2 | 9 |
| EastMojo | rss | 2 | 9 |
| Eurasian Times | rss | 2 | 8 |
| Education World India | rss | 1 | 7 |
| Express Pharma | rss | 1 | 7 |
| Clinical Trials Arena — India | rss | 2 | 6 |
| Breaking Defense | rss | 2 | 6 |
| Defense News | rss | 2 | 5 |
| Airport World — India | rss | 2 | 4 |
| The Hindu — Opinion International | rss | 1 | 4 |

Tier-1 sources dominate the top of the list (good — quality producers carry the feed).

## Silent for 7+ days — recommended actions

- **api (43 silent)**: most are YouTube channels and Telegram handles. Triage with the Clips/Threads owners — keep cadence-low handles silent if expected, otherwise investigate auth/rate-limit issues.
- **rss (17 silent)**: each one needs a 30-second `curl -I <rss_url>` to confirm endpoint still exists. Likely sites changed feed URLs.
- **scrape (10 silent)**: HTML structure drift; per-source parser hooks need refresh. Likely candidates for retirement.

(Per-source listings of all 70 silent sources omitted from this report to keep it scannable; query in `docs/qa/coverage-audit-2026-04-28.md` Phase 0 reproduces them.)

## Notable producers with scrape problems

- **Communications Today** (`communicationstoday.co.in`): RSS path delivers 35 articles/24 h (healthy ingest), but the full-body `_fetch_and_extract` in `html_collector.py` errors with `parsed tree length: 1, wrong data type or not valid HTML` on most articles. Net effect: articles ingest with `lead_text_original` only, no full body. → defect **C-7 / C-8** in `coverage-defects.md`.

## How to refresh this matrix

```sql
-- run inside rig-postgres
WITH src AS (
  SELECT s.*, COALESCE(
    (SELECT count(*) FROM articles a
       WHERE a.source_id=s.id AND a.collected_at>now()-interval '7 days'),0
  ) AS d7
  FROM sources s WHERE is_active=true
)
SELECT verdict, count(*) FROM (
  SELECT
    CASE
      WHEN health_score < 0.5 THEN 'INVESTIGATE_HEALTH'
      WHEN consecutive_failures >= 3 THEN 'INVESTIGATE_FAILS'
      WHEN d7 = 0 THEN 'SILENT_7D'
      WHEN NOT EXISTS (SELECT 1 FROM articles a WHERE a.source_id=src.id AND a.collected_at>now()-interval '24 hours') THEN 'IDLE_24H'
      ELSE 'OK'
    END AS verdict
  FROM src
) v GROUP BY 1 ORDER BY 1;
```
