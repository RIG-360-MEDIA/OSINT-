# Ask-RIG → Agentic Intelligence Workspace — Spec & Vision (2026-06-24)

The chat today has **one mode**: retrieve ~14 sources → synthesize one answer. The leap is to make
it a **mode-aware intelligence agent** that picks the right *tool* per request — synthesize,
enumerate, drill-down, quantify, dossier, compare, monitor, investigate — and **enriches data on
the fly** when the pre-computed signals are too sparse to trust.

---

## Verified data reality (live, 2026-06-24) — what we can actually build on

| Signal | State | Verdict |
|---|---|---|
| Article volume | **50,361 / 24h · 226K / 7d** | ✅ huge, fresh — enumeration is well-fed |
| Entity → article | `article_entity_mentions` (matview) + `actor_entity_id` | ✅ queryable |
| Time / language / outlet / url / summary | base `articles` cols | ✅ clean |
| Quotes | `article_quotes` (speaker, text, is_direct, EN translation, offsets) | ✅ rich |
| **Sentiment / stance** | `article_stances(actor=target, stance, intensity)` | ⚠️ **SPARSE + free-text** |

**The sentiment caveat (decisive):** `stance` is LLM free-text (`grateful`, `mockery`, `skeptical`,
`divided`, `concerned/neutral`…), not clean polarity, and coverage is thin (~78 rows ever about
the TG govt). So **"all negative articles about X" must NOT be a flag lookup.** Pattern instead:
**(1) retrieve the candidate set by entity+time (clean) → (2) classify sentiment per-article on the
fly with a fast LLM → (3) return the filtered list.** More compute, but accurate and honest.

---

## Architecture — modes + tools + on-demand enrichment

1. **Planner upgrade:** emit `intent/mode` + structured `filters` {entity, sentiment, time_window,
   language, outlet, pillar, limit, sort}. (Extends the existing query-type classifier.)
2. **Tool layer** (build on existing `app/agent/`, `app/intel.py`):
   - `list_articles(filters)` — full filtered set, paginated, newest-first
   - `count/aggregate(filters, group_by)` — counts, trends, breakdowns
   - `get_article(id)` — full record for drill-down
   - `classify_batch(article_ids, axis)` — on-the-fly sentiment/topic/relevance per item
   - `retrieve_rag(query)` — the current synthesis path
3. **Router:** mode → tool(s) → renderer. Enumerate → **expandable list UI** (each card → "Explain"
   → `get_article` + summarize); synthesize → current prose path.
4. **On-demand enrichment** is the throughline — never block on sparse precomputed flags.

---

## Capability catalog (grouped; tag = data feasibility)

**🔢 Enumerate** — return the full list, not a summary
- All articles about [entity] in [window], newest-first — ✅ ready
- All articles in [district] / [language] / from [outlet] on [topic] — ✅ ready
- "Just in" — everything in the last hour — ✅ ready
- All **negative/positive** articles about [entity] in [window] — ⚠️ needs on-the-fly classify
- Articles where [A] criticizes/attacks [B] — ⚠️ classify (or sparse stance)
- Every article carrying a quote from [person] — ✅ ready (`article_quotes`)

**🔎 Drill-down** — act on one result
- Explain / summarize / list-quotes / full-translate item #N — ✅ ready
- Sentiment-and-toward-whom for #N — ⚠️ classify on demand
- "What else covers the same event as #N" (entity+time overlap, no clusters) — ✅ ready

**📊 Quantify / trend**
- Count negative vs positive about [entity] this week vs last — ⚠️ classify (sampled)
- Coverage volume by day / district / language; spike detection — ✅ ready
- Most-mentioned people in [topic]; most-covered topics this week — ✅ ready (mentions matview)
- Which outlets cover [entity] most / lean which way — ✅ volume; ⚠️ lean = classify

**🗂 Dossier** — deep profile
- Full dossier on [person/org]: recent coverage, quotes, key events, cross-lingual — ✅ ready
  (quotes + mentions + time); sentiment-toward-them ⚠️ classify

**⚖️ Compare**
- Coverage of [A] vs [B]; English vs Telugu framing of [event] — ✅ ready (lang split)
- Contradictions / who-said-what quote roundup on [event] — ✅ ready (quotes)

**🔔 Monitor / proactive** (true agent)
- Saved watch: alert on new coverage of [entity] / on negative turn — ⚠️ needs scheduler+store
- Watchlist of N entities; morning brief on [topics] — ↔ ties into the existing Brief pillar

**🕵️ Investigate** — multi-step (filter → enrich → rank → synthesize → cite)
- "All corruption allegations against [party] this month, summarize the strongest"
- Build a **timeline** of [event] from all sources — ✅ ready (time-ordered + synthesize)
- Fact-check a claim against the corpus — ✅ retrieval + verdict

**✨ Grandeur (bigger bets)**
- **Report/dossier export** → downloadable Markdown/PDF artifact from any query
- **Entity relationship & stance graph** (who-attacks/supports-whom) from quotes+stances
- **Cross-lingual narrative-divergence detector** (same event, different framing per language)
- **Personalized standing interests** (learns what you track) — gated on the no-auth decision (Mem0)
- **Scheduled push digests** (daily/region/topic) — reuse Brief infra
- **"Why/causal" engine** — assemble cause→effect chains from event coverage
- **Conversational refinement** — "narrow to last 6h", "only Telugu", "now explain #3" mid-thread

---

## Build plan (phased)
1. **Flagship — Enumerate + Explain** (entity+time list → expandable cards → per-item explain).
   Start with the clean path (no-sentiment filters). Renderer = list UI.
2. **On-the-fly sentiment classify** → unlock "all negative/positive" filters honestly.
3. **Quantify/trend** (counts, by-day/district/language, spike).
4. **Dossier** + **Compare** (quotes-driven).
5. **Monitor/push** (reuse Brief scheduler) + **Investigate** multi-step.
6. **Grandeur**: export artifacts, relationship graph, narrative-divergence.

## Honest constraints
- No clusters/stories (forbidden) — use entity+time overlap for "same event".
- Read-only corpus; all new state in the app DB.
- Sentiment = on-the-fly classification, never the sparse precomputed flag, for any "negative/positive" ask.
- "All" must be honestly bounded + paginated (50K/24h means broad filters need tight scoping + caps with a stated count).
