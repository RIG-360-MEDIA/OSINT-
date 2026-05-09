-- 056_newsroom_breaking_segments.sql
-- THE NEWSROOM — Phase 1 schema #6 of 7
--
-- Many-to-many join: which segments belong to which breaking cluster.
-- A single segment can belong to multiple clusters in edge cases
-- (rare — typically one), so it's not a 1:N FK on segments.

CREATE TABLE IF NOT EXISTS newsroom_breaking_segments (
    cluster_id  UUID NOT NULL REFERENCES newsroom_breaking_clusters(id) ON DELETE CASCADE,
    segment_id  UUID NOT NULL REFERENCES newsroom_segments(id)          ON DELETE CASCADE,
    PRIMARY KEY (cluster_id, segment_id)
);

CREATE INDEX IF NOT EXISTS idx_newsroom_breaking_segments_segment
    ON newsroom_breaking_segments (segment_id);

COMMENT ON TABLE newsroom_breaking_segments IS
    'Cluster ↔ segment join. Lets the WALL banner show "carried by N channels — see segments [...]".';
