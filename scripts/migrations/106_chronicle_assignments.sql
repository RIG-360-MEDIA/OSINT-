-- 106_chronicle_assignments.sql
-- Chronicle: per-user story assignment table + LLM result cache.
-- Assignments are created manually by admins (no auto-matching for now).
-- chronicle_cache stores the LLM output keyed by story_id; TTL enforced
-- at read time in chronicle_router (>24h → regenerate).

CREATE TABLE IF NOT EXISTS analytics.user_story_assignments (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL,
    story_id    uuid NOT NULL REFERENCES analytics.story_clusters(story_id) ON DELETE CASCADE,
    assigned_at timestamptz NOT NULL DEFAULT now(),
    assigned_by text DEFAULT 'admin',
    label       text,
    CONSTRAINT uq_chronicle_user_story UNIQUE(user_id, story_id)
);
CREATE INDEX IF NOT EXISTS idx_usa_user    ON analytics.user_story_assignments(user_id);
CREATE INDEX IF NOT EXISTS idx_usa_story   ON analytics.user_story_assignments(story_id);

CREATE TABLE IF NOT EXISTS analytics.chronicle_cache (
    story_id      uuid PRIMARY KEY REFERENCES analytics.story_clusters(story_id) ON DELETE CASCADE,
    payload       jsonb NOT NULL,
    generated_at  timestamptz NOT NULL DEFAULT now(),
    model_version text
);
