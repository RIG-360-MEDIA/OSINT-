-- ============================================================
-- Migration 044 — article_contradictions + event_dissent
-- ============================================================
-- article_contradictions: per-claim divergence between two
-- articles, found by Groq-as-NLI pass over claims about the
-- same entity within 48h.
--
-- event_dissent: cross-source sentiment divergence on the same
-- event_id. Variance across 3+ sources > 0.7 → flag.
--
-- Idempotent — safe to re-run.
-- ============================================================

CREATE TABLE IF NOT EXISTS article_contradictions (
    id                      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    -- The two claims that diverge.
    claim_a_id              UUID        NOT NULL
                                        REFERENCES article_claims(id) ON DELETE CASCADE,
    claim_b_id              UUID        NOT NULL
                                        REFERENCES article_claims(id) ON DELETE CASCADE,
    -- Denormalized for fast filter (entity that both claims are about).
    entity_id               UUID        REFERENCES entity_dictionary(id),
    -- Plain-English summary of WHY they contradict, written by Groq.
    divergence_summary      TEXT        NOT NULL,
    -- 0–1: how confident the model is the claims actually conflict.
    confidence              REAL        NOT NULL DEFAULT 0.5,
    detected_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    detected_by_model       TEXT        NOT NULL DEFAULT 'llama-3.3-70b-versatile',
    -- Set TRUE when a third source corroborates one side, ending the dispute.
    is_resolved             BOOLEAN     NOT NULL DEFAULT FALSE,
    -- Prevent duplicate (a,b) and reversed (b,a) entries.
    CONSTRAINT article_contradictions_pair_chk
      CHECK (claim_a_id < claim_b_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS article_contradictions_pair_uniq_idx
  ON article_contradictions (claim_a_id, claim_b_id);
CREATE INDEX IF NOT EXISTS article_contradictions_entity_idx
  ON article_contradictions (entity_id, detected_at DESC)
  WHERE is_resolved = FALSE;
CREATE INDEX IF NOT EXISTS article_contradictions_detected_at_idx
  ON article_contradictions (detected_at DESC);

COMMENT ON TABLE article_contradictions IS
  'Per-claim divergence between two articles. Groq-as-NLI flagged. Powers Contradictions inbox.';


-- ── Event-level dissent (cross-source sentiment divergence) ──
CREATE TABLE IF NOT EXISTS event_dissent (
    id                      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    -- References story_threads(id) when set; raw cluster_id otherwise.
    thread_id               UUID,
    breaking_cluster_id     UUID        REFERENCES breaking_clusters(id),
    -- JSONB array of { article_id, source_name, source_tier, sentiment, framing }.
    sources                 JSONB       NOT NULL,
    -- Variance score across the source sentiments.
    sentiment_variance      REAL        NOT NULL DEFAULT 0.0,
    -- Plain-English Groq paragraph: "X frames it as A; Y as B; here's why".
    framing_summary         TEXT        NOT NULL,
    detected_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    detected_by_model       TEXT        NOT NULL DEFAULT 'llama-3.3-70b-versatile'
);

CREATE INDEX IF NOT EXISTS event_dissent_thread_idx
  ON event_dissent (thread_id) WHERE thread_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS event_dissent_cluster_idx
  ON event_dissent (breaking_cluster_id) WHERE breaking_cluster_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS event_dissent_detected_at_idx
  ON event_dissent (detected_at DESC);

COMMENT ON TABLE event_dissent IS
  'Cross-source sentiment-divergence flags. Powers Dissent detector chips on event cards.';
