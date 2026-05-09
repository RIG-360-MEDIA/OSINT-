-- ============================================================
-- Migration 050 — user_cards parent/child structure
-- ============================================================
-- Custom-card detail view spawns 3-5 derivative "intelligence
-- sub-cards" at parent-card creation time. Each sub-card is a
-- fully-realised mini-tracker with its own analytical angle,
-- own predicate, own summary. Sub-cards live in the same
-- user_cards table, distinguished by parent_card_id NOT NULL.
--
-- Sub-cards are NEVER directly created by the user — only by
-- tasks.spawn_sub_cards from a Groq call against the parent's
-- user_intent text. The detail view loads parent + all sub-cards
-- via /api/coverage/cards/:id/full.
--
-- Idempotent — safe to re-run.
-- ============================================================

BEGIN;

ALTER TABLE user_cards
  ADD COLUMN IF NOT EXISTS parent_card_id   UUID NULL,
  ADD COLUMN IF NOT EXISTS sub_card_angle   TEXT NULL,
  ADD COLUMN IF NOT EXISTS sub_cards_spawned BOOLEAN NOT NULL DEFAULT FALSE;

-- Self-referential FK so deleting a parent cleans up its children.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.table_constraints
    WHERE constraint_name = 'user_cards_parent_card_id_fkey'
  ) THEN
    ALTER TABLE user_cards
      ADD CONSTRAINT user_cards_parent_card_id_fkey
      FOREIGN KEY (parent_card_id) REFERENCES user_cards(id) ON DELETE CASCADE;
  END IF;
END$$;

-- Index for "find all children of parent X" — the dominant query
-- shape from /api/coverage/cards/:id/full.
CREATE INDEX IF NOT EXISTS user_cards_parent_card_id_idx
  ON user_cards (parent_card_id)
  WHERE parent_card_id IS NOT NULL;

COMMENT ON COLUMN user_cards.parent_card_id IS
  'NULL for user-created parent cards; UUID of parent for spawned sub-cards.';
COMMENT ON COLUMN user_cards.sub_card_angle IS
  'Short human-readable angle (e.g. "Threats to Revanth") for sub-cards. NULL on parents.';
COMMENT ON COLUMN user_cards.sub_cards_spawned IS
  'Set TRUE once tasks.spawn_sub_cards has finished for this parent. Prevents re-spawning on re-runs.';

COMMIT;
