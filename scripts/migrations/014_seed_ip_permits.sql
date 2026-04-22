-- Migration 014 — seed IP / regulatory permit portals (Agent C5).
-- Adds central-government IP, corporate, food-safety, and drug-regulatory
-- portals to govt_document_sources. Idempotent via ON CONFLICT DO NOTHING.

INSERT INTO govt_document_sources (name, portal_url, source_geography, document_type, is_active)
VALUES
    ('IP India Patents',     'https://ipindia.gov.in/recently-granted-patents.htm', 'CENTRAL', 'patent',           TRUE),
    ('IP India Trademarks',  'https://ipindia.gov.in/journal-tm.htm',               'CENTRAL', 'trademark',        TRUE),
    ('IP India GI Tags',     'https://ipindia.gov.in/recent-news-gi.htm',           'CENTRAL', 'gi_tag',           TRUE),
    ('MCA Notifications',    'https://www.mca.gov.in/MinistryV2/notifications.html','CENTRAL', 'mca_notification', TRUE),
    ('FSSAI Notifications',  'https://fssai.gov.in/cms/notifications.php',          'CENTRAL', 'fssai_notification',TRUE),
    ('CDSCO Notifications',  'https://cdsco.gov.in/opencms/opencms/en/Notifications/Notice/', 'CENTRAL', 'cdsco_notification', TRUE)
ON CONFLICT DO NOTHING;
