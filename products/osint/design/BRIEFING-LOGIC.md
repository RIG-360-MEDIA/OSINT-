# THE BRIEFING — computation spec (how each component is generated)

Everything keys off the user's prefs (`primary_subject_id` = YOU, `watchlist` = rivals,
`topics`, `regions`) so it's generic. Window = last 24h on the replay clock unless noted.
Stance polarity map (POL): supportive/sympathetic/promotional/defensive/admiration/optimistic = +1;
critical/mocking/concerned/lament/skeptical = −1; neutral/analytical = 0.
**Caveat that touches everything:** `article_stances` has no `target` column → "toward YOU"
is a *salience proxy* (you're prominent in the article AND a stance is present). "now" = replay
window, not live. No social tables → we read the press, not the public.

---

## ▣ THE BOTTOM LINE (30-sec) — a SELECT of the top signal in each lane + thin LLM phrasing
Four lines, each the #1 of a computed ranking, then one-line phrasing (template, LLM only to smooth):
- **WHERE YOU STAND** = classify(net polarity sign, trajectory slope, dominant split).
  - net = Σ(POL × intensity) over salient stances on YOU → sign ⇒ winning/holding/losing.
  - slope = OLS over `entity_mention_daily` favourability → rising/slipping.
  - "in Telugu" = `cross_language_gap` (favourability by `articles.language_iso`).
  - Fields: `article_stances`(stance,intensity,actor_entity_id) ⋈ `articles`(language_iso,collected_at).
- **KNOW THIS** = top NEW development = argmax(velocity × recency × |POL|) over event clusters.
  - Fields: `entity_mention_hourly` (velocity/accel), `article_events`/`event_clusters`, `register_is_breaking`.
- **THE ATTACK** = #1 threat = argmax(reach × negativity × velocity × tier).
  - reach/tier = `sources.source_tier`; negativity = NEG stance × intensity; the line = top `article_quotes` of a rival; origin = `attack_origination`.
- **YOUR MOVE** = one-line condensation of `counter_narrative` (LLM, faithfulness-gated) for that threat.
- **Form:** deterministic ranking → values are real; LLM only compresses to one imperative line.

## WHAT HAPPENED — pure retrieval, NO LLM (the record must be unimpeachable)
- Logic: top developments in 24h, deduped, each = date · headline · source.
- Compute: `relevance.score_relevant(prefs, window=24h)` over `articles` ⋈ `sources`, ranked by
  recency + salience; dedup by `cluster_id` / duplicate flag; date from `article_events.effective_event_date` or `collected_at`.
- Fields: `articles`(title,collected_at,source_id), `sources`(name), `article_events`(event_date,event_type).
- Form: deterministic. No synthesis ⇒ nothing to hallucinate.

## WHAT IT MEANS — LLM assessment over STRUCTURED facts (textual.situation_room family)
- Logic: connect the dots into the pattern. The model never sees raw articles — only computed facts.
- Facts handed in: the What-Happened list + top hostile stances (actor·stance·outlet) +
  `attack_origination` coordination signal (same line across outlets within hours) + `cross_language_gap` + `share_of_voice`.
- Compute: `llm_synth.synthesize_paragraph(system="state the pattern", facts=structured, source_check=facts)`
  → numeric faithfulness gate (token-overlap vs facts) → fail ⇒ template fallback. English-pinned.

## WHY IT MATTERS — LLM, grounded in what you OWN
- Logic: map the threat onto `issue_ownership` (topics you own/cede) + standing → the stake.
- Facts: owned issues (+scores), the attacked topic, `weighted_pressure` trend.
- Form: LLM with those facts only; faithfulness-gated. "You own agriculture +23; the attack is on agriculture ⇒ …"

## WHAT'S NEXT — momentum extrapolation + explicit confidence (NOT a calendar)
- Logic: rising thread = top accelerating hostile cluster; its spread state = has it crossed
  language / tier / format? The **trigger** = the next boundary it could cross.
- Compute: `entity_mention_hourly` (accel) + `language_iso` (English yet?) + `source_tier` (Tier-1 yet?) + `source_type` (TV approx).
- Confidence = f(n, accel consistency). **Honest:** forward-event data is thin (~9 rows) ⇒ this is
  extrapolation from momentum, labelled as inference, never a scheduled fact.

## HOW TO PLAY IT — LLM, the computed GAPS turned into directives
- Logic: each directive ties to one gap → "lead in Telugu" (`cross_language_gap`),
  "contest finance" (`dog_didnt_bark` silence), "ignore op-eds" (low spread from Is-It-Real), pace from `counter_speed`.
- Form: LLM composes 3–4 imperatives from the gap facts; faithfulness-gated to those gaps.

## THE OTHER SIDE — computed fragility, then phrased (the integrity guardrail)
- Logic: argue against the brief. Compute its weak points, don't invent them:
  - **outlet concentration** = top-outlet share of the NEG stances (Herfindahl). High ⇒ "strip Namasthe out, it's even."
  - **sample thinness** = low n on the key claim.
  - **counter-evidence** = the strongest POS signals the brief downweighted.
  - **tripwire** = the What's-Next boundary, inverted (what would flip the call).
- Fields: `article_stances` grouped by `source_id`; n counts; POS stances.
- Form: deterministic fragility numbers → LLM phrases the honest dissent. This is Aryan's
  editorial-integrity floor — the section that keeps the principal out of a bubble.

---

## Cross-cutting
- **Provenance:** every line stores the article IDs / counts behind it → hover-to-verify, like the Analytics drawer.
- **Faithfulness:** all LLM lines pass the numeric gate in `llm_synth`; failures fall back to templates, never ship raw.
- **Reuse:** What's-Next/Attack/Move/Play-It reassemble already-built+validated metrics (posture.py) + textual.py.
