-- Client scope self-management (Phase 4): mute terms, tracked keywords + priorities,
-- and a management-capability flag on API keys. Idempotent. The client-facing
-- PATCH /v1/scope (management key) and POST /v1/scope/purge read/write these.

ALTER TABLE analytics.org_api_scope ADD COLUMN IF NOT EXISTS mute_terms text[] NOT NULL DEFAULT '{}';
ALTER TABLE analytics.org_api_scope ADD COLUMN IF NOT EXISTS keywords   text[] NOT NULL DEFAULT '{}';
ALTER TABLE analytics.org_api_scope ADD COLUMN IF NOT EXISTS keyword_priorities jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE analytics.api_keys      ADD COLUMN IF NOT EXISTS can_manage boolean NOT NULL DEFAULT false;

GRANT UPDATE, INSERT ON analytics.org_api_scope TO analytics_user;
