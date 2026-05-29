# Onboarding Spec — what we collect from a user, and what each field powers

Confirmed direction (2026-05-29):
- Invite-only access via admin-issued links (no public signup form)
- Auth: email + password via Supabase
- Org concept from day 1 (PR firms have multiple users sharing prefs)
- Role determines starter template (only `govt` available initially)
- Onboarding must be completed in one sitting (no skip / partial save)
- No hard limits on selections
- No demo mode for prospects (sales-led demos done manually)

Goal: every field below directly drives one or more visible sections of the brief page. Anything that doesn't is removed.

---

## Step 0 — Invite acceptance (pre-onboarding)

Captured from the invite link's signed JWT, not asked again:
- Email (verified by clicking the link)
- Org name + org_id
- Role (`govt` / `pr` / `journalist` / `academic` / `corporate`) — chosen by admin when issuing the invite
- Invite expiry timestamp

User sets:
- Password (with strength check)
- Full name
- Designation / job title (free text — "Senior Analyst, Telangana CMO")

---

## Step 1 — Purpose + Persona

| Field | Type | Powers |
|---|---|---|
| Primary purpose | dropdown | LLM brief tone (formal / tactical / academic), template selection |
| Decision-making rhythm | radio (daily / weekly / per-event) | Edition cadence default, alert threshold |
| Reporting upward to | free text | "SEND REPORT" button destination, header style |

**Currently available:** `govt` template only. Others greyed out + "Coming soon" badge.

---

## Step 2 — Primary Subject

The single most important entity/figure the brief is FOR. Drives the entire CM / Counter-Messaging panel set (Section 4 — CmDriving, CmPerspective, CmOppPressure, CmVoicesGrid, OutletBiasSnapshot).

| Field | Type |
|---|---|
| Primary subject entity | typeahead from `entity_dictionary` (1 required) |
| Subject's role / context | auto-filled from entity ("CM, Telangana, INC"), user-editable |
| Subject's relationship to user | radio: my principal / my client / my opposition / my research subject |

---

## Step 3 — Watchlist

Drives Section 5 (Watched Entities cards) and feeds into Section 6 (Climbing Stories filter) and Section 9 (Network Panel co-mentions).

| Field | Type |
|---|---|
| Allies / friendly figures | typeahead multi-select |
| Opposition / rivals | typeahead multi-select |
| Bureaucrats & advisors | typeahead multi-select |
| Civil-society voices | typeahead multi-select |
| Auto-add adjacents? | toggle (default ON) — suggest co-mentioned entities for review |

No hard cap. Visual layout adapts: 4-8 entities = card grid, 9-20 = compact list, 20+ = paginated.

---

## Step 4 — Geographic Scope

Drives Section 9 Mini-India heatmap, location-tagged stories filter, source country filter (`articles.source_country`), Horizon calendar events.

| Field | Type |
|---|---|
| Primary region | radio (single state / multi-state / national / international) |
| States of direct interest | multi-select (TG / AP / etc.) |
| Districts within those states | typeahead (using migration 074 location_scope) |
| Bordering / adjacent regions to monitor | multi-select |
| International countries to track | multi-select ISO codes |

---

## Step 5 — Topics

Drives Section 7 Blindspot Analysis (what topics user expects to see), Section 10 Recommended Reading filter, Section 2 Stories ranking weight, Section 6 Climbing filter.

| Field | Type |
|---|---|
| Core topics (always include) | chip multi-select: Politics, Governance, Defense, Economy, Agriculture, Education, Health, Infrastructure, Energy, Justice & Courts, Civil Society, Foreign Affairs, Culture, Sports |
| Sub-topics within Politics | chip: Elections, Coalitions, Parliament, Policy, Legislation, Scandals, Speeches, Polls |
| Sub-topics within Economy | chip: Budget, Fiscal, Markets, Industries, Jobs, Inflation, Trade |
| Topics to deprioritize | chip multi-select (negative filter) |
| Free-form interest tags | text input, comma-separated |

---

## Step 6 — Languages

Drives Section 1 KPI Languages tile + sub-line, Section 7 Telugu-vs-English Blindspot split, lens-card language tags, Section 9 Source Country breakdown.

| Field | Type |
|---|---|
| Languages I read | checkbox multi: EN / HI / TE / TA / KN / ML / MR / BN / GU / PA / UR + Other |
| Primary language | radio (one of above) — affects default sort + UI labels |
| Show non-read languages? | toggle: hide / show with translation / show as-is |

---

## Step 7 — Sources & Outlets

Drives Section 2 Lens cards (per-outlet quote per story), Section 8 Coverage Matrix, Section 9 Source Integrity rail, Recommended Reading filter.

| Field | Type |
|---|---|
| Tier-1 outlets I trust most | typeahead (The Hindu, Indian Express, Eenadu, etc.) |
| Outlets I want included | multi-select |
| Outlets to exclude entirely | multi-select (negative filter) |
| Vernacular emphasis | slider 0-100% (% of brief from non-English sources) |
| Op-eds vs news reports | slider: pure-news / mixed / opinion-heavy |
| Minimum article length | radio (any / 300+ / 800+ words) |

---

## Step 8 — Stance & Tone

Drives Section 2 Stance dots + coverage breakdown, Section 4 CM panels framing, Section 3 Voices Overnight selection.

| Field | Type |
|---|---|
| Coverage I want to see | multi: Supportive / Neutral / Critical / Investigative / Editorial |
| Brief tone toward primary subject | radio: balanced / always-charitable / show-all-criticism / advocate-mode |
| Highlight provocative quotes? | toggle |
| Include LLM narrative synthesis? | toggle (CmDriving, ForecastPulse, BlindspotInsights are LLM-generated) |

---

## Step 9 — Events to Track

Drives Section 8 Horizon 7-day calendar (event chips with type), Section 4 Risk Window panel.

| Field | Type |
|---|---|
| Event types to surface | multi: Cabinet meetings / Assembly sessions / Press briefings / Court verdicts / Election dates / Public rallies / Policy launches / Court hearings / Budget tablings / Foreign visits / Religious / Cultural / Sports |
| Confidence threshold | radio: high-confidence only / medium+ / show all (incl. rumor-stage) |
| Look-ahead window | radio: 3 days / 7 days / 14 days / 30 days |

---

## Step 10 — Delivery & Notifications

**Editions are NOT a feature right now.** Single brief page that auto-refreshes live (60s polling). Multi-edition publishing deferred — revisit when scrapers resume and we have continuous data flow.

| Field | Type |
|---|---|
| Email digest? | toggle + format (full brief / executive summary / story headlines only) |
| Email digest time | time picker (default 06:00) — only if digest toggle ON |
| Send-report destination email | text (defaults to login email; can add additional CC) |
| Timezone | dropdown (defaults to IST for govt template) |
| Real-time alerts? | toggle + threshold (any mention / 5+ mentions/hr surge / breaking-news only) |
| Alert channel | radio: email / in-app only / both |

---

## Step 11 — Brief Personality

| Field | Type |
|---|---|
| Reading depth | radio: 60-sec scan / 5-min read / 15-min deep dive |
| Visual density | radio: minimalist / standard / data-rich |
| LLM narrative voice | radio: formal-analyst / conversational / tactical-imperative ("BRACE FOR…") / academic |
| Show citations [1] [2] [3]? | toggle (default ON) |
| Show metadata (refresh time, source count, integrity %)? | toggle |

---

## Step 12 — Preview & Confirm

Critical step for validation. Before committing, render:
1. **Sample brief** — actual stories from `event_clusters` filtered by their entity + topic + region + language + outlet picks (limit 3 sample stories)
2. **Entity card preview** — show 1 of their selected entities rendered as it will appear
3. **Estimated brief metrics** — "Your brief will average ~X stories/day, drawing from Y outlets in Z languages"
4. **Edit-anything links** — clicking any value jumps back to that step

Confirm button writes everything to `analytics.user_brief_prefs` (row per user, JSONB columns for arrays).

---

## DB schema (analytics schema — analytics_user has RW)

```sql
CREATE TABLE analytics.orgs (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name            TEXT NOT NULL,
  role_template   TEXT CHECK (role_template IN ('govt','pr','journalist','academic','corporate')),
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE analytics.users (
  id              UUID PRIMARY KEY,    -- matches Supabase user_id
  org_id          UUID REFERENCES analytics.orgs(id),
  email           TEXT NOT NULL UNIQUE,
  full_name       TEXT,
  designation     TEXT,
  is_super_admin  BOOLEAN DEFAULT FALSE,
  invited_by      UUID,
  onboarded_at    TIMESTAMPTZ,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE analytics.user_brief_prefs (
  user_id              UUID PRIMARY KEY REFERENCES analytics.users(id),
  primary_subject_id   UUID,
  watchlist_entity_ids JSONB,                  -- {"allies":[uuid…], "opposition":[…], …}
  regions              JSONB,                  -- {"states":[…], "districts":[…], "countries":[…]}
  topics               JSONB,                  -- {"core":[…], "subtopics":{…}, "deprioritize":[…]}
  languages            JSONB,                  -- {"read":["en","te"], "primary":"en"}
  sources              JSONB,                  -- {"trusted":[…], "include":[…], "exclude":[…], "vernacular_pct":40}
  stance               JSONB,                  -- {"types":[…], "tone":"balanced", "llm_synthesis":true}
  events               JSONB,                  -- {"types":[…], "confidence":"high", "lookahead_days":7}
  delivery             JSONB,                  -- {"editions":[…], "email_digest":true, "alerts":{…}}
  personality          JSONB,                  -- {"depth":"5-min", "density":"standard", "voice":"formal-analyst"}
  updated_at           TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE analytics.invites (
  token_hash      TEXT PRIMARY KEY,            -- SHA-256 of the JWT
  email           TEXT NOT NULL,
  org_id          UUID REFERENCES analytics.orgs(id),
  role_template   TEXT,
  invited_by      UUID REFERENCES analytics.users(id),
  expires_at      TIMESTAMPTZ NOT NULL,
  consumed_at     TIMESTAMPTZ,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

---

## What's NOT in onboarding (deferred)

- Billing / payment details — manual contracts for now
- Team-management UI (invite teammates) — only super_admin invites
- Per-user LLM cost guardrails — we eat the cost
- API access keys — sold separately later
- Custom logo / theme — Tier 3 enterprise feature

---

## Estimated effort

- DB schema + migrations: 1 day
- Supabase auth + invite flow + admin UI: 3 days
- 12-step onboarding wizard in brief-next: 4 days
- Backend endpoints to read prefs + apply to queries: 3 days
- Preview / validation step: 2 days
- Polish + edge cases: 2 days

**~3 weeks** for a thorough, validated personalization-aware brief MVP.
