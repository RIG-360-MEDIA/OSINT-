-- draftsmith 001 — Door B (AI-assisted article generation) box-side schema.
-- Additive only: creates rigwire.draft_* tables; alters nothing existing.
-- All warehouse access elsewhere is read-only SELECT; these tables are the
-- ONLY writes draftsmith performs on the box. Neon is never touched here.
--
-- Apply:  psql "$DATABASE_URL" -f 001_draftsmith.sql   (idempotent-ish: IF NOT EXISTS)
-- Requires: schema rigwire (already present on box rig-postgres), pgcrypto/pg13+ gen_random_uuid.

BEGIN;

-- ---------------------------------------------------------------------------
-- 1.1  Job spine
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rigwire.draft_jobs (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  created_by         text NOT NULL,                    -- editor id (email) forwarded from the CMS
  input_text         text NOT NULL,                    -- 1 line OR up to a ~100-line editorial brief
  dials              jsonb NOT NULL DEFAULT
                     '{"creativity":5,"moxy":3,"length_target":1200,"spot_check":true}'::jsonb,
  state              text NOT NULL DEFAULT 'queued' CHECK (state IN (
                        'queued','planning','gathering','ranking','drafting',
                        'verifying','repairing','images','ready',
                        'failed','cancelled','published')),
  stage_progress     jsonb NOT NULL DEFAULT '{}'::jsonb, -- per-stage timings, per-source ok/fail, token + headroom stats
  query_plan         jsonb,                             -- frozen Stage-1 planner output
  error              text,
  attempt            smallint NOT NULL DEFAULT 0,
  lease_until        timestamptz,                       -- worker crash-recovery lease
  published_by       text,                              -- real editor id, set at publish
  published_story_id text,                              -- Neon manual_stories id
  published_at       timestamptz,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS draft_jobs_state_created_idx ON rigwire.draft_jobs (state, created_at DESC);
CREATE INDEX IF NOT EXISTS draft_jobs_created_by_idx    ON rigwire.draft_jobs (created_by, created_at DESC);

-- DB-ENFORCED: a job may only enter 'published' with a real editor id.
CREATE OR REPLACE FUNCTION rigwire.draft_jobs_publish_guard() RETURNS trigger AS $$
BEGIN
  IF NEW.state = 'published'
     AND (NEW.published_by IS NULL OR NEW.published_by !~ '@' OR lower(NEW.published_by) = 'model')
  THEN
    RAISE EXCEPTION 'draft_jobs: publish requires a real editor id (got %)', NEW.published_by;
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS draft_jobs_publish_guard ON rigwire.draft_jobs;
CREATE TRIGGER draft_jobs_publish_guard
  BEFORE UPDATE OF state ON rigwire.draft_jobs
  FOR EACH ROW EXECUTE FUNCTION rigwire.draft_jobs_publish_guard();

-- ---------------------------------------------------------------------------
-- 1.2  Evidence snapshots (frozen at gather time; retained while published)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rigwire.draft_evidence (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id        uuid NOT NULL REFERENCES rigwire.draft_jobs(id) ON DELETE CASCADE,
  source_id     text NOT NULL,          -- citation handle: c# corpus, f# fact, y# yt, w# web, k# wiki, t# tw, r# reddit, s# other social
  source_type   text NOT NULL CHECK (source_type IN (
                   'corpus_article','story_fact','youtube_clip','web','wikipedia',
                   'twitter','reddit','tiktok','telegram','instagram','wechat')),
  trust_tier    smallint NOT NULL CHECK (trust_tier BETWEEN 1 AND 3),
  title         text,
  url           text,
  outlet        text,
  author        text,
  published_at  timestamptz,
  text_snapshot text NOT NULL,          -- the frozen text the writer may cite; never re-fetched
  raw           jsonb NOT NULL DEFAULT '{}'::jsonb,  -- full raw record snapshot
  relevance     real,
  selected      boolean NOT NULL DEFAULT false,      -- made it into the BRIEF
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (job_id, source_id)
);
CREATE INDEX IF NOT EXISTS draft_evidence_job_idx ON rigwire.draft_evidence (job_id, selected);

-- ---------------------------------------------------------------------------
-- 1.3  Draft versions (append-only: model draft -> repair rounds -> editor edits)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rigwire.draft_versions (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id         uuid NOT NULL REFERENCES rigwire.draft_jobs(id) ON DELETE CASCADE,
  version        int  NOT NULL,
  kind           text NOT NULL CHECK (kind IN ('model','repair','editor')),
  headline       text NOT NULL,
  dek            text,
  beats          jsonb NOT NULL,        -- [{subhead, text, source_ids:[...]}]
  key_facts      jsonb NOT NULL DEFAULT '[]'::jsonb,  -- [{fact, source_ids}]
  pull_quote     jsonb,                 -- {text, speaker, source_id} | null
  unsourced_gaps jsonb NOT NULL DEFAULT '[]'::jsonb,
  word_count     int,
  verify_report  jsonb,                 -- per-beat verdicts (see models.VerifyReport)
  created_by     text NOT NULL,         -- 'model' | editor id
  created_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (job_id, version)
);
CREATE INDEX IF NOT EXISTS draft_versions_job_idx ON rigwire.draft_versions (job_id, version DESC);

-- ---------------------------------------------------------------------------
-- 1.4  Per-claim flags — dismissed ONE AT A TIME, DB-enforced (no bulk clear)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rigwire.draft_flags (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id          uuid NOT NULL REFERENCES rigwire.draft_jobs(id) ON DELETE CASCADE,
  version_id      uuid NOT NULL REFERENCES rigwire.draft_versions(id) ON DELETE CASCADE,
  beat_index      int  NOT NULL,
  span            text NOT NULL,
  severity        text NOT NULL CHECK (severity IN ('red','amber')),
  reason          text NOT NULL,
  source_ids      text[] NOT NULL DEFAULT '{}',
  status          text NOT NULL DEFAULT 'open' CHECK (status IN ('open','dismissed','fixed')),
  resolved_by     text,
  resolved_at     timestamptz,
  resolution_note text,
  created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS draft_flags_job_status_idx ON rigwire.draft_flags (job_id, status);

-- A single UPDATE may transition at most ONE flag out of 'open' — bulk-acknowledge
-- is auto-publish in disguise (statement-level trigger, transition-delta form).
CREATE OR REPLACE FUNCTION rigwire.draft_flags_single_resolve() RETURNS trigger AS $$
DECLARE resolved_count int;
BEGIN
  SELECT count(*) INTO resolved_count
  FROM new_rows n JOIN old_rows o ON o.id = n.id
  WHERE o.status = 'open' AND n.status <> 'open';
  IF resolved_count > 1 THEN
    RAISE EXCEPTION 'draft_flags: flags must be resolved individually (attempted % in one statement)', resolved_count;
  END IF;
  RETURN NULL;
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS draft_flags_single_resolve ON rigwire.draft_flags;
-- NB: transition tables (REFERENCING) cannot be combined with a column list
-- (UPDATE OF status) — fire on any UPDATE; the function filters status transitions.
CREATE TRIGGER draft_flags_single_resolve
  AFTER UPDATE ON rigwire.draft_flags
  REFERENCING OLD TABLE AS old_rows NEW TABLE AS new_rows
  FOR EACH STATEMENT EXECUTE FUNCTION rigwire.draft_flags_single_resolve();

-- Leaving 'open' requires a real editor id (row-level).
CREATE OR REPLACE FUNCTION rigwire.draft_flags_resolver_guard() RETURNS trigger AS $$
BEGIN
  IF NEW.status <> 'open' AND (NEW.resolved_by IS NULL OR NEW.resolved_by !~ '@') THEN
    RAISE EXCEPTION 'draft_flags: resolving a flag requires a real editor id';
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS draft_flags_resolver_guard ON rigwire.draft_flags;
CREATE TRIGGER draft_flags_resolver_guard
  BEFORE UPDATE OF status ON rigwire.draft_flags
  FOR EACH ROW EXECUTE FUNCTION rigwire.draft_flags_resolver_guard();

-- ---------------------------------------------------------------------------
-- 1.5  Thumbnail candidates (6 slots, provenance + license)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rigwire.draft_images (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id               uuid NOT NULL REFERENCES rigwire.draft_jobs(id) ON DELETE CASCADE,
  slot                 smallint NOT NULL CHECK (slot BETWEEN 1 AND 6),
  origin               text NOT NULL CHECK (origin IN ('corpus','wikimedia','web')),
  url                  text NOT NULL,
  thumb_url            text,
  license              text,
  license_url          text,
  attribution          text,
  needs_license_review boolean NOT NULL DEFAULT false,  -- always true for origin='web'
  source_page          text,
  width                int,
  height               int,
  selected             boolean NOT NULL DEFAULT false,
  created_at           timestamptz NOT NULL DEFAULT now(),
  UNIQUE (job_id, slot)
);

-- ---------------------------------------------------------------------------
-- 1.6  Publish audit (box-side record of the single Neon write)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rigwire.draft_publishes (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id        uuid NOT NULL REFERENCES rigwire.draft_jobs(id),
  version_id    uuid NOT NULL REFERENCES rigwire.draft_versions(id),
  neon_story_id text NOT NULL,          -- rigwire.manual_stories.id on Neon
  editor_id     text NOT NULL,
  flags_summary jsonb NOT NULL DEFAULT '{}'::jsonb,  -- {resolved: n, red: n, amber: n}
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (job_id)                       -- one publish per job → idempotency
);

COMMIT;
