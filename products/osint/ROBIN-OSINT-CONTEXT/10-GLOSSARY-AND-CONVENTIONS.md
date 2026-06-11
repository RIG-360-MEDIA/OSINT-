# 10 — Glossary & Working Conventions

## Glossary
| Term | Meaning |
|---|---|
| **Principal** | The focal entity a persona is built around (AP persona = Chandrababu Naidu). `primary_subject_id` in prefs. |
| **Watchlist** | The entities a user tracks; defines their article universe. Entities carry a `tier`. |
| **Primary state** | `regions.states[0]` — drives "Andhra-first" ordering and map MINE scope. |
| **POL** | SQL stance map: `article_stances.intensity` → supportive / neutral / hostile. |
| **`_BODY_PRESENT`** | Filter requiring an entity to appear in the article body (anti-hallucination). |
| **`now_sim()`** | `analytics.now_sim()` — replay-safe "current time" for all time windows. |
| **Substrate / v3** | The extraction layer (translation, register, entities) over raw articles. |
| **Tier (1/2/3)** | Source/entity importance tiers; in relevance: subject ×6 / core ×3 / extended ×1.5. |
| **`thread_id`** | Intended event-cluster id on `articles` — currently empty (0%). |
| **ROBIN-OSINT** | The product (formerly "Night Desk"). Folder still `night-desk/`. |

## Conventions / rules (carry into any new chat)
- **Secrets:** never print or commit values (DB passwords, API keys, Supabase
  service key, the YouTube cookie). Reference by location. AP password is hashed
  and not retrievable.
- **No fabrication:** every displayed/seeded fact must be source-verified; LLM
  outputs need cite-ID guardrails; no invented handles/quotes/stats/cross-state
  developments.
- **Stance measurement:** use `article_stances` (POL), NOT `register_emotion`
  (its "alarm" is event-emotion, skews negative).
- **Git:** commit attribution disabled (no `Co-Authored-By`); branches
  `fix/<area>-phase-N`; conventional commit messages; only commit/push when asked.
- **Immutability / small files / explicit error handling / input validation at
  boundaries** (house coding style).
- **Backend edits:** `py_compile` + run the in-container validation before
  declaring done.
- **SQL in `relevance.py._SQL` is plan-stable — do clever re-ranking in Python.**
- **Two backends, two env files:** osint-backend → `.env`; rig-backend →
  `.env.prod` (different `ANALYTICS_DB_PASSWORD`).

## Key paths
- Frontend: `products/osint/design/night-desk/`
- Backend: `products/osint/backend/` (relevance.py, routers/top_articles.py,
  i18n.py, report_builder.py, report_render.py, report_email.py, map_page.py,
  home_sections.py, war_room.py, analytics_page.py, dossier.py, live_channels.py)
- Walkthroughs: `…/night-desk/WALKTHROUGH.md`, `…/ROBIN-OSINT-Team-Guide.pdf`
- This pack: `products/osint/ROBIN-OSINT-CONTEXT/`
- Host build sources: `/root/rig/products/osint/backend/`, `/root/rig/night-desk-dist/`
- Compose: `infrastructure/docker-compose.yml` (+ `docker-compose.prod.yml`),
  `infrastructure/Caddyfile`
