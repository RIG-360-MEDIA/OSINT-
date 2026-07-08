# Phase 2 — Keyword-Collector Persistence (DB handoff)

**Written 2026-07-08.** Hand this to the DB chat. It explains what the collector
side (the "keyword rebuild") has built, what Phase 2 wires up, and the **exact
DB work needed**. Self-contained — the DB chat should not need the full chat log.

---

## 0. TL;DR for the DB chat

We built 7 standalone keyword collectors (Phase 1, proven). Phase 2 = **persist
their output** so keyword searches build a corpus and every dossier number can
drill through to real posts. The **old store-everything social pipeline and its
old rows will be RETIRED** once this works — so we are building a **clean
keyword-driven store**, not preserving the old firehose model. I need you to
finalize the target table + a small migration (add `matched_keyword`, flatten
author, dedup constraint, an audit table) and hand me the upsert contract.

---

## 1. What Phase 1 built (context)

Location: `backend/collectors/cheap_stack/keyword_search.py` — a swap-able
`REGISTRY: dict[platform -> async search fn]`. Each `search_<platform>(query,
limit)` returns a `KeywordSearchResult` whose `.posts` is a tuple of **normalized
dicts** (the `social_posts` shape). All 7 proven live on the Hetzner datacenter box.

| Platform | Method | Auth |
|---|---|---|
| reddit | global keyword search | `REDDIT_SESSION` cookie |
| tiktok | tikwm feed/search | none |
| youtube | innertube search (+ free transcripts via kome/Piped) | none |
| twitter | twscrape | `TWITTER_AUTH_TOKEN`+`TWITTER_CT0` cookies |
| telegram | 97 curated channels via `t.me/s/?q=` | none |
| instagram | search-index discover + web_profile realtime (hybrid) | none |
| wechat | Sogou Weixin + EN→ZH term map + full-content fetch | none |

Verifier: `verify_keyword_collectors.py` (quality-gated). 43 unit tests green.
NOTE: all creds live in `/root/rig/infrastructure/.env` but are **not loaded into
the running `rig-backend` container** yet (Phase 2 step).

---

## 2. The data to store — normalized collector output

**Core fields present on EVERY post** (these map to typed columns):

| field | meaning | existing social_posts column |
|---|---|---|
| `platform` | reddit/tiktok/youtube/twitter/telegram/instagram/wechat | `platform` ✓ |
| `platform_post_id` | platform's id / shortcode | `platform_post_id` ✓ |
| `author_username` | handle / channel / account | ❌ (currently `author_id` FK) |
| `post_text` | title+body / caption / tweet / article title+excerpt | `post_text` ✓ |
| `post_url` | canonical URL | `post_url` ✓ |
| `posted_at` | ISO8601 UTC (some approx — YT) | `posted_at` ✓ |
| `upvotes` | reddit score / IG+TikTok+Twitter likes | `upvotes` ✓ + `likes` ✓ |
| `comment_count` | replies/comments | `comments_count` ✓ |
| `posted_at`, `views`, `shares` | engagement | `views`/`shares` ✓ |
| `matched_keyword` | **the query that found this post** | ❌ NEW |

**Per-platform EXTRAS** (many already have columns; the rest → `raw` jsonb):

- reddit: `subreddit`, `subreddit_subscribers`, `author_fullname`, `media_urls`,
  `external_url`, `domain`, `over_18`, `upvote_ratio`, `is_video`, `has_media`
- tiktok: `media_url` (no-watermark mp4), `thumbnail`, `duration`(sec), `region`, `shares`
- youtube: `channel_id` (UC…), `verified`, `thumbnail`, `duration`("M:SS"), `published_text`, `views`
- twitter: `lang`, `media_urls`, `is_retweet`, `is_reply`, `shares`(RT), `views`
- telegram: `channel`, `views`, `external_urls`, `external_url`, `media_urls`, `has_media`
- instagram: `source` (index|realtime), `is_realtime`
- wechat: `account`, `title`, `content` (**full ~6k-char Chinese article body**)

Existing `social_posts` already has: `likes, comments_count, shares, upvotes,
views, upvote_ratio, is_retweet, is_reply, lang, has_media, media_urls (jsonb),
raw (jsonb)` + enrichment (`sentiment, topic_category, toxicity, …`). So the
**gaps are small** (see §4).

---

## 3. Phase 2 goal + retire-old

- **Persist** keyword-collected posts → the store, tagged with `matched_keyword`.
- **De-dup** on `(platform, platform_post_id)` — repeated searches compound, not duplicate.
- **Audit** each search (keyword, platform, count, latency) → persist-from-use.
- **Retire the old**: after cutover proven on a fresh keyword, drop the old
  ~57k firehose rows (twitter 44k / reddit 8k / telegram 2k / instagram 2k) and
  any columns only the old normalized/watchlist model used.
- Downstream (later): evidence-linking API + `EvidenceModal` UI + re-enable the
  hidden Keyword tab.

Architecture rule (already decided): social is **keyword/on-demand (Meltwater
model)**, NOT store-everything. History builds forward from use.

---

## 4. DB CHAT — please do these

Conventions: numbered idempotent migration `scripts/migrations/NNN_name.sql`
(applied in order at first boot via `docker-entrypoint-initdb.d`). DB access:
`docker exec rig-postgres psql -U rig -d rig`.

**4.1 Decide the target table** (I lean option A):
- **A. Reuse `social_posts`** — keep the good columns, truncate old rows at
  cutover. Least code churn (downstream queries already read `social_posts`).
- **B. New `keyword_posts` table** — clean slate, run both during cutover.
Tell me A or B.

**4.2 Add columns** (to whichever table):
- `matched_keyword text` — the query that surfaced the post.
- `author_username text` — flat handle (so we DON'T need the `social_authors`
  FK for keyword posts; old normalized model retires).
- `channel text` — telegram channel / youtube channel / wechat account.
- `source text` (a.k.a. collector_method) — which collector produced it.
- (optional) `full_content text` — for the WeChat full article body (else `raw`).
- Everything else (channel_id, verified, external_url, domain, duration, region,
  thumbnail, subreddit, subreddit_subscribers, author_fullname, published_text,
  over_18, is_realtime) → stays in **`raw` jsonb**. Confirm that's fine.

**4.3 Dedup constraint** (REQUIRED for upsert):
- Confirm/create `UNIQUE (platform, platform_post_id)`. Tell me if it already
  exists (I couldn't read the index list cleanly).

**4.4 Indexes** for evidence lookups:
- `(matched_keyword, platform, posted_at DESC)`
- `(platform, posted_at DESC)`
- GIN on `raw` if we'll query extras (optional).

**4.5 New audit table** `keyword_searches`:
- `id bigserial pk, keyword text, platform varchar(16), requested_at timestamptz
   default now(), n_results int, took_ms int, client text`.
- Powers persist-from-use + the on-demand log.

**4.6 Retirement migration** (author it, but I run it ONLY after cutover proven):
- `pg_dump`/`CREATE TABLE social_posts_bak_YYYYMMDD AS …` backup first.
- `DELETE`/`TRUNCATE` old firehose rows.
- Drop columns only the old model used (`watchlist_id`, `author_id`,
  `community_id`, `edit_history`, …) — **confirm which are safe** by checking
  no live reader depends on them.

**4.7 Hand me the landing contract**:
- Final column list + the exact upsert. Expected shape:
  ```sql
  INSERT INTO social_posts (platform, platform_post_id, author_username, channel,
    post_text, post_url, posted_at, upvotes, likes, comments_count, shares, views,
    upvote_ratio, is_retweet, is_reply, lang, has_media, media_urls,
    matched_keyword, source, raw)
  VALUES (...)
  ON CONFLICT (platform, platform_post_id) DO UPDATE SET
    upvotes=EXCLUDED.upvotes, likes=EXCLUDED.likes, comments_count=EXCLUDED.comments_count,
    shares=EXCLUDED.shares, views=EXCLUDED.views, matched_keyword=COALESCE(social_posts.matched_keyword, EXCLUDED.matched_keyword);
  ```
  Confirm column names/types so I write `land_keyword_posts()` against the real schema.

---

## 5. What I (collector chat) will do — once you confirm §4.1–4.3

1. `land_keyword_posts(posts)` — map normalized dict → row, upsert on the dedup
   key, extras → `raw`. Test by landing a junk-keyword search; verify rows.
2. Tag `matched_keyword` + write a `keyword_searches` audit row per search.
3. On-demand trigger (rig-backend internal fn/endpoint) — run REGISTRY collectors
   for a keyword → land. Single Celery producer/consumer, no second beat.
4. Load creds into the container (deliberate `rig-backend` recreate).
5. Prove end-to-end on a FRESH keyword (e.g. "Tridel"): search → rows land →
   dedupe on re-search → evidence query returns the backing posts.
6. Then: evidence API + `EvidenceModal` UI + re-enable the Keyword tab.

## 6. Decisions I need from you (blocking)
1. **Table: reuse `social_posts` (truncate old) [A] or new `keyword_posts` [B]?**
2. **Flatten author to `author_username text` [yes] or keep `social_authors` FK [no]?**
3. **Does `UNIQUE (platform, platform_post_id)` already exist?**
4. **Which old-model columns are safe to drop** at retirement (no live reader)?

Answer those + hand me the §4.7 upsert, and I'll build the landing layer.
