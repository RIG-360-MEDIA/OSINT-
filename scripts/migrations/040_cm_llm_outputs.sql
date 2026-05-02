-- 040_cm_llm_outputs.sql
-- CM Page v2 — Phase 4 LLM auto-publish surfaces.
--
-- Three new tables behind cite-ID guarded LLM tasks. All tables are
-- write-once-then-read; no edits in place. The Lead headline rotation
-- and the Analysis column are append-only. The Action queue uses an
-- expires_at to age out stale items.
--
-- Cite-ID validation: every row carries cite_ids UUID[] (FK by
-- convention to articles.id). The validator helper at
-- backend/nlp/cm/cite_validate.py rejects an LLM output where any
-- cite ID does not resolve to a real article. Rejected rows are
-- still written with status='rejected' for auditability but never
-- surfaced via the read endpoints.
--
-- Apply via:
--   docker exec -i rig-postgres psql -U rig -d rig \
--     < scripts/migrations/040_cm_llm_outputs.sql

-- ── 1. cm_lead_headlines ─────────────────────────────────────────────────
-- Populated by tasks.cm.lead_headline (every 5 minutes). Picks top 5
-- cm-relevant articles, generates a 2-3 line eyebrow + headline per
-- article, validates cite-IDs. Read endpoint returns the latest
-- non-rejected batch ordered by rank.

CREATE TABLE IF NOT EXISTS cm_lead_headlines (
    id            BIGSERIAL   PRIMARY KEY,
    state_code    TEXT        NOT NULL,
    rank          INT         NOT NULL CHECK (rank >= 0 AND rank < 20),
    eyebrow       TEXT        NOT NULL,         -- "WHAT CHANGED · SINCE 09:00"
    headline      TEXT        NOT NULL,
    cite_ids      UUID[]      NOT NULL DEFAULT '{}',
    generated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    model         TEXT        NOT NULL,
    validated     BOOLEAN     NOT NULL DEFAULT FALSE,
    rejected      BOOLEAN     NOT NULL DEFAULT FALSE,
    rejection_reason TEXT
);

CREATE INDEX IF NOT EXISTS cm_lead_headlines_state_recent_idx
    ON cm_lead_headlines (state_code, generated_at DESC, rank ASC)
    WHERE rejected = FALSE AND validated = TRUE;

CREATE INDEX IF NOT EXISTS cm_lead_headlines_audit_idx
    ON cm_lead_headlines (rejected, generated_at DESC)
    WHERE rejected = TRUE;

COMMENT ON TABLE cm_lead_headlines IS
  'CM v2: rotating Lead headlines. Auto-publish with cite-ID guard. '
  'Read endpoint /api/cm/lead returns the most recent batch where '
  'rejected=false AND validated=true.';

-- ── 2. cm_analysis_drafts ────────────────────────────────────────────────
-- Populated by tasks.cm.analysis_column at 06:00 / 12:00 / 18:00.
-- 5-paragraph editorial column + pull-quote + endnote.
-- Auto-publish if cite_ids validate; previous published draft stays
-- visible if today's gets rejected.

CREATE TABLE IF NOT EXISTS cm_analysis_drafts (
    id            BIGSERIAL   PRIMARY KEY,
    state_code    TEXT        NOT NULL,
    status        TEXT        NOT NULL CHECK (status IN ('drafted','published','rejected')),
    eyebrow       TEXT,
    byline        TEXT,
    headline      TEXT        NOT NULL,
    deck          TEXT,
    paragraphs    JSONB       NOT NULL,           -- string[]
    pull_quote    TEXT,
    endnote       TEXT,
    cite_ids      UUID[]      NOT NULL DEFAULT '{}',
    valid_cite_count INTEGER  NOT NULL DEFAULT 0, -- post-validation
    generated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at  TIMESTAMPTZ,
    rejected_at   TIMESTAMPTZ,
    model         TEXT        NOT NULL
);

CREATE INDEX IF NOT EXISTS cm_analysis_published_idx
    ON cm_analysis_drafts (state_code, published_at DESC NULLS LAST)
    WHERE status = 'published';

COMMENT ON TABLE cm_analysis_drafts IS
  'CM v2: editorial Analysis column. Auto-publish gated by cite-ID '
  'validation (>=4 valid cites required; rejected on shortfall). '
  'Read endpoint /api/cm/analysis returns latest published.';

-- ── 3. cm_action_queue ───────────────────────────────────────────────────
-- Populated by tasks.cm.action_queue (every 15 minutes). Hybrid:
-- deterministic rules trigger items first; LLM proposes additional
-- items with cite-IDs; both publish immediately.

CREATE TABLE IF NOT EXISTS cm_action_queue (
    id            BIGSERIAL   PRIMARY KEY,
    state_code    TEXT        NOT NULL,
    priority      TEXT        NOT NULL CHECK (priority IN ('P0','P1','P2')),
    text          TEXT        NOT NULL,
    deadline      TEXT,                            -- "within 6h · before 18:00"
    source_type   TEXT        NOT NULL CHECK (source_type IN ('rule','llm','calendar')),
    rule_name     TEXT,                            -- when source_type='rule'
    cite_ids      UUID[]      NOT NULL DEFAULT '{}',
    generated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at    TIMESTAMPTZ NOT NULL,
    status        TEXT        NOT NULL DEFAULT 'active' CHECK (status IN ('active','expired','completed','dismissed')),
    completed_at  TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS cm_action_active_idx
    ON cm_action_queue (state_code, priority, generated_at DESC)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS cm_action_dedup_idx
    ON cm_action_queue (state_code, source_type, COALESCE(rule_name, ''), text)
    WHERE status = 'active';

COMMENT ON TABLE cm_action_queue IS
  'CM v2: For-the-Chair action items. Auto-publish; expire on '
  'expires_at; dedup on (state, source_type, rule_name, text) for '
  'idempotent re-runs of the rule engine.';
