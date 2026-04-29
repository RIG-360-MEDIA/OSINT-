-- 022_cm_spokesperson_quotes.sql
-- CM Page: extracted political quotes with speaker attribution.
-- Populated by tasks.cm.extract_speakers via Groq extract_json.
-- speaker_canonical is resolved against entity_dictionary aliases at extract
-- time; if no match, speaker_canonical remains NULL and the row still serves
-- raw "verbatim" displays but does not aggregate into the leaderboard.

CREATE TABLE IF NOT EXISTS cm_spokesperson_quotes (
    id                 BIGSERIAL PRIMARY KEY,
    source_kind        TEXT NOT NULL CHECK (source_kind IN ('article','social_post','clip','clipping')),
    source_id          BIGINT NOT NULL,
    state              TEXT,
    speaker            TEXT NOT NULL,                  -- as detected by NER, may be alias
    speaker_canonical  TEXT,                           -- resolved canonical name from entity_dictionary
    party              TEXT,
    role               TEXT,                           -- e.g. 'Chief Minister', 'MLA Hyderabad', 'Spokesperson'
    quote              TEXT NOT NULL,
    quote_lang         TEXT,                           -- 'en' / 'te' / 'hi' / ...
    stance             TEXT CHECK (stance IN ('ruling_supportive','opposition_attack','neutral_factual','mixed','unknown')),
    sentiment          REAL CHECK (sentiment BETWEEN -1 AND 1),
    issue_id           BIGINT,                         -- attached during cluster_issues; nullable
    issue_hint         TEXT,                           -- raw hint from extractor before clustering
    source_url         TEXT,
    extracted_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Unique on (source, speaker, leading 200 chars of quote) — must be an
-- expression index because Postgres doesn't accept function calls inside
-- inline UNIQUE constraints.
CREATE UNIQUE INDEX IF NOT EXISTS cm_quotes_unique_idx
    ON cm_spokesperson_quotes (source_kind, source_id, speaker, (left(quote, 200)));

CREATE INDEX IF NOT EXISTS cm_quotes_extracted_idx
    ON cm_spokesperson_quotes (extracted_at DESC);

CREATE INDEX IF NOT EXISTS cm_quotes_speaker_idx
    ON cm_spokesperson_quotes (speaker_canonical, extracted_at DESC)
    WHERE speaker_canonical IS NOT NULL;

CREATE INDEX IF NOT EXISTS cm_quotes_issue_idx
    ON cm_spokesperson_quotes (issue_id, extracted_at DESC)
    WHERE issue_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS cm_quotes_party_idx
    ON cm_spokesperson_quotes (state, party, extracted_at DESC);

COMMENT ON TABLE cm_spokesperson_quotes IS
  'CM Page: speaker NER output. One row per detected attributed quote.';
