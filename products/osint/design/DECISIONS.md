# NIGHT DESK — consolidated decisions + feature backlog

## Locked architecture
- **Persona model:** primary subject (org or person) + watchlist. For this build: **Government of Telangana** (Revanth Reddy = CM/face).
- **Entity classification = the core of the directional engine:**
  - **Existing accounts:** their entities are **separated server-side** (against / for / neutral) from their own data — auto-seeded/inferred in the backend.
  - **New users:** we **present the entity list upfront in onboarding** and they **choose** their subject + tag their watchlist (against / for / neutral). ← remember this.
- **Voice:** sharp desk-officer; numbers live inside sentences; honest small-print caveats; LLM never auto-sends.
- **Theme:** dark default + **light toggle** (built, token-based, persisted).

## The engines (shared foundations)
1. **Directional-valence engine (VERIFIED):** classify watchlist against/for/neutral → an *attack* = an against-entity expressing a critical stance while the subject is salient. High precision, ~49% recall (actor resolution), direction inferred from co-salience (no target column). Fixes "negative toward you," powers most metrics.
2. **Embedding story-grouping (98.5% coverage):** cluster articles by LaBSE similarity + shared entities + title overlap → "stories," coordination, cross-lingual merge (DB clusters are empty).
3. **Faithfulness-gated LLM** for all prose; **relevance core** (`score_relevant`, freshness-decay + salience) for all personalization/ranking.

## Pages (IA)
Home (BUILT) · War Room (reworking) · Analytics · Dossier (+Press CRM) · Map · Dispatch.

### Home — BUILT (textual report)
The Briefing (Bottom Line + What Happened / What It Means / Why It Matters / What's Next / How to Play It / The Other Side) · Top Stories For You (image cards + "for you") · People to Watch (entities, explainable sentiment) · The Six (Hard Truth, Real or Noise, Are You Being Heard, Coverage Split, Who To Call, Ready For You).

### War Room — locked components
- **#1 Critical Negative Stories** (DIRECTIONAL — proper) · **#4 Opposition Quote Dossier** (gold, verified) · **#5 Escalation Tracker** (merge name-variants) · **#7 Counter-Attack Targets** (directional).
- Honest versions only: #2 Crisis Watch (mark the time-window as inferred), #6 Pre-Drafted (English solid, Telugu flagged), #3 → contested/corroborated (not true/false).

### Directional metrics to wire through Analytics/Dossier/Home
Auto-Alignment Map · Realignment Alerts · Net Standing/Momentum · Directional Share of Voice · Issue Battlefield · Press Alignment (CRM) · Cross-Language Gap · Coalition/Bloc detector · Attacker-Influence ranking · Ally/Surrogate tracker.

## NEW feature backlog — by analytical lens (our data is vast; each lens unlocks more)
**Embedding / semantic (98.5%)**
- Recurring-Attack / Déjà-Vu detector — "they've used this exact line before; here's how it played out."
- Quote-Propagation tracker — watch a specific line travel across outlets/languages.
- Narrative-DNA via embeddings — discover the recurring frames (the dead field, rebuilt).
- Analogue finder — "last time coverage looked like this, X happened."

**Claim / fact (39%)**
- Promise Tracker — "X promised Y" → kept / broken per coverage. (oppo + defense gold)
- Accusation Ledger — specific accusations where you're the object, tagged answered/unanswered.
- Contradiction audit (#3 reframed) — contested vs corroborated across sources.

**Source / outlet (tier 99%)**
- Tier-Crossing tracker — the moment a story jumps Tier-2 → Tier-1 → national (the real "blowing up" trigger).
- Echo-Chamber / Blindspot audit — stories only one side's outlets carry.
- Origination vs amplification — who breaks vs who echoes.

**Temporal (daily series)**
- Narrative half-life / stickiness · attack-rhythm (when attacks come) · counter-speed.

**Geographic (region 73.6%)**
- Constituency Heat — support/opposition by district · where an attack is landing.

**Network / relationship**
- Co-Mention Power Graph — ally/rival map, who's rising/isolated · Bloc & bridge detection.

**Relevance-driven**
- Anomaly Radar — "abnormal vs your 30-day normal" · the overload-killer smart feed.
