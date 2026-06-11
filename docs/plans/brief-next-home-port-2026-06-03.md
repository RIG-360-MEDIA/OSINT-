# Brief-next <- Night-desk **Home** — Port Plan (2026-06-03)

Port the night-desk (`:5180`) **Home** design into the brief-next production app
(Next.js, Supabase auth, `:8002` backend), wired to real data, feature-by-feature
with a per-feature logic check. **Home is the richest page** (strategic written brief +
THE SIX), not a restyle.

- **Design source:** `products/osint/design/night-desk/src/pages/Home.jsx` + `src/data/home.js`
- **Target:** brief-next new `Home` surface (keep its auth/onboarding/admin shell; app-router route)
- **Backend:** `products/osint/backend` — `textual.py` (15 features) + `posture.py` (15 metrics) +
  `stories` (new story layer, flag-wired) + `entities`. All **generic** (principal =
  `primary_subject_id`, opposition = watchlist), **personalized** (need prefs -> behind auth),
  **faithfulness-gated** (llm_synth, English-pinned), and on the **`now_sim()` replay clock** —
  matching night-desk's masthead + the SIX "print" provenance lines.

## Coverage verdict
textual + posture cover **~80% of Home directly**; 3 of THE SIX are near-exact. Remaining gaps
are **small additive surfaces** (a few LLM prompts + 1 new posture metric) — every number is
already derivable from `article_stances` / `article_entity_mentions` / `article_quotes` /
`topic_category` / `language_iso`, which these modules already query. **No fundamental data gap.**

## Section-by-section mapping
| Home section | element | backend source | status |
|---|---|---|---|
| **Masthead** | name/role/party/window/confidence/as-of | prefs (`primary_subject_meta`) + `posture.confidence` + `now_sim()` | exists |
| **THE BRIEFING** | Where You Stand | `textual.executive_bluf` + `posture.stance_trajectory` + `issue_ownership` | compose |
| | Know This | `textual.situation_room` / `crisis_brief` | ok |
| | The Attack | `textual.who_attacking` + `posture.attack_origination` | ok |
| | Your Move (action) | `textual.counter_narrative` | ok |
| | What Happened (dated+sourced) | `textual.source_trail` / `since_last_looked` + `posture.attack_origination` | ok |
| | What It Means | `textual.this_week` / `framing_comparison` | ok |
| | Why It Matters | `textual.situation_room` (risk) + `posture.narrative_half_life` | compose |
| | What's Next (+confidence) | `posture.narrative_half_life` + `stance_trajectory` + confidence | ok |
| | How to Play It | `textual.counter_narrative` + `posture.friend_foe_fence` | compose |
| | **The Other Side** (steelman) | — | NEW small LLM surface (the self-critical "case you're wrong") |
| **TOP STORIES FOR YOU** | story cards (tone/source/age/img) | `/api/brief/stories` (new layer, flag) + relevance | ok |
| | **"For you"** per-story read | — | NEW small per-story grounded synthesis |
| **PEOPLE TO WATCH** | score / verdict / trend | `posture.target_heat` + `outlet_favourability` + `stance_trajectory` | partial |
| | per-entity hostility score (e.g. KCR -64) | — | NEW metric `rival_posture` (stance where actor=watchlist-entity toward principal) |
| | summary / Why / Watch | `textual.instant_oppo_dossier` -> **extend to loop watchlist x5** | extend |
| **THE SIX · 1 Hard Truth** | blunt composite | compose `posture` (cross_language_gap+quote_bias+issue_ownership) + 1 LLM | NEW compose |
| **· 2 Real or Noise?** | HOLD/RESPOND triage | `textual.crisis_brief` + `posture.narrative_half_life` + `cross_language_gap` | compose |
| **· 3 Are You Being Heard?** | quote-share (2.4x, V6 7:2) | `posture.quote_selection_bias` | EXACT |
| **· 4 The Coverage Split** | Telugu -22 / English -1 + gap | `posture.cross_language_gap` | EXACT |
| **· 5 Who To Call** | work/avoid outlets (+reporter) | `posture.friend_foe_fence` + `outlet_favourability` | ok (reporter byline = extend — verify byline data) |
| **· 6 Ready For You** | Statement / Counter-line / Translated | `textual.counter_narrative` + `quote_translation` | EXACT |

*(home.js also feeds: `BREAKING`->Ticker, `BLUF`->`textual.executive_bluf`, `NARRATIVE_DNA`->`textual.narrative_dna`.)*

## Gaps to build (all small, additive — follow existing module patterns)
1. **`posture.rival_posture`** — per-watchlist-entity stance polarity *as actor* in principal-context
   articles (-> People to Watch scores like KCR -64). New metric, same SQL pattern as the others.
2. **`textual.peers_dossier`** — loop `instant_oppo_dossier` logic over the full watchlist (-> the 5
   PEOPLE TO WATCH summary/Why/Watch), not just the top rival.
3. **`textual.other_side`** — steelman LLM surface ("the case you're wrong; strip Namasthe and the
   week is even"). One grounded call, faithfulness-gated.
4. **`textual.story_for_you`** — per-story 1-line strategic "why this matters to *you*" (grounded on
   that story's facts). Small LLM, or fold into the stories enrichment.
5. **`textual.hard_truth`** — blunt composite read over the posture metrics + 1 LLM call.
6. **Real-or-Noise verdict** — HOLD/RESPOND tag derived from half-life + language-gap + tier (cheap
   classifier; LLM optional for the prose).
7. *(optional)* **reporter byline** in Who To Call — needs journalist-granularity; verify `articles`
   carries author/byline before promising it.

## Build sequence (each step ends with a live logic check)
1. **Backend small-adds** (one PR): items 1-6 above, mirroring the existing generic + `n`/confidence +
   faithfulness patterns. **Logic-check each against live `now_sim()` data for the seeded persona**
   (numbers must trace to source rows — the project's no-fabrication rule).
2. **Wire posture+textual into brief-next** `lib/api.js` (currently UNUSED endpoints): add
   `useLivePosture()` + `useLiveTextual()` hooks (React Query, behind auth).
3. **Frontend Home** in brief-next: new app-router page porting night-desk's layout (masthead ->
   THE BRIEFING grid -> TOP STORIES -> PEOPLE TO WATCH -> THE SIX) using night-desk's CSS tokens.
   Build **section-by-section**, each wired + verified against the live endpoint before the next.
4. **Provenance:** render the SIX "print" lines from each surface's `method` + `confidence`/`n`
   (e.g. "reads the press, not the public" = compute-method + sample size), so faithfulness is visible.

## Workstream: wire onboarding (close the saved-but-ignored gap)
**Verified live 2026-06-03 (4 onboarded users):** of the 11 onboarding answers, only **3** reach the
brief engines (subject, subject_meta, watchlist). The rest are collected and discarded. Fixes:

**A. ~~Add a `purpose` column~~ — NOT needed (corrected 2026-06-03).** `purpose` is NOT lost: the wizard
page folds it INTO `personality` (`personality: {...prefs.personality, ...prefs.purpose}`), so
`use_cases` + `llm_tone` are already saved in the `personality` column — confirmed live in all 4 users'
rows. Loading `personality` (B) surfaces purpose. *Optional later cleanup:* un-fold `purpose` into its
own column for cleaner modelling — not required for function.

**B. Load the saved-but-unread fields — ✅ DONE (2026-06-03).** `load_prefs` (`brief_prefs.py`) now
SELECTs + returns `languages, stance, personality, events, sources, delivery` (purpose rides inside
`personality`) on top of subject/watchlist/regions/topics. Compiles clean; **verified live** — all 4
users' full prefs return (e.g. langs `["en","te","hi"]`; stance `balanced`+`echo_floor`; 8 event types;
personality `deep/formal` + `llm_tone:analytical` + `use_cases:[monitor_self,competitive,policy]`).
⚠ **Activates on next osint-backend rebuild** (container code is baked, not bind-mounted) — the SQL is
proven; the deployed endpoint still returns the old 5 fields until redeploy.

**C. Make the engines honor each (field -> effect):**
| field | how it should shape the brief |
|---|---|
| `languages` | `cross_language_gap` + coverage prioritise/filter to the chosen languages (Coverage Split centres on them) |
| `stance.toward` + `echo_floor` | framing lens + **enforce >=30% non-aligned coverage** when echo_floor is on |
| `personality` (+ `purpose.llm_tone`) | the LLM **voice / depth / density** of THE BRIEFING + THE SIX (replace today's fixed tone) |
| `topics` (prioritise / mute) | weight/filter `issue_ownership`, TOP STORIES, `dog_didnt_bark` |
| `regions` (states / countries) | filter/weight coverage to the user's geography |
| `events` (types) | prominent placement now + alerts later for those event types |
| `sources` | source trust / filter once populated |
| `delivery` | **out of scope for Home** — mailer's job (digest / timezone) |

**D. Acceptance (the proof it worked):** two users with the **same subject** but different
languages/topics/regions/stance must get **different briefs**. Today they get identical — that is the bug.

**Open check:** `regions`/`topics` are loaded but unused by textual/posture; the stories/relevance path
*may* already honor them — confirm by reading `relevance.py` before duplicating that logic.

## Constraints / notes
- **Auth:** textual/posture return `{personalized:false}` without prefs -> Home lives behind brief-next's
  existing auth+onboarding gate. Signed-out gets a graceful empty/limited state.
- **Genericity:** textual/posture are entity-agnostic -> Home works for *any* persona with a prefs row.
- **New data:** TOP STORIES uses the new `analytics.story_*` layer via the (flag-wired) `stories`
  endpoint; What Happened can draw on `story_timeline`. Re-verify the stories **surfacing gate** is
  current before relying on it (it has evolved — confirm the live rule when wiring).
- **Don't touch** `backend/routers/brief_router.py` (the *main* backend's brief router — different
  service, mid-rework). This port targets `products/osint/backend` only.

## Open decisions
- New **route** (`/home`, or make `/brief` = Home) vs. restyle the existing `/brief`?
- Do the 6 backend small-adds **first** (so the frontend wires against real endpoints), or scaffold the
  frontend against mock + backfill? (Recommend backend-first for the logic checks.)
