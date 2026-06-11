# YouTube Scraping & Data-Extraction — Rebuild Kickoff

**Status:** greenfield rebuild. The existing module is **reference only** — we are
NOT iterating on it, we are replacing it. It works but the output quality is poor
and the IP-block handling is fragile. This doc captures what exists, why it's not
good enough, and the hard problems the new build must solve.

**Date:** 2026-06-10
**Owner:** RIG Surveillance
**Scope:** ingest YouTube (channels → videos → transcripts) and extract
entity-relevant, timestamped, English-summarised clips for the intelligence corpus.

---

## 1. What we're building

A pipeline that, per monitored YouTube channel:

1. discovers new videos,
2. obtains a usable transcript (captions / audio→ASR),
3. extracts the segments that mention monitored political entities,
4. produces a clean **English** summary + precise start/end timestamp + embedding,
5. stores a clip the user can click and "roll the tape" on.

The output feeds the **Clips** pillar (`/clips`) and the wider corpus
(entity mentions, embeddings for RAG/relevance).

---

## 2. The old module — reference map (do NOT extend, just learn from it)

| Concern | Where it lives today |
|---|---|
| Core collector | `backend/collectors/youtube_collector.py` (~1230 lines, single file) |
| Celery queue | `youtube` → `worker-youtube`, **concurrency 1** (see `CLAUDE.md` topology) |
| Groq calls | `backend/nlp/groq_client.py` (`call_groq`, `FAST_MODEL`, `transcribe_audio_with_whisper`) |
| Embeddings | `backend/nlp/nlp_embedding.py` (`generate_embedding`, LaBSE) |
| Entity disambiguation | `entity_aliases` table (region-aware) via `load_alias_rules()` |
| Storage | `youtube_clips` table (schema below) |
| API/UI | `/clips` page; router was historically `clips_router.py` (now removed in this branch — verify), tests in `backend/tests/test_clips_router.py` |
| IP-reputation rule | memory: never raw-call yt-dlp / transcript-api from a Hetzner debug shell; always throttle; **burnt IP recovery = 24–72h** |

### Old pipeline flow (what to keep conceptually)
- **Video discovery** has a 3-tier fallback chain that is actually good and worth
  reusing: free channel **RSS Atom feed** (`youtube.com/feeds/videos.xml?channel_id=`)
  → **yt-dlp** (cookies + proxy, `skip authcheck`) → **Data API v3 /search** (100
  units/channel, key rotation across `YOUTUBE_API_KEY_2..5`). RSS-first is the quota
  saver — keep that idea.
- **Transcript** has a 4-tier fallback: `youtube-transcript-api` (captions) →
  yt-dlp VTT subtitle download → **Groq Whisper** on downloaded audio → **metadata-only**
  (title+description). Each tier stamps `transcript_source` + a `confidence` weight
  (captions .95 / whisper .85 / yt_dlp .85 / metadata .30).
- **Extraction**: transcript chunked into 10-min windows (max 6/video), each sent to
  Groq with the entity list + alias block; Groq returns clips with entity, start/end,
  English summary, importance; hallucinated entities (not in the canonical list) are
  rejected; clips deduped within 5s.

---

## 3. Why the old one "sucks" — concrete failure modes to BEAT

From the clips audits (`docs/qa/clips-data-quality-report.md`,
`clips-prod-readiness-2026-04-28.md`, `clips-debug-report.md`):

1. **Two competing pipelines / schema split.** Production UI read `video_clips`
   (keyed by free-text `keyword`) while the good collector wrote `youtube_clips`
   (keyed by entity). Result: the clean pipeline's output never reached users.
   → **New build: ONE table, ONE pipeline, entity-keyed. No keyword path.**
2. **~30% filler summaries** ("too short to summarise", "Opening clip…",
   "Clip around X at 0:00") shown as real synopses.
3. **Polluted keyword list** — `clip` itself was a tracked keyword; many topics 0–60%
   on-topic. → entity-driven only, no free-text keywords.
4. **Non-English transcripts surfaced raw** to the English UI (Gujarati/Odia/Devanagari
   text and even bare punctuation `। । ।` as "clips").
5. **Hallucinated / non-canonical `matched_entity`** leaked despite the guard
   (47 clips); some reached `user_entities` and showed in UI.
6. **Whisper fallback was silently dead** — yt-dlp `bestaudio[ext=m4a]` selector
   matched nothing on DASH-muxed videos; 0/1445 clips ever used Whisper, failures
   logged at DEBUG so it was invisible. (Format selector since broadened, but the
   lesson stands: **no silent fallbacks, log every drop with a reason + metric.**)
7. **Metadata-only fake timestamps** — 489 caption clips had `start=0,end=15` but a
   metadata URL; columns and embed URL disagreed. → invariant: real timestamp XOR
   full-video link, never a mix.
8. **Empty `transcript_segment`** on 8/12 sampled caption clips (NOT NULL → `''`).
9. **Almost no clustering** — 200 distinct source videos for 204 clips; barely any
   topic gets >1 clip. Extraction granularity / dedup needs rethink.

**Design takeaways for the rebuild:** single entity-keyed table; reject filler &
non-English summaries at insert; enforce timestamp↔URL invariant; never store empty
preview text; every fallback path observable (metric + WARNING); split the giant
collector into small modules (discovery / transcript / extract / store).

---

## 4. The hard problem: IP blocks (solve creatively)

YouTube aggressively blocks **data-center IPs** (Hetzner) from anonymous
transcript/RSS/audio fetches. Today's mitigations are brittle:
- `YOUTUBE_COOKIES_PATH` — an authenticated session cookie file (bypasses some blocks,
  but cookies expire and a flagged account makes it worse).
- `YOUTUBE_PROXY_URL` — single SOCKS/HTTP proxy.
- A process-level circuit breaker (`_IP_BLOCK_THRESHOLD=3` consecutive blocks → stop
  the transcript path).
- **Operational rule (memory `feedback_youtube_ip_reputation`): never probe yt-dlp /
  transcript-api raw from a shell on the prod IP — CLI probes burnt the IP on
  2026-05-09; recovery took 24–72h.** All access must go through a throttle.

**Creative directions to evaluate (the new build's real research task):**
- **Residential / rotating proxy pool** (vs the single static proxy) — biggest lever.
- **Official Data API captions** where the channel allows it (no scraping).
- **Audio-first via proxy → Groq Whisper** as the primary path, not last resort
  (audio streams are less aggressively blocked than the timed-text endpoint).
- **Third-party transcript providers** (paid APIs) for high-value channels — buy
  reliability for tier-1, scrape the long tail.
- **Cookie rotation / health-checking** + a warm-up & backoff regime; a dedicated
  low-rep "burner" identity, never the org account.
- **Decouple discovery (RSS, cheap, safe) from transcript (risky)** so a transcript
  block never stalls discovery.
- A real **rate-limiter/throttle service** with global budget + jitter + per-IP
  reputation tracking, replacing the ad-hoc `asyncio.sleep` + circuit breaker.

> Decision needed early: **proxy strategy + budget**. Everything downstream depends on
> how reliably we can pull transcripts. Prototype the proxy/transcript path FIRST and
> measure block rate before building the rest.

---

## 5. Data model (current `youtube_clips`)

Columns written by the old collector (reuse or redesign):

```
video_id, video_title, channel_id, channel_name, video_published_at, video_url,
clip_start_seconds, clip_end_seconds, embed_url,
transcript_segment, transcript_language, transcript_translated,
matched_entity, labse_embedding (vector), relevance_score, processed,
transcript_source, confidence
UNIQUE (video_id, clip_start_seconds, matched_entity)
```

Migrations live in `scripts/migrations/NNN_name.sql` (numbered, idempotent, applied
in order at first boot). A new schema = a new migration.

---

## 6. Environment / config

| Var | Purpose |
|---|---|
| `YOUTUBE_API_KEY`, `YOUTUBE_API_KEY_2..5` | Data API v3 keys, rotated on quota 403 |
| `YOUTUBE_COOKIES_PATH` | Netscape cookie file for IP-block bypass |
| `YOUTUBE_PROXY_URL` | SOCKS/HTTP proxy for yt-dlp + transcript-api |
| Groq pool | 16-key pool via `groq_client` (Whisper is "free" on it) |

Deploy topology (from `CLAUDE.md`): workers run **inside the baked `rig-backend`
container** (no bind mount) — code changes need `docker compose build` or
`docker cp` + restart, not a host reinstall. Beat + all workers are in one container;
do not add a `rig-celery-worker-*` compose service (double-fire footgun).

---

## 7. Suggested build phases

0. **Spike the IP/transcript path** with a chosen proxy strategy; measure block rate
   on 20 real Telangana channels. Decide proxy/budget. (Gate for everything else.)
1. **Schema + migration** for the new clips table (one pipeline, entity-keyed).
2. **Discovery module** (RSS-first, yt-dlp + API fallback) — small, tested.
3. **Transcript module** (audio-first via proxy → Whisper; captions where free) with
   per-path metrics and zero silent failures.
4. **Extraction module** (entity-aware Groq, canonical-only, English-only, quality
   gates at insert: no filler, no empty, timestamp↔URL invariant).
5. **Storage + embeddings + dedup/clustering.**
6. **API + `/clips` wiring**, tests (pytest + vitest), observability.

Follow repo conventions: many small files (200–400 lines), type hints, immutable
patterns, tests-first, idempotent migrations.

---

## 8. Open questions to resolve with the user

- Proxy budget & provider (residential pool vs cheap static)? This sets the ceiling.
- Channel list source — is there a `youtube_channels` table, or are channels derived
  from per-user entity prefs? (Verify; the old task layer that fed `process_video`
  needs locating — it was not found under `backend/tasks/` in the obvious place.)
- Is this for the main RIG corpus, the OSINT Night Desk, or both?
- Keep `youtube_clips` and migrate, or new table + backfill?

---

## 9. New-chat kickoff prompt

(Also in `docs/sessions/youtube-rebuild-prompt.md`.) Paste into a fresh session.
