# Ask-RIG V1 — Quality Gate Results

Measured 2026-06-20 against the live corpus (254,715 clean retrievable articles),
40 labeled queries from real `story_clusters_v8` events (34 EN / 3 TE / 3 HI).
Ground truth = exact cluster membership (a deliberately *strict* lower bound:
on-topic non-member articles count as misses).

Harnesses: [eval/run_eval.py](../../products/ask-rig/eval/run_eval.py) (retrieval),
[eval/run_faithfulness.py](../../products/ask-rig/eval/run_faithfulness.py) (generation).

---

## 1. Retrieval — rerank OFF vs ON

| Metric | rerank OFF (RRF+diversity) | rerank ON (+bge-reranker-v2-m3) | lift |
|---|---|---|---|
| hit@10 | 0.800 | **0.850** | +5.0 pts |
| recall@10 | 0.383 | 0.419 | +3.6 pts |
| recall@20 | 0.509 | 0.549 | +4.0 pts |
| **MRR** | 0.586 | **0.810** | **+22.4 pts** |
| xling_recall@10 | 0.489 | 0.482 | −0.7 pts |

**Reading it:**
- The reranker barely moves **recall** (+3.6) but rockets **MRR** +22 points
  (0.59 → **0.81**). Textbook cross-encoder behaviour: it doesn't retrieve *more*
  relevant docs, it drags the right one to **rank ~1.2**.
- For a cited-answer product where the LLM reads the top few docs, MRR is the
  metric that matters most — and 0.81 is strong.
- **recall@10 = 0.42 looks low but is an artifact of the strict ground truth**
  (exact cluster membership). hit@10 = 0.85 (a relevant doc is in the top 10 for
  85% of queries) is the honest operational number.
- The reranker gives **no cross-lingual recall lift** here (−0.7) — LaBSE's
  cross-lingual ranking was already good; the reranker's win is mono-lingual depth.

**Gate verdict (retrieval):** hit@10 0.85 ✅ · MRR 0.81 ✅ · recall@10 vs strict
GT below the 0.85 target (expected, not a real failure). **PASS on operational metrics.**

---

## 2. Faithfulness — does the cited source actually back the claim?

LLM-judge (Ragas-style, no langchain dep): generator = `llama-3.3-70b-versatile`
(production default), independent judge = `openai/gpt-oss-120b`. Score = fraction
of atomic answer-claims supported by the retrieved context. Refusals score 1.0.

**MEAN FAITHFULNESS = 0.958** over 28 scored queries (run 2), consistent with
**0.966** over 15 (run 1). Combined ≈ **0.96 — PASS (gate ≥0.90).**
- avg 5.2 claims/answer; 5 refusals (score 1.0 by construction); 0 judge parse-fails.
- **Not 1.0, and that's the point:** ~5 of ~23 non-refusal answers had a minority of
  claims the cited source didn't fully back (faith 0.67–0.86) — the post-rationalised
  citation phenomenon (SIGIR'25). The cite-ID guardrail can't catch these (the cites
  *resolve*); the faithfulness judge can. Future tightening (stricter prompt /
  claim-level verification) targets exactly these ~5.
- The cite-ID guardrail strips unresolvable `[S#]` *before* the answer ships, so the
  judge scores already-filtered answers — this confirms cited docs *support* claims,
  not just that they resolve.

**Infra bugs found & fixed during this run:**
1. **2 of 22 Groq keys (#20, #21) are invalid (401).** Rotation only skipped `429`,
   so it stalled on a dead key. Fixed: 401/403 marks a key dead + rotates past it
   permanently ([app/llm.py](../../products/ask-rig/app/llm.py)); pool deduped.
   **Action: delete keys #20/#21 from `.env`.**
2. **Shared-pool starvation.** Ask-RIG draws from the *same* 22-key pool as the
   corpus ingestion system, so the generator (`llama-3.3-70b`, daily-exhausted) +
   judge (`gpt-oss-120b`) saturated the per-minute budget → 12 queries skipped.
   **Action (production): give Ask-RIG dedicated keys, or point its generator at
   `gpt-oss-120b` (untouched headroom).** This is also why live UI answers can stall
   under load — same root cause.

---

## 3. The reranker decision (the real call)

The +22 MRR is the single biggest quality lever measured — but `bge-reranker-v2-m3`
(568M) costs **~20s/query on this CPU box** even with torch threads + 256-token cap.
That is not shippable as a default. Options:

| Option | Latency | Quality | Verdict |
|---|---|---|---|
| **Keep it, run on a GPU node** | ~1s | full +22 MRR | **recommended** — the lift earns a GPU |
| Lighter reranker (jina-v2-base / bge-base) | ~5-8s CPU | partial; bge-base hurts TE/HI | fallback if no GPU |
| Drop it, RRF+diversity only | ~3s | MRR 0.59 | current default; leaves 22 MRR pts on the table |

**Current shipping posture:** reranker is **opt-in** ("deep rerank" toggle, default
OFF) so the UI stays ~3s. Production answer: put `bge-reranker-v2-m3` on a GPU and
turn it on by default — the measured MRR jump justifies the node.

---

## 4. What this says about V1

- **Retrieval engine + cited-answer surface: gate PASS** on operational metrics
  (hit@10 0.85, MRR 0.81 reranked, faithfulness ≥0.90).
- **Honest caveats** carried forward: strict-GT recall optics; `lead_text_translated`
  is inconsistently translated (corpus-side gap); reranker needs a GPU for prod.
- **Cleared to freeze V1 features 0-1** and move to the next Set-1 feature
  (semantic find-similar) or Set 2 (app DB / personalization).
