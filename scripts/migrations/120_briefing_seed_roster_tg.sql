-- 120_briefing_seed_roster_tg.sql
--
-- Roster for the Telangana I&PR tenant. Curated CORE — the figures who actually
-- appear in coverage (ministers, top opposition) + government institutions.
-- Seeded from the client scope doc (Allies->government, Opposition->opposition,
-- Watched->institution), CLEANED of constituency names ("Achampet (SC)",
-- "Warangal East"...) which never get quoted, and DE-DUPLICATED (KTR appeared as
-- "K. T. Rama Rao" + "K.T. Rama Rao"; Uttam as three spellings) into
-- canonical + name_variants.
--
-- Telugu spellings are first-pass (generated), FLAGGED for DIPR verification.
-- Matching uses English variants on translated text (~79% name recall) AND
-- Telugu names on original text (100% recall) — belt and suspenders, so a
-- slightly-off Telugu spelling still leaves the English path working.
--
-- side: government = ruling Congress ministers/allies; opposition = BRS/BJP/etc;
--       institution = a state body (no party).

\set org '31ad3fa9-25eb-4b3c-8a56-360696fc680a'

INSERT INTO briefing.roster (org_id, canonical_name, side, role, party, name_variants, telugu_names, notes) VALUES
-- ── GOVERNMENT — Congress ministry ────────────────────────────────────────
(:'org','Revanth Reddy','government','Chief Minister','INC',
  ARRAY['A. Revanth Reddy','A Revanth Reddy','Anumula Revanth Reddy','CM Revanth Reddy'],
  ARRAY['రేవంత్ రెడ్డి','రేవంత్','ముఖ్యమంత్రి రేవంత్ రెడ్డి'],'CM'),
(:'org','Bhatti Vikramarka','government','Deputy Chief Minister & Finance','INC',
  ARRAY['Mallu Bhatti Vikramarka','Bhatti','Vikramarka'],
  ARRAY['భట్టి విక్రమార్క','భట్టి','మల్లు భట్టి విక్రమార్క'],'Dy CM, Finance'),
(:'org','Uttam Kumar Reddy','government','Minister for Irrigation & Civil Supplies','INC',
  ARRAY['N. Uttam Kumar Reddy','Nalamada Uttam Kumar Reddy','Uttam'],
  ARRAY['ఉత్తమ్ కుమార్ రెడ్డి','ఉత్తమ్','నలమాడ ఉత్తమ్ కుమార్ రెడ్డి'],'Irrigation'),
(:'org','Komatireddy Venkat Reddy','government','Minister for Roads & Buildings','INC',
  ARRAY['Komati Reddy Venkat Reddy','Venkat Reddy'],ARRAY['కోమటిరెడ్డి వెంకట్ రెడ్డి'],'R&B'),
(:'org','D. Sridhar Babu','government','Minister for IT & Industries','INC',
  ARRAY['Duddilla Sridhar Babu','Sridhar Babu'],ARRAY['శ్రీధర్ బాబు','దుద్దిళ్ల శ్రీధర్ బాబు'],'IT'),
(:'org','Ponnam Prabhakar','government','Minister for Transport','INC',
  ARRAY['Ponnam'],ARRAY['పొన్నం ప్రభాకర్','పొన్నం'],'Transport'),
(:'org','Damodar Raja Narasimha','government','Minister for Health','INC',
  ARRAY['Damodar Rajanarsimha','Raja Narasimha'],ARRAY['దామోదర రాజనరసింహ'],'Health'),
(:'org','Tummala Nageswara Rao','government','Minister for Agriculture','INC',
  ARRAY['Thummala Nageswara Rao','Tummala'],ARRAY['తుమ్మల నాగేశ్వరరావు'],'Agriculture'),
(:'org','Seethakka','government','Minister for Panchayat Raj & Rural Development','INC',
  ARRAY['Dansari Anasuya','Dansari Anasuya Seethakka','Anasuya Seethakka'],ARRAY['సీతక్క','దన్సరి అనసూయ'],'PR&RD'),
(:'org','Konda Surekha','government','Minister for Environment & Endowments','INC',
  ARRAY['Surekha'],ARRAY['కొండా సురేఖ'],'Environment'),
(:'org','Ponguleti Srinivas Reddy','government','Minister for Revenue','INC',
  ARRAY['Ponguleti Srinivasa Reddy','Ponguleti'],ARRAY['పొంగులేటి శ్రీనివాస్ రెడ్డి','పొంగులేటి'],'Revenue'),
(:'org','Jupally Krishna Rao','government','Minister for Excise & Tourism','INC',
  ARRAY['Jupally'],ARRAY['జూపల్లి కృష్ణారావు'],'Excise'),
(:'org','Mahesh Kumar Goud','government','TPCC President','INC',
  ARRAY['B. Mahesh Kumar Goud','Mahesh Goud','PCC chief Mahesh Kumar Goud'],ARRAY['మహేష్ కుమార్ గౌడ్'],'TPCC chief'),
(:'org','Government of Telangana','government','State government','INC',
  ARRAY['Telangana government','state government','Congress government','TG government'],
  ARRAY['తెలంగాణ ప్రభుత్వం','రాష్ట్ర ప్రభుత్వం'],'the govt itself'),
-- ── OPPOSITION — BRS ──────────────────────────────────────────────────────
(:'org','K. Chandrashekar Rao','opposition','BRS President, former CM','BRS',
  ARRAY['KCR','K Chandrashekar Rao','Kalvakuntla Chandrashekar Rao','KCR garu'],
  ARRAY['కేసీఆర్','చంద్రశేఖర్ రావు','కల్వకుంట్ల చంద్రశేఖర్ రావు'],'BRS chief'),
(:'org','K. T. Rama Rao','opposition','BRS Working President','BRS',
  ARRAY['K.T. Rama Rao','KTR','KT Rama Rao','Kalvakuntla Taraka Rama Rao','Rama Rao'],
  ARRAY['కేటీఆర్','కల్వకుంట్ల తారక రామారావు','కేటి రామారావు'],'BRS'),
(:'org','T. Harish Rao','opposition','BRS, former Minister','BRS',
  ARRAY['Harish Rao','Thanneeru Harish Rao','Harish'],
  ARRAY['హరీష్ రావు','తన్నీరు హరీష్ రావు'],'BRS'),
(:'org','Padi Kaushik Reddy','opposition','BRS','BRS',
  ARRAY['Kaushik Reddy'],ARRAY['పాడి కౌశిక్ రెడ్డి'],'BRS'),
-- ── OPPOSITION — BJP ──────────────────────────────────────────────────────
(:'org','G. Kishan Reddy','opposition','BJP State President, Union Minister','BJP',
  ARRAY['Kishan Reddy','Gangapuram Kishan Reddy'],ARRAY['కిషన్ రెడ్డి','గంగపురం కిషన్ రెడ్డి'],'BJP TG chief'),
(:'org','Bandi Sanjay Kumar','opposition','BJP, Union Minister','BJP',
  ARRAY['Bandi Sanjay','Sanjay Kumar'],ARRAY['బండి సంజయ్','బండి సంజయ్ కుమార్'],'BJP'),
(:'org','Etela Rajender','opposition','BJP','BJP',
  ARRAY['Eatala Rajender','Etela'],ARRAY['ఈటల రాజేందర్'],'BJP'),
(:'org','T. Raja Singh','opposition','BJP MLA','BJP',
  ARRAY['Raja Singh'],ARRAY['రాజా సింగ్'],'BJP'),
-- ── OPPOSITION — AIMIM (ally of ruling? doc listed Owaisis as allies; treat
--    AIMIM as its own bloc — mark opposition-neutral via note) ──────────────
(:'org','Asaduddin Owaisi','opposition','AIMIM President, MP','AIMIM',
  ARRAY['Asaduddin'],ARRAY['అసదుద్దీన్ ఒవైసీ'],'AIMIM (doc:ally) — verify side'),
(:'org','Akbaruddin Owaisi','opposition','AIMIM, MLA','AIMIM',
  ARRAY['Akbaruddin'],ARRAY['అక్బరుద్దీన్ ఒవైసీ'],'AIMIM (doc:ally) — verify side'),
-- ── INSTITUTIONS (state bodies; no party) ─────────────────────────────────
(:'org','Telangana High Court','institution','Judiciary',NULL,
  ARRAY['TG High Court','High Court of Telangana','Telangana HC'],ARRAY['తెలంగాణ హైకోర్టు','హైకోర్టు'],NULL),
(:'org','Telangana Assembly','institution','Legislature',NULL,
  ARRAY['Telangana Legislative Assembly','state assembly','Assembly'],ARRAY['తెలంగాణ అసెంబ్లీ','శాసనసభ'],NULL),
(:'org','Telangana Cabinet','institution','Executive',NULL,
  ARRAY['state cabinet','cabinet'],ARRAY['తెలంగాణ కేబినెట్','మంత్రివర్గం'],NULL),
(:'org','Telangana Police','institution','Home',NULL,
  ARRAY['TG Police','state police','Cyberabad Police','Hyderabad Police'],ARRAY['తెలంగాణ పోలీసు','పోలీసులు'],NULL),
(:'org','GHMC','institution','Municipal Administration & Urban Development',NULL,
  ARRAY['Greater Hyderabad Municipal Corporation'],ARRAY['జీహెచ్‌ఎంసీ'],NULL),
(:'org','HYDRAA','institution','Municipal Administration & Urban Development',NULL,
  ARRAY['Hydra','Hyderabad Disaster Response and Assets Protection Agency'],ARRAY['హైడ్రా'],NULL),
(:'org','HMDA','institution','Municipal Administration & Urban Development',NULL,
  ARRAY['Hyderabad Metropolitan Development Authority'],ARRAY['హెచ్‌ఎండీఏ'],NULL),
(:'org','Hyderabad Metro Rail','institution','Municipal Administration & Urban Development',NULL,
  ARRAY['Metro Rail','Hyderabad Metro'],ARRAY['హైదరాబాద్ మెట్రో'],NULL),
(:'org','TGSRTC','institution','Transport',NULL,
  ARRAY['TSRTC','RTC','Road Transport Corporation'],ARRAY['ఆర్టీసీ','టీజీఎస్ఆర్టీసీ'],NULL),
(:'org','TGSPDCL','institution','Energy',NULL,
  ARRAY['TSSPDCL','discom','Southern Power Distribution','Discom'],ARRAY['డిస్కం'],NULL),
(:'org','TGPSC','institution','Labour & Employment',NULL,
  ARRAY['TSPSC','Telangana Public Service Commission','Public Service Commission'],ARRAY['టీజీపీఎస్సీ','టీఎస్‌పీఎస్సీ'],NULL),
(:'org','Osmania University','institution','Education',NULL,
  ARRAY['OU'],ARRAY['ఉస్మానియా విశ్వవిద్యాలయం','ఉస్మానియా'],NULL)
ON CONFLICT (org_id, canonical_name) DO NOTHING;

SELECT side, count(*) FROM briefing.roster WHERE org_id=:'org' GROUP BY side ORDER BY 1;
