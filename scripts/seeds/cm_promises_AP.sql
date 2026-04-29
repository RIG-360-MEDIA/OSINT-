-- AP NDA "Super Six" — pledges of the Telugu Desam Party-led NDA
-- alliance (TDP + JSP + BJP) carried into the AP 2024 election and
-- forming the operating contract of the Naidu ministry sworn in on
-- 12 June 2024.
--
-- Verify each source_url before treating these as live tracker rows;
-- replace with the official manifesto PDF when located.
--
-- Apply via: docker exec -i rig-postgres psql -U rig -d rig
--                          < scripts/seeds/cm_promises_AP.sql

INSERT INTO cm_promises (
    state, pledge_text, pledge_short, owner_party, source, source_url,
    pledged_at, status
) VALUES
    ('AP',
     'Yuva Galam: Rs 3,000 per month unemployment allowance for educated youth.',
     'Yuva Galam (unemployment allowance)',
     'TDP',
     'TDP 2024 manifesto / Super Six',
     'https://www.telugudesamparty.org/',
     DATE '2024-03-01',
     'unknown'),
    ('AP',
     'Talli ki Vandanam: Rs 15,000 per year per school-going child to mothers.',
     'Talli ki Vandanam (mothers + school)',
     'TDP',
     'TDP 2024 manifesto / Super Six',
     'https://www.telugudesamparty.org/',
     DATE '2024-03-01',
     'unknown'),
    ('AP',
     'Mega DSC: recruitment of teachers in a single mega notification (16,347 posts indicated by manifesto).',
     'Mega DSC (teacher recruitment)',
     'TDP',
     'TDP 2024 manifesto / Super Six',
     'https://www.telugudesamparty.org/',
     DATE '2024-03-01',
     'unknown'),
    ('AP',
     'Free public transport for women across APSRTC services.',
     'Free bus travel for women',
     'TDP',
     'TDP 2024 manifesto / Super Six',
     'https://www.telugudesamparty.org/',
     DATE '2024-03-01',
     'unknown'),
    ('AP',
     'Pension increase to Rs 4,000 per month for the elderly, single women, and persons with disabilities.',
     'Enhanced social pension',
     'TDP',
     'TDP 2024 manifesto / Super Six',
     'https://www.telugudesamparty.org/',
     DATE '2024-03-01',
     'unknown'),
    ('AP',
     'Annadata Sukhibhava: Rs 20,000 per year per farmer family combining state and PM-Kisan support.',
     'Annadata Sukhibhava (farmer support)',
     'TDP',
     'TDP 2024 manifesto / Super Six',
     'https://www.telugudesamparty.org/',
     DATE '2024-03-01',
     'unknown')
ON CONFLICT DO NOTHING;
