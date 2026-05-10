-- 061_drop_breaking_clusters.sql
-- Cleanup: remove the DBSCAN cluster pipeline now that
-- user_breaking_now (migration 060) is the source of truth for the
-- /api/coverage/breaking surface.
--
-- Note: newsroom_breaking_clusters and newsroom_breaking_segments
-- belong to the TV/YouTube pipeline and are left untouched.
-- social_clusters and social_cluster_posts power the social-media
-- page and are also untouched.

BEGIN;

DROP TABLE IF EXISTS breaking_clusters CASCADE;

COMMIT;
