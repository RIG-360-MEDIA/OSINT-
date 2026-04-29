# 03 — Backend endpoint smoke (Step 3)

**Verdict: PASS for HTTP correctness; FAIL for data quality.**
All 20 endpoints respond 200 (or graceful 503). The defensive
`section_errors` pattern in `/dashboard` and the `_safe_execute()` in
`cm_queries` keep things alive. But the *content* exposes the seed
problems from Step 1 and the Groq problem from Step 2.

## Test setup
- Test user: `db4b9207-51aa-4d39-a7bf-e6fab34c3465`
  (`pranavpuri03@gmail.com`), `geo_primary='Hyderabad'`,
  has all 9 page slugs in `user_page_access`.
- Token: unsigned JWT minted in-process (dev mode allows it because
  `SUPABASE_JWT_SECRET` is unset; ENVIRONMENT=development).
- FastAPI startup: ~3 minutes — blocks on LaBSE warmup
  (`@app.on_event("startup") warmup_labse`). **D-13 (LOW)**: warmup
  should be `await asyncio.to_thread(...)` so uvicorn returns ready
  before the first encode finishes. Currently the container is
  unreachable for a long window after every `--reload`.

## Endpoint matrix

| Endpoint | Status | Latency | Notes |
|---|---:|---:|---|
| `/api/cm/pulse` | 200 | 2.1s | unscoped overall sentiment 0.087 |
| `/api/cm/pulse?state=TG` | 200 | 312ms | scoped ✓ |
| `/api/cm/pulse?state=AP` | 200 | 320ms | scoped ✓ |
| `/api/cm/issues` | 200 | 2.1s | leaks **non-Telangana** issue: "Indonesia train accident" |
| `/api/cm/issues?state=TG` | 200 | 195ms | **0 issues** — D-2 confirmed |
| `/api/cm/silence` | 200 | 1.8s | items include real TG figure "Revanth Reddy" ✓ |
| `/api/cm/spokespersons` | 200 | 2.4s | "Vamshi Karangula" — real but `party=null` |
| `/api/cm/cabinet-onmessage` | 200 | 1.5s | same speaker leak |
| `/api/cm/dissent` | 200 | 4.4s | `ruling=[], opposition=[]` (D-3) |
| `/api/cm/trajectory` | 200 | 4.0s | label "India New Zealand Trade Agreement" — non-TG |
| `/api/cm/heatmap` | 200 | **12.1s** | 29 constituency cells; **slowest** endpoint |
| `/api/cm/heatmap?state=TG` | 200 | 361ms | 29 cells (cache hit / scoped) |
| `/api/cm/promises` | 200 | 728ms | sample includes "Free public transport for women across APSRTC" |
| `/api/cm/promises?state=TG` | 200 | 206ms | 6 rows (D-2: only half the seed is TG) |
| `/api/cm/counter-narratives` | 200 | 969ms | `cards=[]` (D-3 confirmed) |
| `/api/cm/risk-window` | 200 | 656ms | upcoming court event 2026-04-30 |
| `/api/cm/quotes` | 200 | 665ms | top quote is **"Piyush Chawla"** (cricketer) — D-12 |
| `/api/cm/quotes?state=TG&limit=3` | 200 | 251ms | 3 rows |
| `/api/cm/voice-share` | 200 | 500ms | top voice: **"Justice Sandeep Mehta"** (SC judge) — D-12 |
| `/api/cm/divergence/language` | 200 | 709ms | topic="OTHER" — placeholder |
| `/api/cm/divergence/medium` | 200 | 644ms | newspaper_editorial bucket |
| `/api/cm/dashboard` | 200 | 3.4s | aggregator; per-section `_safe()` works ✓ |
| `/api/worldmonitor/telangana/news` | 200 | 9.5s | 30 RSS items (4 feeds × ~7) |
| `/api/worldmonitor/telangana/events` | **503** | 644ms | clean error: "ACLED token not configured" ✓ |
| `/api/worldmonitor/telangana/live-channels` | 200 | 6.4s | **8 of 9 channels live**, real video IDs |
| `/api/worldmonitor/telangana/briefing` | 200 | 6.9s (cold) → 742ms (cache=True) | summary populated |

## Briefing summary text (request-time Groq call worked)
> "Telangana state remains stable with no reported incidents of
> social unrest over the past week, according to ACLED data which
> shows 0 events in the last 7 days. The state's educational sector
> is facing a leadership crisis, as the Telangana Social Welfare
> Residential Educational Institutions Society…"

Real Telangana topic, mentions ACLED=0 (no events because token
missing — but the LLM hallucinated "stable" from that). This is a
correctness concern: the LLM should not equate "no token" with
"no events". **D-14 (HIGH)**: pass an explicit "data missing" flag
into the Groq prompt so it doesn't read absence-of-data as
absence-of-event.

## Live channel verification
| Channel | Live? | Video ID |
|---|---|---|
| V6 News | ✓ | OJEUAWZd2CQ |
| TV9 Telugu | ✓ | hIayhrVURWg |
| T News | ✗ | null |
| ABN Telugu | ✓ | FhH9fh0DJ7s |
| 10TV Telugu | ✓ | O-WP08JMYI0 |
| Sakshi TV | ✓ | ocy5UgWokKQ |
| News18 Telugu | ✓ | DMDMCi1ORGo |
| TV5 News | ✓ | Id9uWNnIzjQ |
| NTV Telugu | ✓ | cST5wZxJ4a4 |

8 of 9 currently live; UI gracefully disables the "T News" tile.

## Cache behaviour
- First briefing call: 6.9s, `cached:false`.
- Second call (~5s later): 742ms, `cached:true` ✓.
- TTL `WM_TG_CACHE_TTL_S=1800` (30 min default).
- Cache is **process-local** — if uvicorn runs multiple workers, hit
  rates degrade. Currently `--reload` runs single worker, so OK.

## CM dashboard — all 15 sections served in 3.4s
This is the user-perceived load time. Heatmap dominates at 12.1s
when called solo, but the dashboard's parallel `asyncio.gather`
caps it at the slowest section.

## Security findings (preview — full audit in Step 9)
- **CM router has NO `dependencies=[require_page("worldmonitor")]`**
  — anyone authenticated can hit `/api/cm/*` even without
  worldmonitor page access. **D-11 (HIGH)**.
- WorldMonitor router applies `Depends(require_page("worldmonitor"))`
  at router level ✓.
- Both routers use parameterised SQL via `text(sql)` + bind params ✓
  (verified for `_state_like_clause`, query helpers).

## Defects added
| ID | Sev | Title |
|---|---|---|
| D-11 | HIGH | `cm_router.py` does not gate endpoints with `require_page("worldmonitor")` — any authenticated user can hit /api/cm/* |
| D-12 | HIGH | Speaker / quote extraction is too permissive — returns cricketers ("Piyush Chawla") and SC judges ("Justice Sandeep Mehta") as "spokespersons"; needs political-relevance filter |
| D-13 | LOW | LaBSE warmup blocks uvicorn startup for ~3 minutes; move to background task |
| D-14 | HIGH | Briefing LLM prompt conflates "ACLED token missing" with "no incidents"; produces falsely reassuring summary |
| D-15 | MEDIUM | `/api/cm/heatmap` takes 12s solo — single-call latency budget exceeded |
| D-16 | INFO | "Indonesia train accident" leaking into TG/AP issue clusters — confirms D-2 state-scope failure end-to-end |
