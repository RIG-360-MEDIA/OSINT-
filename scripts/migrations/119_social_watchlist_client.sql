-- 119_social_watchlist_client.sql
-- Multi-tenant watchlist: one social_watchlist table serving many products/clients.
-- Adds a `client` tag so each product's collector scrapes ONLY its own rows
-- (india_govt vs tridel vs future clients) — no cross-contamination.
-- Existing rows default to 'india_govt' (the current product).
-- Idempotent.

ALTER TABLE social_watchlist
    ADD COLUMN IF NOT EXISTS client VARCHAR(32) NOT NULL DEFAULT 'india_govt';

-- collectors select by (client, platform, active, due) — index it
CREATE INDEX IF NOT EXISTS idx_social_watchlist_client
    ON social_watchlist (client, platform, is_active, priority, next_check_at);
