# Social Pipeline — Design (new build)

Built to match the proven RIG substrate pattern shared by **articles**, **clippings**,
and **youtube clips**. No reuse of the old `social_posts` table or the old Signal Room.

## The proven RIG pattern (confirmed across all 3 existing pillars)

| Stage | Articles | Clippings | YouTube |
|---|---|---|---|
| Discovery queue | (RSS feeds) | (paper list) | `pending_youtube_videos` |
| Raw table | `articles` | `clippings` | `youtube_clips_v2` |
| Status enum | `substrate_status` | `substrate_status` | `substrate_status` |
| Drain task | `substrate_drain` | `drain_pending_clippings` | `drain_pending_clips` |
| Extraction | 1 Groq call, lang-routed | 1 Groq call, lang-routed | 1 Groq call, entity-keyed |
| Flat write-back | summary/topic/entities/embedding | same | same |
| Child tables | claims/quotes/stances/numbers/locations/events | 6 `clipping_*` | 4 `youtube_clip_*` |
| Entity resolve | `article_entity_mentions` matview | `clipping_entity_mentions` | `youtube_clip_entity_mentions` |
| Embedding | LaBSE 768 | LaBSE 768 | LaBSE 768 |
| Queue | `nlp` | `documents` | `youtube` |

**Universal invariants** every pillar follows:
1. Raw lands with `substrate_status='pending'` + a raw-text column.
2. A periodic **drain task** claims rows `FOR UPDATE SKIP LOCKED`, `pending→processing`.
3. **One language-routed Groq call** extracts everything in structured JSON.
4. Write-back = flat cols on base table **+ DELETE-then-INSERT child tables** (FK `... ON DELETE CASCADE`).
5. `entities_extracted JSONB` → resolved by a **matview** joining `entity_dictionary`.
6. `extraction_version=3`, LaBSE 768 embedding, lifecycle `pending→processing→ok|extract_failed|junk`.
7. Own Celery queue + Beat drain; junk-guard on short/empty bodies.

YouTube adds the **discovery-queue split** (a `pending_*` table separate from the
artifact table) — the right model for social, which is watch-list driven.

---

## Social schema (migration 118)

### A. `social_watchlist` — what to monitor (discovery config)
```
id              bigserial PK
platform        text   -- twitter | reddit | telegram | instagram
target_type     text   -- handle | subreddit | channel | hashtag | keyword | location
target_value    text   -- e.g. 'narendramodi', 'india', 'OperationSindoor'
label           text   -- human note
is_active        bool   default true
fetch_limit     int    default 25
last_seen_id    text   -- incremental cursor (reddit after / telegram min_id / tweet id)
last_run_at     timestamptz
created_at      timestamptz default now()
UNIQUE(platform, target_type, target_value)
```

### B. `social_posts` — raw collected posts (the scrapers' common shape)
```
id                bigserial PK
platform          text         -- twitter|reddit|telegram|instagram
platform_post_id  text         -- platform's native id
author_username   text
author_name       text
post_text         text         -- RAW content (the substrate input)
post_url          text
posted_at         timestamptz
-- engagement (social-unique: reach + virality signal)
likes             int
comments_count    int
shares            int          -- retweets / forwards
upvotes           int          -- reddit
views             bigint        -- telegram / video
upvote_ratio      real          -- reddit controversy gauge
-- provenance / threading
watchlist_id      bigint  FK -> social_watchlist(id)
parent_post_id    bigint  FK -> social_posts(id)   -- comments/replies link to parent
forwarded_from    text          -- telegram propagation source
has_media         bool
media_urls        jsonb
raw               jsonb         -- full platform payload, forward-compat
-- substrate (mirrors articles/clippings exactly)
language_iso      text
summary           text          -- only for longer posts
sentiment         text          -- positive|negative|neutral|mixed  (post-level)
sentiment_score   real          -- -1..1
topic_category    text
primary_subject   text
entities_extracted jsonb
labse_embedding   vector(768)
substrate_status  varchar(16) default 'pending'
extraction_version int default 0
collected_at      timestamptz default now()
enriched_at       timestamptz
UNIQUE(platform, platform_post_id)
```

### C. Child tables (FK `post_id bigint -> social_posts(id) ON DELETE CASCADE`)
Same family as the other pillars, scoped to what social posts actually contain:
- `social_post_claims`   (claim_text, subject_text, predicate, object_text, confidence)
- `social_post_quotes`   (speaker_name, quote_text, is_direct)
- `social_post_stances`  (actor, actor_entity_id, target, stance, intensity)  -- directed sentiment
- `social_post_locations`(location_text, country, region, city, lat, lng, is_primary)
- `social_post_hashtags` (tag)            -- social-specific discovery signal
- `social_post_mentions` (mentioned_username)  -- social-specific network signal

### D. Entity resolution matview
`social_post_entity_mentions` — unrolls `social_posts.entities_extracted` → joins
`entity_lookup.name_norm` → `entity_dictionary` (post_id, entity_id, canonical_name,
entity_type, country, surface_form). Refreshed by `refresh_social_post_entity_mentions()`.
Kept separate from article/clip/clipping matviews by design.

---

## Extraction — `GROQ_SYS_SOCIAL` (new prompt)

One language-routed Groq call per post, like the others, but tuned for social:
- **Short posts** (tweets, reddit titles, IG captions): entities + sentiment + stances only.
- **Long posts** (telegram, reddit selftext): full substrate — summary, claims, quotes, stances, locations.
- Always emit: `language`, `sentiment` (+score), `topic_category`, `entities_extracted`,
  `hashtags`, `mentions`, `actor_stances` (directed).
- Junk-guard: posts < ~25 chars or pure-link → `substrate_status='junk'`.

Sentiment is **first-class** here (the social product's core signal), unlike articles
where it's derived from stances. We store both: a post-level `sentiment` AND directed
`social_post_stances` (actor→target), so we can answer "how does X feel about Y."

---

## Celery wiring — new `social` queue (rebuilt)

| Task | Trigger | Action |
|---|---|---|
| `tasks.social.collect_twitter` | Beat 15 min | walk active twitter watchlist → scrape → insert posts (pending) |
| `tasks.social.collect_reddit` | Beat 15 min | active subreddits/keywords → scrape → insert |
| `tasks.social.collect_telegram` | Beat 15 min | active channels (min_id cursor) → scrape → insert |
| `tasks.social.collect_instagram` | Beat 30 min | active IG accounts → **relay (TRIJYA-8)** → insert |
| `tasks.social.drain_pending` | Beat 2 min | claim `pending` posts SKIP LOCKED → Groq enrich → child tables → `ok` |

- Collectors route to `social`; drain can share `social` or go to `nlp` (LLM-heavy). TBD.
- Incremental: each collector advances `social_watchlist.last_seen_id` to avoid re-pulling.
- Dedup: `ON CONFLICT (platform, platform_post_id) DO NOTHING`.
- Instagram collector calls the TRIJYA-8 relay; the other three run direct from Hetzner.

---

## Surface (new, not the old Signal Room)
Out of scope for the schema, but the data is API-ready: `/v1` can expose social posts
filtered by entity (via the matview), platform, sentiment, date — same envelope as the
other pillars, and `entity_multi_coverage` can fold social in as a 4th pillar.

## Open decisions (need user input before migration)
1. Table naming: reuse `social_posts` (old one dropped) or a fresh name (`social_signals`)?
2. Drain queue: `social` (simple) or `nlp` (shares LLM worker pool)?
3. Comments depth: store Reddit/IG comments as child `social_posts` (parent_post_id), or skip comments in v1 and only do top-level posts?
4. Sentiment model: Groq LLM sentiment (consistent w/ substrate) vs a cheap local classifier (faster/cheaper at social volume)?
</content>
