# Ask-RIG — continuation prompt (paste this as your first message in a new chat)

---

You are continuing work on **Ask-RIG**, a read-only RAG + **agentic** intelligence chat over a
news corpus, in the `rig-surveillance` repo. Pick up exactly where the last session left off.

## 0. Load context first
- Your auto-memory carries this project — **read `memory/project_ask_rig_build.md` IN FULL** (the
  source of truth) and the notes it links.
- Read `CLAUDE.md` (deploy topology) and the two specs:
  `docs/handoffs/ask-rig-agentic-spec.md` (the vision) and `ask-rig-qa-report.md` (QA findings).
- Product: `products/ask-rig/`. Skim `app/chat.py` (orchestrator/router) and the mode modules.

## 1. What it is now — a MODE-AWARE AGENT
One streaming endpoint `POST /chat` (SSE). `chat_stream` routes each turn to a MODE *before*
synthesis (each gated by a cheap regex; an LLM makes the real intent call; non-matches fall
through to normal synthesis). Order: **drill-down → dossier → quantify → enumerate → synthesize**.
- **Enumerate** (`app/enumerate.py`): "give me all/every X" → full filtered list (entity+time,
  recency-correct), optional live sentiment classify. Emits a `list` SSE event → card UI.
- **Drill-down** (`app/drilldown.py`): a list card's **Explain** (or "explain #5") sends an
  `article_id` → fetches that exact article's full text + quotes → grounded explanation
  (explains Telugu/Hindi in English).
- **Quantify** (`app/quantify.py`): "how many / count / trend / this week vs last" → REAL counts
  from structured queries; sentiment counts are a labelled SAMPLED ESTIMATE.
- **Dossier** (`app/dossier.py`): "everything on / dossier on / profile of X" → 5-section cited
  profile (volume, recent headlines, quotes, co-mentions, trend). **Export** = Download-as-.md.
- **Synthesize**: the deep, cited, structured answers (with depth-v2 prompt + injection defense).

## 2. State (branch `feat/ask-rig-chat`) — all committed
Recent commits: depth answers · enumerate+drilldown · quantify+dossier+export · injection fix.
Run tests: `python -m pytest -q --ignore=tests/test_accounts_api.py --ignore=tests/test_brief_api.py`
(those two fail pre-existing on missing `aiosqlite`). New-mode tests: test_{enumerate,drilldown,
quantify,dossier,planner,reflect,web_enrich}.py — all green.

## 3. Hard constraints
- **Never fabricate**; report trusted/unverified separately. **No clusters/stories** in Ask-RIG.
- Corpus is **READ-ONLY** (`analytics_user`). Git: **attribution disabled** (no Co-Authored-By).
- Sentiment is on-the-fly classification, NEVER the sparse `article_stances` flag (free-text
  emotion labels, ~78 rows ever for the TG govt — a literal stance='negative' query returns 0).
- Gen model: `llama-3.3-70b-versatile` via Groq key-pool (`app/llm.py`).

## 4. Access (you have Bash/SSH/curl)
- Hetzner: `ssh -i ~/.ssh/rig_hetzner -o StrictHostKeyChecking=no root@178.105.63.154` (Docker host;
  `rig-postgres` host-published on :5433; `rig-searxng` internal `:8080`, no host port).
- **Three local deps (Startup items auto-start at logon):** API server (durable
  `askrig-server.sh`, NO --reload), SearXNG tunnel `localhost:8899`→rig-searxng:8080, Postgres
  tunnel `localhost:15432`→:5433. Tunnels + server scripts in `products/ask-rig/scripts/`.
- Secrets in `products/ask-rig/.env` (gitignored — never commit).
- **PORT NOTE:** :8010 has a stuck zombie socket (clears on reboot; durable server reclaims it).
  Current working server runs on a manual port (e.g. :8012/:8013). To preview-drive the UI, point
  `.claude/launch.json` ask-rig at a free port and `preview_start "ask-rig"`.

## 5. Run / verify
```bash
# health (use whatever port the server is on)
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8013/
# offline integration (avoids server-port hassle; HTTP wraps chat_stream verbatim):
cd products/ask-rig && PYTHONIOENCODING=utf-8 python -c "import asyncio;from app.config import load_settings;from app.llm import get_llm;from app.chat import chat_stream
async def r(q):
  s=load_settings();
  async for e in chat_stream(s,get_llm(s),None,q,[]):
    if e['type']=='status':print(e['stage'])
asyncio.run(r('give me a full dossier on Revanth Reddy'))"
```
(Pass `None` for the embedder when testing the mode paths — they don't use it; only synthesis does,
which needs a real embedder + ~20s LaBSE cold-load.)

## 6. Known issues / next
1. **BUG: list-card snippets show raw HTML** (`<figure><img …>`) — `lead_text_translated` carries
   embedded markup. Strip HTML tags from `ListItem.snippet` (in `enumerate.list_articles`) before
   display. Quick, visible win.
2. **Server hygiene**: the durable supervisor can spawn overlapping instances / orphan uvicorns
   (one held :8010 with stale code). Harden to single-instance (pidfile/lock).
3. **Roadmap remaining**: Monitor/proactive mode (saved watches + alerts, reuse Brief scheduler) ·
   Investigate mode (multi-step: filter→rank→synthesize) · Compare mode (EN-vs-TE framing).
   **LangGraph migration = DEFERRED on purpose** (orchestrator is already a clean state machine;
   the verify-node value = injection [done as a prompt fix] + faithfulness [already 0 hallucinated
   cites]). Revisit only for dynamic loop/branch or visual tracing.
4. Entity disambiguation: "Telangana government" resolves to the broad "Telangana" entity — fine
   for coverage, loose for govt-specific asks.

## 7. Data facts (verified live)
50,361 articles/24h, 226K/7d, ~442K surfaceable. `article_entity_mentions` is a MATVIEW.
`article_stances.actor` = the TARGET entity. Article content cols: `full_text_translated`,
`full_text_scraped`, `lead_text_translated`, `summary_executive`, `article_quotes`.

Start by reading the memory file, confirm the 3 deps are up + which port the server is on, then
propose the next step (I'd suggest the snippet-HTML fix first — quick + visible).

---
*Generated 2026-06-25. Live source of truth = `memory/project_ask_rig_build.md` + `git log` on
branch `feat/ask-rig-chat`.*
