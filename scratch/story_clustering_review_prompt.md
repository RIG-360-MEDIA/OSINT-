You are a principal-level ML / news-AI engineer. I'm going to describe a news
"story clustering" engine, a diagnosed failure mode, and a proposed fix approach.
**Critique it honestly — tell me whether the approach is sound, where it's wrong
or risky, what I'm missing, and whether there's a better-established way to do
this.** Don't rubber-stamp it; I want the holes.

## Product context
- A multi-source Indian regional news aggregator (~120K articles, mostly Telugu/
  Hindi/English, many small outlets that republish/rewrite the same events).
- Each article has a 768-dim **LaBSE multilingual embedding** computed on the
  translated lead text (≤512 chars), stored in Postgres + pgvector.
- Goal: group articles that cover the **same specific event** (one press
  conference, one accident, one court hearing, one unfolding crisis) into "story
  threads" — across outlets and across days — to power a "Defining Stories"
  product. Same *topic/person/place but different event* must NOT be merged.

## How the current engine (v2) works (online, per-article)
For each new article with an embedding and no thread yet, `cluster_article`:
1. **kNN retrieval**: find the 5 nearest *active* threads by cosine distance,
   comparing the article embedding to each thread's **seed embedding** (the FIRST
   article that started the thread — it never re-centers), within a 14-day window.
2. **Fast-path MATCH**: if nearest distance **< 0.18** → assign to it, **skip the
   LLM**, set `confidence = 1 − distance`.
3. **Fast-path NEW**: if no candidate or nearest **> 0.55** → spawn a new thread,
   skip the LLM.
4. **Gray zone (0.18–0.55)**: call an **LLM judge** that picks one candidate or
   says NEW. (Prompt is good: it explicitly requires the *same specific event*,
   not same topic, and fails safe to NEW.)
- **Nightly consolidate**: take the 50 lowest-confidence threads, find each one's
  nearest neighbour thread, **merge if distance < 0.30 by distance alone (no
  LLM)**; deactivate threads idle >14 days.
- The per-article + nightly tasks are written but **NOT scheduled** (not wired
  into the scheduler), so threading currently only runs manually/backfill.

## Observed quality (live DB, 7,409 threads)
- **69% singletons** (5,094 one-article threads).
- **156 "runaway" threads >100 articles, max = 29,798 articles.** Runaways have
  **avg source_count = 1.01** (essentially single-source) and **avg confidence =
  0.74** (high).
- Of 2,071 current-version threads, only **~37 are multi-source at all**; a
  realistic "trustworthy" filter (active + ≥2 sources + size 2–30) yields only
  **27 usable threads**.
- Spot-checking large clusters: they're single-source grab-bags — e.g. one
  77-article "cluster" is just *Outlet A ×77* mixing a heatwave, a film release, a
  murder, and a cricket match. Small multi-source clusters look correct.

## Diagnosed root cause (grounded in the engine's own calibration note + code)
- The thresholds were calibrated on a 100-pair sample where **SAME-story pairs had
  cosine distance 0.19–0.50 and DIFFERENT-story pairs had 0.12–0.50.** Those
  distributions **overlap almost entirely, and DIFFERENT pairs go *lower* (0.12)
  than SAME pairs ever reach (0.19).** → **Embedding distance does not separate
  same-event from different-event.** LaBSE on lead text encodes topic + language +
  house style, so two unrelated articles from the same outlet sit at very low
  distance simply because they're the same outlet/style.
- The **<0.18 no-LLM fast-match** therefore auto-merges the lowest-distance pairs,
  which are disproportionately **same-source / same-style / DIFFERENT-event** —
  silently, without the judge. The thread's frozen seed acts as a magnet for that
  source's style, so it accretes that source's articles forever → single-source
  runaways.
- `confidence = 1 − distance`, so these false merges score ~0.85 → **confidence
  cannot filter them.** The actually-smart LLM judge only runs in the 0.18–0.55
  band, where it's least needed.

## Proposed fix approach (THIS is what I want critiqued)
1. **Remove or drastically tighten the no-LLM hard-match fast-path** (the <0.18
   auto-merge is the main damage). Send more decisions to the judge.
2. **Source-diversity guard**: a thread cannot keep growing from a single source
   without cross-source confirmation; treat "≥2 independent sources agree" as the
   core signal that something is a real story. Same-source candidates always go to
   the judge (or are blocked from auto-merge).
3. **Gate on structured signals, not raw embedding distance**: use shared named
   **entities + event_type + publish-time proximity** as the match gate; use the
   embedding only as a recall/candidate filter, not the decision.
4. **Match against the thread centroid / recent members, not a frozen seed.**
5. **Runaway breaker**: hard size cap + split / re-evaluate when a thread exceeds
   N articles or becomes single-source-dominated.
6. **Consumer-facing quality filter**: `is_active AND source_count >= 2 AND size
   cap` (since confidence is unreliable).
7. **Operationalize**: wire the per-article + nightly tasks into the scheduler;
   run the v1→v2 cutover once validated; re-grade on a hand-labeled set and report
   real **precision/recall** (currently there are none — evals are qualitative).

## Questions for you
1. Is this approach sound for "same specific event" clustering, or am I solving
   the wrong layer?
2. What are the biggest risks/blind spots (e.g., entity-extraction noise,
   multilingual entity matching, breaking-news where only one source has it first,
   precision/recall tradeoffs, cost of routing everything to an LLM)?
3. Is there a better-established method I should use instead — e.g. TDT /
   topic-detection-and-tracking, two-stage retrieve-then-verify, same-event graph
   + connected components, incremental/online clustering with a learned same-event
   classifier, time-decayed centroids, etc.?
4. Specifically: is "source diversity as the core story signal" a good idea or a
   trap (single-source scoops, echo-chamber republishing, wire-copy duplication)?
5. If you were building this from scratch for same-event cross-lingual clustering
   at ~20K articles/day, what would your architecture be?

Be specific and critical.
