-- 084_topic_fine_taxonomy.sql
-- =====================================================================
-- Adds the richer 25-bucket "topic_fine" taxonomy as a PURELY ADDITIVE
-- layer on top of the existing 15-bucket topic_category.
--
-- DESIGN (agreed 2026-05-30):
--   * topic_category  -> LEFT 100% UNTOUCHED. Same 15 values, every
--                        article, fully consistent. Existing consumers
--                        (relevance scorer, brief, analytics_user,
--                        rigwire_app) keep working byte-for-byte.
--   * topic_fine       -> NEW nullable column. The improved NLP
--                        classifier (don't-hedge + India-aware buckets)
--                        writes it for NEW articles only. Old rows stay
--                        NULL  => they naturally count as 0 in the new
--                        buckets when you GROUP BY (no row mutation).
--   * topic_categories -> NEW reference table. Declares the full 25-word
--                        vocabulary so every product knows the valid set
--                        and can collapse fine -> coarse via rolls_up_to.
--
-- CONSUMER RULE: "use topic_fine when not NULL, else topic_category".
--
-- LOCK SAFETY (a live NLP drain is UPDATE-ing articles while this runs):
--   * Section 1 (reference table) touches no existing table -> no contention.
--   * Section 2 isolates the ALTER on articles in its own txn with a short
--     lock_timeout so it fails fast instead of stalling the drain. Re-run
--     this file if it times out — every statement is idempotent.
--   * The topic_fine index is intentionally NOT created here: a build lock
--     would block the drain's writes. Add it later, off-peak, with
--     CREATE INDEX CONCURRENTLY (see tail comment).
-- =====================================================================

-- ── Section 1: vocabulary reference table (no lock on articles) ───────
BEGIN;

CREATE TABLE IF NOT EXISTS topic_categories (
    name           TEXT PRIMARY KEY,
    is_new         BOOLEAN NOT NULL DEFAULT FALSE,   -- TRUE = added in the 25-bucket expansion
    rolls_up_to    TEXT    NOT NULL,                 -- coarse (old-15) equivalent for collapsing
    description    TEXT,
    introduced_at  DATE    NOT NULL DEFAULT DATE '2026-05-30'
);

COMMENT ON TABLE topic_categories IS
    'Canonical topic vocabulary. is_new=FALSE are the original 15 (topic_category); '
    'is_new=TRUE are the 10 added for topic_fine. rolls_up_to maps each fine bucket '
    'back to one of the original 15 so consumers can collapse if needed.';

-- Original 15 (is_new=FALSE; roll up to themselves)
INSERT INTO topic_categories (name, is_new, rolls_up_to, description) VALUES
  ('POLITICS',       FALSE, 'POLITICS',       'Party politics, elections, legislators, govt formation'),
  ('GOVERNANCE',     FALSE, 'GOVERNANCE',     'Policy, administration, bureaucracy, govt programs'),
  ('BUSINESS',       FALSE, 'BUSINESS',       'Companies, corporate deals, industry, trade'),
  ('FINANCE',        FALSE, 'FINANCE',        'Stocks, banking, earnings, RBI, mutual funds, economy'),
  ('INFRASTRUCTURE', FALSE, 'INFRASTRUCTURE', 'Roads, rail, metro, power, water, construction'),
  ('SECURITY',       FALSE, 'SECURITY',       'Military ops, terrorism, border, internal security'),
  ('HEALTH',         FALSE, 'HEALTH',         'Disease, hospitals, medicine, public health'),
  ('LEGAL',          FALSE, 'LEGAL',          'Court judgments, litigation, judiciary, law'),
  ('AGRICULTURE',    FALSE, 'AGRICULTURE',    'Farming, crops, farmers, MSP, irrigation'),
  ('INTERNATIONAL',  FALSE, 'INTERNATIONAL',  'Foreign affairs, diplomacy, world events'),
  ('TECHNOLOGY',     FALSE, 'TECHNOLOGY',     'IT, software, AI, gadgets, internet, startups'),
  ('ENVIRONMENT',    FALSE, 'ENVIRONMENT',    'Climate, pollution, wildlife, forests, conservation'),
  ('SOCIAL',         FALSE, 'SOCIAL',         'Society, caste, gender, communities, human interest'),
  ('SPORTS',         FALSE, 'SPORTS',         'Cricket, football, IPL, tournaments, athletes'),
  ('OTHER',          FALSE, 'OTHER',          'Genuinely none of the above')
ON CONFLICT (name) DO NOTHING;

-- New 10 (is_new=TRUE; roll up to nearest original bucket)
INSERT INTO topic_categories (name, is_new, rolls_up_to, description) VALUES
  ('WELFARE',       TRUE, 'GOVERNANCE',   'Ration, pensions, subsidies, scholarships, welfare schemes'),
  ('DEFENCE',       TRUE, 'SECURITY',     'Armed forces, weapons, defence deals, military exercises'),
  ('CRIME',         TRUE, 'SECURITY',     'Murder, theft, fraud, arrests, police cases'),
  ('EDUCATION',     TRUE, 'SOCIAL',       'Schools, universities, exams, results, admissions'),
  ('DISASTER',      TRUE, 'ENVIRONMENT',  'Floods, earthquakes, accidents, fires, cyclones, rescue'),
  ('SCIENCE',       TRUE, 'TECHNOLOGY',   'Research, space, ISRO, discoveries, scientific studies'),
  ('ENTERTAINMENT', TRUE, 'SOCIAL',       'Films, music, celebrities, OTT, TV, cinema'),
  ('RELIGION',      TRUE, 'SOCIAL',       'Temples, festivals, religious events, faith, pilgrimages'),
  ('LIFESTYLE',     TRUE, 'SOCIAL',       'Food, travel, fashion, wellness, culture'),
  ('OBITUARY',      TRUE, 'SOCIAL',       'Deaths, tributes, passing of notable people')
ON CONFLICT (name) DO NOTHING;

GRANT SELECT ON topic_categories TO analytics_user;
GRANT SELECT ON topic_categories TO rigwire_app;

COMMIT;

-- ── Section 2: additive column on articles (own txn, fail-fast lock) ──
BEGIN;
SET LOCAL lock_timeout = '3s';

ALTER TABLE articles ADD COLUMN IF NOT EXISTS topic_fine TEXT;

COMMENT ON COLUMN articles.topic_fine IS
    'Richer 25-bucket topic (see topic_categories). Populated by the improved '
    'NLP classifier for articles processed after 2026-05-30. NULL for older '
    'articles => fall back to topic_category. Not FK-constrained to avoid lock '
    'contention with the live drain; validity enforced in app + topic_categories.';

COMMIT;

-- ── Deferred (run off-peak, NOT inside a transaction) ────────────────
-- CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_articles_topic_fine
--     ON articles (topic_fine) WHERE topic_fine IS NOT NULL;
