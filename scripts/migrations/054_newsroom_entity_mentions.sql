-- 054_newsroom_entity_mentions.sql
-- THE NEWSROOM — Phase 1 schema #4 of 7
--
-- Per-segment entity mentions, decoupled from speaker_entity_id (which
-- is who is speaking). A segment can mention many entities; this table
-- supports the ECHO + DOSSIER queries:
--
--   "all quotes mentioning Revanth Reddy in the last 24h"
--   "mention deltas for KCR over 7 days"
--
-- was_phonetic = TRUE for snaps the phonetic_snap task made when the
-- raw transcript token didn't exact-match any entity but Soundex /
-- Metaphone said it was within edit-distance 2 of a canonical name.

CREATE TABLE IF NOT EXISTS newsroom_entity_mentions (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    segment_id   UUID        NOT NULL REFERENCES newsroom_segments(id) ON DELETE CASCADE,
    entity_id    UUID        NOT NULL REFERENCES entity_dictionary(id) ON DELETE CASCADE,
    span_start   INTEGER,                                -- char offset in text_native
    span_end     INTEGER,
    was_phonetic BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (segment_id, entity_id, span_start)
);

CREATE INDEX IF NOT EXISTS idx_newsroom_mentions_entity_recent
    ON newsroom_entity_mentions (entity_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_newsroom_mentions_segment
    ON newsroom_entity_mentions (segment_id);

COMMENT ON TABLE newsroom_entity_mentions IS
    'Segment ↔ entity_dictionary join. Drives ECHO and DOSSIER modes.';
