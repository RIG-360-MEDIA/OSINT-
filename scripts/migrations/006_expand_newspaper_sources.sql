-- P16 Cutting Room — Phase 2 fixes
--
-- 1. Correct wrong CareersWave URLs found in migration 005:
--    - The Hindu real URL is /the-hindu-epaper-pdf-download-for-upsc/
--      (the -free-download variant returns 404)
--    - Telangana Today real slug differs too.
-- 2. Seed the full CareersWave catalog (40+ papers across 10 languages)
--    so the pipeline can pull "all types" of newspapers, not just 6.
--
-- Idempotent: uses ON CONFLICT (name) DO UPDATE — safe to re-run.

-- Make sure name is unique so ON CONFLICT works.
ALTER TABLE newspaper_sources
    ADD CONSTRAINT newspaper_sources_name_unique UNIQUE (name);

-- Telugu (highest priority for this user)
INSERT INTO newspaper_sources (name, language, careerswave_url, is_active) VALUES
    ('Eenadu',           'te', 'https://www.careerswave.in/eenadu-epaper-pdf-free-download/',           TRUE),
    ('Sakshi',           'te', 'https://www.careerswave.in/sakshi-epaper-pdf-free-download/',           TRUE),
    ('Mana Telangana',   'te', 'https://www.careerswave.in/mana-telangana-epaper-pdf-free-download/',   TRUE),
    ('Manam',            'te', 'https://www.careerswave.in/manam-newspaper-p2024-free-pdf/',            TRUE),
    ('Andhra Jyothi',    'te', 'https://www.careerswave.in/andhra-jyothi-epaper-pdf-free-download/',    TRUE),
    ('Namaste Telangana','te', 'https://www.careerswave.in/namaste-telangana-epaper-pdf-free-download/',TRUE)
ON CONFLICT (name) DO UPDATE SET
    careerswave_url = EXCLUDED.careerswave_url,
    is_active       = EXCLUDED.is_active,
    language        = EXCLUDED.language;

-- English (national + Hyderabad regional)
INSERT INTO newspaper_sources (name, language, careerswave_url, is_active) VALUES
    ('The Hindu',         'en', 'https://www.careerswave.in/the-hindu-epaper-pdf-download-for-upsc/',       TRUE),
    ('Times of India',    'en', 'https://www.careerswave.in/times-of-india-epaper-pdf-free-download/',       TRUE),
    ('Hindustan Times',   'en', 'https://www.careerswave.in/hindustan-times-epaper-pdf-free-download/',      TRUE),
    ('Indian Express',    'en', 'https://www.careerswave.in/indian-express-epaper-pdf-free-download/',       TRUE),
    ('Economic Times',    'en', 'https://www.careerswave.in/economic-times-epaper-pdf-free-download/',       TRUE),
    ('Business Line',     'en', 'https://www.careerswave.in/business-line-epaper-pdf-free-download/',        TRUE),
    ('Business Standard', 'en', 'https://www.careerswave.in/business-standard-newspaper-in-pdf/',            TRUE),
    ('The Telegraph',     'en', 'https://www.careerswave.in/telegraph-epaper-pdf-free-download/',            TRUE),
    ('Mint',              'en', 'https://www.careerswave.in/mint-epaper-pdf-free-download/',                 TRUE),
    ('Financial Express', 'en', 'https://www.careerswave.in/the-financial-express-epaper-pdf-free-download/',TRUE),
    ('Deccan Chronicle',  'en', 'https://www.careerswave.in/deccan-chronicle-epaper-pdf-free-download/',     TRUE),
    ('Deccan Herald',     'en', 'https://www.careerswave.in/deccan-herald-epaper-p2024-free-pdf/',           TRUE),
    ('Telangana Today',   'en', 'https://www.careerswave.in/telangana-today-epaper-pdf-free-download/',      TRUE),
    ('Greater Kashmir',   'en', 'https://www.careerswave.in/greater-kashmir-epaper-pdf-free-download/',      TRUE),
    ('Nagaland Post',     'en', 'https://www.careerswave.in/nagaland-post-epaper-pdf-down/',                 TRUE),
    ('O Heraldo',         'en', 'https://www.careerswave.in/o-heraldo-epaper-pdf-free-download/',            TRUE)
ON CONFLICT (name) DO UPDATE SET
    careerswave_url = EXCLUDED.careerswave_url,
    is_active       = EXCLUDED.is_active,
    language        = EXCLUDED.language;

-- Hindi
INSERT INTO newspaper_sources (name, language, careerswave_url, is_active) VALUES
    ('Dainik Jagran',     'hi', 'https://www.careerswave.in/dainik-jagran-epaper-pdf-free-download/',     TRUE),
    ('Dainik Bhaskar',    'hi', 'https://www.careerswave.in/dainik-bhaskar-epaper-pdf-free-download/',    TRUE),
    ('Amar Ujala',        'hi', 'https://www.careerswave.in/amar-ujala-epaper-pdf-free-download/',        TRUE),
    ('Punjab Kesari',     'hi', 'https://www.careerswave.in/punjab-kesari-epaper-pdf-free-download/',     TRUE),
    ('Navbharat Times',   'hi', 'https://www.careerswave.in/navbharat-times-epaper-pdf-free-download/',   TRUE),
    ('Jansatta',          'hi', 'https://www.careerswave.in/jansatta-epaper-pdf-free-download/',          TRUE),
    ('Hindustan',         'hi', 'https://www.careerswave.in/hindustan-epaper-pdf-free-download/',         TRUE),
    ('Prabhat Khabar',    'hi', 'https://www.careerswave.in/prabhat-khabar-epaper-pdf-free-download/',    TRUE),
    ('Rashtriya Sahara',  'hi', 'https://www.careerswave.in/rashtriya-sahara-epaper-pdf-free-download/',  TRUE),
    ('Dainik Navajyoti',  'hi', 'https://www.careerswave.in/dainik-navajyoti-epaper-pdf-free-download/',  TRUE),
    ('Hari Bhoomi',       'hi', 'https://www.careerswave.in/hari-bhoomi-epaper-pdf-free-download/',       TRUE),
    ('Nai Dunia',         'hi', 'https://www.careerswave.in/nai-dunia-epaper-download/',                  TRUE),
    ('Samachar Jagat',    'hi', 'https://www.careerswave.in/samachar-jagat-epaper-p2024-free-pdf/',       TRUE)
ON CONFLICT (name) DO UPDATE SET
    careerswave_url = EXCLUDED.careerswave_url,
    is_active       = EXCLUDED.is_active,
    language        = EXCLUDED.language;

-- Regional — Tamil, Kannada, Malayalam, Marathi, Bengali, Gujarati, Punjabi
INSERT INTO newspaper_sources (name, language, careerswave_url, is_active) VALUES
    ('Daily Thanthi',     'ta', 'https://www.careerswave.in/daily-thanthi-epaper-pdf-free-download/',     TRUE),
    ('Dinamalar',         'ta', 'https://www.careerswave.in/dinamalar-epaper-pdf-free-download/',         TRUE),
    ('Dinamani',          'ta', 'https://www.careerswave.in/dinamani-epaper-pdf-free-download/',          TRUE),
    ('Udayavani',         'kn', 'https://www.careerswave.in/udayavani-epaper-pdf-free-download/',         TRUE),
    ('Prajavani',         'kn', 'https://www.careerswave.in/prajavani-epaper-pdf-free-download/',         TRUE),
    ('Vijaya Karnataka',  'kn', 'https://www.careerswave.in/vijaya-karnataka-newspaper-p2024-free-pdf/',  TRUE),
    ('Malayala Manorama', 'ml', 'https://www.careerswave.in/malayala-manorama-epaper-pdf-free-download/', TRUE),
    ('Mathrubhumi',       'ml', 'https://www.careerswave.in/mathrubhumi-epaper-pdf-free-download/',       TRUE),
    ('Loksatta',          'mr', 'https://www.careerswave.in/loksatta-epaper-pdf-free-download/',          TRUE),
    ('Maharashtra Times', 'mr', 'https://www.careerswave.in/maharashtra-times-epaper-pdf-free-download/', TRUE),
    ('Anandabazar',       'bn', 'https://www.careerswave.in/anandabazar-epaper-pdf-free-download/',       TRUE),
    ('Bartaman',          'bn', 'https://www.careerswave.in/bartaman-epaper-pdf-free-download/',          TRUE),
    ('Gujarat Samachar',  'gu', 'https://www.careerswave.in/gujarat-samachar-epaper-pdf-free-download/',  TRUE),
    ('Divya Bhaskar',     'gu', 'https://www.careerswave.in/divya-bhaskar-epaper-pdf-free-download/',     TRUE),
    ('Ajit',              'pa', 'https://www.careerswave.in/ajit-epaper-pdf-free-download/',              TRUE)
ON CONFLICT (name) DO UPDATE SET
    careerswave_url = EXCLUDED.careerswave_url,
    is_active       = EXCLUDED.is_active,
    language        = EXCLUDED.language;
