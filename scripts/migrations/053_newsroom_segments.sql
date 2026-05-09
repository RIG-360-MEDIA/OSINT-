-- 053_newsroom_segments.sql
-- THE NEWSROOM — Phase 1 schema #3 of 7
--
-- Speaker-attributed transcript segments. Each row holds the canonical
-- reconciled text plus all three lens outputs retained for audit so
-- transcript quality regressions are debuggable post-hoc.
--
-- speaker_entity_id FKs to entity_dictionary(id) (the canonical entity
-- table on this codebase — NOT a non-existent `entities` table). The
-- snap from raw speaker_label ("SPEAKER_01") to canonical entity is
-- done by tasks.newsroom.phonetic_snap (Soundex + Metaphone vs
-- entity_dictionary.canonical_name + aliases, edit distance ≤ 2).

CREATE TABLE IF NOT EXISTS newsroom_segments (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    broadcast_id      UUID        NOT NULL REFERENCES newsroom_broadcasts(id) ON DELETE CASCADE,
    start_sec         NUMERIC(10,2) NOT NULL,
    end_sec           NUMERIC(10,2) NOT NULL,

    -- Speaker
    speaker_label     TEXT,                              -- e.g. 'SPEAKER_01' from pyannote
    speaker_entity_id UUID        REFERENCES entity_dictionary(id) ON DELETE SET NULL,

    -- Reconciled canonical transcript
    text_native       TEXT        NOT NULL,              -- source language
    text_en           TEXT,                              -- English translation
    confidence        NUMERIC(3,2),                      -- 0.00–1.00

    -- Audit: raw lens outputs retained verbatim so we can debug
    -- regressions in the 3-Lens Consensus pipeline post-hoc.
    l1_text           TEXT,                              -- yt-dlp auto-captions
    l2_text           TEXT,                              -- Groq Whisper
    l3_text           TEXT,                              -- local ASR (Faster-Whisper / IndicConformer)

    -- Quote / framing flags (populated by Phase 3 extract_quotes task)
    is_quote          BOOLEAN     NOT NULL DEFAULT FALSE,
    is_editorial      BOOLEAN     NOT NULL DEFAULT FALSE,  -- anchor opinion vs reported speech
    sentiment         NUMERIC(3,2),                      -- -1.00..+1.00
    framing           TEXT,                              -- 'adversarial','aligned','neutral'

    -- Live vs VOD (denormalised from broadcasts.is_live for fast filtering)
    is_live           BOOLEAN     NOT NULL DEFAULT FALSE,

    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_newsroom_segments_broadcast
    ON newsroom_segments (broadcast_id, start_sec);

CREATE INDEX IF NOT EXISTS idx_newsroom_segments_entity
    ON newsroom_segments (speaker_entity_id, created_at DESC)
    WHERE speaker_entity_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_newsroom_segments_recent
    ON newsroom_segments (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_newsroom_segments_live_recent
    ON newsroom_segments (is_live, created_at DESC)
    WHERE is_live = TRUE;

CREATE INDEX IF NOT EXISTS idx_newsroom_segments_quote
    ON newsroom_segments (is_quote, created_at DESC)
    WHERE is_quote = TRUE;

CREATE INDEX IF NOT EXISTS idx_newsroom_segments_framing
    ON newsroom_segments (framing)
    WHERE framing IS NOT NULL;

COMMENT ON TABLE newsroom_segments IS
    'Speaker-attributed transcript segments. Holds canonical reconciled text + all 3 raw lens outputs for audit.';

-- LISTEN/NOTIFY trigger so the SSE endpoint (Phase 6) can stream new
-- segments to the WALL/STREAM modes without polling. Uses a per-row
-- AFTER INSERT trigger that emits the new id on channel 'newsroom_segment'.
CREATE OR REPLACE FUNCTION notify_newsroom_segment_inserted() RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify(
        'newsroom_segment',
        json_build_object(
            'segment_id',   NEW.id,
            'broadcast_id', NEW.broadcast_id,
            'is_live',      NEW.is_live,
            'created_at',   NEW.created_at
        )::text
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_notify_newsroom_segment ON newsroom_segments;
CREATE TRIGGER trg_notify_newsroom_segment
    AFTER INSERT ON newsroom_segments
    FOR EACH ROW EXECUTE FUNCTION notify_newsroom_segment_inserted();
