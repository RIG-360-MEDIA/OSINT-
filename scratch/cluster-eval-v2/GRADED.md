# 500-article v2 validation — graded report

- **Sample:** 500 articles | duration: 884.4s
- **Clusters:** 430 total, 44 multi-article, 386 singletons
- **LLM calls:** 345 (69% of articles needed judge)
- **Errors:** 0
- **Source diversity:** {'2-3 sources': 37, '1 source': 393}
- **Momentum:** {'stable': 418, 'escalating': 10, 'fading': 2}

## Grading legend

- ✅ **TIGHT** — every article IS the same story
- ⚠️ **LOOSE** — most are the same; 1-2 don't fit
- ❌ **WRONG** — these are not the same story

---

### #1 · 12 articles · sources=2 · escalating ⚡ LARGE
**Title:** Telangana scorches as summer temperatures hit 46.5 degrees Celsius, shows TSDPS data
**Entities:** Akhtarul Iman, Armed Forces Tribunal, Care Health Insurance Ltd, M. P. Giri, Computer Age Management Services
**Sources in cluster:** Mana Telangana×7; Telangana Today×5

  - *Telangana Today* `en` — **Telangana scorches as summer temperatures hit 46.5 degrees Celsius, shows TSDPS data**
    Subject: Telangana experiences extreme heatwave with temperatures reaching 46.5°C in Nirmal district.
  - *Telangana Today* `en` — **Dasoju Sravan accuses Congress of neglecting slum residents in Khairatabad**
    Subject: BRS MLC Dasoju Sravan accuses the Congress government of neglecting slum residents in Hyderabad's Khairatabad constituency.
  - *Mana Telangana* `en` — **కుంటలో పడి బాలుడు మృతి**
    Subject: A four-year-old boy died after falling into a pond while playing.
  - *Mana Telangana* `en` — **’ఐ యామ్ గేమ్’ వచ్చేది అప్పుడే**
    Subject: The release date for Dulquer Salmaan's film 'I Am Game' has been officially announced for a global theatrical release on August 20
  - *Mana Telangana* `en` — **ప్రేమోన్మాదికి ఉరి**
    Subject: A man was sentenced to death for murdering his wife's parents in a fit of rage after she refused to return to him.
  - *Mana Telangana* `en` — **ఎయిర్‌పోర్టులో భారీగా గంజాయి పట్టివేత**
    Subject: Two individuals were arrested at Rajiv Gandhi International Airport in Hyderabad for smuggling 8.705 kg of hydroponic cannabis wor
  - *Mana Telangana* `en` — **కోనేరులో పడి ముగ్గురు చిన్నారులు మృతి**
    Subject: Three children died after accidentally falling into a pond in Kondapur village, Jagtial district, Telangana.
  - *Telangana Today* `en` — **SRH v RCB: Malkajgiri police warn cricket fans against fake IPL ticket scams**
    Subject: Malkajgiri police warn fans about fake IPL ticket scams for the SRH vs RCB match.
  - *Telangana Today* `en` — **Girl attempts suicide after being reprimanded for skipping bath**
    Subject: A 17-year-old girl attempted suicide by jumping into a well after being scolded by her parents for skipping a bath in Asifabad.
  - *Telangana Today* `en` — **Three children drown in temple tank in Jagtial**
    Subject: Three children drowned in a temple tank in Jagtial district, Telangana.
  - *Mana Telangana* `en` — **చేతులెత్తేసిన ముంబై బ్యాటర్లు.. కోల్ కతా టార్గెట్ ఎంతంటే?**
    Subject: Mumbai Indians struggled in their batting innings against Kolkata Knight Riders in an IPL 2026 match, scoring 147 for 8.
  - *Mana Telangana* `en` — **వివాదంలో మాజీ మేయర్ బొంతు రామ్మోహన్..!?**
    Subject: A former mayor is embroiled in a dispute over a hostel rental and alleged threats and violence.

---

### #2 · 8 articles · sources=1 · escalating
**Title:** Congress: డీఎంకే వల్ల కాలేదు, 59 ఏళ్ల కాంగ్రెస్ కోరిక తీర్చిన విజయ్..
**Entities:** Narendra Modi, Brijendra Singh Ola, West Bengal, Bhuban Gam, Surja Kanta Atta
**Sources in cluster:** NTV Telugu×8

  - *NTV Telugu* `en` — **OLA New EV: సర్వీస్ కష్టాలు తీరాయి.. సరికొత్త ఈవీ వాహనాలతో దూసుకురానున్న ‘ఓలా ఎలక్ట్రిక్’..**
    Subject: Ola Electric resolves service issues and announces new electric vehicle launches in India
  - *NTV Telugu* `en` — **PM Modi: ఇటలీలో మోడీకి అత్యున్నత గౌరవం.. అగ్రికోలా మెడల్‌తో సత్కారం**
    Subject: Prime Minister Narendra Modi received the FAO's highest honor, the Agricola Medal, during his visit to Italy.
  - *NTV Telugu* `en` — **West Bengal: అక్రమ బంగ్లాదేశీయుల బహిష్కరణ.. బెంగాల్‌లో సీఏఏ స్టార్ట్..**
    Subject: West Bengal government begins implementation of the Citizenship Amendment Act (CAA) to deport illegal Bangladeshi immigrants.
  - *NTV Telugu* `en` — **NTR : ఎన్టీఆర్ ‘బాల రామాయణం’ కంటే ముందే తాతతో కలిసి ఆ సినిమాలో నటించాడని మీకు తెలుసా?**
    Subject: Junior NTR began his acting career as a child artist in mythological roles before his debut as a lead actor, including performing 
  - *NTV Telugu* `en` — **Pahalgam Terror Attack: పహల్గామ్ ఉగ్రదాడిలో ఎన్ఐఏ సంచలన ఛార్జిషీట్.. ఆ ఇద్దరి గైడ్స్‌ ఎంత పని చేశారంటే..!**
    Subject: The NIA has filed a chargesheet revealing local guides' involvement in supporting terrorists during the Pahalgam attack.
  - *NTV Telugu* `en` — **Congress: డీఎంకే వల్ల కాలేదు, 59 ఏళ్ల కాంగ్రెస్ కోరిక తీర్చిన విజయ్..**
    Subject: Congress enters Tamil Nadu government after 59 years, with two MLAs appointed as ministers.
  - *NTV Telugu* `en` — **Off The Record : టీడీపీ, జనసేన మధ్య హాట్ హాట్ గా ఏలూరు మేయర్ సీటు**
    Subject: TDP and Janasena are locked in a political rivalry over the Eluru Mayor's seat, with accusations of party-switching and strategic 
  - *NTV Telugu* `en` — **Off The Record : జగిత్యాలలో కేవీ ఏర్పాటు కోసం రాజకీయ యుద్ధం**
    Subject: Political conflict between an MP and MLA over land allocation for a Kendriya Vidyalaya in Jagtial, Telangana.

---

### #3 · 4 articles · sources=3 · escalating
**Title:** Nationwide Medical Shop Strike: నేడు దేశవ్యాప్తంగా మెడికల్ ఎమర్జెన్సీ? బంద్ కానున్న 15 లక్షల మందుల దుకాణాలు!
**Entities:** Revolutionary Marxist Party of India, Narendra Modi, Irshad Rasool Kar, Ratna De Nag
**Sources in cluster:** HMTV×2; NTV Telugu×1; Siasat Daily×1

  - *NTV Telugu* `te` — **Nationwide Medical Shop Strike: నేడు దేశవ్యాప్తంగా మెడికల్ ఎమర్జెన్సీ? బంద్ కానున్న 15 లక్షల మందుల దుకాణాలు!**
    Subject: Pharmacies across India are on a 24-hour strike against online medicine sales and steep discounts, affecting nearly 1.5 million st
  - *Siasat Daily* `en` — **Nationwide chemists’ strike today against online sale of medicines**
    Subject: Chemists across India are on strike to protest against unregulated online medicine sales.
  - *HMTV* `te` — **Karimnagar: నేడు దేశవ్యాప్తంగా మెడికల్ షాపులు బంద్!**
    Subject: Medical shops across India are observing a nationwide one-day strike to protest against online medicine sales and demand stricter 
  - *HMTV* `te` — **Anantapur: మెడికల్ షాప్స్ క్లోజ్.. రోడ్డుపైకి వచ్చిన కెమిస్టులు!**
    Subject: Medical shop owners in Anantapur protest against online medicine sales by holding a strike and rally.

---

### #4 · 3 articles · sources=3 · fading
**Title:** Mirai 2 : సైలెంట్‌గా మొదలైన తేజ సజ్జా ‘మిరాయ్ 2’ షూటింగ్... రంగంలోకి రానా, మంచు మనోజ్!
**Entities:** Satish Chandra Rai, Saifullah Mir, Yogender Singh Rana, Union budget announcement.
**Sources in cluster:** Namasthe Telangana×1; V6 Velugu×1; Telugu 360×1

  - *Namasthe Telangana* `en` — **Mirai 2 | తేజ సజ్జా మిరాయ్‌ 2 షూటింగ్‌ షురూ.. ఇంతకీ ఎక్కడో తెలుసా..?**
    Subject: Filming for the Telugu movie Mirai 2 starring Teja Sajja has begun in Visakhapatnam.
  - *V6 Velugu* `te` — **Mirai 2 : సైలెంట్‌గా మొదలైన తేజ సజ్జా ‘మిరాయ్ 2’ షూటింగ్... రంగంలోకి రానా, మంచు మనోజ్!**
    Subject: The sequel film 'Mirai 2' starring Teja Sajja began shooting silently in Visakhapatnam, with Rana Daggubati joining as a powerful 
  - *Telugu 360* `en` — **Rana Daggubati to join Mirai 2?**
    Subject: Rana Daggubati's potential involvement in the sequel of the film 'Mirai' and its production updates.

---

### #5 · 3 articles · sources=3 · escalating
**Title:** అన్నాడీఎంకే రెబల్ ఎమ్మెల్యేలకు మంత్రి పదవులు ఇయ్యం: కుండబద్దలు కొట్టిన టీవీకే
**Entities:** Tamilaga Vettri Kazhagam, Parmod Kumar Vij, Interim Government
**Sources in cluster:** Telugu 360×1; NTV Telugu×1; V6 Velugu×1

  - *Telugu 360* `en` — **Left Parties Warn TVK Government Over AIADMK Entry Into Tamil Nadu Cabinet**
    Subject: Left parties threaten to review support to TVK government if AIADMK joins Tamil Nadu cabinet
  - *NTV Telugu* `en` — **TVK Vijay: అలా అయితే మద్దతు విత్‌డ్రా చేసుకుంటాం.. సీఎం విజయ్‌కు కొత్త తలనొప్పి..**
    Subject: Tamil Nadu CM Vijay faces coalition tensions as Left parties and VCK warn of withdrawing support if rebel ADMK faction is given mi
  - *V6 Velugu* `te` — **అన్నాడీఎంకే రెబల్ ఎమ్మెల్యేలకు మంత్రి పదవులు ఇయ్యం: కుండబద్దలు కొట్టిన టీవీకే**
    Subject: Tamil Nadu minister Adavil Arjun clarifies that rebel AIADMK MLAs will not be given cabinet positions in the TVK government led by

---

### #6 · 3 articles · sources=3 · escalating
**Title:** ప్లేఆఫ్స్‌కి ముందు ఆర్సిబికి గుడ్‌న్యూస్.. అతడు వచ్చేస్తున్నాడు..
**Entities:** Royal Challengers Bengaluru, 5th T20I, India tour of England, Revolutionary Marxist Party of India
**Sources in cluster:** Telangana Today×1; Mana Telangana×1; HMTV×1

  - *Telangana Today* `en` — **Phil Salt set to rejoin RCB’s squad later this week**
    Subject: Phil Salt is set to rejoin Royal Challengers Bengaluru's squad after recovering from a finger injury.
  - *Mana Telangana* `en` — **ప్లేఆఫ్స్‌కి ముందు ఆర్సిబికి గుడ్‌న్యూస్.. అతడు వచ్చేస్తున్నాడు..**
    Subject: Royal Challengers Bangalore receive a boost ahead of IPL playoffs with Phil Salt's return from injury.
  - *HMTV* `te` — **RCB: ప్లేఆఫ్స్‌ ముందు ఆర్‌సీబీ అభిమానులకు గుడ్‌న్యూస్.. మాన్‌స్టర్ వస్తున్నాడు!**
    Subject: RCB's Phil Salt returns for IPL 2026 playoffs after injury recovery

---

### #7 · 3 articles · sources=3 · escalating
**Title:** పాక్ ఇజ్జత్ తీసిన బంగ్లా టైగర్స్.. WTF ఫైనల్ నుంచి ఔట్.. టీమిండియాకు షాకిచ్చిందిగా
**Entities:** Revolutionary Marxist Party of India, Santosh Lad, Armed Forces Tribunal
**Sources in cluster:** Namasthe Telangana×1; HMTV×1; Telangana Today×1

  - *Namasthe Telangana* `te` — **చరిత్రకు చేరువలో బంగ్లా!.. పాక్‌తో రెండో టెస్టు**
    Subject: Bangladesh is on the verge of a historic victory in the second Test against Pakistan in the Test series.
  - *HMTV* `te` — **పాక్ ఇజ్జత్ తీసిన బంగ్లా టైగర్స్.. WTF ఫైనల్ నుంచి ఔట్.. టీమిండియాకు షాకిచ్చిందిగా**
    Subject: Bangladesh's historic Test series sweep against Pakistan reshapes the World Test Championship standings, pushing India to sixth pl
  - *Telangana Today* `en` — **India drop to sixth in WTC standings after Bangladesh sweep Pakistan**
    Subject: India's drop to sixth in the ICC World Test Championship standings following Bangladesh's 2-0 series sweep over Pakistan.

---

### #8 · 3 articles · sources=3 · escalating
**Title:** RRB Railway Jobs 2026: పదో తరగతి అర్హతతో రైల్వేలో 6,565 ఉద్యోగాలకు నోటిఫికేషన్‌..
**Entities:** Defected from BJP to TMC; Died on 23 February 2026, Government NDA Seats: 202, Satish Chandra Rai, National Insurance Company, Indian Railways
**Sources in cluster:** TV9 Telugu×1; V6 Velugu×1; NTV Telugu×1

  - *TV9 Telugu* `te` — **RRB Railway Jobs 2026: పదో తరగతి అర్హతతో రైల్వేలో 6,565 ఉద్యోగాలకు నోటిఫికేషన్‌..**
    Subject: Indian Railways has announced 6,565 technician job vacancies for candidates with 10th pass and ITI/diploma qualifications, to be f
  - *V6 Velugu* `te` — **Jobs : రైల్వేలో 6 వేల 565 టెక్నీషియన్ ఉద్యోగాలు : డిగ్రీ/డిప్లొమా/ఐటీఐ అర్హత ఉంటే చాలు..!**
    Subject: The Indian Railways recruitment of 6,565 technician positions with eligibility criteria and application deadlines.
  - *NTV Telugu* `en` — **RRB Technician 2026: నిరుద్యోగులకు గోల్డెన్ చాన్స్.. రైల్వేలో 6,565 టెక్నీషియన్ పోస్టులు.. దరఖాస్తు, అర్హత పూర్తి వివరాలు**
    Subject: Indian Railways is recruiting 6,565 technicians through RRB notifications for Grade 1 and Grade 3 posts.

---

### #9 · 3 articles · sources=2 · escalating
**Title:** కీలక పోరులో లక్నోపై రాజస్థాన్ రాయల్స్ గెలుపు..
**Entities:** Lucknow Super Giants, Punjabhai Vansh, Rajasthan Royals, Jaipur, Dhruv Jurel
**Sources in cluster:** Namasthe Telangana×2; TV9 Telugu×1

  - *TV9 Telugu* `te` — **కీలక పోరులో లక్నోపై రాజస్థాన్ రాయల్స్ గెలుపు..**
    Subject: Rajasthan Royals defeated Lucknow Super Giants in a high-scoring IPL 2026 match in Jaipur, powered by Vaibhav Suryavanshi's explos
  - *Namasthe Telangana* `en` — **RR vs LSG | వైభవ్ ఊచకోతకు బలైన లక్నో.. పంజాబ్‌ను కిందకు నెట్టేసిన రాజస్థాన్..!**
    Subject: Rajasthan Royals secured a crucial 7-wicket victory over Lucknow Super Giants in an IPL match, boosting their playoff hopes.
  - *Namasthe Telangana* `en` — **Vaibhav Sooryavanshi: ఆ సంకేతానికి అర్థం లేదు.. సూర్యవంశీ వెరైటీ సెల‌బ్రేష‌న్‌.. వీడియో**
    Subject: 15-year-old cricketer Vaibhav Sooryavanshi's explosive 93-run innings and quirky celebration spark curiosity during Rajasthan Roya

---

### #10 · 3 articles · sources=2 · escalating
**Title:** జలమండలి జీఎం ఇంట్లో ..కోట్లకొద్దీ నోట్ల కట్టలు, కిలోల కొద్దీ బంగారం
**Sources in cluster:** V6 Velugu×2; Namasthe Telangana×1

  - *V6 Velugu* `te` — **జలమండలి GM కుమార్‌పై అక్రమాస్తుల కేసు నమోదు.. రూ. 5 కోట్ల ఆస్తులు కూడబెట్టాడు.. బంగారం ఎన్ని కిలోలు ఉందంటే..**
    Subject: The Telangana ACB has registered a disproportionate assets case against S.A.L. Kumar, GM of HMWSS&SB, alleging illegal wealth accu
  - *Namasthe Telangana* `te` — **జలమండలిలో అవినీతి జలగ**
    Subject: Corruption scandal at Hyderabad's water authority (Jalmandali) involving a senior official with millions in unaccounted cash and a
  - *V6 Velugu* `te` — **జలమండలి జీఎం ఇంట్లో ..కోట్లకొద్దీ నోట్ల కట్టలు, కిలోల కొద్దీ బంగారం**
    Subject: Anti-Corruption Bureau raids the home of Water Board General Manager Anantha Lakshmi Kumar, seizing cash, gold, and assets worth o

---

### #11 · 3 articles · sources=3 · escalating
**Title:** RR vs LSG | మార్ష్‌, ఇంగ్లిస్ విధ్వంసం.. రాజస్థాన్‌ ఆశలన్నీ వైభవ్‌ మీదే..!
**Entities:** Lucknow Super Giants, S. R. Raja, Punjabhai Vansh, Rishabh Pant
**Sources in cluster:** Namasthe Telangana×1; V6 Velugu×1; Telangana Today×1

  - *Namasthe Telangana* `te` — **RR vs LSG | మార్ష్‌, ఇంగ్లిస్ విధ్వంసం.. రాజస్థాన్‌ ఆశలన్నీ వైభవ్‌ మీదే..!**
    Subject: The article is fundamentally about Lucknow Super Giants posting a strong total of 220 runs against Rajasthan Royals in an IPL matc
  - *V6 Velugu* `te` — **లక్నో బ్యాటర్ల విధ్వంసం.. సెంచరీ మిస్ చేసుకున్న మార్ష్.. రాజస్థాన్ టార్గెట్ 221**
    Subject: Lucknow Super Giants set a target of 220 for Rajasthan Royals in an IPL 2026 match at Sawai Mansingh Stadium, Jaipur.
  - *Telangana Today* `bn` — **Sooryavanshi’s fury takes Rajasthan closer to playoffs**
    Subject: Rajasthan Royals' victory over Lucknow Super Giants in an IPL match, led by Vaibhav Sooryavanshi's 38-ball 93, brings them closer 

---

### #12 · 2 articles · sources=2 · stable
**Title:** Kerala CM Satheesan to handle Finance, Law as Guv approves portfolio recommendations
**Entities:** Thiruvananthapuram, Kerala Congress, Sunny Joseph, Trinamool Congress, V. D. Satheesan
**Sources in cluster:** V6 Velugu×1; Telangana Today×1

  - *V6 Velugu* `te` — **కేరళ మంత్రులకు శాఖల కేటాయింపు.. హోం మినిస్టర్‎గా రమేష్ చెన్నితాల**
    Subject: Kerala's newly elected UDF government allocates ministerial portfolios, with Ramesh Chennithala appointed as Home Minister.
  - *Telangana Today* `bn` — **Kerala CM Satheesan to handle Finance, Law as Guv approves portfolio recommendations**
    Subject: Kerala Chief Minister V D Satheesan assumes Finance and Law portfolios along with 36 departments, as Governor approves UDF cabinet

---

### #13 · 2 articles · sources=1 · stable
**Title:** ఇన్నాళ్లు ఓ లెక్క.. ఈ 5 రోజులు మరో లెక్క.. తెలుగు రాష్ట్రాలకు ‘రెడ్ అలర్ట్’ వార్నింగ్!
**Sources in cluster:** TV9 Telugu×2

  - *TV9 Telugu* `te` — **ఇన్నాళ్లు ఓ లెక్క.. ఈ 5 రోజులు మరో లెక్క.. తెలుగు రాష్ట్రాలకు ‘రెడ్ అలర్ట్’ వార్నింగ్!**
    Subject: Telugu states face extreme heatwave conditions with red and yellow alerts issued for Telangana and high alert in Andhra Pradesh.
  - *TV9 Telugu* `te` — **పిడుగురాళ్లలో 47.6,  నిర్మల్‌లో 46.5 డిగ్రీలు.. సూరీడుతో జాగ్రత్త**
    Subject: Extreme heat warnings in Telangana and Andhra Pradesh with record temperatures recorded in Piduguralla and Nirmal.

---

### #14 · 2 articles · sources=2 · stable
**Title:** వనస్తలిపురంలో భర్తను చంపి.. మృతదేహాన్ని తీసుకెళ్తుండగా పట్టుకున్న స్థానికులు
**Entities:** Amarish Der, Armed Forces Tribunal, Socialist Party of India
**Sources in cluster:** Mana Telangana×1; Siasat Daily×1

  - *Mana Telangana* `en` — **వనస్తలిపురంలో భర్తను చంపి.. మృతదేహాన్ని తీసుకెళ్తుండగా పట్టుకున్న స్థానికులు**
    Subject: A woman allegedly killed her husband in Vanasthalipuram, Rangareddy district, after he harassed her, and locals caught her while s
  - *Siasat Daily* `en` — **Hyderabad man killed after midnight fight; wife, brother-in-law under suspicion**
    Subject: A man in Hyderabad was allegedly killed by his wife and her brother following a midnight fight.

---

### #15 · 2 articles · sources=2 · stable
**Title:** Pradhan reviews NEET-UG re-exam security, orders crackdown on fake Telegram channels
**Entities:** Amarish Der, South Eastern Coalfields, Pratap Chandra Pradhan, Tulsi Ram, Minister
**Sources in cluster:** Telangana Today×1; Siasat Daily×1

  - *Telangana Today* `en` — **Pradhan reviews NEET-UG re-exam security, orders crackdown on fake Telegram channels**
    Subject: Union Education Minister Dharmendra Pradhan reviews security measures for the NEET-UG re-exam and orders a crackdown on fake Teleg
  - *Siasat Daily* `en` — **Education Minister reviews NEET-UG re-exam security, orders crackdown **
    Subject: Union Education Minister Dharmendra Pradhan reviews security for NEET-UG re-exam and orders action against fake Telegram channels 

---

### #16 · 2 articles · sources=2 · stable
**Title:** Hyderabad: Traffic authorities relocate 40-year-old tree from Begumpet junction
**Entities:** Amarish Der, Marwar Junction, Texmaco Rail & Engineering, Sahina Mumtaz Begum, Zahid Beg
**Sources in cluster:** Telangana Today — Yadadri×1; Siasat Daily×1

  - *Telangana Today — Yadadri* `en` — **Hyderabad: Traffic authorities relocate 40-year-old tree from Begumpet junction**
    Subject: Hyderabad traffic authorities relocated a 40-year-old tree from Begumpet junction to improve traffic flow and ensure environmental
  - *Siasat Daily* `en` — **40-year-old tree moved, not axed, to ease traffic at Hyderabad junction**
    Subject: A 40-year-old tree was transplanted to ease traffic congestion in Hyderabad.

---

### #17 · 2 articles · sources=2 · stable
**Title:** Watch: Jr NTR’s film with Prashanth Neel titled ‘Dragon’; Gripping glimpse video released
**Entities:** Sulata Deo, Vishal Prashant
**Sources in cluster:** Telugu 360×1; Telangana Today×1

  - *Telugu 360* `en` — **Dragon Glimpse: NTR in an Explosive Avatar**
    Subject: NTR and Prashanth Neel collaborate on action film 'Dragon', set for 2027 release with a plot centered on the Golden Triangle and o
  - *Telangana Today* `en` — **Watch: Jr NTR’s film with Prashanth Neel titled ‘Dragon’; Gripping glimpse video released**
    Subject: The announcement of Jr NTR and Prashanth Neel's film 'Dragon' with a released glimpse video.

---

### #18 · 2 articles · sources=1 · stable
**Title:** KKR Vs MI: పాపం పాండ్యా.. కెప్టెన్సీ చేపట్టిన ప్రతీసారి ఇలానే.. మళ్లీ టార్గెట్ అవుతున్న హార్దిక్..
**Entities:** Kolkata Knight Riders, Munitions India, Mumbai Indians, Hardik Pandya, Tilak Varma
**Sources in cluster:** NTV Telugu×2

  - *NTV Telugu* `te` — **KKR Vs MI: ఈడెన్ గార్డెన్స్‌లో హైవోల్టేజ్ పోరు.. టాస్ గెలిచిన కేకేఆర్.. ముంబై బ్యాటింగ్..**
    Subject: A high-stakes IPL 2026 match between Kolkata Knight Riders and Mumbai Indians at Eden Gardens, with KKR winning the toss and optin
  - *NTV Telugu* `te` — **KKR Vs MI: పాపం పాండ్యా.. కెప్టెన్సీ చేపట్టిన ప్రతీసారి ఇలానే.. మళ్లీ టార్గెట్ అవుతున్న హార్దిక్..**
    Subject: A rain-affected IPL 2026 match between KKR and MI sees MI struggle at 57/4 in 8 overs, reigniting criticism of Hardik Pandya's cap

---

### #19 · 2 articles · sources=2 · stable
**Title:** JrNTR: ‘ఈసారి టైగర్ కాదు.. డ్రాగన్’.. సెలబ్రిటీల విషెష్⁭తో ట్రెండ్ అవుతున్న ఎన్టీఆర్ బర్త్‌డే
**Sources in cluster:** NTV Telugu×1; V6 Velugu×1

  - *NTV Telugu* `en` — **Allu Arjun: ‘ఈసారి టైగర్ కాదు.. డ్రాగన్’.. అంటూ బావ కోసం బన్నీ స్పెషల్ విషెస్ ..**
    Subject: Allu Arjun congratulates his brother-in-law Jr NTR on his birthday with a special message referencing the 'Dragon' film glimpse.
  - *V6 Velugu* `te` — **JrNTR: ‘ఈసారి టైగర్ కాదు.. డ్రాగన్’.. సెలబ్రిటీల విషెష్⁭తో ట్రెండ్ అవుతున్న ఎన్టీఆర్ బర్త్‌డే**
    Subject: Jr. NTR's 43rd birthday celebrations and celebrity reactions

---

### #20 · 2 articles · sources=2 · stable
**Title:** MS Dhoni: ధోనీ ‘సైలెంట్ రిటైర్మెంట్’..? ఫ్యాన్స్‌కు షాకిస్తోన్న మిస్టర్ కూల్ తాజా నిర్ణయం..!
**Entities:** 2023 World Test Championship final, Scooters India Limited
**Sources in cluster:** TV9 Telugu×1; Telangana Today×1

  - *TV9 Telugu* `te` — **MS Dhoni: ధోనీ ‘సైలెంట్ రిటైర్మెంట్’..? ఫ్యాన్స్‌కు షాకిస్తోన్న మిస్టర్ కూల్ తాజా నిర్ణయం..!**
    Subject: Speculation surrounds MS Dhoni's potential silent retirement from IPL 2026 amid his absence from CSK's final match tour and emotio
  - *Telangana Today* `en` — **Between the cheers and the silence: The uneasy wait for Dhoni’s final goodbye**
    Subject: The emotional anticipation surrounding MS Dhoni's potential final appearance for Chennai Super Kings in IPL 2026.

---

### #21 · 2 articles · sources=2 · stable
**Title:** Telangana raises upper age limit for uniformed services recruitment
**Entities:** Satish Chandra Rai, Isuzu Motors India, United News of India
**Sources in cluster:** Mana Telangana×1; Telangana Today×1

  - *Mana Telangana* `en` — **ప్రభుత్వ ఉదోగాలకు గరిష్ఠ వయోపరిమితి పెంపు**
    Subject: The Telangana government has extended the maximum age limit for applying to government jobs from 34 to 44 years.
  - *Telangana Today* `en` — **Telangana raises upper age limit for uniformed services recruitment**
    Subject: Telangana government increases upper age limit for recruitment to uniformed services by five years for one year.

---

### #22 · 2 articles · sources=2 · stable
**Title:** Bodhan: 270 క్వింటాళ్ల రేషన్ బియ్యం సీజ్.. వెనుక పెద్దల హస్తంపై ఆరోపణలు!
**Entities:** Mir Zulfeqar Ali
**Sources in cluster:** HMTV×1; Namasthe Telangana×1

  - *HMTV* `te` — **Bodhan: 270 క్వింటాళ్ల రేషన్ బియ్యం సీజ్.. వెనుక పెద్దల హస్తంపై ఆరోపణలు!**
    Subject: Police in Bodhan, Telangana, seize 270 quintals of ration rice from Sai Agro Industries and allege smuggling to other states.
  - *Namasthe Telangana* `en` — **పీడీఎస్‌ బియ్యం పక్కదారి**
    Subject: Authorities seized 275 quintals of illegally stored PDS rice worth ₹8.26 lakh from a rice mill in Srinivasa Nagar, Bodhan.

---

### #23 · 2 articles · sources=2 · stable
**Title:** శవాన్ని ఎక్కడ దాచాడు?  మోహన్‌లాల్ 'దృశ్యం 3' మైండ్ బ్లోయింగ్ బుకింగ్స్!
**Entities:** K. Chandrashekar Rao
**Sources in cluster:** HMTV×1; V6 Velugu×1

  - *HMTV* `te` — **మోహన్‌లాల్ పేరుకు అర్థమేంటి? సూపర్ స్టార్ ఇచ్చిన సమాధానం వైరల్!**
    Subject: Malayalam superstar Mohanlal's humorous response to a question about the meaning of his name goes viral during the filming break o
  - *V6 Velugu* `te` — **శవాన్ని ఎక్కడ దాచాడు?  మోహన్‌లాల్ 'దృశ్యం 3' మైండ్ బ్లోయింగ్ బుకింగ్స్!**
    Subject: The article is fundamentally about the advance booking success and anticipation surrounding the upcoming Malayalam film 'Drishyam 

---

### #24 · 2 articles · sources=1 · stable
**Title:** రెండున్నరేండ్లలో తట్టెడు మట్టి ఎత్తలే!
**Sources in cluster:** Namasthe Telangana×2

  - *Namasthe Telangana* `en` — **రెండున్నరేండ్లలో తట్టెడు మట్టి ఎత్తలే!**
    Subject: Criticism of Congress government's neglect of a major irrigation project in Telangana.
  - *Namasthe Telangana* `en` — **పాలమూరుపై కాంగ్రెస్‌ది మొద్దునిద్ర**
    Subject: The article criticizes the Congress government's alleged negligence on the Palamuru-Rangareddy irrigation project, accusing it of 

---

### #25 · 2 articles · sources=2 · stable
**Title:** Telangana CM urges people to stay indoors amid heatwave
**Entities:** Revanth Reddy, Great Eastern Shipping, Kashinath Date, People's Democratic Alliance
**Sources in cluster:** NTV Telugu×1; Telangana Today×1

  - *NTV Telugu* `te` — **Weather Updates : తెలంగాణలో ఠారెత్తిస్తున్న ఎండలు.. సీఎం రేవంత్ కీలక ఆదేశాలు**
    Subject: Telangana Chief Minister Revanth Reddy issues key directives to handle extreme heatwave conditions in the state.
  - *Telangana Today* `en` — **Telangana CM urges people to stay indoors amid heatwave**
    Subject: Telangana Chief Minister A Revanth Reddy urges citizens to stay indoors during peak heatwave conditions.

---

### #26 · 2 articles · sources=2 · stable
**Title:** టెట్రా ప్యాకెట్లలో వోడ్కా అమ్మకాలపై సుప్రీం నోటీసులు
**Entities:** Surya Kant, Revolutionary Marxist Party of India
**Sources in cluster:** Mana Telangana×1; V6 Velugu×1

  - *Mana Telangana* `en` — **టెట్రా ప్యాకెట్లలో వోడ్కా అమ్మకాలపై సుప్రీం నోటీసులు**
    Subject: Supreme Court issues notices on the sale of vodka in tetra packs and sachets, citing concerns over minors being misled by packagin
  - *V6 Velugu* `te` — **టెట్రా ప్యాక్‌ల్లో వోడ్కా అమ్మకాలపై సుప్రీం కోర్టు ఆగ్రహం**
    Subject: Supreme Court expresses concern over vodka sales in unmarked tetra packs and sachets, citing risks of misleading consumers and enc

---

### #27 · 2 articles · sources=2 · stable
**Title:** Condom in Beer | బీర్ బాటిల్‌లో కండోమ్ ప్యాకెట్.. కంగుతిన్న కస్టమర్
**Entities:** Kingfisher
**Sources in cluster:** V6 Velugu×1; Namasthe Telangana×1

  - *V6 Velugu* `te` — **KF  బీర్⁪లో చించేసిన కండోమ్ ప్యాకెట్.. కంగుతిన్న కస్టమర్.. సిద్దిపేట జిల్లాలోని వైన్స్⁫లో ఘటన !**
    Subject: A condom packet found inside a beer bottle at a wineshop in Siddipet district sparks customer outrage and demands for action.
  - *Namasthe Telangana* `te` — **Condom in Beer | బీర్ బాటిల్‌లో కండోమ్ ప్యాకెట్.. కంగుతిన్న కస్టమర్**
    Subject: A customer in Siddipet district, Telangana, found a condom packet inside a Kingfisher beer bottle and posted the incident on socia

---

### #28 · 2 articles · sources=1 · stable
**Title:** Iran warns war will spread ‘far beyond region’ if US resumes attacks
**Entities:** United Spirits, Surja Kanta Atta, Adani Ports & SEZ, Electronics Corporation of India
**Sources in cluster:** Siasat Daily×2

  - *Siasat Daily* `en` — **Trump says was an hour away from deciding on Iran attacks, slaps new sanctions**
    Subject: U.S. President Donald Trump announces he delayed potential Iran attacks after diplomatic calls and imposes new sanctions on Irania
  - *Siasat Daily* `en` — **Iran warns war will spread ‘far beyond region’ if US resumes attacks**
    Subject: Iran's Revolutionary Guards warn that renewed US or Israeli military action could escalate conflict beyond the Middle East, while 

---

### #29 · 2 articles · sources=2 · stable
**Title:** Charan’s Peddi Trailer Draws Unanimous Praise
**Entities:** Satish Chandra Rai, Asian News International, Research and Analysis Wing, Telecom Regulatory Authority of India
**Sources in cluster:** Telugu 360×1; TV9 Telugu×1

  - *Telugu 360* `en` — **Charan’s Peddi Trailer Draws Unanimous Praise**
    Subject: Ram Charan's film 'Peddi' receives unanimous praise for its emotional depth, technical excellence, and transformative performance,
  - *TV9 Telugu* `te` — **Peddi: పెద్ది ట్రైలర్.. ఆ విషయాలు గమనించారా..?**
    Subject: The trailer release of the Telugu film 'Peddi' starring Ram Charan has generated high expectations among fans.

---

### #30 · 2 articles · sources=2 · stable
**Title:** Suryastra | సూర్యాస్త్ర రాకెట్ వ్యవస్థ ప్రయోగం విజయవంతం.. భారత రక్షణ వ్యవస్థ మరింత బలోపేతం
**Sources in cluster:** Namasthe Telangana×1; NTV Telugu×1

  - *Namasthe Telangana* `en` — **Suryastra | సూర్యాస్త్ర రాకెట్ వ్యవస్థ ప్రయోగం విజయవంతం.. భారత రక్షణ వ్యవస్థ మరింత బలోపేతం**
    Subject: India successfully tested the domestically developed long-range 'Suryastra' rocket system, enhancing its defense capabilities.
  - *NTV Telugu* `en` — **Suryastra Rocket: శత్రువులకు హెచ్చరికగా.. స్వదేశీ ‘సూర్యాస్త్ర’ రాకెట్ సక్సెస్.. పెరిగిన డిఫెన్స్ పవర్**
    Subject: India successfully tests indigenous 'Suryastra' rocket system, enhancing its defense capabilities.

---

### #31 · 2 articles · sources=2 · fading
**Title:** RR vs LSG | టాస్ గెలిచిన రాజస్థాన్.. ప్లే ఆఫ్స్ ఆశలు నిలిచేనా..!
**Entities:** Lucknow Super Giants, Rajasthan Royals, Yashasvi Jaiswal
**Sources in cluster:** Namasthe Telangana×1; V6 Velugu×1

  - *Namasthe Telangana* `en` — **RR vs LSG | టాస్ గెలిచిన రాజస్థాన్.. ప్లే ఆఫ్స్ ఆశలు నిలిచేనా..!**
    Subject: Rajasthan Royals won the toss and chose to bowl against Lucknow Super Giants in a crucial IPL match affecting playoff chances.
  - *V6 Velugu* `te` — **టాస్ గెలిచి బౌలింగ్ తీసుకున్న రాజస్థాన్.. **
    Subject: Rajasthan Royals won the toss and chose to bowl against Lucknow Super Giants in an IPL match in Jaipur.

---

### #32 · 2 articles · sources=2 · stable
**Title:** Twisha Sharma : కుళ్ళిపోతున్న టాలీవుడ్ హీరోయిన్ డెడ్ బాడీ?
**Entities:** Pune, Rohit Sharma
**Sources in cluster:** V6 Velugu×1; NTV Telugu×1

  - *V6 Velugu* `te` — **మీ కూతురి డెడ్ బాడీ కుళ్లిపోతుంది.. తీసుకెళ్లండి: ట్విషా శర్మ ఫ్యామిలీకి పోలీసుల లేఖ**
    Subject: Police urge Twisha Sharma's family to collect her decomposing body from Bhopal AIIMS morgue amid re-autopsy demands
  - *NTV Telugu* `en` — **Twisha Sharma : కుళ్ళిపోతున్న టాలీవుడ్ హీరోయిన్ డెడ్ బాడీ?**
    Subject: Investigation into the mysterious death of Telugu actress Twisha Sharma and concerns over delayed post-mortem and evidence handlin

---

### #33 · 2 articles · sources=1 · stable
**Title:** చిలుక మధుసూదన్ రెడ్డికి సిట్‌‌ నోటీసులు
**Entities:** K. T. Rama Rao, Harish Rao, K. Chandrashekar Rao, K.T. Rama Rao
**Sources in cluster:** V6 Velugu×2

  - *V6 Velugu* `te` — **ఫోన్ ట్యాపింగ్ కేసులో గడ్డి అన్నారం మార్కెట్ కమిటీ చైర్మన్ చిలుక మధుసూదన్ రెడ్డికి సిట్ నోటీసులు**
    Subject: CBI issues notices to Gaddi Annaram Market Committee chairman Chiluk Madhusudan Reddy in a phone tapping case linked to 2023 Telan
  - *V6 Velugu* `te` — **చిలుక మధుసూదన్ రెడ్డికి సిట్‌‌ నోటీసులు**
    Subject: CBI summons Chiluk Madhusudan Reddy for questioning in a phone tapping case linked to 2023 Telangana assembly elections.

---

### #34 · 2 articles · sources=2 · stable
**Title:** Bandi Sanjay says BRS running ‘fake media factory’ over his son’s POCSO case
**Entities:** Kalvakuntla Sanjay, K. Chandrashekar Rao, Amarish Der, Action Construction Equipment, Armed Forces Tribunal
**Sources in cluster:** Telangana Today — Nizamabad×1; Siasat Daily×1

  - *Telangana Today — Nizamabad* `en` — **After Hyderabad and other places, posters targeting Bandi Sanjay’s son appear in Nizamabad**
    Subject: Posters targeting Bandi Bageerath, son of Union Minister Bandi Sanjay Kumar, appear in Nizamabad over a POCSO case, sparking polit
  - *Siasat Daily* `en` — **Bandi Sanjay says BRS running ‘fake media factory’ over his son’s POCSO case**
    Subject: Union Minister Bandi Sanjay responds to POCSO case involving his son and alleges BRS is spreading misinformation.

---

### #35 · 2 articles · sources=2 · stable
**Title:** కులగణన వ్యతిరేక పిల్‌ను తిరస్కరించిన సుప్రీం
**Entities:** Surya Kant, Bharat Aluminium Company
**Sources in cluster:** Siasat Daily×1; Mana Telangana×1

  - *Siasat Daily* `en` — **Every govt must know how many people are backward classes: SC on caste census**
    Subject: Supreme Court upholds government's authority to conduct caste-based census for welfare policy.
  - *Mana Telangana* `en` — **కులగణన వ్యతిరేక పిల్‌ను తిరస్కరించిన సుప్రీం**
    Subject: The Supreme Court dismissed a public interest litigation (PIL) opposing caste enumeration in the census, asserting its necessity f

---

### #36 · 2 articles · sources=2 · stable
**Title:** US Tragedy | అమెరికాలో బాపట్ల టెక్కీ మృతి.. తల్లిదండ్రులు, తమ్ముడికి తీవ్ర గాయాలు
**Entities:** United Spirits, Amarish Der, Cotton Corporation of India
**Sources in cluster:** Telangana Today — Yadadri×1; Namasthe Telangana×1

  - *Telangana Today — Yadadri* `en` — **Hyderabad native killed, family members injured in US accident**
    Subject: A Hyderabad native was killed and his family injured in a road accident in New Mexico, US.
  - *Namasthe Telangana* `en` — **US Tragedy | అమెరికాలో బాపట్ల టెక్కీ మృతి.. తల్లిదండ్రులు, తమ్ముడికి తీవ్ర గాయాలు**
    Subject: A software engineer from Bapatla, Andhra Pradesh, died in a road accident in the US, while his parents and brother were seriously 

---

### #37 · 2 articles · sources=2 · stable
**Title:** ACB Raid | రూ.30 వేలు లంచం తీసుకుంటూ ఏసీబీ అధికారులకు చిక్కిన మహిళా ఎస్సై, రైటర్‌
**Entities:** Swaraj India, Amarish Der, Central Administrative Tribunal, Satish Chandra Rai
**Sources in cluster:** Namasthe Telangana×1; Telangana Today×1

  - *Namasthe Telangana* `te` — **ACB Raid | రూ.30 వేలు లంచం తీసుకుంటూ ఏసీబీ అధికారులకు చిక్కిన మహిళా ఎస్సై, రైటర్‌**
    Subject: A female police officer and a writer in Hyderabad were caught accepting a ₹30,000 bribe by the Anti-Corruption Bureau (ACB).
  - *Telangana Today* `en` — **ACB catches woman SI and constable in Rs 30,000 bribe trap in Hyderabad**
    Subject: A woman sub-inspector and constable in Hyderabad were arrested for allegedly demanding and accepting a Rs 30,000 bribe in an attem

---

### #38 · 2 articles · sources=2 · stable
**Title:** ఐపీఎల్‌ ఆదాయంలోనూ కోహ్లీనే కింగ్‌
**Entities:** Virat Kohli, Kolkata Knight Riders, Rohit Sharma, Revolutionary Marxist Party of India, Royal Challengers Bengaluru
**Sources in cluster:** Namasthe Telangana×1; TV9 Telugu×1

  - *Namasthe Telangana* `en` — **ఐపీఎల్‌ ఆదాయంలోనూ కోహ్లీనే కింగ్‌**
    Subject: Virat Kohli has become the highest-earning cricketer in IPL history with ₹230 crore in earnings.
  - *TV9 Telugu* `te` — **Virat Kohli : ఐపీఎల్ చరిత్రలోనే నయా రికార్డ్.. రూ.230 కోట్లతో కింగ్ కోహ్లీ నంబర్ 1**
    Subject: Virat Kohli becomes the highest-earning player in IPL history with ₹230 crore in earnings from playing for RCB since 2008.

---

### #39 · 2 articles · sources=2 · stable
**Title:** PM Modi gifts ‘Melody’ to Giorgia Meloni, revives viral ‘Melodi’ moment
**Entities:** Narendra Modi, Reliance General Insurance, Sonia Gandhi, KL Rahul
**Sources in cluster:** Telangana Today×1; Namasthe Telangana×1

  - *Telangana Today* `en` — **PM Modi gifts ‘Melody’ to Giorgia Meloni, revives viral ‘Melodi’ moment**
    Subject: Prime Minister Narendra Modi gifts 'Melody' toffees to Italian PM Giorgia Meloni, reviving the viral '#Melodi' social media trend.
  - *Namasthe Telangana* `te` — **Rahul Gandhi | నాటకీయతే.. నాయకత్వం కాదు.. మోదీపై రాహుల్ గాంధీ ఫైర్.. రాహుల్‌పై మండిపడ్డ బీజేపీ**
    Subject: Rahul Gandhi criticizes Modi's leadership and BJP responds to his remarks about Modi's diplomatic gesture in Italy.

---

### #40 · 2 articles · sources=2 · stable
**Title:** TG PGECET 2026 Postponed: టీజీ పీజీఈసెట్‌ ప్రవేశ పరీక్ష వాయిదా.. కారణం ఇదే! కొత్త షెడ్యూల్‌ చూశారా
**Entities:** Defected from BJP to TMC; Died on 23 February 2026, Government NDA Seats: 202, Amarish Der, JNTU Hyderabad
**Sources in cluster:** Telangana Today — Yadadri×1; TV9 Telugu×1

  - *Telangana Today — Yadadri* `en` — **JNTU-Hyderabad postpones Telangana PGECET**
    Subject: JNTU-Hyderabad has postponed the Telangana PGECET exam from May 28 to June 1 due to the Bakrid festival.
  - *TV9 Telugu* `te` — **TG PGECET 2026 Postponed: టీజీ పీజీఈసెట్‌ ప్రవేశ పరీక్ష వాయిదా.. కారణం ఇదే! కొత్త షెడ్యూల్‌ చూశారా**
    Subject: The Telangana PGECET 2026 entrance exam for postgraduate courses has been postponed from May 28 to June 1 due to Bakrid.

---

### #41 · 2 articles · sources=1 · stable
**Title:** Video: India achieves milestone in UAV-launched missile system
**Entities:** Scooters India Limited, Revolutionary Marxist Party of India, Sulata Deo
**Sources in cluster:** Telangana Today×2

  - *Telangana Today* `en` — **Video: India achieves milestone in UAV-launched missile system**
    Subject: India successfully completes final trials of domestically developed UAV-launched precision guided missile system ULPGM-V3.
  - *Telangana Today* `en` — **DRDO successfully tests ULPGM-V3 missile in air-to-ground and air-to-air modes**
    Subject: The DRDO successfully tests the ULPGM-V3 missile in both air-to-ground and air-to-air modes, marking it ready for mass production.

---

### #42 · 2 articles · sources=2 · stable
**Title:** PM Modi: రోమ్‌లో మోదీ.. భారత్-ఇటలీ వ్యూహాత్మక భాగస్వామ్యంపై దృష్టి.!
**Entities:** Narendra Modi
**Sources in cluster:** NTV Telugu×1; HMTV×1

  - *NTV Telugu* `en` — **PM Modi: రోమ్‌లో మోదీ.. భారత్-ఇటలీ వ్యూహాత్మక భాగస్వామ్యంపై దృష్టి.!**
    Subject: Prime Minister Narendra Modi's visit to Rome to strengthen strategic and economic ties between India and Italy.
  - *HMTV* `te` — **Narendra Modi Foreign Tour: ఐదు రోజులు ఐదు దేశాలు...మోదీ విదేశీ యాత్రల వెనుక అదరిపోయే నిజాలు**
    Subject: Prime Minister Narendra Modi's five-day, five-country foreign tour focused on boosting India's economic and strategic interests co

---

### #43 · 2 articles · sources=2 · stable
**Title:** US-Iran War: ఇరాన్ యుద్ధంలో అమెరికాకు భారీ దెబ్బ.. 42 విమానాలు ధ్వంసం..
**Entities:** Armed Forces Tribunal, United Spirits
**Sources in cluster:** Namasthe Telangana×1; NTV Telugu×1

  - *Namasthe Telangana* `en` — **US Aircraft: ఇరాన్‌తో వార్‌.. 42 విమానాలు కోల్పోయిన అమెరికా**
    Subject: The article reports on the loss of 42 US aircraft during military operations against Iran since February 28, citing a Congressiona
  - *NTV Telugu* `en` — **US-Iran War: ఇరాన్ యుద్ధంలో అమెరికాకు భారీ దెబ్బ.. 42 విమానాలు ధ్వంసం..**
    Subject: The article reports on alleged significant losses by the United States in a purported US-Iran war, including the destruction of 42

---

### #44 · 2 articles · sources=2 · stable
**Title:** Medak farmer commits suicide over unsold paddy
**Entities:** Other Minerals & Metals
**Sources in cluster:** Namasthe Telangana×1; Telangana Today×1

  - *Namasthe Telangana* `bn` — **అన్నదాత అరిగోస**
    Subject: Farmers in Telangana face distress due to delayed and inefficient grain procurement by the government.
  - *Telangana Today* `bn` — **Medak farmer commits suicide over unsold paddy**
    Subject: A Telangana farmer commits suicide after being unable to sell his paddy despite waiting 20 days at a procurement center.

---

## Singletons sample (first 20 of 386)

- *Namasthe Telangana* `en` — ధాన్యం కొనుగోలు చేయాలని  రహదారిపై బైఠాయించి రైతుల ఆందోళన
- *Telangana Today* `en` — Low-sodium salt substitutes emerge as healthier alternative amid rising hypertension concerns
- *Telangana Today* `en` — Sidharth Malhotra gives major fitness goals with latest workout session
- *TV9 Telugu* `te` — Video: మైదానంలో సెగలు.. బయట కౌగిలింతలు..! శాంసన్, క్లాసెన్ వివాదంలో ఊహించని మలుపు..!
- *Namasthe Telangana* `en` — Dhurandhar 2 | చిక్కుల్లో ‘ధురంధర్ 2’.. కేంద్రానికి దిల్లీ హైకోర్టు కీలక ఆదేశాలు!
- *NTV Telugu* `te` — Healthy Jackfruit Tacos : హెల్తీ మినీ జాక్‌ఫ్రూట్ టాకోస్.. టేస్టీగా ఇంట్లోనే ఇలా చేసుకోండి.!
- *Telugu 360* `en` — David Reddy Teaser: Manoj Manchu as Rakshas Reddy
- *HMTV* `te` — Kurnool: టీడీపీ సభలో ఫొటోల గందరగోళం.. నిందితుడికి ఎమ్మెల్యే నివాళి!
- *Telugu 360* `en` — Mega158: Pawan Kalyan turns Special Guest
- *HMTV* `te` — WhatsApp: వాట్సాప్‌లో తెలియ‌ని వ్య‌క్తులు మెసేజ్ చేస్తున్నారా.? ఈ సెట్టింగ్ ఆన్ చేస్తే స‌రి
- *Namasthe Telangana* `en` — Farmer | కాంగ్రెస్ సర్కార్ నిర్లక్ష్యం.. రైతు ఆత్మహత్య..!
- *Telangana Today — Yadadri* `en` — Mother, daughter strangled to death in sweet lime orchard in Nalgonda
- *Namasthe Telangana* `en` — కేఆర్‌ఎంబీ మూడోసారీ
- *Siasat Daily* `en` — Punjab CEO holds meeting on SIR with political party representatives
- *Mana Telangana* `en` — 23న కేబినెట్
- *Siasat Daily* `en` — Karnataka High Court says jail term alone not enough for parole
- *Namasthe Telangana* `en` — రూటు మార్చని ఆర్టీసీ
- *HMTV* `te` — బడ్జెట్ రెడీ చేస్కోండి బాసూ.. మార్కెట్లోకి 4 కొత్త సబ్ కాంపాక్ట్ SUVలు.. మైలేజ్, లుక్స్‌లో కిర్రాక్..!
- *Telugu 360* `en` — June 2026: Biggest Bets in Indian Cinema
- *V6 Velugu* `te` — ఐకేపీ సెంటర్లలో ధాన్యం తూకం వేసేందుకు.. హమాలీలుగా మారిన మహిళలు