-- Migration 002: entity_dict_meta
-- Tracks entity_dictionary version so NLP workers can detect changes
-- and reload the in-memory dictionary without a container restart.

CREATE TABLE IF NOT EXISTS entity_dict_meta (
    id               INTEGER PRIMARY KEY DEFAULT 1,
    version          INTEGER NOT NULL DEFAULT 1,
    last_updated_at  TIMESTAMPTZ DEFAULT NOW(),
    entry_count      INTEGER DEFAULT 0,
    updated_by       TEXT DEFAULT 'system',
    CONSTRAINT single_row CHECK (id = 1)
);

-- Insert initial row (no-op if already exists)
INSERT INTO entity_dict_meta (id, version, entry_count)
VALUES (
    1,
    1,
    (SELECT COUNT(*) FROM entity_dictionary)
)
ON CONFLICT (id) DO NOTHING;

-- ── Manual bump function ───────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION bump_entity_dict_version()
RETURNS void AS $$
BEGIN
    UPDATE entity_dict_meta
    SET version          = version + 1,
        last_updated_at  = NOW(),
        entry_count      = (SELECT COUNT(*) FROM entity_dictionary)
    WHERE id = 1;
END;
$$ LANGUAGE plpgsql;

-- ── Trigger function ──────────────────────────────────────────────────────────
-- Fires after any INSERT/UPDATE/DELETE on entity_dictionary.
-- Bumps version so workers know to reload.
CREATE OR REPLACE FUNCTION entity_dict_change_trigger()
RETURNS trigger AS $$
BEGIN
    UPDATE entity_dict_meta
    SET version         = version + 1,
        last_updated_at = NOW()
    WHERE id = 1;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS entity_dict_version_bump ON entity_dictionary;

CREATE TRIGGER entity_dict_version_bump
AFTER INSERT OR UPDATE OR DELETE
ON entity_dictionary
FOR EACH STATEMENT
EXECUTE FUNCTION entity_dict_change_trigger();
