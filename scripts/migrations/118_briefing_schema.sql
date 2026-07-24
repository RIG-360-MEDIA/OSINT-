-- 118_briefing_schema.sql
--
-- Daily Media Briefing — full rebuild engine schema. Multi-tenant from day one:
-- every table carries org_id -> analytics.orgs(org_id). Telangana (I&PR) is the
-- first tenant. Nothing here touches the legacy report_builder path.
--
-- Design spec: docs/reports/briefing-rebuild-spec.md
-- Build plan:  docs/reports/briefing-build-plan.md
--
-- Two data classes, kept strictly separate:
--   CORPUS facts  -> counts, timestamps, quotes, numbers, images (never model-touched)
--   PROMPT verdicts -> aboutness, tone, topic, dept, event, evidence (always verified)

CREATE SCHEMA IF NOT EXISTS briefing;

-- ─────────────────────────────────────────────────────────────────────────────
-- REFERENCE DATA (per-org, client-approved, small, curated)
-- ─────────────────────────────────────────────────────────────────────────────

-- The roster: who IS the government, and who is the opposition. Load-bearing in
-- five places (aboutness, sentiment side, gov-voice check, §7 sides, name norm).
CREATE TABLE IF NOT EXISTS briefing.roster (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         uuid NOT NULL REFERENCES analytics.orgs(id) ON DELETE CASCADE,
    canonical_name text NOT NULL,
    side           text NOT NULL CHECK (side IN ('government','opposition','institution')),
    role           text,                         -- e.g. "Chief Minister", "Irrigation Dept"
    party          text,                         -- normalised party, nullable for institutions
    name_variants  text[] NOT NULL DEFAULT '{}', -- every spelling seen ("N. Uttam Kumar Reddy", "Uttam")
    telugu_names   text[] NOT NULL DEFAULT '{}', -- Telugu-script spellings (see build note on translation)
    active         boolean NOT NULL DEFAULT true,
    notes          text,
    created_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (org_id, canonical_name)
);
CREATE INDEX IF NOT EXISTS idx_roster_org ON briefing.roster(org_id) WHERE active;

-- Departments: the closed vocabulary the prompt must pick from for `lands_on`.
CREATE TABLE IF NOT EXISTS briefing.departments (
    id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id   uuid NOT NULL REFERENCES analytics.orgs(id) ON DELETE CASCADE,
    name     text NOT NULL,
    active   boolean NOT NULL DEFAULT true,
    UNIQUE (org_id, name)
);

-- Topics: the 11 client topics (closed list).
CREATE TABLE IF NOT EXISTS briefing.topics (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id     uuid NOT NULL REFERENCES analytics.orgs(id) ON DELETE CASCADE,
    name       text NOT NULL,
    sort_order int NOT NULL DEFAULT 0,
    active     boolean NOT NULL DEFAULT true,
    UNIQUE (org_id, name)
);

-- Schemes: flagship programmes, with variant + disambiguation handling for
-- generic names (Mahalakshmi = goddess/temple; Cheyutha = ordinary Telugu word).
CREATE TABLE IF NOT EXISTS briefing.schemes (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              uuid NOT NULL REFERENCES analytics.orgs(id) ON DELETE CASCADE,
    name                text NOT NULL,
    department          text,
    name_variants       text[] NOT NULL DEFAULT '{}',
    telugu_names        text[] NOT NULL DEFAULT '{}',
    disambiguation_terms text[] NOT NULL DEFAULT '{}', -- must co-occur for a generic name to count
    active              boolean NOT NULL DEFAULT true,
    UNIQUE (org_id, name)
);

-- Outlet identity: merge one media house across pillars (web "TV9 Telugu" =
-- TV "TV9 Telugu Live"). Blocks §9, helps §6.
CREATE TABLE IF NOT EXISTS briefing.outlet_identity (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         uuid NOT NULL REFERENCES analytics.orgs(id) ON DELETE CASCADE,
    house_name     text NOT NULL,
    lean_note      text,                          -- e.g. "BRS-leaning", "govt-leaning"
    web_source_ids uuid[] NOT NULL DEFAULT '{}',  -- sources.id for the web pillar
    tv_channels    text[] NOT NULL DEFAULT '{}',  -- youtube_clips_v2.channel_name values
    np_papers      text[] NOT NULL DEFAULT '{}',  -- newspaper source identifiers
    UNIQUE (org_id, house_name)
);

-- ─────────────────────────────────────────────────────────────────────────────
-- RUN + VERDICT STORAGE (immutable; judged once, never recomputed)
-- ─────────────────────────────────────────────────────────────────────────────

-- One row per daily (or 7-day scheme) run.
CREATE TABLE IF NOT EXISTS briefing.runs (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        uuid NOT NULL REFERENCES analytics.orgs(id) ON DELETE CASCADE,
    cover_date    date NOT NULL,                  -- the IST calendar day covered
    window_start  timestamptz NOT NULL,           -- 00:00 IST as UTC
    window_end    timestamptz NOT NULL,           -- 23:59:59 IST as UTC
    model         text,
    prompt_version text NOT NULL,
    status        text NOT NULL DEFAULT 'running' CHECK (status IN ('running','judged','merged','assembled','failed')),
    counts        jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (org_id, cover_date)
);
CREATE INDEX IF NOT EXISTS idx_runs_org_date ON briefing.runs(org_id, cover_date DESC);

-- One row per judged item (article / clipping / TV video). The TV video is one
-- row even though the corpus stores it as multiple transcript segments.
CREATE TABLE IF NOT EXISTS briefing.items (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          uuid NOT NULL REFERENCES analytics.orgs(id) ON DELETE CASCADE,
    run_id          uuid NOT NULL REFERENCES briefing.runs(id) ON DELETE CASCADE,
    pillar          text NOT NULL CHECK (pillar IN ('web','tv','newspaper')),
    item_ref        text NOT NULL,                -- articles.id / clippings.id / youtube video_id (as text)
    source_ref      text,                         -- outlet identifier for joins
    published_at    timestamptz,                  -- collection ts (proxy; see spec caveat)
    lang            text,
    -- judgement (PROMPT)
    about_government boolean,
    verdict         text CHECK (verdict IN ('favourable','critical','neutral')),
    strength        text CHECK (strength IN ('strong','mild')),
    topic           text,
    department      text,
    scheme          text,
    event_action    text,
    event_actors    text[] DEFAULT '{}',
    event_date      date,
    event_place     text,
    evidence        text,
    evidence_verified boolean NOT NULL DEFAULT false,
    lands_on        text,
    confidence      numeric(3,2),
    unclear         boolean NOT NULL DEFAULT false, -- confidence < gate OR evidence unverified
    -- provenance
    model           text,
    prompt_version  text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, pillar, item_ref)
);
CREATE INDEX IF NOT EXISTS idx_items_run ON briefing.items(run_id);
CREATE INDEX IF NOT EXISTS idx_items_run_about ON briefing.items(run_id) WHERE about_government;
CREATE INDEX IF NOT EXISTS idx_items_topic ON briefing.items(run_id, topic);
CREATE INDEX IF NOT EXISTS idx_items_scheme ON briefing.items(run_id, scheme);

-- Merged events (our own merge; NOT story_clusters_v8, which is articles-only).
CREATE TABLE IF NOT EXISTS briefing.events (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         uuid NOT NULL REFERENCES analytics.orgs(id) ON DELETE CASCADE,
    run_id         uuid NOT NULL REFERENCES briefing.runs(id) ON DELETE CASCADE,
    label          text NOT NULL,
    member_item_ids uuid[] NOT NULL DEFAULT '{}',
    spread_web     int NOT NULL DEFAULT 0,        -- distinct web outlets
    spread_tv      int NOT NULL DEFAULT 0,        -- distinct TV channels (deduped)
    spread_np      int NOT NULL DEFAULT 0,        -- distinct newspapers
    net_tone       int,                           -- -100..100
    importance     numeric,                       -- ranking score
    top_web_item   uuid REFERENCES briefing.items(id),
    top_tv_item    uuid REFERENCES briefing.items(id),
    top_np_item    uuid REFERENCES briefing.items(id),
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_events_run ON briefing.events(run_id, importance DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- ASSEMBLED REPORT + EDIT AUDIT
-- ─────────────────────────────────────────────────────────────────────────────

-- The immutable assembled report JSON (all sections + strip).
CREATE TABLE IF NOT EXISTS briefing.report (
    run_id     uuid PRIMARY KEY REFERENCES briefing.runs(id) ON DELETE CASCADE,
    org_id     uuid NOT NULL REFERENCES analytics.orgs(id) ON DELETE CASCADE,
    json       jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Edit audit: what a press officer changed before sending. Original kept.
CREATE TABLE IF NOT EXISTS briefing.report_overrides (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id        uuid NOT NULL REFERENCES briefing.runs(id) ON DELETE CASCADE,
    org_id        uuid NOT NULL REFERENCES analytics.orgs(id) ON DELETE CASCADE,
    section       text NOT NULL,
    json_path     text NOT NULL,
    original_text text,
    edited_text   text,
    edited_by     text,
    edited_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_overrides_run ON briefing.report_overrides(run_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- VALIDATION (the gold set — permanent regression tests)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS briefing.validation_labels (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        uuid NOT NULL REFERENCES analytics.orgs(id) ON DELETE CASCADE,
    cover_date    date NOT NULL,
    pillar        text NOT NULL,
    item_ref      text NOT NULL,
    human_about   boolean,                        -- gold: is it about the government
    human_verdict text,                           -- gold: favourable/critical/neutral
    labeled_by    text NOT NULL,
    note          text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (org_id, cover_date, pillar, item_ref)
);
