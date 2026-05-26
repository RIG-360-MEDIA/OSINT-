-- 068_user_watched_entities.sql
-- Per-user explicit bucket assignments over the entity_dictionary.
-- Powers per-user sentiment, allies/opponents framing in the breaking
-- band, journalist-bias alignment, and the home page's competitor row.

BEGIN;

CREATE TABLE IF NOT EXISTS user_watched_entities (
  user_id    uuid NOT NULL,
  entity_id  uuid NOT NULL REFERENCES entity_dictionary(id) ON DELETE CASCADE,
  bucket     text NOT NULL CHECK (bucket IN ('ally','opponent','neutral','watched','passive')),
  weight     smallint NOT NULL DEFAULT 5,
  source     text,                         -- 'auto_party' | 'auto_geo' | 'manual' | 'auto_promote'
  added_at   timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, entity_id)
);

CREATE INDEX IF NOT EXISTS idx_uwe_user_bucket
  ON user_watched_entities(user_id, bucket);
CREATE INDEX IF NOT EXISTS idx_uwe_entity
  ON user_watched_entities(entity_id);

COMMENT ON COLUMN user_watched_entities.bucket IS
  '''ally'' | ''opponent'' | ''neutral'' | ''watched'' (locations/orgs/constituencies) '
  '| ''passive'' (auto-promoted on first surface, awaiting review)';

COMMIT;
