# Keyword Collectors — Extraction Map (what we get per platform, per post)

**Written 2026-07-08.** Ground truth for the Phase-1 keyword-search collectors
(`backend/collectors/cheap_stack/keyword_search.py`). Every field below is what
the normalizer actually emits into the `social_posts` dict shape — verified
live on the Hetzner box, not aspirational.

Status: ✅ Reddit · ✅ TikTok · ✅ YouTube (+ free transcripts) · ✅ Twitter/X.
Pending: Telegram, Instagram, WeChat, VK.

## Per-post field matrix

| Field | Reddit | TikTok | YouTube | Twitter/X |
|---|---|---|---|---|
| `platform_post_id` + `post_url` | ✅ | ✅ (video id) | ✅ (video id) | ✅ (tweet id) |
| `post_text` | title + selftext | caption | title + search snippet | full tweet text |
| `author_username` | redditor | handle | channel name | handle |
| **likes / upvotes** (`upvotes`) | score (upvotes) | likes (digg) | — (search hides) | likes |
| **comments** (`comment_count`) | ✅ | ✅ | — (search hides) | replies |
| **shares** (`shares`) | — | ✅ | — | retweets |
| **views** (`views`) | — | ✅ (play_count) | ✅ | ✅ |
| `posted_at` | exact | exact | approx (from relative) | exact |
| **media** | `media_urls` (images + reddit-video mp4) | `media_url` (no-watermark MP4) + `thumbnail` | `thumbnail` | `media_urls` (photos + video) |
| **outbound link** | `external_url` + `domain` | — | — | (in text) |
| `duration` | — | ✅ (seconds) | ✅ ("M:SS") | — |
| language | — | `region` | — | `lang` |
| flags | `over_18`, `upvote_ratio`, `is_video` | `region` | `verified` (badge) | `is_retweet`, `is_reply` |
| **spoken content (transcript)** | — | ❌ (no caption API; Whisper-on-MP4 possible) | ✅ **full transcript** (free, box-native) | — |
| `matched_keyword` (provenance) | ✅ | ✅ | ✅ | ✅ |

## Per-community / channel / author (the aggregate dimension)

- **Reddit → community:** `subreddit` name + **`subreddit_subscribers`** (community
  size = reach/importance weighting) + `author_fullname` (`t2_…`, stable across
  username changes).
- **YouTube → channel:** **`channel_id` (UC…)** — bridges a keyword hit into the
  RSS discovery pipeline (monitor that source going forward) — + `verified` badge.
- **Twitter → author:** handle + (in the raw scraper output, not yet surfaced in
  the normalizer) display name, hashtags, @mentions, quote_count — good for network
  mapping.
- **TikTok → author:** handle + `region`.

## Notes / honest limits

- **YouTube transcript** is the richest single signal we have — the actual spoken
  words, free, via `free_transcript.py` (kome.ai primary + Piped backup). ~1/3 of
  videos have no captions (music/short clips) and MISS honestly.
- **YouTube timestamps** are approximate (search returns "7 years ago", not exact);
  raw label kept in `published_text`. No like/comment counts from search.
- **TikTok / YouTube** are **relevance-sorted**, not recency — good for "influential"
  content, not a live feed. **Reddit / Twitter** are chronological live feeds.
- **kw-match metric caveat:** short/1-char tokens (e.g. "PLA-N" → "n") and spelling
  variants (`#telengana` vs Telangana) can make the *literal* match score understate
  real relevance (see the Telangana TikTok 33% case). The content is the truth, not
  the number. TODO: drop 1-char tokens / fold variants.
- **Not yet surfaced but available in raw:** Twitter display name, hashtags,
  mentions, quote_count (in `twitter_scraper._normalise` raw); Reddit flair/awards/
  crossposts (in scraper `raw`).
- **Whisper-on-MP4** (deferred, user declined for now): since we capture playable
  MP4/video URLs, speech-to-text on local GPU would give TikTok transcripts and fill
  YouTube no-caption gaps — universal, free on owned hardware.
