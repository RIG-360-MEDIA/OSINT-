-- 012_seed_courts.sql
-- Phase 3, Agent C3: Seed Courts & Tribunals document sources.
-- Adapters live in backend/collectors/sources/courts.py and are registered
-- via @register_source decorators (URL-substring → async scraper).
--
-- eCourts is seeded with is_active=FALSE because it requires per-case
-- search forms (CNR / case-number) behind CAPTCHA — not crawlable as a
-- flat list. The stub adapter is registered so lookups don't fall through
-- to the generic scraper, but the row stays inactive until someone wires
-- a per-case query producer.

INSERT INTO govt_document_sources (name, portal_url, source_geography, document_type, is_active)
VALUES
    ('Supreme Court of India', 'https://main.sci.gov.in/judgments',                   'CENTRAL', 'judgment',     TRUE),
    ('NCLT',                   'https://nclt.gov.in/order-judgement-date-wise',       'CENTRAL', 'nclt_order',   TRUE),
    ('NCLAT',                  'https://nclat.nic.in/?page_id=10',                    'CENTRAL', 'nclat_order',  TRUE),
    ('NGT',                    'https://greentribunal.gov.in/orders-judgements',      'CENTRAL', 'ngt_order',    TRUE),
    ('eCourts (stub)',         'https://services.ecourts.gov.in/ecourtindia_v6/',     'CENTRAL', 'ecourts',      FALSE)
ON CONFLICT DO NOTHING;
