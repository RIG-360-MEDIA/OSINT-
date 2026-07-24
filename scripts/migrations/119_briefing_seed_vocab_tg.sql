-- 119_briefing_seed_vocab_tg.sql
--
-- Seed the closed vocabularies for the Telangana I&PR tenant:
-- departments (24), topics (11), schemes (flagship + variants + Telugu +
-- disambiguation). org = Telangana CM & Government.
--
-- Translation finding (2026-07-24): machine translation renders a Telugu
-- minister name in English only ~79% of the time (104/131 for "Revanth"),
-- while matching the Telugu spelling on the original text catches 100%.
-- Hence telugu_names / telugu variants are populated here and matter.
-- Telugu spellings below are first-pass — flagged for client verification.

\set org '31ad3fa9-25eb-4b3c-8a56-360696fc680a'

-- ── Departments (closed list for lands_on) ──────────────────────────────────
INSERT INTO briefing.departments (org_id, name) VALUES
  (:'org','Agriculture'),
  (:'org','Animal Husbandry'),
  (:'org','Civil Supplies'),
  (:'org','Education'),
  (:'org','Endowments'),
  (:'org','Energy'),
  (:'org','Environment & Forests'),
  (:'org','Finance'),
  (:'org','General Administration'),
  (:'org','Health & Family Welfare'),
  (:'org','Home'),
  (:'org','Industries & Commerce'),
  (:'org','Information Technology'),
  (:'org','Irrigation (I&CAD)'),
  (:'org','Labour & Employment'),
  (:'org','Municipal Administration & Urban Development'),
  (:'org','Panchayat Raj & Rural Development'),
  (:'org','Revenue'),
  (:'org','Roads & Buildings'),
  (:'org','Social Welfare'),
  (:'org','Transport'),
  (:'org','Tribal Welfare'),
  (:'org','Women & Child Welfare'),
  (:'org','Youth Affairs')
ON CONFLICT (org_id, name) DO NOTHING;

-- ── Topics (11: client 9 + Law&Order + Employment/Exams) ────────────────────
INSERT INTO briefing.topics (org_id, name, sort_order) VALUES
  (:'org','Politics',1),
  (:'org','Governance',2),
  (:'org','Security',3),
  (:'org','Law & Order',4),
  (:'org','Infrastructure',5),
  (:'org','Health',6),
  (:'org','Agriculture',7),
  (:'org','Social',8),
  (:'org','Finance',9),
  (:'org','Environment',10),
  (:'org','Employment & Exams',11)
ON CONFLICT (org_id, name) DO NOTHING;

-- ── Schemes (flagship; variants + Telugu + disambiguation) ──────────────────
-- disambiguation_terms: for generic names, at least one must co-occur or the
-- match is rejected (Mahalakshmi = goddess/temple; Cheyutha = ordinary word).
INSERT INTO briefing.schemes (org_id, name, department, name_variants, telugu_names, disambiguation_terms) VALUES
  (:'org','Rythu Bharosa','Agriculture',
     ARRAY['Rythu Bharosa','Rythu Bandhu'], ARRAY['రైతు భరోసా','రైతుబంధు'],
     ARRAY['farmer','investment support','per acre','crop']),
  (:'org','Rythu Bima','Agriculture',
     ARRAY['Rythu Bima','crop insurance','farmer insurance'], ARRAY['రైతు బీమా'],
     ARRAY['farmer','insurance','premium']),
  (:'org','Gruha Jyothi','Energy',
     ARRAY['Gruha Jyothi','free power','200 units'], ARRAY['గృహ జ్యోతి'],
     ARRAY['electricity','power','units','bill']),
  (:'org','Indiramma Housing','Housing',
     ARRAY['Indiramma Indlu','Indiramma housing','Indiramma Atmiya Bharosa'], ARRAY['ఇందిరమ్మ ఇళ్లు','ఇందిరమ్మ'],
     ARRAY['house','housing','allotment','beneficiary']),
  (:'org','Mahalakshmi','Transport',
     ARRAY['Mahalakshmi scheme','free bus travel','free bus'], ARRAY['మహాలక్ష్మి'],
     ARRAY['bus','free travel','women','RTC','TSRTC','TGSRTC','scheme']),
  (:'org','Cheyutha','Social Welfare',
     ARRAY['Cheyutha pension','Cheyutha scheme'], ARRAY['చేయూత'],
     ARRAY['pension','scheme','elderly','beneficiary']),
  (:'org','Dalit Bandhu','Social Welfare',
     ARRAY['Dalit Bandhu'], ARRAY['దళిత బంధు'],
     ARRAY['dalit','SC','beneficiary','lakh']),
  (:'org','Yuva Vikasam','Education',
     ARRAY['Yuva Vikasam','Rajiv Yuva Vikasam'], ARRAY['యువ వికాసం'],
     ARRAY['youth','student','scheme']),
  (:'org','Kaleshwaram','Irrigation (I&CAD)',
     ARRAY['Kaleshwaram','Medigadda','Annaram','Sundilla','Kaleshwaram Lift Irrigation'], ARRAY['కాళేశ్వరం','మేడిగడ్డ','అన్నారం','సుందిళ్ల'],
     ARRAY[]::text[]),
  (:'org','Mission Bhagiratha','Panchayat Raj & Rural Development',
     ARRAY['Mission Bhagiratha','Bhagiratha'], ARRAY['మిషన్ భగీరథ','భగీరథ'],
     ARRAY['water','drinking water','tap','supply']),
  (:'org','Six Guarantees','General Administration',
     ARRAY['Six Guarantees','6 Guarantees','Praja Palana'], ARRAY['ఆరు గ్యారంటీలు','ప్రజా పాలన'],
     ARRAY['guarantee','Congress','promise','manifesto']),
  (:'org','Musi Rejuvenation','Municipal Administration & Urban Development',
     ARRAY['Musi Riverfront','Musi rejuvenation','Musi River'], ARRAY['మూసీ'],
     ARRAY['river','riverfront','Hyderabad','development'])
ON CONFLICT (org_id, name) DO NOTHING;

SELECT
  (SELECT count(*) FROM briefing.departments WHERE org_id=:'org') AS departments,
  (SELECT count(*) FROM briefing.topics WHERE org_id=:'org') AS topics,
  (SELECT count(*) FROM briefing.schemes WHERE org_id=:'org') AS schemes;
