# Brief — Pillar Coverage & Govt-Sources Matrix

**Generated:** 2026-04-26
**Stack state at probe time:**
- All 5 containers up (`rig-postgres`, `rig-backend`, `rig-frontend`, `rig-searxng`, `rig-freshrss`).
- All 6 Celery worker pools running inside `rig-backend` (`collectors`, `youtube`, `documents`, `nlp`, `relevance,brief`, plus `beat`).
- DB row counts: `articles=11,918`, `govt_documents=225`, `briefs=4`.

---

## 1. Pillar coverage matrix (what the brief uses vs. what exists)

| Pillar | Backing table | Brief reads it? | Where (or "no JOIN") |
|---|---|---|---|
| Articles (RSS / HTML) | `articles` via `user_article_relevance` | ✅ | [backend/routers/brief_router.py:99–127](../../backend/routers/brief_router.py) |
| Clips (YouTube transcripts) | `clips` | ❌ | no JOIN |
| Cuttings (newspaper editions) | `clippings` / `newspaper_editions` | ❌ | no JOIN |
| Threads (social signals) | `story_threads` | ❌ | no JOIN |
| **Govt documents (PDFs)** | **`govt_documents`** + `user_govt_doc_relevance` | **❌** | **no JOIN — central finding** |
| Briefs (yesterday/last-week) | `briefs` | ❌ | no recurrence/trend analysis |

**Pillar coverage: 1 of 6.** The brief is articles-only. The `user_govt_doc_relevance` table exists ([scripts/migrations/006_govt_documents.sql](../../scripts/migrations/006_govt_documents.sql)) and is populated by `score_govt_doc_for_all_users`, but `brief_router.py` and `brief_generator.py` never read from it.

---

## 2. Govt-sources reality check ("how many sources do we get docs from")

### 2.1 Code vs. seed-table mismatch

| Surface | Count |
|---|---|
| `@register_source` decorations across `backend/collectors/sources/*.py` | **72** |
| Rows in `govt_document_sources` table | **50** |
| `is_active = TRUE` rows | **35** (CENTRAL=26, INTERNATIONAL=5, LOCAL=4) |

→ 22 in-code adapters lack a seed row, so Beat will never schedule them. This is itself a defect (logged as **D-BRIEF-12** in [brief-defects.md](./brief-defects.md)).

### 2.2 Per-source row counts (live, 2026-04-26)

**17 sources are producing rows. 33 are silent.**

| Source | rows_total | rows_last_7d | latest |
|---|---:|---:|---|
| MoF Notifications | 69 | 69 | 2026-04-26 07:48 UTC |
| CAG India | 50 | 50 | 2026-04-26 07:39 UTC |
| GHMC Tenders | 26 | 26 | 2026-04-26 07:17 UTC |
| Telangana High Court | 22 | 22 | 2026-04-26 07:23 UTC |
| NCLAT | 20 | 20 | 2026-04-26 07:21 UTC |
| MHA Notifications | 10 | 10 | 2026-04-26 04:12 UTC |
| PNGRB Notifications | 7 | 7 | 2026-04-26 04:12 UTC |
| MEA Press Releases | 6 | 6 | 2026-04-26 07:10 UTC |
| TS-iPASS | 3 | 3 | 2026-04-22 07:39 UTC |
| RBI Circulars | 2 | 2 | 2026-04-26 04:12 UTC |
| MoD Press Releases | 2 | 2 | 2026-04-26 04:12 UTC |
| TRAI Press Releases | 2 | 2 | 2026-04-23 03:14 UTC |
| PIB Press Releases | 2 | 2 | 2026-04-22 02:04 UTC |
| NCLT | 1 | 1 | 2026-04-22 07:39 UTC |
| NITI Aayog Reports | 1 | 1 | 2026-04-23 03:04 UTC |
| SEBI Orders | 1 | 1 | 2026-04-26 04:12 UTC |
| FSSAI Notifications | 1 | 1 | 2026-04-26 04:12 UTC |

### 2.3 Sources with zero rows (33)

ADB India, BIS Annual Report, CCI Orders, CDSCO Notifications, CERC Orders, eCourts (stub), eProcurement Telangana, Gazette of India, GeM Circulars, HMDA Notifications, ILO India, IMF India Reports, IP India GI Tags, IP India Patents, IP India Trademarks, IRDAI Circulars, Lok Sabha Bills, Lok Sabha Q&A, MCA Notifications, Ministry of Jal Shakti, NGT, Parl. Committee Reports, PRS Bill Tracker, Rajya Sabha Bills, Rajya Sabha Debates, RBI Press Releases, Supreme Court of India, Telangana GO.Ms Portal, TGERC Tariff Orders, TS Gazette, TSPSC Notifications, UN India, World Bank India.

Of these, 2 are by-design stubs (eCourts, Gazette) per [docs/qa/sources-per-source-verdict.md](./sources-per-source-verdict.md). The remaining **31 are real outages** — most likely Playwright-Chromium silent failure on SPA portals (sansad.in, sci.gov.in, mca.gov.in) or selector drift.

### 2.4 Last-7d collection day distribution

| day | rows |
|---|---:|
| 2026-04-26 (today) | 210 |
| 2026-04-23 | 3 |
| 2026-04-22 | 7 |
| 2026-04-21 | 5 |

→ Until today's run, the pipeline was producing only ~5 docs/day. Today's spike (210) suggests a recent fix (matches `fix/archive-phase-8` branch you are on). **The brief still cannot see any of it.**

---

## 3. Headline answer to the user's question

> **"How many sources are we able to get govt docs from?"**
>
> - **17 sources** produced ≥1 row in the last 7 days.
> - **33 sources** are silent (31 broken, 2 by-design stubs).
> - **0 sources** reach the brief — the brief never queries `govt_documents`.
>
> So: govt-doc collection is partially healthy (17/50 = 34% of seeded sources, 17/72 = 24% of coded adapters), but **the brief uses none of it**. That is the gap the user is feeling.

---

## 4. Repro queries (to re-run any time)

```bash
docker exec rig-postgres psql -U rig -d rig <<'SQL'
-- per-source totals
SELECT s.name AS source, COUNT(d.id) AS rows_total, MAX(d.collected_at) AS latest
FROM govt_document_sources s
LEFT JOIN govt_documents d ON d.source_id = s.id
GROUP BY s.name ORDER BY rows_total DESC;

-- last 7d
SELECT s.name AS source, COUNT(d.id) AS rows_7d
FROM govt_document_sources s
LEFT JOIN govt_documents d ON d.source_id = s.id
   AND d.collected_at >= NOW() - INTERVAL '7 days'
GROUP BY s.name HAVING COUNT(d.id) > 0 ORDER BY rows_7d DESC;

-- silent sources
SELECT s.name FROM govt_document_sources s
LEFT JOIN govt_documents d ON d.source_id = s.id
WHERE d.id IS NULL ORDER BY s.name;

-- brief footprint
SELECT user_id, brief_date, articles_used, model_used, generated_at
FROM briefs ORDER BY generated_at DESC;
SQL
```
