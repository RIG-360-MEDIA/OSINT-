# Night-Desk — Customer-Readiness Audit (2026-06-26)

Full audit before handing the night-desk product to a customer. Covers frontend
(every page/card), backend (every endpoint + data source), live data quality, and
the processing/worker/cron/pipeline health on the live Hetzner deployment.

**Verdict: NOT ship-ready yet.** The platform is up and structurally solid (all 11
containers healthy, site serves 200, auth posture is genuinely good, most pages have
strong empty/error states), but there are an exhausted cloud LLM budget, 2 security
issues, and 1 embarrassing visual fallback that must be fixed before a paying customer
sees it.

> **Correction (2026-06-26):** an earlier draft listed "YouTube/Clips pillar DEAD" as
> CRITICAL. That was an audit error — I checked the legacy `youtube_clips` table
> (frozen Jun 7) instead of the live `youtube_clips_v2` the backend serves
> (`relevance.py:291`). **The Clips pillar is HEALTHY: 253 new clips/24h, 3,036/7d,
> latest 18:51 today.** The legacy table is a dead orphan (cleanup, not a defect).

---

## ✅ What's working (verified live)

- All 11 containers up; `osint-backend` healthy 35h; `desk.rig360media.com/` → 200; `/ask/health` → 200.
- **Articles pipeline healthy**: latest article 18:51 UTC (current), **45,799 in last 24h**. Substrate + NLP + embedding all draining (nlp backlog 27k→20k; embed-null 126k→50k after today's GPU backfill).
- **Auth is solid** (backend agent verified): JWT signature-verified HS256, refuses unverified in prod; `user_id` always from JWT `sub` (no IDOR on per-user data); admin endpoints gated; Chronicle/Dossier/Map have real RBAC.
- **LLM hallucination guardrail exists**: `llm_synth.py` numeric faithfulness gate rejects un-grounded numbers, falls back to templates.
- Crons clean: **old over-merging `rig-forward` is fully commented** (no double-clustering); v9 forward + matview-refresh (every 30 min on 5 matviews) running.
- Frontend empty/error-state coverage is genuinely good on **Dossier, Map, Ask** (loading overlays, retry buttons, "no coverage" fallbacks).
- Newspapers (clippings) live, sagas + content-gen still producing.

---

## 🔴 CRITICAL (block the demo)

1. **Picsum stock photos on real intelligence stories.** `Home.jsx:458-459` — any story missing a thumbnail falls back to `https://picsum.photos/seed/...`, and `onError` also swaps broken thumbnails to picsum. A customer sees random stock photos attached to real stories. Fix: branded/hatched placeholder (Analytics' `FALLBACK_BG` is the in-repo pattern).

2. ~~YouTube / Clips pillar is DEAD~~ — **RETRACTED, false alarm.** Live table `youtube_clips_v2` is healthy (253/24h, 3,036/7d, latest 18:51 today). I'd checked the dead legacy `youtube_clips` table by mistake. *(Cleanup: drop the orphan `youtube_clips` v1 table.)*

---

## 🟠 HIGH (fix before handover)

### Data / capacity
3. **Cloud LLM budget exhausted.** Groq `qwen3-32b` at ~**499k/500k tokens-per-day across *every* org key**, plus Cerebras TPD maxed (continuous 429s in osint-backend logs). Generated content throttled to ~23 stories/24h; LLM-backed cards (briefing narrative, war-room lines, chronicle) degrade to templates or stale cache when the budget is gone. Needs more keys / paid tier / heavier local-LLM routing before sustained customer load.
4. ~~Signals pillar matview not refreshed~~ — **RETRACTED.** `article_signals_mv` is referenced nowhere in the night-desk backend (unused internal matview); the night-desk has no "Signals" page. "Negative signals" in War Room is a derived metric from fresh article data, not this matview. Not a customer-facing issue.

### Security (backend agent)
5. **Open-relay on report send.** `report_router.py:52-61` — `/report/send?to=` lets any signed-in user email a brief to an **arbitrary address**, no check it's theirs. Data-exfil / spam vector. Remove or validate the `to=` override.
6. **District gate fails open.** `map_router.py:35-40` — if the district lookup returns NULL the 403 is skipped (and no 404), so an unknown/bad `did` bypasses region gating. Make it fail closed (404 on unknown district).

### Robustness (backend agent)
7. **Chronicle feeds its own errors to the LLM as truth.** `chronicle_router.py:440-574` — phase-1 "extraction failed" strings flow into phase-2 LLM and reach the client as real analysis; also ingests low-confidence matches (`attach_score >= 0.60`, line 116-128). Suppress error placeholders; surface "analysis unavailable."
8. **Hardcoded fallback entities with baked-in UUIDs.** `entities.py:22-63` (Naidu/Rahul/Akhilesh/Owaisi) — if those rows change, queries silently return empty + ship stale hardcoded metadata. Validate-or-drop.
9. **Unbounded temp table → timeout risk.** `analytics_page.py:443-469` — `CREATE TEMP TABLE _univ` with no LIMIT; a high-mention watchlist entity can blow the 20s request timeout → Analytics page 500s. (This is the same class of issue as the earlier top-articles timeout.)
10. **Silent stale-cache degradation.** `home_cache.py:636,664` — catch-all serves 30-min+ stale payloads with only `stale:true` and **no logging of the cause** → unobservable failures in prod.

### Frontend robustness (frontend agent)
11. **No top-level error boundary** (`App.jsx`) + **unguarded object access** (`WarRoom` `STATION.*`/`LEAD.*`, `Analytics` `m.metric.n`). A single null sub-object in a backend payload **white-screens the whole app** instead of a graceful fallback.
12. **Dead buttons in War Room.** "Suggested Reply" approve / edit / kill have **no onClick** — visibly dead controls. Wire or hide.

---

## 🟡 MEDIUM

- **Playwright/Chromium binary missing** (`/root/.cache/ms-playwright/...` absent) → a JS-render collector is broken (`Playwright session crashed; aborting batch` ×3/30m). Reinstall `playwright install chromium` in the container or remove the source.
- **Error-log spam**: rig-backend logs **~4,774 ERROR lines / 30 min**, ~99% non-fatal HTML-parse noise (`empty HTML tree`, `parsed tree length: 1`). Masks real errors; demote to debug/warn.
- **Analytics blank card bodies** — unknown `m.viz` → `null` body; empty `items` arrays render with no "no data" message.
- **Dispatch depends on un-audited `ReportDispatch`** — verify PDF + Gmail send actually work before a live demo. `report/send` SMTP failures masked as bare 502 (`report_router.py:67`).
- **Two clip tables** — RESOLVED: backend serves `youtube_clips_v2` (live, 253/24h); `youtube_clips` v1 is a dead orphan (frozen Jun 7) — drop it to avoid future confusion.
- **Map defaults to "AP"** for any persona lacking a state (`map_router.py:31`); **`emerging` hardcodes stopwords** `government`/`police` (drops real surging entities).
- **Home-cache scheduler overlap** possible (180s compute vs 30-min cycle) → concurrent writes to same row.
- **`clipping-image/{id}` unauthenticated** — intentional (published content) but an undocumented enumeration surface.

---

## 🟢 LOW / cleanup

- Cron.d clutter: dead `rig-forward` file + `rig-matview-refresh.bak-20260603` (the `.bak` has a dot so cron ignores it — harmless, but remove).
- Hardcoded copy: "Search 11,000+ entities" (`Home.jsx:532`), `languages || 4` (`Ask.jsx:80`).
- Stale unrouted `pages/Chronicle.jsx` + `components/chronicle/*` dead code in the tree.
- Ask example chips are Telangana/Hyderabad-specific (fine if that's the customer's beat).
- Watchlist JSONB mutated in place (violates immutability convention; user-scoped, no leak).
- No DB-readiness gate at container start (only a `/ready` endpoint exists).

---

## Prioritized pre-ship fix list

1. Replace picsum fallback with a branded placeholder. *(Critical, ~30 min)*
2. Add LLM capacity (keys / paid tier / local-LLM routing) — current budget can't sustain customer load. *(High)*
4. Remove/validate `report/send?to=` override; make district gate fail closed. *(High, security)*
5. Add a React error boundary + null-guards on WarRoom/Analytics; wire or hide dead War Room buttons. *(High)*
6. Suppress Chronicle error-text→LLM; bound the `_univ` temp table; log home_cache exception causes. *(High)*
8. Reinstall Playwright chromium; demote HTML-parse noise to debug. *(Medium)*
9. Verify Dispatch PDF + Gmail end-to-end. *(Medium)*

*Audit method: 2 parallel code-inventory agents (frontend `products/osint/design/night-desk/src`, backend `products/osint/backend`) + live infra/data sweep on Hetzner (containers, crons, workers, pipeline backlogs, per-pillar freshness, error logs). Endpoints were not hit with a live auth token — backend findings are from code + DB; recommend an authed click-through of each page before sign-off.*
