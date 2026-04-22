-- 013_seed_parliament.sql
-- Phase 3 / Agent C4: seed Parliament-of-India document portals.
-- Six central-government parliamentary sources (5 sansad.in + 1 PRS).

INSERT INTO govt_document_sources (name, portal_url, source_geography, document_type, is_active)
VALUES
    ('Lok Sabha Q&A',          'https://sansad.in/ls/questions/questions-and-answers',  'CENTRAL', 'lok_sabha_question', TRUE),
    ('Lok Sabha Bills',        'https://sansad.in/ls/legislation/bills-introduced',     'CENTRAL', 'bill',               TRUE),
    ('Rajya Sabha Bills',      'https://sansad.in/rs/legislation/bills-pending',        'CENTRAL', 'bill',               TRUE),
    ('Rajya Sabha Debates',    'https://sansad.in/rs/proceedings/synopsis',             'CENTRAL', 'rs_debate',          TRUE),
    ('Parl. Committee Reports','https://sansad.in/ls/committees/committee-reports',     'CENTRAL', 'committee_report',   TRUE),
    ('PRS Bill Tracker',       'https://prsindia.org/billtrack',                        'CENTRAL', 'bill',               TRUE)
ON CONFLICT DO NOTHING;
