# Branch Reconciliation Plan — 2026-05-26

## Situation
- Local `fix/brief-prod-readiness` is **131 commits ahead, 74 commits behind** `origin/fix/brief-prod-readiness`.
- Common ancestor: ~early May 2026.
- Both sides built similar features in parallel.

## What origin has (74 commits) — by category

### A) CRITICAL — KEEP from origin (no local equivalent)
| Origin commit | What it does | Why critical |
|---|---|---|
| `854c857` | chore(deps): bump backend deps — closes **33 of 46 CVEs** | Security |
| `368fdeb` | chore(deps): bump next 15.5.18 + vitest 4 — closes 1 critical + 4 moderate CVEs | Security |
| `371fb7f` | docs(onboarding): comprehensive project context, postmortem log, chat-opener — **40 files, 16,183 lines** | Pure docs add, no local conflict |

### B) OVERLAPPING — both sides have these (origin is May 17, local is older)
| Origin commit | Files touched | Local has it? |
|---|---|---|
| `4b8370c` editorial-layout components (NarrativeThreads, SentimentTrajectory, NotableQuotes, BrewingHorizon, CompetitorMentions, EditorsNote) | 9 files, 893 lines | YES — local committed identical names in commit `2f36af6` (likely older versions) |
| `4795e7b` v3 prompt + unified LLM pool + byline & tweet enrichment | 15 files, 4584 lines | YES — local committed all of this in `ce569c4` + `5b1fbbc` |
| `a819fa7` Cerebras failover when Groq rate-limited | 1 file, 134 lines | YES — in our `groq_client.py` |
| `fbb1d26` + `708c4b1` + `7e19a72` Groq token-bucket + concurrency fixes | 3 files | YES — in our `groq_client.py` |
| `b1211ae` extraction batch + dispatch stagger | 1 file | Possibly |

### C) ORIGIN-ONLY (likely missing locally — review case by case)
- `efe05e2`, `e759d98`, `477ab71`, `9846924`, `d932bbf` — card-detail UI polish (5 commits)
- `1e4f983`, `d4840ad`, `75f0d9b`, `b450553` — user-cards fast-retry + entity_refs matching (4 commits)
- `c14d44c`, `1521db6`, `28e695e`, `87f261f`, `32dc988` — top-stories layout work (5 commits)
- May-09 fixes for SOCIAL feed exclusion + duplicate filter — niche

## What local has that origin doesn't (131 commits)

Today's 9 commits (`56e1ebd` through `5f7bbb8`) plus 122 prior local commits. Many of those 122 are duplicates of what origin built differently.

### Truly unique to local (your call to keep):
1. **All of TODAY's session** (commits `56e1ebd` → `5f7bbb8`):
   - observability/brief_*.py (4 new files)
   - Entity FK backfill via aliases (15,755 entities, +162K links)
   - claims_quotes ::text patch + entity resolver
   - run_corpus_pass v2→v3 stamp merge + canonical_url homepage guard
   - celery_app: newsroom imports + v3-weekly schedule
2. **Frontend brief-app** (separate from coverage editorial components)

## Conflicts predicted (per file)

| File | Conflict severity | Recommendation |
|---|---|---|
| `backend/nlp/groq_client.py` | **High** — both heavily modified | Keep origin (it's May 17 + more polished); re-apply your `_LOCAL_FAIL_COOLDOWN=0.0` patch on top |
| `backend/celery_app.py` | Medium | Keep origin's structure; re-apply newsroom imports + weekly v3 schedule |
| `backend/tasks/coverage/claims_quotes_task.py` | Medium | Keep origin; re-apply ::text casts + B2 English skip + entity alias resolver |
| `backend/tasks/substrate/run_corpus_pass.py` | Medium | Keep origin's v3 prompt; re-apply the extraction_version=3 stamp + canonical_url guard |
| `frontend/src/components/coverage/*` | High — both built same components | Inspect each — likely keep origin's May 17 version |
| `backend/main.py` | Low | Probably keep origin |
| `infrastructure/docker-compose.yml` | Low | Inspect 1 line each side |

## Recommended strategy: **rebase-the-deltas**

Instead of merging 131 commits onto origin (a horror story), do this:

### Step 1 — Make a safety net
```bash
git branch local-snapshot-2026-05-26  # preserves current local in case rollback needed
```

### Step 2 — Cherry-pick only TRULY UNIQUE work
The 9 today's-session commits + brief-app frontend + maybe 5-10 other genuinely-unique commits.

### Step 3 — Reset local branch to match origin
```bash
git reset --hard origin/fix/brief-prod-readiness
```

This wipes the 131 local commits and adopts origin's May 17 state. **DANGEROUS but clean.**

### Step 4 — Re-apply your unique work on top
```bash
git cherry-pick <today-1> <today-2> ... <today-9>
```

Plus today's session worked AGAINST stale code. The cherry-picks may have conflicts where origin's newer code differs. Resolve per-file using origin as the base.

### Step 5 — Test before pushing
Verify the rebuilt branch still has:
- Brief endpoints public
- Entity FK linking
- v3 architecture merge
- All today's wins

## Alternative: "merge with abandonment"

If steps 3-4 feel too aggressive, the safer fallback:

```bash
git merge --strategy-option=theirs origin/fix/brief-prod-readiness
```

This auto-resolves conflicts in origin's favor for any overlap. You keep your today's-session commits. But it creates a messy merge commit and the history becomes harder to read.

## Risk assessment
| Strategy | Risk | Time | Quality |
|---|---|---|---|
| Reset + cherry-pick (recommended) | Medium — must verify nothing lost | 2-3 hours | Clean history |
| Merge with `-X theirs` | Low — git resolves automatically | 30 min | Messy history |
| Force-push local | High — destroys origin's 74 commits including CVE patches | 5 min | DON'T DO THIS |

## Do tonight
**Nothing destructive.** Just:
```bash
git branch local-snapshot-2026-05-26   # preserve current state
```

Tomorrow with focused time: execute the chosen strategy.
