-- Migration 011: Seed central-regulator portals into govt_document_sources.
--
-- Owned by Phase-3 agent C2. Adds eight central regulators whose scrapers live
-- in backend/collectors/sources/central_regulators.py and are dispatched by
-- backend/collectors/govt_collector.fetch_document_urls via the
-- @register_source(url_substring) decorator.
--
-- Idempotent — ON CONFLICT DO NOTHING guards against repeated runs.

INSERT INTO govt_document_sources (name, portal_url, source_geography, document_type, is_active)
VALUES
    ('RBI Circulars',         'https://www.rbi.org.in/Scripts/BS_CircularIndexDisplay.aspx', 'CENTRAL', 'rbi_circular',     TRUE),
    ('RBI Press Releases',    'https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx',  'CENTRAL', 'press_release',    TRUE),
    ('SEBI Orders',           'https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=1&ssid=6&smid=0', 'CENTRAL', 'sebi_order', TRUE),
    ('CCI Orders',            'https://www.cci.gov.in/antitrust/orders',                     'CENTRAL', 'cci_order',        TRUE),
    ('IRDAI Circulars',       'https://irdai.gov.in/circulars',                              'CENTRAL', 'irdai_circular',   TRUE),
    ('TRAI Press Releases',   'https://www.trai.gov.in/notifications/press-release',         'CENTRAL', 'trai_order',       TRUE),
    ('CERC Orders',           'https://cercind.gov.in/ord_curr.html',                        'CENTRAL', 'cerc_order',       TRUE),
    ('PNGRB Notifications',   'https://www.pngrb.gov.in/eng/regulations.html',               'CENTRAL', 'pngrb_notification', TRUE)
ON CONFLICT DO NOTHING;
