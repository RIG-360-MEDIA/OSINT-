-- 018_dossier.sql
-- Dossier feature tables. Pure additive — no FKs to existing tables, no triggers
-- that mutate other schemas. Safe to drop wholesale by `DROP TABLE` if disabled.
-- All names prefixed/scoped to make accidental collision impossible.

CREATE TABLE IF NOT EXISTS entity_dossier (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         TEXT NOT NULL,
    target          TEXT NOT NULL,
    target_type     TEXT NOT NULL CHECK (target_type IN (
                        'name','email','phone','username','domain','image'
                    )),
    status          TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
                        'pending','running','completed','failed','partial'
                    )),
    summary         JSONB,
    error           TEXT,
    purpose_note    TEXT,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_entity_dossier_user
    ON entity_dossier (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_entity_dossier_target
    ON entity_dossier (target_type, target);


CREATE TABLE IF NOT EXISTS dossier_finding (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dossier_id      UUID NOT NULL REFERENCES entity_dossier(id) ON DELETE CASCADE,
    source          TEXT NOT NULL,
    field           TEXT NOT NULL,
    value           JSONB NOT NULL,
    source_url      TEXT,
    confidence      REAL NOT NULL DEFAULT 0.8 CHECK (confidence >= 0 AND confidence <= 1),
    found_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dossier_finding_dossier
    ON dossier_finding (dossier_id);

CREATE INDEX IF NOT EXISTS idx_dossier_finding_source
    ON dossier_finding (source);


CREATE TABLE IF NOT EXISTS dossier_cache (
    cache_key       TEXT PRIMARY KEY,
    source          TEXT NOT NULL,
    target_hash     TEXT NOT NULL,
    payload         JSONB NOT NULL,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dossier_cache_expiry
    ON dossier_cache (expires_at);


CREATE TABLE IF NOT EXISTS dossier_audit_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         TEXT NOT NULL,
    dossier_id      UUID,
    action          TEXT NOT NULL,
    target          TEXT,
    purpose_note    TEXT,
    metadata        JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dossier_audit_user
    ON dossier_audit_log (user_id, created_at DESC);
