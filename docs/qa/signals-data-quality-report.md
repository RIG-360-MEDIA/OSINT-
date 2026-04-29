# Signals — Data Quality Report

**Probed:** 2026-04-27 against `rig-postgres` (live).
**Source:** companion to [signals-live-session.md](signals-live-session.md).

## Schema audit

| Table | Rows | PK | Critical constraints | Notes |
|---|---|---|---|---|
| `social_monitors` | 14 | `id` UUID | UNIQUE `(platform, identifier)` | No index on `(platform, is_active)` → SIG-6. |
| `social_posts` | 207 | `id` UUID | UNIQUE `(platform, platform_post_id)` | Indexes on `collected_at DESC`, `(monitor_id, collected_at DESC)`, `platform`, GIN on `matched_entities`, HNSW on `labse_embedding`. |
| `social_sentiment_daily` | 25 | `id` UUID | UNIQUE `(monitor_id, date)` | Idempotent ON CONFLICT DO UPDATE. |
| `user_entities` (consumer) | 30 | `id` UUID | UNIQUE `(user_id, canonical_name)` | All 30 rows owned by one user. |

## Row counts and freshness

| Platform | Rows | First seen | Last seen | Staleness vs today |
|---|---|---|---|---|
| reddit   | 100 | 2026-04-21 10:05 | 2026-04-21 10:05 | **6 days** |
| telegram | 107 | 2026-04-23 13:04 | 2026-04-23 15:59 | **4 days** |
| twitter  | 0   | — | — | **∞ (never collected)** |

Reddit's first/last-seen timestamps are **identical** — all 100 rows
landed in a single batch run on 2026-04-21 and nothing has run since.

## Integrity checks

| Check | Result |
|---|---|
| `(platform, platform_post_id)` duplicates | 0 ✓ |
| `sentiment_score IS NULL` | 0 % ✓ |
| `matched_entities` empty | 100 % ❌ (SIG-10) |
| `monitor_id` orphan FKs | 0 ✓ (FK constraint enforces) |
| `posted_at > collected_at` | 0 ✓ |

## Sentiment distribution (telegram, n=107)

Sample of 10 most-recent rows:

| Score | Excerpt |
|---|---|
| 0      | `Delhi HC orders social media platforms to remove videos…` |
| 0      | `SRH Captain: సన్‌రైజర్స్‌లోకి ప్యాట్ కమిన్స్…` (Telugu) |
| 0.5423 | `As part of its ongoing outreach to keep the media…` |
| 0.3612 | `Amid the evolving situation in West Asia…` |
| 0.2960 | `During the inter-ministerial briefing…` |
| 0.5719 | `During the inter-ministerial briefing…` |
| 0.5423 | `Paying homage to the legendary film director…` |
| 0.5859 | `Amid the evolving situation in West Asia…` |
| 0.1280 | `…recent developments in West Asia, Nidhi…` |
| -0.7003 | `…Mukesh…` (negative tone) |

**Quality flags:**
- All 107 telegram rows tagged `post_language='en'` regardless of
  actual content (SIG-13). The Telugu row collapses to neutral 0.
- VADER thresholds (±0.15 per [social_task.py:376-523](../../backend/tasks/social_task.py))
  → first row "Delhi HC orders … to remove videos" is **factually
  negative news** but VADER scored it 0.0; aggregator buckets it
  neutral. Spot-checks suggest VADER mis-classifies on factual /
  bureaucratic prose.

## Entity-match audit (SIG-10 deep dive)

| Population | Count |
|---|---|
| `user_entities` rows (1 user) | 30 |
| `social_posts.matched_entities` non-empty | 0 / 207 |
| Manual sample: telegram post mentions "BRS Party Official" matches user entity "BRS"? | YES — should match, doesn't |

`_fetch_user_entities` ([social_task.py:26-35](../../backend/tasks/social_task.py)):

```python
text("SELECT DISTINCT canonical_name FROM user_entities")
```

Two issues:
1. Posts existed before entities were added → entity-tagging is
   write-time only, no re-tag job.
2. Query has no `user_id` filter — every post would match against the
   union of all users' entities (privacy / correctness).

## N+1 evidence (SIG-4)

```sql
EXPLAIN ANALYZE
  SELECT m.id, (SELECT count(*) FROM social_posts WHERE monitor_id=m.id)
  FROM social_monitors m;
```

```
Seq Scan on social_monitors m  (rows=14, loops=1)
   SubPlan 1
     ->  Aggregate
           ->  Seq Scan on social_posts  (rows=15, loops=14)
                 Filter: (monitor_id = m.id)
                 Rows Removed by Filter: 192
 Execution Time: 0.555 ms
```

Sub-plan executes once per monitor row (loops=14). Acceptable today;
linear in monitor count, full-scans `social_posts` each loop. Fix:
single GROUP BY + LEFT JOIN.

## Volume projection (until SIG-11 fixed)

If SIG-11 is unresolved:
- Beat keeps publishing `collect_reddit/twitter/telegram` every
  30 min / 1 h / 30 min.
- `kombu_message` table grows by ~5/h indefinitely (currently 479).
- Postgres broker overhead becomes meaningful after ~10 k pending.

Recommendation: pause Beat schedules for `collect_*` tasks until the
queue topology fix lands, OR ship SIG-11 fix first thing.
