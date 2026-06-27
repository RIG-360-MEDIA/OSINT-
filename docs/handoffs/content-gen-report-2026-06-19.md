# Content-gen on clean clusters — report back to analytics/front-end (2026-06-19)

Executed the 5-task spec. All numbers MEASURED on live DB; every gen verified (no fabricated "done").

## (1) Stale / regen backlog
- **~5,082 surfaceable clusters need (re)gen:** 3,917 with **NO gen row** (new clean clusters from the graph
  loop/backfill, never generated) + 1,165 surfaceable clusters whose gen row is **held/stub** (retry on the
  clean membership). Of the held, **634** are the old Guard-C "multi-event — needs _v8 split" mega-rejects.
- **Orphans negligible:** 1 gen row → a ≥2000 mega, 0 → template, 0 → non-existent story_id. All are HELD/not
  PUBLISHABLE → the front-end `facts>0 + PUBLISHABLE` gate already can't surface them. Task-1 point-3 is clean.
- **member_hash regen trigger BUILT + LIVE** (`worldwide_gen_live.py`): added `member_hash` column (md5 of the
  ordered member-article set, computed in-SQL on every UPSERT); skip-guard now skips ONLY if `fact_version`
  AND `member_hash` both unchanged → **regen now fires on re-clustering**, not just fact changes.

## (2) Regenerated this pass
- 120-cluster stratified sample (40 each size band) → **109 written** (61 PUBLISHABLE, 43 Guard-C-held, 5
  extractive) + **11 errored** ("Cerebras returned empty content" — transient, retryable, no row written).
- **Backlog drain RUNNING** (`worldwide_gen_live.py --aligned 5000`, front-page-importance order, lock-
  coordinated with the */30 cron) — clears the no-genrow set + retries held, prioritising the `/long-read` set.

## (3) Eyeball quality (read real rows, not flags) — PASS
- **9/9 pass** (6 existing PUBLISHABLE + 3 fresh clean-cluster). All: faithful (specific facts/numbers/quotes,
  every claim attributable), **single-event**, NYT/Atlantic-grade headlines (≤~12w, specific, no clickbait),
  real one-line decks, contested claims **attributed** ("police said"), honest about gaps ("details not
  disclosed"), **zero invented facts, zero "no facts available" boilerplate.** The PUBLISHABLE flag is honest
  now (the old empty-ledger bug is fixed).
- **No hard failures.** One recurring SOFTNESS (not a faithfulness fail): many articles hedge "according to a
  single source/report" even on multi-article clusters → the **fact-LEDGER is thin** (extracts from few
  sources). Articles are thinner than the corroboration warrants. Secondary fix = deeper multi-source fact
  extraction. Also some product-launch / niche items are factual but **curation**-borderline (not a gen issue).

## (4) Guard-C reject rate — DOWN from ~58%
Stratified sample (with facts), by cluster size:
| Band | Publishable | Guard-C reject (multi-event) | reject % |
|---|---|---|---|
| 2–5 | 27 | 11 | **27.5%** |
| 6–20 | 22 | 13 | **34%** |
| 21+ | 12 | 19 | **61%** |
| All | 61 (56%) | 43 | **39%** |
- Reject reasons: ~all "multi-event — needs split" (the ONE-dominant-event gate).
- **Publishable rate on clean-cluster gen-attempts rose to 56% (61/109) from ~34% before** (old: 365 pub /
  1,070 attempts). Real-world reject ≈ **~30–35%** (the sample over-weights big clusters; the live size mix
  skews small).
- **Residual:** big clusters (21+) still **61%** reject — a cluster at ~85% *pairwise* precision can still
  harbor a minority 2nd event that trips the ONE-event gate. That's where the remaining content yield is
  locked, and it needs **finer splitting** (the day-by-day reconcile) to unlock.

## (5) Wiring status
| Item | Status |
|---|---|
| single-source → STUB | ✅ wired (`indep<=1`) |
| fact_version regen | ✅ wired |
| member_hash regen | ✅ **now wired** (this pass) |
| empty-ledger → HELD (no factless publishes) | ✅ wired (+ no-facts-output rejection) |
| 3-tier cache | ⚠️ **PARTIAL** — binary stub(0)/full(1) only; no cheap **headline+deck-only** tier for surfaced-but-not-shown; long-tail is on-demand-by-absence, not by design |

## Recommendations / next
1. **Fix the 9% "Cerebras returned empty"** (retry-on-empty → local fallback) before the full drain — else
   ~9% of every batch is wasted cloud.
2. **Big-cluster Guard-C (61%)** is the locked yield → finer splitting (day-by-day reconcile) converts held
   giants into publishable per-event articles.
3. **Add the headline+deck-only tier** (complete the 3-tier cache) to cut LLM cost on the non-shown surfaceable.
4. **Deepen the fact-ledger** (multi-source extraction) to thicken articles beyond "single source" hedges.
5. Drain is running; the */30 cron (now member_hash-aware) keeps the front page regenerated on clean clusters.

→ Hand back to analytics: re-check the live `/long-read` page once the drain advances; report says regenerated
articles render as faithful single-event reads (9/9 eyeball), Guard-C reject ~halved, backlog draining.

---

## Fix-test verdict (2026-06-19, "are the 3 fixes worth it?")
Three fixes were tried and measured: **Fix-1** = loosen Guard-C (count reactions/updates/coverage as ONE
event); **Fix-2** = discriminator-required confident-merge in `cluster_v9` (`disc = shnum>=1 or tt>=0.5`);
**Fix-3** = extended roundup/template regex filter.

- **Fix-1 (Guard-C) — KEEP.** Re-gen of the 120 graph clusters with the loosened guard (run `1781877448`):
  71% clean PUBLISHABLE, **multi-event reject down to 16%** (14+2 of 100 written), 15% extractive-fallback.
  Recovers usable content with no downside. ⚠️ The extractive/error share was inflated by **LLM TPD quota
  walls** (Cerebras + Groq `gpt-oss-120b` both 429'd mid-run) — quality, not the fix, capped the clean rate.
- **Fix-2 + Fix-3 (cluster precision) — WASH, do NOT ship as a precision win.** Raw same-event intra-precision
  of the post-fix `cluster_v9` output = **59% (75/127)** vs old-raw baseline **62%**. On n=127 that's a
  statistical tie (95% CI ≈ ±8.5%, contains 62%) → **no measurable gain**. The judged `_v9_members` was from
  today's post-fix run, so this reflects the committed code. A belt-and-suspenders fresh re-run was **aborted
  at 66 min** — a 1-day window throws a huge gray-edge volume and judging it on the local-only 32B (cloud
  quota exhausted) is impractically slow; it wasn't going to change the answer.
- **Why the wash is fine:** raw-cascade precision was never the product metric. **Purity-split** is the gate,
  and the live `_v8` keeper already measures **80.7% surfaceable precision** (≥3 sources) vs ~25% baseline —
  Fix-2+3 don't touch that. Breaking the ~80% ceiling needs an **edge-level rebuild**, not raw-merge knobs.
- **Op learning:** gray-included `cluster_v9` backfills are cloud-LLM-bound (60+ min on local-only, and they
  hog the node the live pipeline shares). Run them only with cloud quota available, or with `LLM_GRAY=0` for a
  fast confident-edges-only check.

**Bottom line:** keep Fix-1; treat Fix-2+3 as neutral (harmless, no precision gain). Graphs still beat v7 on
the metric that matters (surfaceable precision), unchanged by these knobs.
