# Daily Media Briefing — build plan (fix → build → validate → ship)

Companion to `briefing-rebuild-spec.md` (what the report IS). This is the ORDER of
work, HOW each piece is done, and the gates that must pass before moving on.

Principle the client set: **fix every flagged issue and build every foundation FIRST,
test against a real validation set (multiple past days), and only proceed once tests
pass.** Nothing user-facing is built until the engine is proven.

Legend: ✅ done · ⛔ blocker · 🔬 needs validation

---

## PROGRESS LOG (2026-07-24)
- **Phase 0 DONE.** 210 trial articles deleted (NOT 137 — verified first; the 7
  headline-only sources also held 1,820 real pre-May articles that were correctly
  KEPT. Edge case caught: `article_entity_mentions` is a MATVIEW not a table; delete
  ran cluster-members-first then CASCADE, detached to survive SSH drop.)
- **Phase 1 schema DONE.** Migration 118 — 11 `briefing.*` tables, all FK→
  `analytics.orgs(id)` (not `org_id` — caught + fixed). Multi-tenant.
- **Phase 1 vocab DONE.** Migration 119 — 24 departments, 11 topics, 12 schemes
  (with EN+Telugu variants + disambiguation terms).
- **Phase 1 roster DONE + VALIDATED.** Migration 120 — 36 curated core (14 gov, 12
  institution, 10 opposition) from the scope doc, constituencies stripped, duplicates
  merged. **Live-tested against 22 Jul quotes:** matched Bhatti(54)/Revanth(36)/Ponnam/
  Harish Rao/KTR/Bandi Sanjay/Kishan Reddy — right person, right side, every time;
  ZERO false positives; every top *unmatched* speaker (Trump/Modi/Nadda/cricketers/
  Nara Lokesh-AP) correctly excluded. Variant matching confirmed working.
- **Translation finding (Q2):** MT renders a Telugu name in English only ~79%
  (104/131 "Revanth"); Telugu-spelling match on original = 100%. → telugu_names KEPT,
  matching uses both paths. Client verifies Telugu spellings.

## PHASE 2-3 PROGRESS (2026-07-24, later)
- **LLM resolved.** Groq `qwen/qwen3-32b` is DEAD (404). Judge = `llama-3.3-70b-versatile`
  (0.1s) / prose = `openai/gpt-oss-120b`, both via `json_response=False` + parse `{...}`
  (strict json mode returns empty). App user = `analytics_user` (GRANTed on briefing.*).
- **INFRA BUG FIXED (affects all products).** Cerebras failover mapped to `llama3.1-8b`
  which 404s (Cerebras free tier now = gpt-oss-120b / zai-glm-4.7 / gemma-4-31b only).
  This silently broke ALL Cerebras failover once Groq hit daily TPD. Remapped judge/gen
  models → zai-glm-4.7 / gpt-oss-120b + fixed the two `.get(...,"llama3.1-8b")` defaults
  in `products/osint/backend/groq_client.py` (.bak kept). → belongs in KB issues.
- **Engine BUILT + WORKING** (`products/osint/backend/briefing/`): prompt.py (judge
  prompt v1, aboutness+verdict+topic+dept+scheme+event+evidence+confidence), refdata.py,
  judge.py (LLM + evidence-verify guardrail, incl Telugu), pipeline.py (day → 3-pillar
  wide-net → judge concurrent → verify → store `briefing.items`; TV deduped to video_id).
- **VALIDATED on real 23 Jul data:** end-to-end run stored web+TV verdicts, 0 unclear.
  Hand-check of the readable web sample = **7/7 aboutness+verdict agree**; the 8
  gov-relevant items all correct. Prompt is diverse — caught internal dissent, split
  police-success(fav) vs allegation(crit), excluded sport/Delhi/lifestyle. >85% bar met
  on sample. FULL formal 50-item×3-day gate still to run with fresh Groq budget.
- **Budget note:** a day's testing exhausted Groq free TPD (20×100k=2M). Full ~3000-item
  day needs Cerebras as workhorse (37×1M=37M) — now working after the failover fix.

## STILL TO BUILD (next sessions)
event-merge · section-assembly (SQL over briefing.items → report JSON) · Playwright
renderer · nightly task (05:00 IST) · TV number-extraction · full formal validation gate.

## PHASE 0 — Cleanup ✅ DONE
(210 trial articles deleted; 37 sources re-enabled; Eenadu scraper + title fix;
circuit-breaker fix deployed. 0.5 steady-state observe + 0.6 drop-old-path pending.)

---

## PHASE 1 — Foundations (the reference data everything reads)

These are small, curated, **client-reviewable** tables. They are the single biggest
lever on quality and the thing most likely to silently break the report if wrong.

### 1.1 The Roster ⛔ (blocks the entire engine)
**What:** ~150 rows — every person/body that IS the Telangana government, plus the
Telangana opposition. Columns: canonical name · side (government / opposition /
institution) · role · **name variants** · **Telugu spelling** · active flag.
**How:**
1. Seed from the client's scope doc (Allies 49→gov, Opposition 30, Watched 116→
   institutions after stripping districts, Neutral 271→discard as mostly AP).
2. Enrich variants from what actually appears in the corpus (e.g. "Uttam Kumar Reddy"
   / "N. Uttam Kumar Reddy" / "Uttam" all seen on 22 Jul).
3. Add Telugu spellings.
4. **Client sign-off**, dated.
**Used by:** aboutness, sentiment side-assignment, government-voice check, speaker-name
normalisation, §7, §9. Load-bearing in 5 places.
**Table:** `briefing.roster`.

### 1.2 Controlled vocabularies ⛔
- **Departments** (~24, fixed) — `briefing.departments`
- **Topics** (11: 9 + Law&Order + Employment/Exams) — `briefing.topics`
- **Schemes** (flagship list, EN + Telugu variants, + disambiguation terms for generic
  names like Mahalakshmi/Cheyutha) — `briefing.schemes`
These are the closed lists the prompt must choose from (no free text → no
"Irrigation/I&CAD" splitting).

### 1.3 Outlet-identity map ⛔ (blocks §9, helps §6)
**What:** merge the same media house across pillars — "TV9 Telugu" (web) = "TV9 Telugu
Live" (TV) → house "TV9". Columns: house · member source_ids/channel names · pillar.
**How:** generate a draft from top outlets across all 3 tables, hand-review, client can
adjust. **Table:** `briefing.outlet_identity`.

---

## PHASE 2 — The judgement engine (the core)

### 2.1 The prompt ⛔
One call per item; answers aboutness + verdict + topic + department + event fields +
evidence + confidence together. Draft exists (`briefing-tone-prompt.md`); needs the
extra emitted fields (topic, department, structured `event`) folded in.
Output JSON per item:
```
{ about_government, verdict, strength, topic, department, scheme,
  event:{action,actors[],date,place}, evidence, lands_on, confidence }
```

### 2.2 The pipeline
`LIST → FILTER → JUDGE → VERIFY → (MERGE, phase 3) → STORE → COUNT`
- **LIST/FILTER:** wide net = outlet-covers-TG OR geo_primary-TG OR district-TG OR
  scope-entity/keyword; minus mute terms (safe literals only); TV segments folded to
  one item per `video_id`; one calendar day (7-day for schemes).
- **JUDGE:** the prompt, batched, temperature 0, provider TBD (see Q).
- **VERIFY:** evidence sentence must be found in the item text (fuzzy exact) or verdict
  discarded → item marked unjudged.
- **STORE:** one immutable row per item.
**Table:** `briefing.items` (item_id, pillar, source_id, ts, lang, verdict, strength,
topic, department, scheme, event_json, evidence, confidence, model, prompt_version,
run_id).

### 2.3 Storage / immutability
Judged once, stored, never recomputed. A given day's numbers are fixed forever.
**Table:** `briefing.runs` (run_id, date, model, prompt_version, counts, created_at).

---

## PHASE 3 — Event-merge (our own; NOT v8)

**What:** group the government-relevant items (~200–300/day) into events, across all 3
media, so §1/§2/§3/§5/§7 can rank and pair.
**How:** two-stage —
1. per-item `event` object already extracted in the judge call (actors+action+date+place);
2. one reconcile pass over the whole day's ~200 event objects → cluster on shared
   actors + same action + same date + same place (structured match, not title text).
**Robustness required (from real data):** "Lok Bhavan" vs "Raj Bhavan"; Telugu vs
English; must not merge two distinct same-day protests by the same people.
**Table:** `briefing.events` (event_id, run_id, label, member_item_ids[], spread by
pillar, net tone, top item per pillar).

---

## PHASE 4 — VALIDATION GATE 🔬 (must pass before Phase 5)

Nothing user-facing is built until these pass. Build validation sets from **multiple
real past days** (proposed: 22 Jul + 21 Jul, plus one high-event day).

| Test | Method | Pass bar |
|---|---|---|
| **Aboutness** | hand-label ~150 items is-it-about-govt Y/N | ≥90% (it's the gate) |
| **Sentiment** | 50 hand-labelled favourable/critical/neutral, **print scored separately** | ≥80% agreement, print not <70% |
| **Event-merge** | the 22 Jul bandh (9 articles / 6 v8-clusters) must come back as ONE event; the water/barrages story as one | correct merge, no false-merge of distinct events |
| **Evidence verify** | sample 30 verdicts, confirm evidence sentence really in source | 100% (it's a hard gate) |
| **Roster recall** | do known ministers quoted that day get matched? | no minister missed |

If any fails → fix prompt / roster / merge logic and re-run on the SAME sets. Keep the
sets permanently as regression tests.

---

## PHASE 5 — Section assembly (backend computes each section from stored data)

An orchestrator reads `briefing.items` + `briefing.events` for the day and produces one
immutable **report JSON** with all 10 sections + strip. Pure aggregation — no new model
calls except the LLM prose for §1 lines and §2 narrative (each written from its own
items, verified).
- Strip: counts, biggest subject, net sentiment, top outlet/medium
- §1: rank events → 6, diversity cap → LLM writes each line from its items → verify
- §2: pick 1 by score → assemble all elements
- §3: group by topic → top item/medium/topic (images) — needs `clipping_image_b64`,
  `thumbnail_url`, yt thumbnail
- §4: 7-day scheme scorecard + tone-over-time (needs 7 days of stored items)
- §5: district tags + tone → map + table
- §6: per-medium tone + divergence
- §7: contested pair from events + roster sides + quotes (build-time MT)
- §8: gated figures from `article_numbers`/`clipping_numbers`
- §9: per-house from outlet-identity + 7-day sparkline (fills after a week)
- §10: cited items; **Full Record** = all government-relevant items (separate)
**Table:** `briefing.report` (run_id, json, immutable) + `briefing.report_overrides`
(edits made before send).

---

## PHASE 6 — Renderer + frontend (what the user sees)

- **Renderer:** headless Chromium (Playwright) service — renders the report JSON to the
  same HTML the user edits, exports PDF, handles Telugu shaping. Replaces WeasyPrint.
- **Frontend (Dispatch page, React):** renders report JSON; section toggles; inline
  edit (saves to `report_overrides`); "export PDF"; "send". This is where DIPR corrects
  MT quotes before send.
- **Router:** `GET /api/brief/report` now serves the STORED daily JSON (not a live
  rebuild); `/report.pdf` renders via Playwright; `/report/send` unchanged path.

---

## PHASE 7 — Delivery + scheduling

- **Nightly Celery task** on the `brief`/`relevance` queue: run pipeline → merge →
  assemble → store, at a fixed hour (see Q on timing vs print lag).
- **Delivery:** existing `report_email` / VeriDeck to DIPR at delivery hour.
- **KB update:** record the new pipeline in `01-rig-surveillance-backend`.

---

## Known data gaps carried in (decide per Q)
- TV has no number extraction (§8 = web+print only).
- `quote_text_en` empty → §7 English is build-time MT.
- 9 outlets IP-blocked (Sakshi/Hindu) — headline-only via Google News, currently off.
- District tile map is not true geography (GeoJSON optional).
- Timeline = collection time, not publish time.

---

## RESOLVED (2026-07-24)
- **B1 Scope → FULL GENERIC NOW.** Every `briefing.*` reference table carries `org_id`;
  engine is multi-tenant from day one; Telangana is the first tenant, seeded from its
  scope doc. Aligns with existing multi-tenant `analytics.org_api_scope` /
  `user_brief_prefs`.
- **A1 LLM → the existing unified pool** (`products/osint/backend/groq_client.py`):
  local Ollama (4090) primary → Groq 20-key → Cerebras → LM Studio, automatic failover,
  token bucket, health checks. JSON calls auto-skip local (hangs on json_mode) → route
  to Groq/Cerebras. Use `call_groq(..., json_response=True)`. Add token-limit task types:
  `brief_judge` (~600 tok), `brief_merge` (~2000), `brief_line` (~500), `brief_narr`
  (~1500). NO new integration. Failover already does "switch if one fails."
- **A2 Infra → extend osint-backend.** New `briefing.*` schema in rig-postgres, nightly
  Celery task on the `brief` queue, Dispatch page rewired to serve stored JSON.
- **C1 Roster → we draft from the client's scope doc, DIPR signs off.** The doc is
  ALREADY PROVIDED (`Telangana_CM_Government_Coverage_Scope.docx`, 466 entities, already
  read + parsed into Opposition 30 / Allies 49 / Watched 116 / Neutral 271). No re-send
  needed. It becomes org-scoped reference data; roster is the source of truth for
  gov/opposition sides.

## OPEN QUESTIONS (remaining — answer these and the path is unambiguous)

### A. Timing
A3. **Run + delivery timing:** print lags a day — run at (e.g.) 05:00 IST to capture
    the morning's papers, deliver 06:00? Or run late-night for a pre-dawn brief?

### C. Roster
C2. **Telugu spellings** — do you have a source list, or I generate and you/client verify?

### D. Validation
D1. **Strictness** — 80% sentiment agreement enough for a government client, or higher?
D2. **Who hand-labels** the validation sets — I propose labels and you/client confirm,
    or the client labels from scratch?
D3. **Which days** — 22 + 21 Jul, or pick specific high-event days?

### E. Delivery / product
E1. **Full Record** — a second page in the same PDF, or online-only?
E2. **Edited-before-send** — press officer edits; do we save + audit the edited version?
E3. Daily brief + the 7-day scheme view — same document, or the scheme scorecard as a
    separate weekly send?

### F. Data-gap calls
F1. **TV numbers** — build extraction now, or ship §8 as web+print only?
F2. **Headline-only outlets** (Sakshi etc.) — keep disabled, or re-enable for
    volume-only counts (excluded from tone)?
F3. **Delete the 137 trial articles** now? (Y/N)
F4. **District map** — invest in true GeoJSON outline, or keep the honest tile grid?
