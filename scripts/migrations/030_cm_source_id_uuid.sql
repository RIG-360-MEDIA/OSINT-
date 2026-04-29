-- 030_cm_source_id_uuid.sql
-- Corrective: change CM source_id columns from BIGINT to UUID so they
-- match the actual primary-key type of `articles`, `social_posts`,
-- `clips`, `newspaper_clippings`, `govt_documents` (all UUID in this
-- deployment). Migration 028's mv_cm_issue_hourly view depended on this
-- alignment and could not be created until now.
--
-- Tables are still empty (CM tasks have not yet run), so ALTER COLUMN
-- TYPE is safe and instant. If any rows landed before this is applied,
-- they would not have valid source_ids anyway — TRUNCATE first.

TRUNCATE cm_stance_scores, cm_spokesperson_quotes, cm_issue_evidence,
         cm_counter_narratives, cm_dissent_signals;

ALTER TABLE cm_stance_scores
    ALTER COLUMN source_id TYPE UUID USING NULL;

ALTER TABLE cm_spokesperson_quotes
    ALTER COLUMN source_id TYPE UUID USING NULL;

ALTER TABLE cm_issue_evidence
    ALTER COLUMN source_id TYPE UUID USING NULL;

-- counter-narrative grounding refs are also UUIDs (article / govt_doc /
-- clipping ids). Tables were truncated above so an empty-array cast is
-- always safe; the explicit empty literal sidesteps Postgres refusing
-- to coerce bigint[] → uuid[] directly.
ALTER TABLE cm_counter_narratives
    ALTER COLUMN grounding_doc_ids TYPE UUID[] USING (ARRAY[]::UUID[]);

-- cm_risk_calendar.source_id is also a UUID reference to govt_documents.id.
ALTER TABLE cm_risk_calendar
    ALTER COLUMN source_id TYPE UUID USING NULL;

COMMENT ON COLUMN cm_stance_scores.source_id IS 'UUID FK-like reference to source row (no hard constraint — see source_kind).';
COMMENT ON COLUMN cm_spokesperson_quotes.source_id IS 'UUID FK-like reference to source row.';
COMMENT ON COLUMN cm_issue_evidence.source_id IS 'UUID FK-like reference to source row.';
