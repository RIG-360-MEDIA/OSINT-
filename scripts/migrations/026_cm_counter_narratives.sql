-- 026_cm_counter_narratives.sql
-- CM Page: DRAFT talking-point bullets generated daily for the top hostile
-- issues. Cite-ID guardrail enforced at generation time: every cited doc_id
-- in talking_points must be in grounding_doc_ids; the row is rejected and
-- regenerated once if any cite is unknown. Frontend renders a clear DRAFT
-- watermark over these cards — no auto-publish.

CREATE TABLE IF NOT EXISTS cm_counter_narratives (
    id                   BIGSERIAL PRIMARY KEY,
    issue_id             BIGINT NOT NULL REFERENCES cm_issues(id) ON DELETE CASCADE,
    state                TEXT,
    generated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    talking_points       JSONB NOT NULL,                                  -- [{"text": "...", "cites": [123, 456]}]
    grounding_doc_ids    BIGINT[] NOT NULL,                               -- IDs of articles/govt_docs/clippings used as grounding
    grounding_kinds      TEXT[] NOT NULL,                                 -- parallel array: 'article'|'govt_document'|'clipping' per doc id
    model                TEXT NOT NULL,
    retry_count          SMALLINT NOT NULL DEFAULT 0,                     -- 1 if first attempt was rejected for unknown cite
    rejected             BOOLEAN NOT NULL DEFAULT FALSE                   -- TRUE means even retry failed; row kept for audit
);

CREATE INDEX IF NOT EXISTS cm_cn_issue_idx
    ON cm_counter_narratives (issue_id, generated_at DESC);

CREATE INDEX IF NOT EXISTS cm_cn_state_idx
    ON cm_counter_narratives (state, generated_at DESC);

COMMENT ON TABLE cm_counter_narratives IS
  'CM Page: RAG-grounded DRAFT talking points. talking_points[].cites must intersect grounding_doc_ids.';
