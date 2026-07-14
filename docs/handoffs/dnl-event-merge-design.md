# Same-event cluster merge — approaches, and a self-improving design

## SHIPPED (2026-07-11) — Phase 0 + Phase 1 live, Phase 2 collecting
NON-DESTRUCTIVE by design: everything writes `analytics.story_dedup(story_id → canonical_story_id)`, a
reversible map. Fragment clusters are PRESERVED (for the future timeline / bias-spread / multi-perspective
views); only the front page collapses to the canonical (`ranking.ts`: `AND NOT EXISTS (… story_dedup …)`).
Result: **73 fragments folded into 41 canonical events**; the Vietnam-boat "5 updates" pile is now 1 card.

- **Phase 0** `/root/rig/scripts/dnl_event_merge_v0.sh` (cron :17). Vector-only: cluster CENTROID (avg member
  LaBSE v4, via pgvector `avg()` + `<=>`) cosine > 0.83 + same dominant entity + adjacent-day → connected
  components → canonical = most articles. NOTE: cos>0.9 on the REPRESENTATIVE embedding was too strict
  (caught 1/8 boat pairs); centroids + 0.83 + transitive components is the working operating point. Folded 62.
- **Phase 1** `/root/rig/scripts/dnl_event_merge_llm.sh` + `merge_adjudicate.py` (cron :40). Gated LLM: only
  BORDERLINE / CROSS-ENTITY pairs (cos 0.80–0.905, different dominant entity) Phase-0 couldn't merge → adjudicated
  by `backend.nlp.groq_client` Cerebras **gpt-oss-120b** (runs INSIDE rig-backend; the pool + httpx live there).
  GOTCHA: gpt-oss-120b is a REASONING model — needs `max_tokens ≥ 600` + `reasoning_effort:"low"` or `content`
  is empty (finish_reason "length"). 17/17 verdicts, sharp precision (rejected 2 distinct Peskov statements at
  0.96 cos; merged cross-entity Devon murder / Srebrenica tribute). Folded +11. Every verdict logged to
  `analytics.merge_verdicts` (story_a, story_b, cos, llm_same, llm_conf, reason).
- **Phase 2 (flywheel)** — `merge_verdicts` is the training data, accumulating hourly. Once ~200+ labels:
  fit P(same | cos, entity_match, time_delta) → recalibrate Phase-0 θ + distill a cheap student → LLM only on
  the uncertain tail. NOT yet built (needs label volume).
- Sync: both jobs `TRUNCATE + \copy` story_dedup → Neon; `reader_ro` granted. Cluster USES stay intact (map is
  additive) so timeline / left-right bias / multi-perspective features can aggregate folded fragments later.

---

# Same-event cluster merge — approaches, and a self-improving design (original design notes)

**Problem:** one real-world event (Phú Quốc boat capsize) becomes 7+ separate clusters, each generated
into a near-duplicate story. Root cause: online clustering opens a NEW cluster per time-window / when the
similarity threshold isn't met, and never re-joins them. This is a well-studied problem with a name.

## What the problem is called (so you can research it)
- **Near-duplicate detection** (surface/lexical) — copies & rewrites.
- **Topic Detection & Tracking (TDT)** — DARPA research area (late 90s): *New Event Detection* + *Event Tracking*. The canonical framing of "is this a new event or an update to a known one?"
- **Cross-document event coreference (CDEC)** — NLP research (ECB+, CoNLL, Barhom 2019, Cattan 2021 "streaming" CDEC). "Do these two mentions/docs refer to the same event?"
- **Online / streaming event clustering** — the production version (Google News, Event Registry).
- **Entity canonicalization / disambiguation** — related (our "s. janaki" vs "janaki" split is this).

## The ladder of approaches (cheap → smart)
1. **Lexical near-dup** — MinHash+LSH (Broder), SimHash (Charikar), TF-IDF cosine. Fast, O(n) with LSH. **Catches copies, misses paraphrase** (our exact failure: "A Wave, A Turn" vs "Fifteen Indians Die").
2. **Semantic embeddings + ANN** — SBERT/LaBSE/E5/GTE vectors, cosine, HNSW/FAISS/ScaNN retrieval. Online clustering: new doc → nearest centroid; merge if cos > θ else new cluster. **This is what most news systems (and ours) do; the bug is θ + time-windowing.**
3. **Event-structured signature** — an event = (WHO, WHAT, WHERE, WHEN). Merge if key entities overlap AND time windows overlap AND location matches AND hard facts agree (casualty count, place). Much more precise than "dominant entity" alone.
4. **Graph + community detection** — nodes=clusters, edges=similarity, Louvain/connected-components to merge (we already use igraph-Louvain). Fix = add cross-time-window edges.
5. **LLM adjudication** — ask an LLM "same event? yes/no" on candidate pairs. Highest accuracy on paraphrase; expensive.

## Who does what
- **Ground News** — MinHash-LSH *and* semantic embeddings in parallel, across 50k+ publishers.
- **Google News "Full Coverage"** — online embedding clustering + entity/temporal heuristics, heavy tuning.
- **Event Registry (eventregistry.org)** — cross-lingual event clustering via Wikipedia entity-linking + embeddings; the research-grade reference implementation.
- **GDELT** — structured event extraction (CAMEO actor/action/geo/date) then dedup on the tuple.
- **Techmeme** — heuristics + human curation. **AP/Reuters** — internal, human-in-loop on breaking news.

## Is "an LLM sweeps all clusters each hour and merges" good?
**Directionally yes — but not naively.** Three fixes make it production-viable:
1. **Never O(n²).** Comparing all cluster pairs each hour = millions of calls. Gate with **retrieval first**: embeddings/ANN propose only *candidate* pairs (same/overlapping entity, time-close, cos > 0.75). The LLM only adjudicates the **borderline** shortlist. O(n·k), not O(n²).
2. **Feed structured facts, not just headlines.** Give the LLM each cluster's (top entities, numbers, place, date, 1-line gist). Require agreement on **hard facts** (15 dead, Phú Quốc) — this blocks hallucinated merges.
3. **Conservative + reversible + logged.** A wrong merge (fusing two distinct events) is worse than a dup, and breaking-news is where it hurts most. Keep merges as a reversible `duplicate_of` mapping, not a destructive rewrite; log every decision.

## The part you intuited that matters most: LLM-as-teacher → self-improving system
Your instinct — "when the LLM merges, that should be a *learning* that makes our own system/model better" — is exactly the right architecture. It's **knowledge distillation + active learning + threshold calibration**. The flywheel:

1. **LLM decisions become labels.** Every "same / different" verdict is a labeled training pair — a dataset for a problem you never had labels for (weak supervision).
2. **Calibrate the cheap threshold.** Fit P(same-event | cosine, entity-overlap, time-delta) on those labels (isotonic/Platt). Now the embedding threshold θ is *learned to match the LLM*, not guessed.
3. **Distill into a fast student.** Train a tiny cross-encoder / logistic-reg / gradient-boost on features (embedding cos, entity Jaccard, shared-number flag, time delta, geo match) → predicts same-event in microseconds. The LLM (teacher) is distilled into a cheap model (student).
4. **Active learning.** Once the student exists, the LLM is only spent on cases where the **student is uncertain** (0.4–0.6). Max label value per LLM dollar.
5. **Loop.** Student handles the bulk; LLM adjudicates the shrinking hard tail; its verdicts retrain the student. Cost falls, accuracy rises over time. Track merge precision/recall on a held-out gold set (LLM + spot human check).

**End state:** embeddings (candidate gen) → distilled student (fast merge decision) → LLM (uncertain tail only) → verdicts feed back to retrain student + recalibrate θ. A merge system that gets cheaper and better the longer it runs.

## Recommended concrete path for THIS system (we have LaBSE on the box, igraph-Louvain, an LLM pool)
- **Phase 0 (fix the bleeding):** raise cross-time-window re-join — add edges between clusters that share ≥N member-articles' entities + cos(representative LaBSE) > 0.9 + same day. Pure vector, no LLM. (The infra likely half-exists — the "cross-window re-join" mentioned in ops notes.)
- **Phase 1 (LLM adjudicator, gated):** hourly job — for clusters touched this hour, ANN-retrieve candidate same-event pairs, LLM adjudicates the borderline set with structured facts, writes a reversible `duplicate_of`. Log every verdict.
- **Phase 2 (flywheel):** train the distilled student on the logged verdicts; calibrate θ; move LLM to the uncertain tail only.
- **Eval throughout:** a labeled merge gold set; track precision (don't fuse distinct events) and recall (catch the dupes). Precision is the one you protect — a bad merge on breaking news is the failure that gets noticed.
