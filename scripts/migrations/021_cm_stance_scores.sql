-- 021_cm_stance_scores.sql
-- CM Page foundation: stance classification scores for articles, social posts,
-- newspaper clippings, and clips. One row per source item. UPSERT on
-- (source_kind, source_id) so the stance task can re-score safely.
--
-- party_kind is the resolved coalition side (ruling/opposition/neutral) for
-- the user's current state — derived at scoring time from the speaker's party
-- looked up in entity_dictionary plus the per-state coalition map maintained
-- in backend/nlp/cm/coalitions.py. Stored denormalised here so the read path
-- avoids a join.

CREATE TABLE IF NOT EXISTS cm_stance_scores (
    id           BIGSERIAL PRIMARY KEY,
    source_kind  TEXT NOT NULL CHECK (source_kind IN ('article','social_post','clip','clipping')),
    source_id    BIGINT NOT NULL,
    state        TEXT,                                            -- 'TG' / 'AP' / NULL when geo-agnostic
    stance       TEXT NOT NULL CHECK (stance IN ('ruling_supportive','opposition_attack','neutral_factual','mixed','unknown')),
    party        TEXT,                                            -- raw party label from entity_dictionary
    party_kind   TEXT CHECK (party_kind IN ('ruling','opposition','neutral')),
    confidence   REAL NOT NULL DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
    model        TEXT NOT NULL,                                   -- e.g. 'llama-3.1-8b-instant'
    scored_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT cm_stance_unique UNIQUE (source_kind, source_id)
);

CREATE INDEX IF NOT EXISTS cm_stance_scored_at_idx
    ON cm_stance_scores (scored_at DESC);

CREATE INDEX IF NOT EXISTS cm_stance_party_kind_idx
    ON cm_stance_scores (state, party_kind, scored_at DESC);

CREATE INDEX IF NOT EXISTS cm_stance_source_kind_idx
    ON cm_stance_scores (source_kind, scored_at DESC);

COMMENT ON TABLE cm_stance_scores IS
  'CM Page: per-item political stance classification. UPSERT keyed by (source_kind, source_id).';
