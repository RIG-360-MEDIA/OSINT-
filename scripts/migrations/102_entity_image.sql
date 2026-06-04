-- 102_entity_image.sql
-- Entity portrait cache for the Dossier (2026-06-04). Keeps portraits OSINT-scoped
-- (analytics.*, writable by analytics_user) rather than touching public.entity_dictionary.
-- Populated by products/osint/backend/resolve_entity_images.py (Wikipedia REST summary,
-- conservative match — only stores a photo when the page description confirms the entity
-- kind, so no wrong-person faces; misses set ok=false -> the UI falls back to initials).
-- Idempotent.

CREATE TABLE IF NOT EXISTS analytics.entity_image (
  entity_id   uuid PRIMARY KEY,
  image_url   text,
  attribution text,
  source      text,
  ok          boolean NOT NULL DEFAULT true,
  fetched_at  timestamptz NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE, DELETE ON analytics.entity_image TO analytics_user;
