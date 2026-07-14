# RIG Scout — Session Handoff

> Paste the **Kickoff Prompt** below into a fresh chat, and keep this file open.
> It gives a new session everything it needs to continue Scout work as if it
> were in the original conversation.

---

## 🚀 Kickoff Prompt (copy–paste this into the new chat)

```
We're continuing work on RIG Scout — a standalone OSINT aggregator I built.
Read docs/handoffs/scout-handoff.md in the repo (C:\Users\Dell\Desktop\rig-surveillance)
for full context before doing anything. Short version:

Scout takes ONE keyword (or a plain-English ask) and fans out to every source we
have — social (reddit/twitter/telegram/tiktok/youtube/instagram/wechat), free OSINT
(Google News RSS, Bing News RSS, SearXNG web, GLEIF company, OpenAlex academic, GDELT,
Wikipedia, geo, tenders), and a gated identity-footprint lookup. Each source keeps its
OWN native fields (we do NOT flatten to a common schema), returns newest-first, and the
user picks top-N. Image-verify + satellite are separate NON-keyword input-mode tools.

Phase 2 = natural-language asks ("harmful content on indian army", "top 50 tweets on X
in last 10 min", "India from USA's perspective"). A rule-based parser turns the sentence
into a transparent QueryPlan (query, top_n, sort, time-window, sentiment, sources,
co-occurrence anchor). Filtering is DETERMINISTIC keyword/lexicon (window + negative-lexicon
+ co-occurrence/recency/engagement sort + top-N) via plan.apply_plan(). The LLM judge was
REMOVED (2026-07-13) — it was an unevaluated binary gatekeeper (no gold set, non-deterministic,
single-GPU dependency). If subjective filtering is revisited, do it as an EVALUATED scored
cascade (gold set first), not an opaque LLM gate.

It runs LIVE in two places:
  - Locally: http://localhost:8610 (this is what I test on; judge = my 4090)
  - Deployed: https://api.rig360media.com/scout/ (judge backend NOT wired — keyword floor)

Ground rules that always apply: free/no-paid where possible; isolated in osint-backend
(never touch rig-backend ingest); NEVER fabricate results — verify against live services
and report honestly (trusted/unverified/failed separately); identity footprint = PUBLIC
accounts only; OLD box 178.105.63.154 is DELETED, use 178.104.145.135; for TRIJYA-7 tasks
check CPU/RAM/GPU first and confirm "Connected to TRIJYA-7 ✅".

My current focus / what I want next: <FILL THIS IN>.
```

---

## What Scout is

One search box → every source we can reach → **top raw data from each, newest-first,
no deductions**. Built as a **standalone FastAPI webapp** (`products/scout/`), NOT bolted
into the existing OSINT desk / Ask-RIG products. It's an orchestration layer that imports
our existing collectors in-process and fans out.

Two modes:
1. **Keyword search** — type a keyword, get every source's latest matches.
2. **Ask (plain English)** — describe intent, a rule parser builds a transparent plan,
   then the same fan-out runs filtered/sorted/judged.

Plus two **separate, non-keyword** input-mode tools in their own tabs:
- **Image verify** (`/media/`, rigmedia:8701) — reverse-search + EXIF/GPS + ELA.
- **Satellite** (`/geo/`) — change detection.

## Design rules the user cares about (do not violate)

- **Each source keeps its native fields.** Do NOT flatten everything into one schema —
  a tweet, a GLEIF company record and a news item are different; show them differently.
- **Newest-first** from day one.
- **User sets top-N** (10 / 25 / 50 selector). "If he wants top 50 twitter posts, he can."
- **Per-source panels / dropdowns** so one source can be analyzed at a time.
- **Honest streaming** — each source panel fills independently; slow sources don't block
  fast ones; failures show as an honest error/note, never a fake result.
- **Free / no-paid** wherever possible.
- **Isolated** — Scout lives in the osint side; never touches rig-backend ingest.

## Architecture / key files (`products/scout/`)

| File | Role |
|---|---|
| `app.py` | FastAPI. Endpoints: `/scout`, `/scout/one`, `/scout/sources`, `/scout/ask/plan`, `/scout/ask/one`, `/health`, `/`. `_load_local_env()` reads repo `.env` so it runs off-container. |
| `sources.py` | `SPECS` dict of every source; `run_one`, `run_multi` (multi-query merge+dedup), `scout`, `source_list`, `_guard` (per-source timeout + honest error), `_identity` (gated to handle-like keywords). |
| `plan.py` | `QueryPlan` dataclass + `rule_parse(nl)` — rule-based NL→plan (NOT text-to-SQL; live scrapes aren't a warehouse). Time-window, top-N, sentiment, source hints, perspective/co-occurrence split. `_is_negative` keyword floor. |
| `judge.py` | The LLM judge (see below). |
| `static/index.html` | The UI: tabs, per-source streaming panels, skeletons, "Top merged" dedup/rank view, top-N selector, plan banner, image/satellite iframes. |

Supporting collectors (in the osint backend, reused by Scout):
- `products/osint/backend/news_collector.py` — `news_search` (Google News RSS),
  `bing_news_search` (Bing News RSS). **Google News RSS is the reliable web workhorse**
  (SearXNG is box-only and flaky — it scrapes Brave/Mojeek/Yahoo which 429/403 the
  datacenter IP and get suspended 180s).
- `products/osint/backend/wiki_collector.py` — exact-title then opensearch fallback.
- Social = `backend/collectors/cheap_stack/keyword_search.py` `REGISTRY`
  (reddit/tiktok/youtube/twitter/telegram/instagram/wechat).

## Filtering (`plan.py apply_plan`) — deterministic, keyword-only

Ask-mode filtering is pure keyword/lexicon and deterministic (same query → same result):
`window_minutes` age filter → negative-lexicon (`_is_negative`, word-boundary regex) when
sentiment=negative → co-occurrence sort (if a perspective anchor) else recency/engagement →
top-N trim. No model, no GPU, no network in the filter step. Note tag = "keyword-filtered".

**History:** an LLM judge (`judge.py`, Ollama qwen2.5:14b on the TRIJYA-7 4090 via SSH
tunnel, Groq + keyword fallbacks) was built and then **removed on 2026-07-13** — see below.
The TRIJYA-7 tunnel/persistence setup is documented in case a future EVALUATED scorer wants
that GPU, but nothing in Scout calls it now.

## (Removed) The LLM judge — why it's gone

After a source is scraped, the judge answers one yes/no per post: *does this match the
subjective criterion* (e.g. "negative/harmful toward the Indian army", or "about topic X
AND reflects anchor Y's viewpoint")? Keyword matching can't do this — it misses coded
hostility ("army is paid, media is paid") and false-positives on praise that contains
scary words ("army attacked the flood, rescued 200"). The LLM reads *meaning*.

- **Multi-backend, graceful degrade:** local **Ollama pool** (free, unlimited) → **Groq**
  (shared org TPD often exhausted) → **keyword floor**. Tags result
  `judged by ollama|groq|keyword` so it's transparent which ran.
- **Endpoints** from `OLLAMA_ENDPOINTS` env (`"url|model,url|model"`), 14b/7b sorted first.
- Concurrency capped at 2 (`_SEM`) to protect the single GPU.
- **Keyword floor stays** as the always-available safety net when the GPU/Groq are down.

### Keyword vs LLM (the difference, simply)

| | Keyword | LLM judge |
|---|---|---|
| Decides by | word on a list | reading the meaning |
| "army is paid, media is paid" | ❌ missed | ✅ caught |
| "army rescued flood victims" | ❌ wrongly kept | ✅ dropped |
| Knows *who* the target is | no | yes |
| Cost | instant, free | ~1.5s, needs GPU |

## TRIJYA-7 GPU judge (the local setup)

- **4090**, Ollama on `[::1]:11434` (localhost-only bind) with `qwen2.5:14b` + `7b-instruct`.
- Reached from this laptop via SSH tunnel `localhost:11435 → [::1]:11434`.
- **Keyless** via `administrators_authorized_keys` (admin account; ACL = Administrators +
  SYSTEM only, set with icacls). Host `100.115.170.88` user `trijya`.
- **Persistence** = Startup-folder `.vbs` launchers (Register-ScheduledTask needed
  elevation → Access denied):
  - `…\Startup\scout_tunnel.vbs` → `C:\Users\Dell\.claude\scout_tunnel.ps1`
    (while-loop `ssh -N -L 127.0.0.1:11435:[::1]:11434 …`, reconnect every 5s).
  - `…\Startup\scout_app.vbs` → `C:\Users\Dell\.claude\scout_app.ps1`
    (while-loop `uvicorn products.scout.app:app --port 8610` from the repo, restart on exit).
- `.env` (repo root, gitignored): `OLLAMA_ENDPOINTS=http://127.0.0.1:11435|qwen2.5:14b`
  plus REDDIT/TWITTER session cookies.
- **TRIJYA-7 protocol:** before any task check CPU/RAM/GPU (CPU>80% or FreeRAM<20% or
  GPU>80% → STOP, tell user to wait); confirm "Connected to TRIJYA-7 ✅"; all tasks on
  TRIJYA-7 unless told otherwise.

**Restart local Scout** (picks up `.env` changes):
```powershell
Get-NetTCPConnection -State Listen -LocalPort 8610 | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
# scout_app.ps1 wrapper auto-restarts uvicorn within ~15s
```

## Current state (2026-07-13) — WORKING, keyword-only

Two changes shipped today:

1. **LLM judge REMOVED.** Ask-mode now runs deterministic keyword filtering only
   (`plan.apply_plan`). Rationale in the section above. `judge.py` deleted; `J` import
   dropped from `app.py`. Verified: "harmful content on indian army" → twitter=10,
   note="keyword-filtered", no GPU call.
2. **Instagram fails honestly.** Verified logged-out IG is fully walled (no engine indexes
   IG captions; anonymous web_profile_info returns text-less 2013 stubs). `search_instagram`
   now gates on `INSTA_SESSIONID`: without it, `ok=False, error="Instagram needs a logged-in
   session (set INSTA_SESSIONID)"` — instead of doomed discovery returning 0 behind a
   confusing note. The full authed pipeline runs unchanged once a valid session is set.

## Known gaps / next candidates

1. **Deployed box Scout is stale** — `api.rig360media.com/scout/` still has the OLD code
   (LLM judge + old IG behavior). Redeploy the current `products/scout/` + the IG collector
   to bring it in line with local.
2. **Instagram needs a fresh `INSTA_SESSIONID`** — this is a *credential the user must
   supply* (do NOT create/log into an IG account). Residential egress works (adgpi fetch
   connected); the blocker is purely the session cookie. Drop a fresh, non-checkpointed
   sessionid into `.env` and IG lights up.
3. **SearXNG (web)** — box-only and flaky by nature. Google News RSS is the reliable path;
   SearXNG is best-effort with a soft note.
4. **Telegram** = 97 curated channels, not global Telegram search (by design).
5. **If subjective filtering is wanted back** — build it as an EVALUATED scored cascade
   (hand-labeled gold set → deterministic target-aware stance scorer on everything → an
   LLM only on the ambiguous band, emitting score+rationale → user-controlled threshold),
   reusing the platform's directed-stance engine. NOT an opaque binary LLM gate.

## Deploy notes

- rigscout image was made via `docker commit rig-backend rigscout-base` (base image lacks
  `curl_cffi` at bake time). Box `/root/rig` must be kept in sync (some osint collectors
  were missing → scp'd).
- Caddy serves `/scout/*`; frontend uses relative paths (`scout/sources`) → `handle_path`
  strips one segment. Works.

## Hard constraints (always)

- **Never fabricate results.** Verify against live services; report trusted / unverified /
  failed separately.
- **Identity footprint = PUBLIC accounts only.** Off-limits: broker people-search,
  breach-data, face-search, dark-web. Same-username ≠ same-person.
- **OLD box `178.105.63.154` is DELETED.** Use `178.104.145.135`. `getent` before deploy.
- **Social/OSINT = keyword/on-demand.** Only articles + newspapers are store-everything.
