# Ask-RIG — continuation prompt (paste this as your first message in a new chat)

---

You are continuing work on **Ask-RIG**, a read-only RAG product with a unified, ChatGPT/Claude-style
agentic chat, inside the `rig-surveillance` repo. Pick up exactly where the last session left off.

## 0. First, load context (do this before touching anything)
- Your auto-memory already carries this project. **Read `memory/project_ask_rig_build.md` in FULL**
  (it is the source of truth for everything below) plus the related notes it links.
- Read `CLAUDE.md` at the repo root for deployment topology.
- The product lives at `products/ask-rig/`. Skim `app/chat.py` (the orchestrator), `app/planner.py`,
  `app/reflect.py`, `app/config.py`, and `app/static/index.html`.

## 1. What Ask-RIG is
- A FastAPI service: ONE streaming chat endpoint (`POST /chat`, SSE) over a corpus of Indian news
  (EN/TE/HI/TA) + live web. Anonymous, no auth.
- Pipeline per turn: **plan** (LLM planner: standalone-query/follow-up/web-gate/entity) → **retrieve**
  (corpus hybrid v4+FTS+RRF + on-demand entity feed + live web) → **reflect/escalate** (gap-fill 2nd
  pass on complex questions) → **synthesise** (depth-calibrated grounded answer with [S#] citations).
- Frontend: single `app/static/index.html` ("AXIOM Reading Room" design — warm paper light default +
  warm-charcoal dark; persists thread to localStorage; copy/regenerate/new-chat).

## 2. State of the work (branch `feat/ask-rig-chat`)
Built/shipped this session (verify with `git log` + `git status`):
- Smart planner (`app/planner.py`), agent-loop escalation (`app/reflect.py`).
- Depth-v2 synthesis prompt (`CHAT_SYSTEM` in `app/chat.py`): paragraph-per-point, relevance
  self-filter, anti-hedge opener, "As of <real date>" anchor, hard structure rules near the top.
- Web full-text extraction (`app/web/extract.py::enrich_web_results`, trafilatura — NOT Crawl4AI).
- UI: persist-across-refresh, copy, regenerate, labeled "New chat" button.
- Durable dev infra (Startup items, see §4).
- Tests: `tests/test_planner.py`, `test_reflect.py`, `test_web_enrich.py` (+ existing). Run with
  `python -m pytest -q --ignore=tests/test_accounts_api.py --ignore=tests/test_brief_api.py`
  (those two fail pre-existing on missing `aiosqlite` — unrelated).

## 3. Hard constraints (do NOT violate)
- **Never fabricate** results/eval data; report trusted/unverified/failed separately; inspect artifacts.
- **No clusters/stories** anywhere in Ask-RIG (clustering not production-ready) — use per-article tables.
- Corpus is **READ-ONLY** (connects as `analytics_user`, `default_transaction_read_only=on`).
- Git: attribution is **disabled** globally — no Co-Authored-By trailer. Conventional-commit messages.
- Generation model: `llama-3.3-70b-versatile` via Groq key-pool rotation (`app/llm.py`).

## 4. Infrastructure & access (you have the same tools — Bash, SSH, curl)
- **Hetzner prod server:** `ssh -i ~/.ssh/rig_hetzner -o StrictHostKeyChecking=no root@178.105.63.154`
  (Docker host; `docker ps`, `docker exec rig-postgres psql -U ...`, etc. Caddy is dockerized as
  `rig-caddy`.) SearXNG = container `rig-searxng` on `infrastructure_rig-network` (internal port 8080,
  no published host port).
- **Local dev needs THREE things up (all should auto-start at logon):**
  1. **Ask-RIG API server** → `http://localhost:8010` (durable Startup item `RIG-AskRig-Server.vbs`;
     runs uvicorn with `--reload`; log `C:\Users\Dell\.askrig-server.log`).
  2. **SearXNG tunnel** → `http://localhost:8899` → Hetzner `rig-searxng:8080` (Startup item
     `RIG-SearXNG-Tunnel.vbs`; log `C:\Users\Dell\.searxng-tunnel.log`). `.env` points web search here.
  3. **Postgres tunnel** → `localhost:15432` → Hetzner Postgres (the corpus). NOT yet a durable Startup
     item — if it drops, queries error (DB, not "Failed to fetch"). Making it durable is a pending task.
- Scripts for all of the above live in `products/ask-rig/scripts/` (`askrig-server.sh`,
  `searxng-tunnel.sh`, `*-hidden.vbs`, `install-*.ps1`).
- Secrets (DB DSN, LLM keys) are in `products/ask-rig/.env` — **gitignored, never commit**.

## 5. Run / verify (don't `preview_start` ask-rig — port 8010 conflict with the durable server)
```bash
# health
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8010/                 # server
curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8899/search?q=x&format=json"  # searxng
(echo > /dev/tcp/localhost/15432) 2>/dev/null && echo DB-OPEN || echo DB-CLOSED  # postgres tunnel
# end-to-end chat (counts SSE event types)
curl -N -s -X POST http://localhost:8010/chat -H "Content-Type: application/json" \
  -d '{"query":"Who is Revanth Reddy","history":[]}' --max-time 70 \
  | grep -oE '"type": *"[a-z]+"' | sort | uniq -c
```
First chat query after a server restart pays a ~15-25s LaBSE embedder cold-load — be patient.

## 6. Known good test queries
- "What is the latest in Telangana across infrastructure, education and politics?" (triggers escalation)
- "Who is Revanth Reddy" (profile → entity feed, no web)
- "How is the situation in the USA regarding immigration" (web-heavy; was the depth/contamination A/B)

## 7. Pending / next (pick up here)
1. **Commit** the uncommitted work on `feat/ask-rig-chat` (depth-v2 prompt, web bump, new-chat button,
   server/tunnel scripts), then optionally push + PR.
2. Make the **Postgres 15432 tunnel durable** (Startup item, mirror the SearXNG one).
3. **Phase 4:** faithfulness/verify pass (does every claim trace to its cited source?) + Langfuse tracing.
4. **Retrieval quality:** relevance reranking / corpus-vs-web weighting for non-India (US/China/Russia/
   Europe/Middle-East) questions — the corpus is India-tilted; lean web for global topics.
5. **Mem0** cross-session memory is BLOCKED on the no-auth identity decision (per-browser only for now).

Start by reading the memory file, then confirm the 3 local deps are up (§5), then tell me what you find
and propose the next step.

---
*Generated 2026-06-21. If anything here is stale, the live source of truth is
`memory/project_ask_rig_build.md` and `git log` on branch `feat/ask-rig-chat`.*
