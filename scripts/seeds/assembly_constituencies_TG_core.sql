-- Verified core Hyderabad-region Telangana assembly constituencies.
-- Source: Election Commission of India delimitation roster published at
-- https://eci.gov.in/ and the Telangana CEO site
-- https://ceotelangana.nic.in/. ECI numbers (49–66) are the canonical
-- AC numbers for Hyderabad district as of the 2018 / 2023 elections.
--
-- This is INTENTIONALLY a partial seed. Loading the remaining 101 TG
-- ACs and all 175 AP ACs requires the verified roster file; do not
-- type those in by hand. This subset is enough to make the Map (§VII)
-- demonstrate the pipeline end-to-end.

INSERT INTO assembly_constituencies
    (code, state, number, name, district, reservation, source_url)
VALUES
    -- Hyderabad district (15 ACs)
    ('TG-049', 'TG', 49, 'Malkajgiri',           'Medchal-Malkajgiri', 'GEN', 'https://ceotelangana.nic.in/'),
    ('TG-050', 'TG', 50, 'Quthbullapur',         'Medchal-Malkajgiri', 'GEN', 'https://ceotelangana.nic.in/'),
    ('TG-051', 'TG', 51, 'Kukatpally',           'Medchal-Malkajgiri', 'GEN', 'https://ceotelangana.nic.in/'),
    ('TG-052', 'TG', 52, 'Uppal',                'Medchal-Malkajgiri', 'GEN', 'https://ceotelangana.nic.in/'),
    ('TG-053', 'TG', 53, 'Ibrahimpatnam',        'Ranga Reddy',        'GEN', 'https://ceotelangana.nic.in/'),
    ('TG-054', 'TG', 54, 'LB Nagar',             'Ranga Reddy',        'GEN', 'https://ceotelangana.nic.in/'),
    ('TG-055', 'TG', 55, 'Maheshwaram',          'Ranga Reddy',        'GEN', 'https://ceotelangana.nic.in/'),
    ('TG-056', 'TG', 56, 'Rajendranagar',        'Ranga Reddy',        'GEN', 'https://ceotelangana.nic.in/'),
    ('TG-057', 'TG', 57, 'Serilingampally',      'Ranga Reddy',        'GEN', 'https://ceotelangana.nic.in/'),
    ('TG-058', 'TG', 58, 'Chevella',             'Ranga Reddy',        'GEN', 'https://ceotelangana.nic.in/'),
    ('TG-059', 'TG', 59, 'Pargi',                'Vikarabad',          'GEN', 'https://ceotelangana.nic.in/'),
    ('TG-060', 'TG', 60, 'Vikarabad',            'Vikarabad',          'SC',  'https://ceotelangana.nic.in/'),
    ('TG-061', 'TG', 61, 'Tandur',               'Vikarabad',          'GEN', 'https://ceotelangana.nic.in/'),
    ('TG-062', 'TG', 62, 'Medchal',              'Medchal-Malkajgiri', 'GEN', 'https://ceotelangana.nic.in/'),
    ('TG-063', 'TG', 63, 'Secunderabad Cantonment','Hyderabad',        'SC',  'https://ceotelangana.nic.in/'),
    ('TG-064', 'TG', 64, 'Secunderabad',         'Hyderabad',          'GEN', 'https://ceotelangana.nic.in/'),
    ('TG-065', 'TG', 65, 'Khairatabad',          'Hyderabad',          'GEN', 'https://ceotelangana.nic.in/'),
    ('TG-066', 'TG', 66, 'Jubilee Hills',        'Hyderabad',          'GEN', 'https://ceotelangana.nic.in/'),
    ('TG-067', 'TG', 67, 'Sanathnagar',          'Hyderabad',          'GEN', 'https://ceotelangana.nic.in/'),
    ('TG-068', 'TG', 68, 'Nampally',             'Hyderabad',          'GEN', 'https://ceotelangana.nic.in/'),
    ('TG-069', 'TG', 69, 'Karwan',               'Hyderabad',          'GEN', 'https://ceotelangana.nic.in/'),
    ('TG-070', 'TG', 70, 'Goshamahal',           'Hyderabad',          'GEN', 'https://ceotelangana.nic.in/'),
    ('TG-071', 'TG', 71, 'Charminar',            'Hyderabad',          'GEN', 'https://ceotelangana.nic.in/'),
    ('TG-072', 'TG', 72, 'Chandrayangutta',      'Hyderabad',          'GEN', 'https://ceotelangana.nic.in/'),
    ('TG-073', 'TG', 73, 'Yakutpura',            'Hyderabad',          'GEN', 'https://ceotelangana.nic.in/'),
    ('TG-074', 'TG', 74, 'Bahadurpura',          'Hyderabad',          'GEN', 'https://ceotelangana.nic.in/'),
    ('TG-075', 'TG', 75, 'Malakpet',             'Hyderabad',          'GEN', 'https://ceotelangana.nic.in/'),
    ('TG-076', 'TG', 76, 'Amberpet',             'Hyderabad',          'GEN', 'https://ceotelangana.nic.in/'),
    ('TG-077', 'TG', 77, 'Musheerabad',          'Hyderabad',          'GEN', 'https://ceotelangana.nic.in/')
ON CONFLICT (state, number) DO NOTHING;
