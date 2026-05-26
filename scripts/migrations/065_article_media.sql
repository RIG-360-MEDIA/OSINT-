-- 065_article_media.sql
-- Inline images, embedded videos, embedded tweets per article.
-- Powers image gallery (2A), video reel (2B), tweet wall (2C),
-- and hero-image upgrade (2E).

BEGIN;

CREATE TABLE IF NOT EXISTS article_media (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  article_id  uuid NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
  media_type  text NOT NULL CHECK (media_type IN ('image','video','tweet','embed')),
  url         text,                          -- src URL (image) or canonical URL (video/tweet)
  external_id text,                          -- youtube video id / tweet id
  caption     text,
  alt_text    text,
  width       smallint,
  height      smallint,
  position    smallint,
  is_hero     boolean NOT NULL DEFAULT false,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_article_media_article
  ON article_media(article_id);
CREATE INDEX IF NOT EXISTS idx_article_media_type
  ON article_media(article_id, media_type);
CREATE INDEX IF NOT EXISTS idx_article_media_hero
  ON article_media(article_id) WHERE is_hero;
CREATE INDEX IF NOT EXISTS idx_article_media_external
  ON article_media(media_type, external_id) WHERE external_id IS NOT NULL;

COMMIT;
