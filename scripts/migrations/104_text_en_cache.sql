-- 104_text_en_cache.sql
-- Translation cache for the bilingual rule (2026-06-04). The corpus's stored
-- 'translations' are unreliable (lead_text_translated is still Telugu for ~84% of
-- te articles), so any non-English text shown in the UI (headlines, quotes, claims,
-- timeline) is translated to English via i18n.py (free Google endpoint over httpx)
-- and cached here by md5(source) so each string is translated only once. Idempotent.

CREATE TABLE IF NOT EXISTS analytics.text_en (
  src_hash   text PRIMARY KEY,
  text_en    text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE, DELETE ON analytics.text_en TO analytics_user;
