-- 064_article_links.sql
-- Outbound links extracted from each article's body. Powers the citation
-- graph (1A) and cross-source dedup (canonical_url comparison).

BEGIN;

CREATE TABLE IF NOT EXISTS article_links (
  id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  article_id               uuid NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
  outbound_url             text NOT NULL,
  outbound_url_normalized  text,
  outbound_domain          text,
  anchor_text              text,
  link_type                text,             -- 'external' | 'internal' | 'image' | 'video'
  position                 smallint,
  created_at               timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_article_links_article
  ON article_links(article_id);
CREATE INDEX IF NOT EXISTS idx_article_links_normalized
  ON article_links(outbound_url_normalized);
CREATE INDEX IF NOT EXISTS idx_article_links_domain
  ON article_links(outbound_domain);

COMMIT;
