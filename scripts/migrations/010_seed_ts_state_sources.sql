-- 010_seed_ts_state_sources.sql
-- Phase 3 / Agent C1: seed Telangana state portal sources.
--
-- TS GOIR is already covered by an earlier migration / built-in scraper, so
-- it's intentionally omitted here. The remaining seven portals get inserted
-- with source_geography = 'LOCAL'.
--
-- ON CONFLICT DO NOTHING keeps the migration idempotent — re-running it is
-- safe even if a row was added manually.

INSERT INTO govt_document_sources (name, portal_url, source_geography, document_type, is_active)
VALUES
    ('TS Gazette',            'https://gad.telangana.gov.in/Gazette',                       'LOCAL', 'gazette',      TRUE),
    ('TGERC Tariff Orders',   'https://tserc.gov.in/file_upload/uploads/Tariff%20Orders/',  'LOCAL', 'tariff_order', TRUE),
    ('TS-iPASS',              'https://ipass.telangana.gov.in/',                            'LOCAL', 'clearance',    TRUE),
    ('TSPSC Notifications',   'https://www.tspsc.gov.in/notifications.html',                'LOCAL', 'notification', TRUE),
    ('GHMC Tenders',          'https://ghmc.gov.in/tenders.aspx',                           'LOCAL', 'tender',       TRUE),
    ('HMDA Notifications',    'https://www.hmda.gov.in/circulars-and-notifications/',       'LOCAL', 'notification', TRUE),
    ('eProcurement Telangana','https://tender.telangana.gov.in/',                           'LOCAL', 'tender',       TRUE)
ON CONFLICT DO NOTHING;
