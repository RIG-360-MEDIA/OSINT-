-- 092_story_enrichment_extraction.sql
-- STEP 3 enrichment, PHASE B (extraction) — loader-enrichment-spec §3.
-- Additive, keyed by story_id, FK->story_clusters CASCADE, run_id-stamped, computed-not-generated.
-- story_facts is B-minus: conservative grouping (subject + unit + entity; under-merge when unsure)
-- with member_count / citing_article_ids / single_source so a merged-from-two-events false range
-- is both avoided (grouping conservatism) and auditable (the three-way trace reads claim texts).

CREATE TABLE IF NOT EXISTS analytics.story_quotes (
  id                bigserial PRIMARY KEY,
  story_id          uuid REFERENCES analytics.story_clusters(story_id) ON DELETE CASCADE,
  quote_text        text,
  quote_text_en     text,
  speaker           text,
  speaker_entity_id uuid,
  article_id        uuid,
  is_direct         boolean,
  run_id            bigint
);
CREATE INDEX IF NOT EXISTS idx_story_quotes_story ON analytics.story_quotes(story_id);

CREATE TABLE IF NOT EXISTS analytics.story_stance (
  story_id            uuid PRIMARY KEY REFERENCES analytics.story_clusters(story_id) ON DELETE CASCADE,
  stance_distribution jsonb,             -- {stance: count}
  sentiment           jsonb,             -- {mean_intensity, n}  -- n carried so a mean-over-2 != mean-over-40
  n_stances           int,
  run_id              bigint
);

CREATE TABLE IF NOT EXISTS analytics.story_facts (
  id                 bigserial PRIMARY KEY,
  story_id           uuid REFERENCES analytics.story_clusters(story_id) ON DELETE CASCADE,
  fact_key           text,              -- normalized subject_text = "what's measured" (e.g. "death toll")
  unit               text,              -- currency/scale token (₹, crore, %, '') — group is same-unit so min/max compare
  value_min          numeric,
  value_max          numeric,
  value_latest       numeric,           -- value from the latest-collected citing article
  member_count       int,               -- distinct citing articles
  citing_article_ids uuid[],
  single_source      boolean,           -- TRUE => one article: not corroborated divergence, just one claim
  sample_claim       text,              -- an example claim_text for audit
  run_id             bigint
);
CREATE INDEX IF NOT EXISTS idx_story_facts_story ON analytics.story_facts(story_id);
