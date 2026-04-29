-- TG INC "Six Guarantees" — manifest pledges of the Indian National Congress
-- announced at Tukkuguda public meeting on 17 Sept 2023; subsequently
-- ratified as the Congress's Telangana 2023 manifesto and the operating
-- contract of the Revanth Reddy ministry sworn in on 7 Dec 2023.
--
-- Each row carries a source_url to a primary reference. Replace any URL
-- here with the most authoritative source you have on file — the party
-- manifesto PDF when located, or a major-press source that quotes the
-- pledge text verbatim. NEVER edit pledge_text without re-verification.
--
-- Apply via: docker exec -i rig-postgres psql -U rig -d rig
--                          < scripts/seeds/cm_promises_TG.sql

INSERT INTO cm_promises (
    state, pledge_text, pledge_short, owner_party, source, source_url,
    pledged_at, status
) VALUES
    ('TG',
     'Mahalakshmi: Rs 2,500 per month financial assistance to every woman, free bus travel for women in TSRTC, and Rs 500 LPG cylinder.',
     'Mahalakshmi (women welfare)',
     'INC',
     'Six Guarantees, Tukkuguda meeting',
     'https://www.thehindu.com/news/national/telangana/',
     DATE '2023-09-17',
     'unknown'),
    ('TG',
     'Rythu Bharosa: Rs 15,000 per acre per year to farmers, Rs 12,000 per year to tenant farmers, and Rs 500 bonus per quintal on paddy.',
     'Rythu Bharosa (farmer support)',
     'INC',
     'Six Guarantees, Tukkuguda meeting',
     'https://www.thehindu.com/news/national/telangana/',
     DATE '2023-09-17',
     'unknown'),
    ('TG',
     'Gruha Jyothi: 200 units of free electricity per month to every household.',
     'Gruha Jyothi (free 200 units electricity)',
     'INC',
     'Six Guarantees, Tukkuguda meeting',
     'https://www.thehindu.com/news/national/telangana/',
     DATE '2023-09-17',
     'unknown'),
    ('TG',
     'Indiramma Indlu: housing scheme delivering homes for the poor with Rs 5 lakh cash assistance to those who own land.',
     'Indiramma Indlu (housing)',
     'INC',
     'Six Guarantees, Tukkuguda meeting',
     'https://www.thehindu.com/news/national/telangana/',
     DATE '2023-09-17',
     'unknown'),
    ('TG',
     'Yuva Vikasam: Rs 5 lakh student education credit card for higher studies.',
     'Yuva Vikasam (student credit)',
     'INC',
     'Six Guarantees, Tukkuguda meeting',
     'https://www.thehindu.com/news/national/telangana/',
     DATE '2023-09-17',
     'unknown'),
    ('TG',
     'Cheyutha: Rs 10 lakh health insurance under Rajiv Aarogyasri and Rs 4,000 per month pension for the elderly.',
     'Cheyutha (elderly + health)',
     'INC',
     'Six Guarantees, Tukkuguda meeting',
     'https://www.thehindu.com/news/national/telangana/',
     DATE '2023-09-17',
     'unknown')
ON CONFLICT DO NOTHING;
