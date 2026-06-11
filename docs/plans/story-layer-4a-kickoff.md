# Kickoff — Story-layer read-path migration (STEP 4a)

**Paste this into a fresh backend/product session.** It is self-contained.
Owner profile: backend/FastAPI + a little frontend, comfortable with live `psql`
and feature-flagged rollouts. **This is not a map task** — ignore anything about
the Night Desk / deck.gl map.

---

## 0. Mission (one paragraph)
The Brief and OSINT "Stories" surfaces currently read the **stale** old engine
(`public.event_clusters` ~6.8K rows + `public.story_threads` ~7.4K) — unchanged
since ~May 22, so the product shows ~11-day-old "stories." Analytics/DB built a
fresh, validated, whole-corpus story layer in **`analytics.story_*`** (~34.6K
stories + enrichment). Your job: wire the routers (and the feed) to read the new
layer **behind a kill-switch**, **dark**, **read-path only**, fully reversible.
This is **4a (surfacing wiring)**. It is **NOT 4b** (live forward-mode / breaking
burst) — do not enable forward clustering.

## 1. ⚠ Repo/path correction (READ — the handoff doc is misleading on this)
- The source handoff lives in the **rig-news** repo:
  `C:\Users\Dell\Desktop\rig-news\docs\plans\product-readpath-handoff-2026-06-02.md`.
- **But `rig-news` is the Next.js frontend only — it has NO `backend/` and none of
  these routers.** All the backend code is in **`rig-surveillance`** (this repo).
  Do your router work here. Confirmed live this session:
  - `backend/routers/brief_router.py` ✓
  - `products/osint/backend/routers/stories.py` ✓
  - 31 files reference `event_clusters`/`story_threads`.
- If a "frontend feed" change is needed, decide whether the consumer is
  `rig-surveillance/frontend/` or the `rig-news` Next.js app — confirm which one
  renders the Brief/Stories feed before editing any UI.

## 2. Read first (in order)
1. The handoff doc (rig-news path above) — the contract, constraints, and gate.
2. This repo's root `CLAUDE.md` — worker topology; **rig-backend code is BAKED into
   the image, not bind-mounted**, so router edits need a rebuild/redeploy to take
   effect on Hetzner (this is why the kill-switch should be an **env var**, below).
3. Memory: `clustering scorer refit + story-layer build` (the story_* keeper was
   swapped live 2026-06-03; `story_*_old` kept ~1wk as rollback) and
   `emotion ≠ stance` (use `article_stances`, never `register_emotion`).

## 3. The exact swap-sites (verified live)
- **`backend/routers/brief_router.py:41-43`** — `get_stories(limit=5)`:
  *"Top N defining stories from event_clusters (T5 importance_score)."* Reads
  `event_clusters` directly. **Cleanest swap point** → §4 query.
- **`products/osint/backend/routers/stories.py:491-549`** — NOT a simple swap. It is
  **relevance-personalized first** (per-user stream; "a Telangana CM sees Telangana")
  and only falls back to the **`event_clusters` global importance ranking**
  (line ~548, `FROM event_clusters ec JOIN article_events ae …`) for signed-out /
  no-prefs requests. It already **deliberately avoids** `story_threads` ("WIP").
  → The new layer must slot into BOTH the **global fallback** AND, ideally, the
  **personalized path** (join `analytics.story_cluster_members` → article → user
  relevance). **This is the field-gap to raise with DB chat** (§7): the personalized
  path needs per-article→story mapping + relevance; confirm the contract carries it.

## 4. The surfacing SQL contract (CONFIRM COLUMNS LIVE before wiring)
House rule from the handoff: **don't trust column names verbatim — `\d
analytics.story_clusters` first.** Then:
```sql
SELECT c.*  -- + LEFT JOIN story_timeline/geo/stance/enrichment_status ON story_id
FROM analytics.story_clusters c
WHERE c.status = 'active'
  AND c.is_template_family = false                      -- NON-NEGOTIABLE: hides topic-blob fake-top-stories (§2b guard)
  AND ( c.independent_source_count >= 3                  -- real multi-source stories
        OR c.rescued_from_story_id IS NOT NULL )         -- + rescued buried stories (surface WITH enrichment, not naked)
ORDER BY c.importance_score DESC NULLS LAST, c.independent_source_count DESC;
```
- Verify `importance_score` is populated; if not, rank by `independent_source_count`
  alone (DB chat confirms).
- **Coverage honesty:** read `story_enrichment_status` so the UI distinguishes
  "no facts found" from "not yet processed." Empty enrichment ≠ unknown.

## 5. Kill-switch (build BEFORE flipping anything)
- A single flag both routers honor: `STORY_SOURCE = new | old`.
  - `new` → read `analytics.story_*` (§4). `old` → today's `event_clusters` /
    `story_threads` path, unchanged.
- **Make it an env var** (e.g. `STORY_SOURCE`, default `old`) read at request time,
  not a hardcoded constant — because backend code is baked into the image, an env
  flip via compose reverts the whole product with **zero rebuild**. Keep BOTH
  read-paths in the code during 4a.

## 6. Blob-alarm (must be live + TEST-FIRED before user-visible)
DB chat provides the detector; you/ops wire the page. Alert if
`COUNT(surfaced stories WHERE is_template_family) > 0` (must always be 0); ideally
also flag `surfaced AND entity_core_cov < 0.45 AND independent_source_count >= 25`.
**Test-fire once** (simulate suppression off → returns >0 → proves it pages), then
leave armed. A blob reaching users is the failure we're guarding against.

## 7. Hard constraints (the parachute — do NOT violate)
- **Do NOT drop / alter / stop writing `event_clusters` / `story_threads`** — they
  are the instant rollback for the first live week.
- **Do NOT enable forward-mode / live clustering** (that's 4b, a separate gate).
- **Nothing user-visible** until kill-switch wired + blob-alarm live AND test-fired.
  Wire it dark; flip only on explicit human go.

## 8. ⚠ COLLISION WARNING (coordinate before editing `brief_router.py`)
There are **6 active `.claude/worktrees/*` copies of `brief_router.py`** (and
`thread_router.py`) right now — a concurrent brief-rework session is in flight
(memory: *"active parallel session edits brief files; RBAC work must not touch
them"*). **Before you edit `brief_router.py`:** check whether that session owns it,
sync, and rebase onto its work — do not collide. The handoff stresses the same:
*"these are your files, we did NOT edit them, to avoid colliding."* If the
brief-rework session is still live, it may be the natural owner of the brief half.

## 9. DB access (Hetzner)
```
ssh -i ~/.ssh/rig_hetzner root@178.105.63.154
docker exec -i rig-postgres psql -U rig -d rig -tA   # pipe SQL via stdin; PowerShell→ssh mangles -c
```
`\d analytics.story_clusters`, `\d analytics.story_cluster_members`,
`\d analytics.story_enrichment_status` first. (Read-only `analytics_user` role also
exists for `analytics.*`.)

## 10. Suggested agent sequence
1. **planner** — sequence the dark-wire → test-fire → flip gate (order is the point).
2. **database-reviewer** — confirm the live `analytics.story_*` schema vs §3/§4;
   validate the surfacing query plan; confirm `importance_score` populated.
3. **Backend wiring** — env-var flag + both read-paths in both routers; reconcile
   the new layer with `stories.py`'s relevance-personalized path.
4. **tdd-guide** — tests proving `new` vs `old` switch, no `is_template_family`
   leaks, rescued subs present, enrichment joins clean.
5. **code-reviewer** (+ **security-reviewer** on the flag/alarm).

## 11. The 4a done-gate (what "done" means — no go-live before all four)
1. Both routers read `new` behind the flag; `old` still works on flip. 
2. Feed reads right off `story_*` + enrichment (no `is_template_family` leaks;
   rescued subs present; enrichment clean) — confirm in the product UI.
3. Blob-alarm live + **test-fired** (proven to page).
4. `event_clusters` / `story_threads` untouched (parachute intact).
**Then**, only on explicit go, flip user-visible. 4b is a later gate.

## 12. First step back to DB/analytics chat
Confirm the routers are yours to wire (or hand the brief half to the brief-rework
session), and **flag the personalization gap in §3**: `stories.py` needs a per-user
relevance path (article→story→relevance) that the global §4 query doesn't cover —
ask DB chat to extend the contract (e.g. confirm `story_cluster_members.article_id`
is the join to the user relevance stream) **before** you build, not after it breaks.
