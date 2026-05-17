# Onboarding Requirements — living document

> **Purpose.** As we build or change features, each one needs *something*
> from the user profile to work well — geography, role, languages, topic
> weights, watched entities, etc. We are NOT redesigning onboarding now.
> We are accumulating the list of things onboarding will eventually have
> to capture, organised by the feature that needs them. When we sit down
> to redesign the onboarding wizard, this document is the spec.

> **Working rule.** Every time we build, change, or audit a feature, add
> or update its entry here. If a feature needs a field the profile
> doesn't have today, write it under "needs" — don't silently add it to
> the schema. The wizard redesign will batch-handle the schema changes.

---

## How to use this doc

When you finish (or revisit) a feature:

1. Open this file.
2. Find the feature's section (or add a new one).
3. Update **Status** and **Last updated**.
4. Under **Onboarding data needed**, list every profile field this feature
   reads from or assumes about the user.
5. Mark each field as one of:
   - ✅ already captured by current onboarding
   - 🟡 inferred / hardcoded today, should be explicit
   - 🔴 missing — user has no way to express this yet
6. Add to **Open questions** anything ambiguous.

When we redesign onboarding, the wizard will be derived from the union
of all 🟡 + 🔴 fields across all features.

---

## Profile schema — today vs target

### Today (`user_profiles`)

```
user_id              uuid
raw_description      text         -- free-form "tell us about yourself"
role_type            text         -- single string, no enum
organisation         text
geo_primary          text         -- single string, ambiguous granularity
geo_secondary        text[]
signal_priorities    jsonb        -- {TOPIC: weight 0-9}  ← already structured
language_preferences text[]
brief_time           time
brief_timezone       text
role_context         text
```

Limitations: single-string geo, role is free text, no structured
country/region/city, no explicit watched-entities list, no
cross-border interest regions, junk-language patterns unconfigured.

### Target (after wizard redesign)

```
home_city          text                    -- "London"
home_region        text                    -- "Greater London"
home_country       text                    -- ISO-3166 'GB'
interest_regions   jsonb                   -- [{country,region,city,weight}, ...]
role_archetype     text                    -- enum: government | pr_agency |
                                           --       corporate_comms | political_campaign |
                                           --       ngo_advocacy | journalist |
                                           --       investor_relations | consultancy | other
organisation       text
signal_priorities  jsonb                   -- {TOPIC: weight}
watched_entities   jsonb                   -- [{entity_id, name, weight}, ...]
languages          text[]                  -- ISO-639-1
brief_time         time
brief_timezone     text
```

---

## Cross-cutting fields (used by many features)

These are the fields that show up in almost every feature. Keep them
in mind when reviewing each entry below.

| Field | Purpose | Status |
|---|---|---|
| `home_city` | Default for "regional" geo classification | 🔴 missing |
| `home_region` | State/province/equivalent | 🔴 missing |
| `home_country` | ISO country code; powers cross-border vs national | 🔴 missing |
| `interest_regions[]` | Other regions the user actively tracks | 🔴 missing |
| `role_archetype` | Drives WHY-FOR-USER framing across LLM calls | 🟡 inferred from `role_type` text |
| `signal_priorities` | Topic weights 0-9 | ✅ exists |
| `watched_entities[]` | Explicit watchlist | 🔴 missing |
| `languages[]` | ISO-639-1 codes for ingestion + junk-filter | 🟡 partial via `language_preferences` |

---

## Per-feature requirements

### Breaking News (`/api/coverage/breaking`)

**Status:** shipped (2026-05-10)
**Last updated:** 2026-05-10
**Code refs:** `backend/tasks/coverage/pick_breaking_per_user_task.py`,
`backend/routers/coverage_articles_router.py` (`/breaking`),
`frontend/src/components/coverage/BreakingBand.tsx`,
migrations `060`, `061`, `062`.

**What the feature does**
Every 60 minutes, for each user: pull last-hour Tier-1+2 articles
matching the user's relevance, dedup near-identicals, apply
tier-1-beats-tier-2, hand to Groq with locality-first prompt → output
one catchy English headline + one why-for-user line tailored to the
user's geography and role.

**Onboarding data it needs**

| Field | Why | Status |
|---|---|---|
| `home_city` | Score article geo at city granularity (`_geo_score = 4`) | 🔴 missing — falls back to substring match on `geo_primary` |
| `home_region` | Score article geo at region granularity (`= 3`) | 🔴 missing |
| `home_country` | Score same-country articles (`= 2`); replaces hardcoded India fallback | 🔴 missing |
| `interest_regions[]` | Cross-border priorities (e.g. UK PR firm tracking EU + US) | 🔴 missing |
| `role_archetype` | WHY-FOR-USER framing in Groq prompt — PR vs govt vs investor produce different one-liners | 🟡 hardcoded `role_type` string is passed in today |
| `signal_priorities` | Topic weights influence Groq's pick reasoning | ✅ used today |
| `languages[]` | Drives which junk-title patterns to apply (currently English+Hindi+Telugu hardcoded) | 🟡 patterns hardcoded in code |

**Workarounds in place today**
- `_geo_score` has hardcoded India neighbours (`{telangana, andhra pradesh, secunderabad, …}`) — needs to become data-driven from `interest_regions[]`.
- `_JUNK_TITLE_PATTERNS` includes `\brashifal\b`, `\baaj ka\b` — Hindi-specific. Needs per-language config table.
- Groq prompt receives `role_type` as a free-text string — `role_archetype` enum will give cleaner reasoning surface.

**Open questions**
- How to express "I cover all of EU" without listing every country? (interest_regions could support `region: "EU"`?)
- For multi-region users (e.g. consultancy with offices in 3 countries), is there a single `home` or do they have multiple homes?

---

### Articles Feed (`/api/coverage/feed`)

**Status:** shipped (pre-existing)
**Last updated:** 2026-05-10 (audit only, no changes)
**Code refs:** `backend/routers/coverage_router.py:feed`,
`user_article_relevance` table.

**What the feature does**
Per-user paginated article list, ordered by `score_final` from
`user_article_relevance`. The relevance scorer runs on every new
article, scoring it against this user's profile.

**Onboarding data it needs**

| Field | Why | Status |
|---|---|---|
| `home_city`, `home_region`, `home_country` | Geo multiplier in relevance scoring | 🔴 missing — uses `geo_primary` string |
| `interest_regions[]` | Cross-border bonuses | 🔴 missing |
| `signal_priorities` | Topic weights determine `score_stage1` | ✅ used today |
| `watched_entities[]` | Direct entity match boosts | 🔴 missing — relies on text-match against `raw_description` |

**Workarounds in place today**
- Geo scoring is single-string substring match.
- Entity matches are derived heuristically from `raw_description`.

---

### Top 5 Stories (`/api/coverage/top-stories`)

**Status:** shipped (pre-existing)
**Last updated:** 2026-05-10 (audit only)
**Code refs:** `backend/tasks/coverage/top_stories_task.py`.

**Onboarding data it needs**

| Field | Why | Status |
|---|---|---|
| `home_country` + `interest_regions[]` | Geo filter for which articles enter the candidate pool | 🟡 implicit via per-user relevance |
| `role_archetype` | Drives "why-this-matters" rationale tone | 🟡 free text today |
| `signal_priorities` | Topic ranking | ✅ used |
| `watched_entities[]` | Boost stories about watched entities | 🔴 missing |

---

### Custom Cards (`/api/coverage/cards`)

**Status:** shipped (pre-existing)
**Last updated:** 2026-05-10 (audit only)
**Code refs:** `backend/tasks/coverage/user_cards_task.py`,
`backend/tasks/coverage/spawn_sub_cards_task.py`.

**Onboarding data it needs**

| Field | Why | Status |
|---|---|---|
| `watched_entities[]` | Auto-suggest cards from initial watchlist | 🔴 missing |
| `home_country` + `interest_regions[]` | Default geo filter on auto-spawned cards | 🟡 implicit |
| `role_archetype` | Sub-card angle generation (adversarial / aligned / etc.) | 🟡 free text today |
| `languages[]` | Which language articles feed each card | 🟡 partial |

**Open questions**
- Should onboarding seed the user with 1-2 default cards based on their watchlist + region, or always start them with an empty board?

---

### Right-Rail Quotes (`/api/coverage/quotes`)

**Status:** shipped (pre-existing)
**Code refs:** `backend/tasks/coverage/claims_quotes_task.py`.

**Onboarding data it needs**

| Field | Why | Status |
|---|---|---|
| `watched_entities[]` | Filter quotes to ones mentioning watched entities | 🔴 missing — currently all quotes |
| `languages[]` | Translation pipeline targets the user's preferred output language | 🟡 partial |

---

### Newsroom — TV / YouTube (`/clips`)

**Status:** in progress (Phase 7+)
**Code refs:** `backend/routers/newsroom_router.py`, `frontend/src/app/clips/`.

**Onboarding data it needs**

| Field | Why | Status |
|---|---|---|
| `home_country` + `languages[]` | Which channels to ingest for this user | 🔴 missing — Telugu/Telangana hardcoded |
| `watched_entities[]` | ECHO mode "what they're saying about you" | 🔴 missing |
| `interest_regions[]` | DOSSIER mode regional context | 🔴 missing |
| `role_archetype` | BRIEF mode framing | 🟡 free text |

**Open questions**
- Should onboarding ask which TV channels / YouTube creators the user wants ingested, or auto-suggest from country + language?

---

### Brief (`/brief`)

**Status:** shipped (pre-existing)
**Code refs:** `backend/tasks/generate_brief_for_user.py`.

**Onboarding data it needs**

| Field | Why | Status |
|---|---|---|
| `brief_time`, `brief_timezone` | When to generate / deliver | ✅ exists |
| `role_archetype` | Brief framing tone | 🟡 free text today |
| `home_country` + `interest_regions[]` | Geographic scope of stories included | 🟡 implicit |
| `languages[]` | Output language preference | 🟡 partial |

---

### Signals — Reddit / Telegram (`/signals`)

**Status:** to be redesigned (THE READOUT / THE PULSE concept)
**Code refs:** TBD. See `docs/readout/IMPLEMENTATION_PROMPT.md`.

**Onboarding data it needs**

| Field | Why | Status |
|---|---|---|
| `watched_entities[]` | Mirror mode "what they're saying about you" | 🔴 missing |
| `home_country` + `interest_regions[]` | Geographic relevance of social posts | 🔴 missing |
| `role_archetype` | Recommended-action framing (e.g. "issue statement" makes sense for PR/govt, not for a journalist) | 🔴 missing |
| `signal_priorities` | Trending-topics ranking | ✅ used |
| `languages[]` | Which subreddits / Telegram channels to ingest per user | 🟡 partial |

---

### Articles RAG Ask Bar (planned)

**Status:** planned
**Onboarding data it needs**

| Field | Why | Status |
|---|---|---|
| `watched_entities[]` | Default scope for "ask anything" queries | 🔴 missing |
| `interest_regions[]` | Default geo filter on RAG retrieval | 🔴 missing |
| `languages[]` | Output language of the answer | 🟡 partial |
| `role_archetype` | Tone of answer ("for a PR audience" vs "for a policy audience") | 🔴 missing |

---

## Backlog — fields with no current owner

These keep coming up but no specific feature has claimed them yet.

- **Sensitivity / NSFW filter level** — different users tolerate different signal/noise.
- **Notification thresholds per topic** — how loud must a story be to push a notification?
- **Working hours / quiet hours** — shape the timing of pushes.
- **Stakeholder list separate from watched_entities** — who would the user *brief* (their boss / clients), distinct from who they *track*?
- **Confidentiality level** — internal user vs client-facing user.

When a feature lands that needs one of these, move it to that feature's section.

---

## How the wizard will be derived

When we sit down to design onboarding properly:

1. Take the union of all 🔴 + 🟡 fields above.
2. Group by capture-time burden (cheap to ask vs expensive).
3. Sequence the steps so each one delivers a working feature when complete (e.g. after Step 3 the user already has a usable feed; after Step 5 they have cards seeded).
4. Provide a "skip + use defaults" path so onboarding is never blocking.
5. Make every field reversible from settings.

**Until then, this document is the spec.** Don't add fields to the schema
silently. Don't hardcode region/role/language assumptions in feature code.
Both flow through here first.
