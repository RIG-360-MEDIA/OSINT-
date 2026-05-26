# Opening prompts for new Claude chats

This folder contains 5 ready-to-paste opening prompts. Each one boots a fresh
Claude Code chat with a god-level persona, full context for its scope, the
"what we have / what we don't" picture, and discussion rules.

## How to use

1. Open a new Claude Code chat in a separate terminal/window.
2. Pick the prompt for that scope (below).
3. Copy the entire file content (everything after "Copy everything below into a fresh chat.").
4. Paste into the new chat as the FIRST message.
5. Wait — the chat will read `docs/onboarding/*` and ask clarifying questions before doing anything.

## The 5 prompts

| File | Persona | Scope |
|---|---|---|
| [01-brief.md](01-brief.md) | Editor-in-chief of an intelligence brief | Build `/brief` page; port the prototype at `~/Downloads/osint (2)`; ~70% maps cleanly to v3 backend |
| [02-map.md](02-map.md) | Senior geospatial visualization architect | Build `/map` page; world + personal layers; visualize `article_locations` data |
| [03-analytics.md](03-analytics.md) | Investigative-tooling data product designer | Build `/analytics` page; journalist tracking, source bias, entity emergence, sentiment, etc. |
| [04-content-platform.md](04-content-platform.md) | Senior publishing platform architect | DISCUSSION ONLY first. New separate site that consumes RIG corpus and publishes in 4 formats |
| [05-historical-pipeline.md](05-historical-pipeline.md) | Senior archive-engineering architect | DISCUSSION ONLY. Multi-decade historical retrieval, 100+ languages, 1B+ docs target |

## Collision-prevention rules

All 5 chats follow these rules to ensure they DON'T break the running RIG system:

- READ-ONLY on `articles` + all `article_*` tables (every chat)
- NEVER touch `backend/tasks/substrate/*` (the v3 drain runs 24/7)
- NEVER touch `backend/nlp/groq_client.py` (the LLM pool)
- NEVER touch `/tmp/drain_watchdog.sh` on Hetzner
- NEVER touch FreshRSS, Celery workers, Ollama on TRIJYA-7

Chats 1, 2, 3 work in the RIG frontend codebase but on separate branches:
- `feat/brief-redesign`
- `feat/map-page`
- `feat/analytics-page`

Chats 4 and 5 are in NEW separate repos — zero overlap with RIG.

## Order

You can run these in parallel safely. Suggested sequence:

1. Start Chat 1 (Brief) — it's the highest-priority surface and has the most context already.
2. Start Chat 4 (Content Platform) — discussion-only, no code, can run alongside.
3. Start Chat 5 (Historical) — discussion-only, no code, can run alongside.
4. After Brief settles on architecture, start Chat 2 (Map) — they share API patterns.
5. After Map progresses, start Chat 3 (Analytics) — heaviest data work, benefits from earlier learnings.

## When in doubt

Each prompt ends with "Begin by reading the onboarding docs, then ask clarifying questions." That's the contract. If a chat skips that and jumps to code, stop it and remind it.
