# Clustering eval — manual review

- Corpus sample: **100 articles** (May 12, 2026; Telangana-focused, multilingual: te/en/hi)
- Embedding: `paraphrase-multilingual-MiniLM-L12-v2` (384-dim, multilingual)
- Candidate retrieval: top-10 kNN with cosine sim ≥ 0.5 (= 142 pairs sent to LLM)
- LLM judge: Cerebras `qwen-3-235b-a22b-instruct-2507`, temperature=0
- **Result:** 6 multi-article clusters + 80 singletons

## How to grade this report

Read each cluster below. Mark it:
- ✅ **TIGHT** — every article in this cluster IS the same story
- ⚠️ **LOOSE** — most are the same, but 1-2 articles don't belong
- ❌ **WRONG** — these are not the same story

Then scan the **high-sim splits** below — these are pairs the embedding thought close but the LLM rejected. Were any of them actually the same story (= missed clusters)?

---

## Multi-article clusters

### Cluster 1  ·  8 articles
  - **[0]** *Namasthe Telangana* `en` — **బర్తరఫ్ బర్తరఫ్ చేయాల్సిందే..**
    Subject: BRS-led protests demand removal of Union Minister Bandi Sanjay and arrest of his son Sai Bhagirath
  - **[31]** *HMTV* `en` — **Kamareddy: కేంద్ర మంత్రి కుమారుడి అరెస్ట్ కోసం కాంగ్రెస్ పట్టు!**
    Subject: Congress party protests for arrest of Union Minister's son in minor girl assault case
  - **[51]** *Siasat Daily* `en` — **POCSO charges against Bandi Sanjay’s son altered to aggravated sexual assault**
    Subject: Police upgrade charges against Bandi Sanjay's son in POCSO case to aggravated penetrative sexual assault
  - **[57]** *Namasthe Telangana* `en` — **రక్షకుడే భక్షకుడైతే ఎవరికి చెప్పుకోవాలి**
    Subject: Telangana MLA questions arrest of Home Minister's son in POCSO case
  - **[69]** *Telangana Today* `en` — **Telangana police invoke stringent POCSO provisions against Bageerath**
    Subject: Telangana police upgrade charges in POCSO case against Union Minister Bandi Sanjay's son with stricter non-bailable provisions
  - **[79]** *V6 Velugu* `te` — **బండి భగీరథ్ పై పోక్సో కేసు నీరు గార్చేందుకు బీజేపీ, కాంగ్రెస్ కుమ్మక్కు... బీఆర్ఎస్ ఆధ్వర్యంలో నిరసన**
    Subject: Telangana opposition parties protest against BJP and Congress for allegedly shielding Bandi Bhagirath in POCSO case
  - **[87]** *Eenadu* `te` — **పోక్సో కేసు.. బండి భగీరథ్‌కు పోలీసుల నోటీసులు**
    Subject: Telangana police issue notice to Bandi Bhagirath in POCSO case
  - **[97]** *Namasthe Telangana* `en` — **బండి భగీరథ్‌ను అరెస్టు చేయాలి**
    Subject: BRS activists and women's groups demand immediate arrest of Bandi Bhagirath in sexual harassment case

**LLM SAME-reasons within this cluster (17 edges):**
  - [0↔31] sim=0.719 → SAME: Both articles describe protests demanding the arrest of Union Minister Bandi Sanjay's son in the same alleged minor assault case, despite different dates and locations.
  - [0↔57] sim=0.686 → SAME: Both articles describe protests demanding the arrest of Bandi Sanjay's son in the same POCSO case involving sexual assault of a minor.
  - [0↔79] sim=0.700 → SAME: Both articles describe the same BRS-led protests demanding Union Minister Bandi Sanjay's removal and arrest of his son Bhagirath in connection with the same POCSO case.
  - [0↔87] sim=0.503 → SAME: Both articles describe the same specific incident—the allegations against Bandi Bhagirath (son of Union Minister Bandi Sanjay) in a POCSO case involving a minor, including related legal actions and public response.
  - [0↔97] sim=0.768 → SAME: Both articles describe protests by BRS members demanding the arrest of Bandi Bhagirath (son of Union Minister Bandi Sanjay) over the same sexual assault allegation, and call for action against his father; the events are part of the sa
  - [31↔87] sim=0.525 → SAME: Both articles describe the same specific incident involving allegations against Union Minister Bandi Sanjay's son Bandi Bhagirath in a POCSO case, including related legal actions and public response.
  - [51↔69] sim=0.773 → SAME: Both articles describe the same event—police upgrading charges against Bandi Sanjay's son in a POCSO case to aggravated penetrative sexual assault under Section 5(1).
  - [51↔87] sim=0.555 → SAME: Both articles describe the same POCSO case against Bandi Sanjay's son, involving police notice for questioning and legal proceedings, with charges being upgraded/registered under specific sections of the POCSO Act.
  - [57↔69] sim=0.665 → SAME: Both articles describe the same POCSO case involving Bandi Sanjay's son, with details of legal actions and public response centered on the same incident.
  - [57↔79] sim=0.783 → SAME: Both articles describe protests demanding arrest of Bandi Bhagiratha, son of Union Home Minister Bandi Sanjay, in the same POCSO case involving a minor.
  - [57↔87] sim=0.752 → SAME: Both articles describe the same specific incident — the POCSO case involving Bandi Bhagiratha, son of Union Minister Bandi Sanjay, including allegations of harassment of a minor and official actions taken (protest demanding arrest in 
  - [57↔97] sim=0.693 → SAME: Both articles describe protests demanding the arrest of Bandi Bhagiratha, son of Union Minister Bandi Sanjay, in the same POCSO case involving a minor.
  - [69↔79] sim=0.595 → SAME: Both articles describe the same specific event—the POCSO case against Bandi Sanjay's son Bageerath/Bhagirath—and focus on the legal and political developments surrounding it, including intensified charges and related protests.
  - [69↔87] sim=0.683 → SAME: Both articles describe the same POCSO case against Bandi Sanjay's son, involving the same allegations, complainants, and legal proceedings, with updates on charges and police action.
  - [79↔87] sim=0.727 → SAME: Both articles describe the same specific event—the POCSO case involving Bandi Bhagirath, including allegations, police action, and political context.
  - [79↔97] sim=0.639 → SAME: Both articles describe the same specific event — protests led by BRS and women's groups demanding the arrest of Bandi Bhagirath in a POCSO/sexual harassment case, with allegations of political shielding and police inaction.
  - [87↔97] sim=0.563 → SAME: Both articles describe the same POCSO case involving Bandi Bhagirath, including allegations of sexual harassment of a minor, police action, and public response.


### Cluster 2  ·  4 articles
  - **[36]** *V6 Velugu* `te` — **ఒక్కో మెడికల్ సీటుకు రూ.60 లక్షలు: దొరికిన బీహార్ సాల్వర్ గ్యాంగ్.. MBBS విద్యార్థే కింగ్ పిన్**
    Subject: NEET exam paper leak and scam involving a gang in Bihar
  - **[39]** *Namasthe Telangana* `te` — **మోదీ వైఫల్యంతోనే నీట్‌ పేపర్‌ లీక్‌**
    Subject: Telangana BJP leader blames Modi government for NEET exam paper leak
  - **[65]** *Telangana Today — Hyderabad* `en` — **NEET UG 2026 exam cancelled, re-test to be conducted soon**
    Subject: NEET UG 2026 exam cancellation and re-test announcement
  - **[75]** *Siasat Daily* `en` — **NEET UG 2026 paper leak: Congress, BRS demand apology from Modi govt**
    Subject: NEET UG 2026 exam cancelled due to paper leak allegations, triggering political backlash and student distress

**LLM SAME-reasons within this cluster (4 edges):**
  - [36↔65] sim=0.731 → SAME: Both articles describe the cancellation of the NEET UG 2026 exam due to a paper leak and irregularities, with re-testing to be conducted and fees refunded.
  - [39↔65] sim=0.568 → SAME: Both articles describe the same specific event—the cancellation of the NEET UG 2026 exam due to a paper leak and the announcement of a re-test.
  - [39↔75] sim=0.760 → SAME: Both articles describe the same specific event—the NEET UG 2026 exam paper leak and cancellation—and cover identical political reactions, including demands for an apology from the Modi government, a probe, and concerns over student im
  - [65↔75] sim=0.776 → SAME: Both articles describe the cancellation of the NEET UG 2026 exam held on May 3 due to paper leak allegations, the CBI inquiry, and plans for a re-test.


### Cluster 3  ·  2 articles
  - **[1]** *Mana Telangana* `en` — **‘ఆర్‌ఎన్23’ చిత్రం ఆరంభం**
    Subject: Rohit Narra's upcoming film 'RN23' begins production
  - **[68]** *V6 Velugu* `te` — **Nara Rohit: కమర్షియల్ ఫ్యామిలీ ఎంటర్‌టైనర్‌గా.. నారా రోహిత్-నయన్ కొత్త సినిమా షురూ..**
    Subject: Nara Rohit's new commercial family entertainer film begins production

**LLM SAME-reasons within this cluster (1 edges):**
  - [1↔68] sim=0.637 → SAME: Both articles describe the launch of the same film 'RN23' starring Nara Rohit and Nayanthara, directed by Chinimilli Manikumar, produced under similar banners, with identical start dates and genre descriptions.


### Cluster 4  ·  2 articles
  - **[13]** *NTV Telugu* `en` — **CM Vijay: జ్యోతిష్యుడికి కీలక పోస్ట్.. సీఎం విజయ్ కీలక నిర్ణయం..**
    Subject: CM Vijay appoints astrologer Radhan Pandit as special duty officer
  - **[22]** *TV9 Telugu* `te` — **ప్రముఖ జ్యోతిష్యుడిని సీఎంవో ప్రత్యేక అధికారిగా నియమించుకున్న ముఖ్యమంత్రి..!**
    Subject: Tamil Nadu Chief Minister appoints personal astrologer as special officer

**LLM SAME-reasons within this cluster (1 edges):**
  - [13↔22] sim=0.807 → SAME: Both articles describe the same event — Tamil Nadu CM Vijay appointing his personal astrologer to a government position as Officer on Special Duty — with minor variations in the astrologer's name and details.


### Cluster 5  ·  2 articles
  - **[18]** *HMTV* `en` — **Rahul Dravid: ఫ్రాంచైజీ యజమానిగా ద్రవిడ్.. కెప్టెన్ అశ్విన్, లీగ్ ఓనర్ స్టార్ హీరో!**
    Subject: Rahul Dravid becomes franchise owner in European T20 Premier League with Dublin-based team
  - **[45]** *NTV Telugu* `bn` — **ETPL Dublin Guardians: రాహుల్ ద్రవిడ్ యజమానిగా, రవిచంద్రన్ అశ్విన్ కెప్టెన్‌గా సరికొత్త టీం బరిలోకి.!**
    Subject: ETPL Dublin Guardians team announced with Rahul Dravid as owner and Ravi Chandran Ashwin as captain

**LLM SAME-reasons within this cluster (1 edges):**
  - [18↔45] sim=0.651 → SAME: Both articles describe the same event—Rahul Dravid becoming owner and Ravichandran Ashwin being named captain of the Dublin franchise in the European T20 Premier League.


### Cluster 6  ·  2 articles
  - **[28]** *NTV Telugu* `en` — **The Paradise: బట్టకాల్చి మీదేస్తే ఊరుకోం..  రీషూట్ పుకార్లపై మేకర్స్ స్ట్రాంగ్ కౌంటర్!**
    Subject: The Paradise film production team denies rumors of reshoots and confirms on-schedule shooting
  - **[64]** *Telugu 360* `en` — **Nani’s The Paradise slams all baseless rumors**
    Subject: Production team of Nani's The Paradise addresses baseless rumors and confirms project's on-track status

**LLM SAME-reasons within this cluster (1 edges):**
  - [28↔64] sim=0.813 → SAME: Both articles report the same event—The Paradise film production team denying reshoot rumors and confirming the project is on schedule.


---

## Calibration

Pairs sent to LLM: **142**

- SAME verdicts: **25** — sim min=0.503, median=0.693, max=0.813
- DIFFERENT verdicts: **117** — sim min=0.502, median=0.554, max=0.877

If SAME-median > DIFFERENT-median, embedding sim is informative. If they overlap heavily, embedding alone is insufficient (LLM does the real work).

### High-sim splits (LLM rejected despite sim ≥ 0.62)

If any of these *should* have been clustered, embeddings can find them but the LLM is over-strict.

- **[77↔99]** sim=0.877 — LLM: *DIFFERENT: Different temples (Kondagattu vs. Devrayanallu) hosting separate Hanuman Jayanti celebrations.*
  - [77] *Namasthe Telangana* `en` — అంజన్నకు నీరాజనం.. కొండగట్టు భక్తజనసంద్రం
  - [99] *Namasthe Telangana* `bn` — వైభవంగా హనుమాన్‌ జయంతి
- **[4↔99]** sim=0.835 — LLM: *DIFFERENT: Different temples in different locations (Tirupati vs. Devrayanallu) hosting separate Hanuman Jayanti celebrations.*
  - [4] *HMTV* `en` — Tirupati: భక్తిశ్రద్ధలతో ఆంజనేయ హోమం
  - [99] *Namasthe Telangana* `bn` — వైభవంగా హనుమాన్‌ జయంతి
- **[4↔77]** sim=0.825 — LLM: *DIFFERENT: Different temples and locations (Tirupati vs. Kondagattu) hosting separate Hanuman Jayanti events.*
  - [4] *HMTV* `en` — Tirupati: భక్తిశ్రద్ధలతో ఆంజనేయ హోమం
  - [77] *Namasthe Telangana* `en` — అంజన్నకు నీరాజనం.. కొండగట్టు భక్తజనసంద్రం
- **[11↔77]** sim=0.809 — LLM: *DIFFERENT: Different temple events in different locations (Nagole vs. Kondagattu) during Hanuman Jayanti, with no indication of same specific incident.*
  - [11] *HMTV* `en` — Nagole: హనుమాన్ జయంతి సంబరాలు పూజల్లో పాల్గొన్న ఎమ్మెల్యే సుధీర్ రెడ్డి
  - [77] *Namasthe Telangana* `en` — అంజన్నకు నీరాజనం.. కొండగట్టు భక్తజనసంద్రం
- **[16↔25]** sim=0.783 — LLM: *DIFFERENT: One article covers RJ Balaji facing backlash over past remarks on Telugu cinema, while the other discusses his admiration for Ram Charan and interest in collaborating with him—distinct even*
  - [16] *NTV Telugu* `en` — RJ Balaji: ‘వీర భద్రుడు’ రిలీజ్‌కు ముందు కొత్త వివాదం.. ఆర్‌జే బాలాజీపై ఫ్యాన్స్ ఫైర్!
  - [25] *NTV Telugu* `en` — RJ Balaji: చరణ్‌తో సినిమా చేయాలని ఉంది..  దర్శకుడు ఆర్ జె బాలాజీ ఆసక్తికర వ్యాఖ్యలు !
- **[4↔11]** sim=0.779 — LLM: *DIFFERENT: Different locations and events; one in Tirupati temple with rituals, another in Nagole with MLA participation*
  - [4] *HMTV* `en` — Tirupati: భక్తిశ్రద్ధలతో ఆంజనేయ హోమం
  - [11] *HMTV* `en` — Nagole: హనుమాన్ జయంతి సంబరాలు పూజల్లో పాల్గొన్న ఎమ్మెల్యే సుధీర్ రెడ్డి
- **[11↔99]** sim=0.758 — LLM: *DIFFERENT: Different temples and locations; one involves a specific MLA's participation, the other a community celebration at a historic temple with distinct rituals.*
  - [11] *HMTV* `en` — Nagole: హనుమాన్ జయంతి సంబరాలు పూజల్లో పాల్గొన్న ఎమ్మెల్యే సుధీర్ రెడ్డి
  - [99] *Namasthe Telangana* `bn` — వైభవంగా హనుమాన్‌ జయంతి
- **[35↔99]** sim=0.751 — LLM: *DIFFERENT: Article A discusses the spiritual significance of Hanuman's birth and general observances on Hanuman Jayanti, while Article B reports on specific celebrations at a particular temple in Devr*
  - [35] *HMTV* `en` — Hanuman Jayanti:  ఆంజనేయుడి జన్మరహస్యం... కలియుగంలో గట్టెక్కించే కపిధ్వజుడు
  - [99] *Namasthe Telangana* `bn` — వైభవంగా హనుమాన్‌ జయంతి
- **[31↔57]** sim=0.746 — LLM: *DIFFERENT: Protests occurred in different locations (Kamareddy vs. Kurnool) and were led by different individuals, despite involving the same accused; Article A describes a Congress party protest, whi*
  - [31] *HMTV* `en` — Kamareddy: కేంద్ర మంత్రి కుమారుడి అరెస్ట్ కోసం కాంగ్రెస్ పట్టు!
  - [57] *Namasthe Telangana* `en` — రక్షకుడే భక్షకుడైతే ఎవరికి చెప్పుకోవాలి
- **[6↔73]** sim=0.746 — LLM: *DIFFERENT: Protests occurred in different locations (Bonakal vs. Armoor) over separate procurement delays involving distinct farmer groups and local authorities.*
  - [6] *Namasthe Telangana* `en` — కొనుగోళ్లు వేగవంతం చేయండి
  - [73] *V6 Velugu* `te` — ధాన్యం కాంటా వేయట్లేదని సొసైటీ ఆఫీసుకు తాళం.. ఆర్మూర్లో రైతుల నిరసన
- **[36↔39]** sim=0.733 — LLM: *DIFFERENT: Article A focuses on the arrest of a Bihar-based gang involved in a NEET exam scam with a medical student as kingpin, while Article B covers political criticism by KTR blaming the Modi gove*
  - [36] *V6 Velugu* `te` — ఒక్కో మెడికల్ సీటుకు రూ.60 లక్షలు: దొరికిన బీహార్ సాల్వర్ గ్యాంగ్.. MBBS విద్యార్థే కింగ్ పిన్
  - [39] *Namasthe Telangana* `te` — మోదీ వైఫల్యంతోనే నీట్‌ పేపర్‌ లీక్‌
- **[36↔75]** sim=0.722 — LLM: *DIFFERENT: Article A describes a NEET exam scam involving a Bihar-based gang and seat-selling for ₹60 lakh per seat, while Article B covers the cancellation of NEET UG 2026 due to paper leak allegatio*
  - [36] *V6 Velugu* `te` — ఒక్కో మెడికల్ సీటుకు రూ.60 లక్షలు: దొరికిన బీహార్ సాల్వర్ గ్యాంగ్.. MBBS విద్యార్థే కింగ్ పిన్
  - [75] *Siasat Daily* `en` — NEET UG 2026 paper leak: Congress, BRS demand apology from Modi govt
- **[31↔79]** sim=0.721 — LLM: *DIFFERENT: Article A describes a Congress-led protest demanding arrest of Bandi Sanjay's son in a minor assault case, while Article B describes BRS-led protests accusing BJP and Congress of colluding *
  - [31] *HMTV* `en` — Kamareddy: కేంద్ర మంత్రి కుమారుడి అరెస్ట్ కోసం కాంగ్రెస్ పట్టు!
  - [79] *V6 Velugu* `te` — బండి భగీరథ్ పై పోక్సో కేసు నీరు గార్చేందుకు బీజేపీ, కాంగ్రెస్ కుమ్మక్కు... బీఆర్ఎస్ ఆధ్వర్యంలో నిరసన
- **[13↔74]** sim=0.699 — LLM: *DIFFERENT: Different events involving different appointments in different regions and contexts.*
  - [13] *NTV Telugu* `en` — CM Vijay: జ్యోతిష్యుడికి కీలక పోస్ట్.. సీఎం విజయ్ కీలక నిర్ణయం..
  - [74] *Namasthe Telangana* `en` — Karepalli | సింగరేణి ఇంచార్జ్ ఎంపీడీవోగా రవీంద్ర ప్రసాద్..!
- **[11↔35]** sim=0.699 — LLM: *DIFFERENT: Article A describes a specific event where an MLA attended Hanuman Jayanti celebrations, while Article B discusses the spiritual significance of Hanuman's birth and general religious observ*
  - [11] *HMTV* `en` — Nagole: హనుమాన్ జయంతి సంబరాలు పూజల్లో పాల్గొన్న ఎమ్మెల్యే సుధీర్ రెడ్డి
  - [35] *HMTV* `en` — Hanuman Jayanti:  ఆంజనేయుడి జన్మరహస్యం... కలియుగంలో గట్టెక్కించే కపిధ్వజుడు

### Low-sim joins (LLM matched despite sim < 0.62)

If any of these are *wrong* matches, the LLM is too liberal.

- **[0↔87]** sim=0.503 — LLM: *SAME: Both articles describe the same specific incident—the allegations against Bandi Bhagirath (son of Union Minister Bandi Sanjay) in a POCSO case involving a minor, including related legal actions *
  - [0] *Namasthe Telangana* `en` — బర్తరఫ్ బర్తరఫ్ చేయాల్సిందే..
  - [87] *Eenadu* `te` — పోక్సో కేసు.. బండి భగీరథ్‌కు పోలీసుల నోటీసులు
- **[31↔87]** sim=0.525 — LLM: *SAME: Both articles describe the same specific incident involving allegations against Union Minister Bandi Sanjay's son Bandi Bhagirath in a POCSO case, including related legal actions and public resp*
  - [31] *HMTV* `en` — Kamareddy: కేంద్ర మంత్రి కుమారుడి అరెస్ట్ కోసం కాంగ్రెస్ పట్టు!
  - [87] *Eenadu* `te` — పోక్సో కేసు.. బండి భగీరథ్‌కు పోలీసుల నోటీసులు
- **[51↔87]** sim=0.555 — LLM: *SAME: Both articles describe the same POCSO case against Bandi Sanjay's son, involving police notice for questioning and legal proceedings, with charges being upgraded/registered under specific sectio*
  - [51] *Siasat Daily* `en` — POCSO charges against Bandi Sanjay’s son altered to aggravated sexual assault
  - [87] *Eenadu* `te` — పోక్సో కేసు.. బండి భగీరథ్‌కు పోలీసుల నోటీసులు
- **[87↔97]** sim=0.563 — LLM: *SAME: Both articles describe the same POCSO case involving Bandi Bhagirath, including allegations of sexual harassment of a minor, police action, and public response.*
  - [87] *Eenadu* `te` — పోక్సో కేసు.. బండి భగీరథ్‌కు పోలీసుల నోటీసులు
  - [97] *Namasthe Telangana* `en` — బండి భగీరథ్‌ను అరెస్టు చేయాలి
- **[39↔65]** sim=0.568 — LLM: *SAME: Both articles describe the same specific event—the cancellation of the NEET UG 2026 exam due to a paper leak and the announcement of a re-test.*
  - [39] *Namasthe Telangana* `te` — మోదీ వైఫల్యంతోనే నీట్‌ పేపర్‌ లీక్‌
  - [65] *Telangana Today — Hyderabad* `en` — NEET UG 2026 exam cancelled, re-test to be conducted soon
- **[69↔79]** sim=0.595 — LLM: *SAME: Both articles describe the same specific event—the POCSO case against Bandi Sanjay's son Bageerath/Bhagirath—and focus on the legal and political developments surrounding it, including intensifi*
  - [69] *Telangana Today* `en` — Telangana police invoke stringent POCSO provisions against Bageerath
  - [79] *V6 Velugu* `te` — బండి భగీరథ్ పై పోక్సో కేసు నీరు గార్చేందుకు బీజేపీ, కాంగ్రెస్ కుమ్మక్కు... బీఆర్ఎస్ ఆధ్వర్యంలో నిరసన

---

## Singletons sample (first 25)

These are articles that didn't cluster. Many are legitimately unique; some may indicate missed clusters.

- **[2]** *HMTV* `en` — Nellore: హెల్మెట్ లేకపోతే ప్రాణాలకే ముప్పు.. స్కూల్ విద్యార్థులకు పోలీసుల క్లాస్!
    Nellore police conduct traffic awareness program for school students
- **[3]** *Telangana Today* `en` — Priyanka Chopra, Jaideep Ahlawat and Jim Sarbh to star in Mira Nair’s next ‘Amri’
    Mira Nair's biographical film 'Amri' on artist Amrita Sher-Gil to star Priyanka Chopra, Jaideep Ahlawat, and Jim Sarbh
- **[4]** *HMTV* `en` — Tirupati: భక్తిశ్రద్ధలతో ఆంజనేయ హోమం
    Hindu religious ceremony celebrating Hanuman Jayanti at Tirupati temple
- **[5]** *Namasthe Telangana* `te` — నేడు సీపీగెట్‌ నోటిఫికేషన్‌ విడుదల
    Telangana's Common Post-Graduate Entrance Test (CPGET)-2026 notification to be released on Wednesday evening
- **[6]** *Namasthe Telangana* `en` — కొనుగోళ్లు వేగవంతం చేయండి
    Farmers stage protest in Bonakal demanding faster procurement of paddy and maize
- **[7]** *Siasat Daily* `en` — Hegseth faces bipartisan grilling about weapons drawdown during Iran war
    Bipartisan lawmakers question US Defense Secretary Pete Hegseth on Iran war's impact on weapons stockpiles and strategy
- **[8]** *V6 Velugu* `te` — పైపులైన్ తొలగింపునకు రూ.10 వేలు లంచం..ఏసీబీకి చిక్కిన కార్యదర్శి, సర్పంచ్ భర్త
    Gadham Rajugoud and Anjaneyulu arrested for taking ₹10,000 bribe to remove drainage pipeline
- **[9]** *V6 Velugu* `te` — OTT మూవీ రివ్యూ: కంటతడి పెట్టించే హార్ట్‌టచింగ్ స్టోరీ
    Telangana film 'Love Mocktail 3' streaming on ZEE5 Kannada
- **[10]** *HMTV* `en` — Bobbili: ప్రభుత్వ స్థలాల్లో ఇళ్ల నిర్మాణం.. అధికారులకు ఫిర్యాదు చేసినా నో రెస్పాన్స్!
    Government land encroachment in Bobbili ITI Colony
- **[11]** *HMTV* `en` — Nagole: హనుమాన్ జయంతి సంబరాలు పూజల్లో పాల్గొన్న ఎమ్మెల్యే సుధీర్ రెడ్డి
    Telangana MLA Sudhir Reddy attends Hanuman Jayanti celebrations at Ramayya Temple
- **[12]** *Mana Telangana* `en` — నేనే నాలుగు ఓవర్లు బౌలింగ్ చేశానా?.... నమ్మలేకపోతున్నా?:  డిసి బౌలర్
    Delhi Capitals secure victory over Punjab in IPL match
- **[14]** *Namasthe Telangana* `en` — Pakistan | పాకిస్తాన్‌లో ఆత్మాహుతి దాడి.. 8 మంది మృతి.. 35 మందికి గాయాలు.. ఎమర్జెన్సీ అలర్ట్
    Suicide bombing in Lakki Marwat, Pakistan
- **[15]** *HMTV* `en` — Savitri Screen Presence: సావిత్రి నటప్రస్థానంలో అదృశ్యశక్తి... ఆమె లేకుంటే
    Savitri's cinematic continuity maintained by personal assistant Dakshayani
- **[16]** *NTV Telugu* `en` — RJ Balaji: ‘వీర భద్రుడు’ రిలీజ్‌కు ముందు కొత్త వివాదం.. ఆర్‌జే బాలాజీపై ఫ్యాన్స్ ఫైర్!
    RJ Balaji's controversial remarks about Telugu cinema spark fan backlash ahead of film release
- **[17]** *Namasthe Telangana* `en` — 25 చెట్లతో సమానం..‘ఆల్గే ట్రీ’
    Bhopal installs India's first carbon-capturing 'Algae Tree' under Smart City project
- **[19]** *Telangana Today* `en` — Possessiveness disturbing: Court warns against alienating child from father
    Bombay High Court warns against parental alienation in child custody dispute
- **[20]** *Telangana Today* `en` — Two Sangareddy residents die as Karnataka bus hit bike on KA-TG border
    Two Sangareddy residents killed in motorcycle collision with Karnataka RTC bus on state border
- **[21]** *HMTV* `en` — వర్క్ ఫ్రమ్ హోమ్ వైపు మళ్ళీ అడుగులు.. ప్రధాని పిలుపుతో కంపెనీల కీలక నిర్ణయం!
    Indian government encourages remote work to reduce fuel consumption amid geopolitical tensions
- **[23]** *V6 Velugu* `te` — Vinesh Phogat: రెజ్లింగ్‌లో మళ్లీ రగడ.. నన్ను ఆసియా క్రీడలకు దూరం చేయాలని కుట్రలు చేస్తున్నారు..
    Vinesh Phogat alleges WFI conspiracy to exclude her from Asia Games
- **[24]** *TV9 Telugu* `te` — Rashmi Gautam: నేను బీజేపీకి, మోడీకి సపోర్ట్ చేస్తా.. హాట్‌ టాపిక్‌గా యాంకర్ రష్మీ పోస్ట్ .. ఏం జరిగిందంటే?
    Rashmi Gautam's social media post expressing support for BJP and Modi
- **[25]** *NTV Telugu* `en` — RJ Balaji: చరణ్‌తో సినిమా చేయాలని ఉంది..  దర్శకుడు ఆర్ జె బాలాజీ ఆసక్తికర వ్యాఖ్యలు !
    RJ Balaji expresses admiration for Ram Charan and interest in collaborating on a film
- **[26]** *V6 Velugu* `te` — మే 12న బంజారాహిల్స్ లో జాబ్ మేళా : కలెక్టర్ ప్రియాంక ఆల
    Hyderabad's Banjara Hills job fair scheduled for May 12
- **[27]** *TV9 Telugu* `te` — మీది ప్రధానిని అనే స్థాయా..?.. కర్నాటక కాంగ్రెస్ సర్కార్‌పై ప్రహ్లాద్ జోషి ఫైర్
    Karnataka Congress government criticized by Union Minister Pralhad Joshi over economic policies
- **[29]** *V6 Velugu* `te` — మీటింగ్ తేదీ మార్పు కుదరదన్న కృష్ణాబోర్డు
    Krishna River Board rejects Telangana's request to reschedule tripartite committee meeting
- **[30]** *HMTV* `en` — Amaravati: జైళ్ల సంస్కరణల దిశగా ఏపీ ప్రభుత్వం.. హోంమంత్రి కీలక ఆదేశాలు
    Andhra Pradesh government initiates jail reforms with focus on rehabilitation