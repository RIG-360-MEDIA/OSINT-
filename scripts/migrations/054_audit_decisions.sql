-- 054_audit_decisions.sql — Phase 5 of the data-quality observability work.
--
-- A super-admin marks a specific (article, field, extraction_version)
-- triple correct or wrong. The /observe AuditQueue panel writes here.
--
-- Design notes:
--   * NO FK cascade into the v3 substrate. If an article is hard-deleted,
--     we keep the decision row for audit history (article_id is plain uuid).
--   * Unique constraint on (article_id, field_name, extraction_version)
--     so two super_admins can't double-mark the same field at the same
--     extraction version.
--   * verdict is one of 'correct' | 'wrong' | 'unsure'.

BEGIN;

CREATE TABLE IF NOT EXISTS audit_decisions (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id      uuid NOT NULL,
    field_name      text NOT NULL,
    extraction_version int  NOT NULL,
    verdict         text NOT NULL CHECK (verdict IN ('correct', 'wrong', 'unsure')),
    note            text,
    decided_by      uuid,
    decided_at      timestamptz NOT NULL DEFAULT NOW(),
    CONSTRAINT audit_decisions_unique
        UNIQUE (article_id, field_name, extraction_version)
);

CREATE INDEX IF NOT EXISTS idx_audit_decisions_article
    ON audit_decisions (article_id);

CREATE INDEX IF NOT EXISTS idx_audit_decisions_field_verdict
    ON audit_decisions (field_name, verdict);

CREATE INDEX IF NOT EXISTS idx_audit_decisions_decided_at
    ON audit_decisions (decided_at DESC);

COMMIT;
