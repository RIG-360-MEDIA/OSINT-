-- 015_seed_international.sql
-- Seed international body portals (India-relevant) into govt_document_sources.
-- Owner: Agent C6 / Phase 3.
INSERT INTO govt_document_sources (name, portal_url, source_geography, document_type, is_active)
VALUES
    ('World Bank India',       'https://documents.worldbank.org/en/publication/documents-reports/documentlist?colti=country&colt=india', 'INTERNATIONAL', 'wb_india_report', TRUE),
    ('ADB India',              'https://www.adb.org/where-we-work/india/publications',                          'INTERNATIONAL', 'adb_india_report',      TRUE),
    ('IMF India Reports',      'https://www.imf.org/en/Publications/CR/2024/india',                             'INTERNATIONAL', 'imf_country_report',    TRUE),
    ('UN India',               'https://india.un.org/en/resources/publications',                                'INTERNATIONAL', 'un_india_publication',  TRUE),
    ('ILO India',              'https://www.ilo.org/asia/countries/india/publications/lang--en/index.htm',      'INTERNATIONAL', 'ilo_india_publication', TRUE),
    ('BIS Annual Report',      'https://www.bis.org/publ/arpdf/ar2024e.pdf',                                    'INTERNATIONAL', 'bis_publication',       TRUE)
ON CONFLICT DO NOTHING;
