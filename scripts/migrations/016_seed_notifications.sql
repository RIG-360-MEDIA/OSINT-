-- 016_seed_notifications.sql
-- Phase 3 Agent C7 — central gazettes & cross-ministry notification feeds.
--
-- e-Gazette is captcha-gated (ASP.NET viewstate + image captcha); the adapter
-- ships in v1 as a noop that logs a warning, and the source is seeded with
-- is_active=FALSE so the scheduler skips it until session-cookie support
-- lands. All other CENTRAL ministry portals are scraped via static HTML.

INSERT INTO govt_document_sources (name, portal_url, source_geography, document_type, is_active)
VALUES
    ('Gazette of India',       'https://egazette.gov.in/WriteReadData/UploadedTOC/',           'CENTRAL', 'gazette',          FALSE),
    ('MoF Notifications',      'https://www.finmin.nic.in/notifications-and-circulars',       'CENTRAL', 'mof_notification', TRUE),
    ('MEA Press Releases',     'https://www.mea.gov.in/press-releases.htm',                   'CENTRAL', 'mea_release',      TRUE),
    ('MoD Press Releases',     'https://mod.gov.in/dod/whats-new',                            'CENTRAL', 'mod_release',      TRUE),
    ('MHA Notifications',      'https://www.mha.gov.in/en/notifications',                     'CENTRAL', 'mha_notification', TRUE),
    ('NITI Aayog Reports',     'https://www.niti.gov.in/reports-publications',                'CENTRAL', 'niti_report',      TRUE),
    ('GeM Circulars',          'https://gem.gov.in/news-and-events',                          'CENTRAL', 'gem_circular',     TRUE)
ON CONFLICT DO NOTHING;
