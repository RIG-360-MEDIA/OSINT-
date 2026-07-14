# Unified OSINT Scout — Design (Aryan Mehta review)

Working name: **Scout**. A standalone webapp that fans one query across every capability we
built (social, free OSINT sources, identity footprint) and returns **raw, ranked, deduped
data — no deductions**. Image-verification + satellite ride along as separate input-mode tools.

---

## The one-line thesis
This is a **federated scatter-gather search** problem, not a "combine our tools" problem. The
value is 90% in three unglamorous layers everyone skips: the **canonical result schema**, the
**relevance+recency ranker**, and the **evaluation harness**. Build those or you've built a
demo, not a product.

---

## Phase 1 — Keyword → fan-out aggregator

### Architecture (reuse, don't rebuild)
New service `products/scout/` (FastAPI + static UI, isolated, same pattern as media/geo/identity).
It is an **orchestration layer over existing services** — it collects nothing itself:
- Social → `backend/collectors/cheap_stack/keyword_search.py` `REGISTRY` (already fans out 7 platforms, honest ok/error).
- Free OSINT sources → the existing `/api/keywords/*` endpoints (osint-backend).
- Identity footprint → `rigident /footprint` — **conditional** (see gate below).

`POST /scout {keyword}` → `asyncio.gather` over all sources with **per-source timeouts
(8–15s) and partial results**. Never block on the slowest. **Stream partials to the UI** as
each source returns — latency is a UX problem disguised as infra.

### Canonical schema (build this FIRST — it's the contract for Phase 1 AND 2)
Every source normalizes to ONE `ScoutItem`:
```
source, source_type(social|osint|identity), platform, title, text, url,
author, published_at, engagement{views,likes,comments}, media[], lang,
relevance_score, recency_score, final_score, raw{}   # raw = source-native fields
```
Without this, the frontend is chaos and Phase 2 is impossible.

### "No deductions" — but ranking IS a decision (be honest)
"Top / most relevant" secretly requires a ranker. Raw engagement is NOT comparable across
platforms (Reddit upvotes ≠ TikTok views ≠ tender date). So per item:
- **relevance_score**: keyword match in title/text (BM25-ish) + entity match, normalized 0–1 per source.
- **recency_score**: exponential time-decay `exp(-Δt/τ)` — a 6-month post must not rank like a 20-min one. This is the single highest-leverage thing; bake it in day one.
- **final_score** = w1·relevance + w2·recency + w3·source-normalized-engagement.
- **Dedup**: same story across platforms → MinHash LSH (URL/text) + optional embedding cosine. "Good bulk" = expand wide, then dedup, or you'll drown the user in reposts.

### Identity footprint — GATE it (this is a trap)
Identity footprint is **entity/handle-driven, not topic-driven**. Running it on "PLA Navy" as a
topic keyword = noise. Only invoke when the keyword looks like a **handle or named person/org**
(cheap heuristic + our own entity check), and present it as a **distinct panel**, never mixed
into the content stream.

### Image / satellite — correct instinct
Not keyword-addressable. Separate **tabs** in the same webapp, different input modes (paste
image / lat-long), proxying the live rigmedia + riggeo UIs. Don't force them into the query box.

### Caching
Per-keyword cache (persist-from-use, same as everything else). A keyword search is expensive
fan-out; run once, serve repeats free; TTL by freshness need.

---

## Phase 2 — Natural language → query plan (NOT text-to-SQL)

**Strong pushback on the framing.** Text-to-SQL is the wrong model for most of this, because
our data is NOT a warehouse — social/identity/tenders are **live API scrapes**, not tables.
NL→SQL only applies to the **stored corpus** (articles/newspapers in Postgres). For live
sources, NL→SQL is a category error.

### The right frame: NL → structured **Query Plan** (intermediate representation)
An LLM decomposes the request into an IR; a **deterministic planner** executes it:
```
QueryPlan {
  entities:   [Indian Army, ...]
  topics:     [US politics, ...]
  lens:       {perspective: India, langs: [hi,en-IN], geo: IN, source_bias: Indian outlets}
  filters:    {toxicity>=τ, date_range, ...}    # reuse existing social toxicity/weaponization signals!
  expansions: [synonyms, entity aliases, translations]   # recall booster
  source_set: [social, articles, tenders, ...]
}
```
- "USA politics from India's perspective" → topic=US politics; lens=Indian sources + hi/en-IN + India geo; expand keywords (Trump, US election…); this is a **plan**, not one SQL string.
- "Harmful content on Indian army" → entity=Indian Army + filter=toxicity (we ALREADY store `toxicity`, `weaponization_signals`, `coordination_cluster_id`) → this one IS partly SQL over enriched social + fan-out.

### The failure mode you MUST design for (war story)
LLM decomposition **silently mistranslates intent** → recall collapse (you miss half the topic)
or precision collapse (garbage). At Ground News, the blindspot classifier only survived public
scrutiny because it was **explainable**. So: **show the user the interpreted plan** — an
editable "I read this as: topic X, sources Y, lens Z, these expansions — adjust?" panel. Never a
black box. Transparency = trust + it's how you debug recall.

### Recall maximization ("as much relevant data as possible")
Aggressive **query expansion** (synonyms + entity aliases + cross-lingual translation) → multiple
retrieval passes → dedup. Multilingual is **first-class** here ("India's perspective" = Hindi/
regional). Retrofitting language is always more expensive than building it in.

---

## Evaluation harness — FIRST, not last (non-negotiable)
> A model without an evaluation framework is a guess with infrastructure around it.

Before declaring Phase 1 "good", build a **gold set**: 20–30 keywords across domains (defense,
politics, companies, a known-hard one). Metrics, on a dashboard:
- **precision@10** per source (human-label a sample relevant/not).
- **coverage**: how many sources returned ≥N results (catches silent source death — we JUST
  lived this with the reddit/twitter cookies).
- **freshness**: median age of top-10.
- **dedup rate**: % collapsed.
This is how you answer "are results relevant + bulky?" with a number, not a vibe. It also
doubles as the Phase-2 acceptance gate.

---

## Build order (do NOT skip ahead)
1. Canonical `ScoutItem` schema.
2. Scatter-gather aggregator over existing services (timeouts, partials, streaming).
3. Ranker (relevance + recency-decay + engagement) + dedup.
4. Standalone UI (unified ranked stream + per-source panels + image/sat tabs).
5. **Eval harness + gold set** → prove precision/coverage/freshness.
6. ONLY THEN Phase 2: NL→QueryPlan LLM + editable-plan UI + planner reusing the same aggregator.

Phase 1's aggregator IS the engine Phase 2 drives. Same fan-out calls, smarter front-end.

## Risks I'm watching
- **Datacenter-IP throttling** amplified by fan-out (we hit it on maigret/reddit) → per-source rate budgets.
- **Cookie/session expiry** → the watchdog already covers this; Scout must surface per-source `ok/error` honestly (never a silent empty).
- **"Relevance" is the real IP** — don't under-invest it because the ask said "just data."
