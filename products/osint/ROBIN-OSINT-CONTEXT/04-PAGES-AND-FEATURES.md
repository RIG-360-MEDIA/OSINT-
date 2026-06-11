# 04 — Pages & Features

> Full, accurate walkthroughs already exist — read those alongside this summary:
> - **Developer reference:** `products/osint/design/night-desk/WALKTHROUGH.md`
> - **Non-technical team guide (PDF):**
>   `products/osint/design/night-desk/ROBIN-OSINT-Team-Guide.pdf`
>   (source: `WALKTHROUGH-team-guide.html`)

## The 6 pages and the endpoints that feed them (verified against the SPA code)

| Page | URL | Feeds from | What it shows |
|---|---|---|---|
| **Home — The Briefing** | `/` | `GET /api/brief/home` + `GET /api/brief/top-articles?limit=6` | Masthead, The Briefing (exec narrative), **Top Stories For You** (the cards we fixed), People to Watch, The Six |
| **War Room — Crisis Desk** | `/war-room` | `GET /api/brief/warroom` | Threat Stack + The Field (Momentum / Attack Map / Bloc). COUNTER-ATTACK panel was removed. |
| **Analytics — Instrument Panel** | `/analytics` | `GET /api/brief/analytics` | Volume, topics, tone donut, entities, quotes, claims, figures, Picture Wall |
| **Dossier — Entity Files** | `/dossier` | `/api/brief/dossier/roster` → `/entity/{id}` → `/entity/{id}/articles` | Searchable roster → full entity file (pulse, standing, SoV, issues, quotes, claims, network, reach, timeline). RBAC-gated. |
| **Map — The Theatre** | `/map` | `/api/brief/map?scope=` + `/global-layers` + `/district/{id}` + `/country/{iso}` (+`/articles`) + `/channels` | Flat-2D-default deck.gl/maplibre map. MINE = district choropleth (flies to region); GLOBAL = world choropleth. NASA EONET + ACLED layers. Live YouTube channels. |
| **Dispatch — Daily Report** | `/dispatch` | `/api/brief/report` + `/report.pdf` + `/report/send` | Preview + Download PDF + Email-me. (Mock cards removed.) |
| Auth | Login | Supabase + `/api/me` | Sign-in gate; onboarding wizard writes `user_brief_prefs`. |

## Top Stories "For You" (the part most actively worked on)
- Endpoint: `routers/top_articles.py` → `GET /api/brief/top-articles`.
- Ranking core: `relevance.py:score_relevant` (tiered, title-salience,
  freshness-decayed). Then `_diversify()` picks the final cards.
- Card fields: headline (+`headline_en` translation), **summary**, source, age,
  tone, matched entity, topic, geo, score, thumbnail, url.
- Current behaviour after 2026-06-05 fixes: English summaries, de-duplicated,
  entity-capped, **Andhra-first**, faster freshness. See 06 + 07.

## Daily PDF report (built, working)
- `report_builder.py` (content, A–I sections, anti-fabrication `_SYS`,
  state-scoped universe) → `report_render.py` (WeasyPrint, table-based layout,
  Telugu fonts) → `report_email.py` (Gmail SMTP 587 STARTTLS).
- `send_daily_reports.py` cron emails each signed-in user their state brief every
  morning (IST). Downloadable from Dispatch too.
