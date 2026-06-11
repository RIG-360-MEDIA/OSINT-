# Work Log — 2026-06-06 — Sentiment Redesign, Entity Cleanup & Explainability

Single long session. Goal that emerged: the home **Coverage Sentiment** number was
measuring the wrong thing; fixing it required cleaning the entity foundation, then
making the number directional, relevance geo-aware, and explainable — all deployed live.

## Core diagnosis
- `article_stances.actor` is **the TARGET** (entity the posture is ABOUT), implicit
  speaker = the outlet. Prompt: `run_corpus_pass.py:569` ("what is THIS article's
  posture toward them?"). Proof: dead singer SP Balasubrahmanyam tagged supportive.
- The old number used `actor_entity_id <> :pid` → measured posture toward *everyone
  except* the principal. Correct = `= :pid` (toward the principal).
- Only ~42% of stance targets were entity-resolved; the dictionary was ~31% polluted
  (junk aliases, duplicate people w/ conflicting parties, orgs typed as person).

## What shipped to PRODUCTION (desk.rig360media.com), all verified healthy
**Data (live, hot-reloaded, reversible):**
- Junk-alias purge (5,209 rows — killed bare "Party" collision). Backup `entity_dictionary_bak_20260606`.
- Entity dedup: Revanth Reddy 8→1 + generalized 27 title-variant clusters (rollback `entity_merge_map_20260606`).
- Added AP Government (org) + rival voices (Sajjala/Botsa/Vijayasai/Perni → YSRCP) + Annamalai (BJP/TN); fixed YSRCP type.
- Bulk harvest-add 2,287 unresolved entities (NULL attrs, `source='harvest_20260606'`, reversible).
- Dateline backfill: geo_primary on 1,503 articles (`dateline_backfill_20260606`).
- Stripped bare "Modi" alias from non-PM Modis.
- Removed Amit Shah from AP persona watchlist; fixed Revanth persona orphaned principal (dedup side-effect).

**Code (committed branch `feat/directional-sentiment-relevance-geo`, deployed to prod files directly):**
- `posture.py` — flipped all `<>:pid` → `=:pid` (directional, 10 spots on prod).
- `home_sections.py` — `_sentiment_series` target filter + `sentiment_explain()` + headline_en/lang/url.
- `relevance.py` — wired `article_districts` into geo_hit (AP coverage 125→1,459, ~12×).
- `nlp_entities.py` — fuzzy normalized-key fallback w/ ambiguity guard (NOT deployed — rig-backend heavy rebuild).
- `routers/home.py` — `GET /api/brief/home/sentiment-explain` endpoint.
- Frontend (`night-desk/src/Home.jsx` + `index.css`) — clickable number → "Why?" pill → top-5 +/- panel,
  bilingual (English when real, Latin-script heuristic), rows link to source article.
- `.gitattributes` — LF for code (kills CRLF phantom-diff that nearly broke the deploy).

## Deploy mechanics learned (CRITICAL for next time)
- **osint-backend** = baked (build context `../products/osint/backend`). Deploy = edit prod's real files
  (they DIFFER from local; edit theirs, not git checkout) → `docker compose up -d --build osint-backend`.
- **Frontend** = night-desk built LOCALLY (`npm run build`), source NOT on server. Caddy (dockerized
  `rig-caddy`) serves host `/root/rig/night-desk-dist` (→ `/srv/night-desk`). Deploy = build local →
  backup → `scp -r dist/* root@host:/root/rig/night-desk-dist/`. Static = live instantly.
- **The "1,556-line divergence" was a CRLF/LF illusion** (+ parallel git lineage), not real drift.
- Home sentiment served from `analytics.home_cache` (DB table, recompute every 30 min). DELETE the row to force fresh.

## STILL PENDING
- nlp_entities.py fuzzy matcher → rig-backend rebuild (interrupts ingestion — schedule it).
- Watchlist sweep: personas' `watchlist.entity_ids[]` may still reference the 34 deleted dup entities (silently drop).
- Alignment weighting (us/rival/neutral; neutral-turning-hostile counts more) — the next layer beyond directional.
- Local↔prod sync: home_sections.py/posture.py/relevance.py edited directly on prod; local now behind.
- HOUSEKEEPING (user's): rotate plaintext GMAIL_APP_PASSWORD → .env; commit Hetzner's ~11 uncommitted hotfixes.

See `~/.claude/.../memory/project_sentiment_redesign.md` for the full running record.
