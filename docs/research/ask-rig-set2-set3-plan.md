# Ask-RIG Set 2 (Personalization) + Set 3 (Live-web fusion) — build plan

> **STATUS: SHIPPED 2026-06-21.** 86 tests pass; full live + in-browser validation.
> Set 2 (auth, saved/alerts, watch, mutes, catch-me-up, personalized /ask) and Set 3
> (web search + extract + RRF fuse + /research) all built, tested, and wired into the
> tabbed UI. Web fusion degrades gracefully until `ASKRIG_SEARXNG_URL` points at a live
> SearXNG. See [[project_ask_rig_build]] memory for the full record.

Goal: jump from Set 1 → fully-built, extensively-tested, **user-specific** Set 2 + Set 3.

## Hard architectural rule
The corpus Postgres stays **read-only** (`analytics_user`). ALL per-user writes go to a
**separate app DB** (`ASKRIG_APP_DB_URL`, default `sqlite+aiosqlite`). Two engines,
never mixed. This is the seam the agent (future) also writes through.

## Set 2 — Personalization & delivery (the "user-specific & strong" core)
App-DB tables (SQLAlchemy async ORM):
- `users` — id, username, pwd hash+salt (pbkdf2, stdlib), default langs, home geo.
- `user_tokens` — bearer tokens (sha256-hashed), many per user.
- `query_history` — every /ask logged per user.
- `saved_searches` — named query + high-water `last_seen_published_at` → **alert** = new matches since.
- `watched_entities` — entity_id + name + high-water → **"what's new"** per entity.
- `mutes` — kind ∈ {source, language, keyword, entity} + value → filtered from results.
- `read_articles` + `user_state.last_catchup_at` → **catch-me-up** = unseen since last visit.

Personalization applied to retrieval (`personalize.py`, pure + tested):
- **Mute filter** (source/language/keyword) on returned docs — cheap, in-process.
- **Entity mute + watched boost** — one `article_entity_mentions` lookup over the
  returned doc-ids × user's entity set; muted entities dropped, watched ones boosted.

Auth: token bearer (`Authorization: Bearer <tok>`); `current_user` FastAPI dependency.

## Set 3 — Live-web fusion
- `web/search.py` — SearXNG JSON client (`ASKRIG_SEARXNG_URL`); **graceful-degrade** if down.
- `web/extract.py` — trafilatura main-text extraction (httpx fetch, size+timeout capped, SSRF guard).
- `web/fuse.py` — merge web + corpus results by RRF; tag provenance (corpus vs web).
- `/ask` gains `web: bool` → fuse; `/research` = deep-research loop (decompose → search →
  read → synthesize cited) reusing the LLM pool.

## Validation
- Unit: auth hashing, token verify, personalize mute/boost logic, RRF fuse, web-result parse, SSRF guard.
- Integration: every endpoint against a temp SQLite DB (fixture); mocked web provider (no live net in tests).
- Live: real signup → save search → watch entity → personalized /ask → web-fused /ask, end-to-end.
- Gate: 80%+ coverage on new modules; all endpoints return correct per-user isolation
  (user A never sees user B's state).
