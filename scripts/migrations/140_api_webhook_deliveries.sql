-- Webhook delivery: a log of every delivery attempt + a consecutive-failure counter.
-- Idempotent. The delivery worker (v1/webhook_delivery.py, run by cron) reads active
-- api_webhooks, POSTs new matching coverage HMAC-signed, and records here.

CREATE TABLE IF NOT EXISTS analytics.api_webhook_deliveries (
  id            bigserial PRIMARY KEY,
  webhook_id    uuid NOT NULL,
  event         text NOT NULL,
  item_id       uuid,
  status        text NOT NULL,            -- delivered | failed
  response_code int,
  attempts      int  NOT NULL DEFAULT 1,
  error         text,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS api_webhook_deliveries_wid_idx
  ON analytics.api_webhook_deliveries(webhook_id, created_at DESC);

-- api_webhooks already has failure_count + last_delivered_at (watermark); ensure grants.
GRANT SELECT, INSERT ON analytics.api_webhook_deliveries TO analytics_user;
GRANT USAGE, SELECT ON SEQUENCE analytics.api_webhook_deliveries_id_seq TO analytics_user;
GRANT UPDATE ON analytics.api_webhooks TO analytics_user;
