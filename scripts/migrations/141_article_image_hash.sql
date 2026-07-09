-- 141_article_image_hash.sql
-- Perceptual-hash index for image→corpus cross-check (media verification fusion).
-- One dHash per article thumbnail; near-duplicate (small Hamming distance) = the same
-- photo reused across outlets. Written by the isolated rigmedia service (analytics_user);
-- rigmedia also creates this at startup (ensure_schema) so this file is the repo record.
CREATE TABLE IF NOT EXISTS analytics.article_image_hash (
    article_id  uuid PRIMARY KEY,
    dhash       bit(64)     NOT NULL,
    computed_at timestamptz NOT NULL DEFAULT now()
);
-- Hamming search is a seq scan (bit_count(a # b)); fine at bounded index sizes.
COMMENT ON TABLE analytics.article_image_hash IS
    'dHash of article thumbnails for image-identity corpus matching (media verify).';
