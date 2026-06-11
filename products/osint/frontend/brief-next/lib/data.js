// Mock data for RIG Intelligence morning brief
// Ported from brief-app/data.js — IIFE stripped, exports added.
// As real /api/brief/* endpoints come online, sections below get replaced.

export const SPARK = {
  // Synthetic 24h velocity series
  articles: [3, 4, 6, 5, 9, 12, 14, 11, 8, 13, 17, 22, 28, 24, 19, 21, 27, 32, 29, 34, 30, 36, 38, 42],
  outlets: [2, 3, 3, 4, 5, 6, 8, 9, 11, 10, 12, 13, 14, 15, 14, 16, 17, 16, 17, 18, 17, 18, 18, 18],
  sentiment: [0.1, 0.05, -0.1, -0.05, 0.0, -0.15, -0.2, -0.25, -0.18, -0.3, -0.35, -0.4, -0.38, -0.42, -0.35, -0.3, -0.32, -0.4, -0.45, -0.42, -0.4, -0.38, -0.42, -0.4],

  // Climbing stories (rapid rise late in window)
  climb_a: [1, 2, 2, 3, 2, 3, 4, 5, 6, 7, 9, 12, 16, 22, 28, 36, 44, 52, 58, 64, 70, 78, 84, 92],
  climb_b: [4, 5, 5, 6, 7, 6, 7, 8, 9, 11, 14, 18, 22, 25, 30, 34, 38, 42, 46, 50, 53, 58, 62, 66],
  climb_c: [2, 3, 3, 2, 4, 5, 6, 7, 8, 10, 13, 17, 21, 26, 31, 35, 39, 43, 47, 50, 53, 56, 58, 61],

  // Entity 24h mention curves
  rev: [12, 14, 11, 13, 16, 18, 22, 25, 28, 32, 36, 40, 38, 42, 45, 41, 38, 44, 47, 43, 46, 48, 47, 47],
  ktr: [8, 9, 11, 14, 18, 22, 28, 35, 42, 48, 52, 56, 60, 64, 68, 72, 75, 78, 80, 82, 84, 86, 88, 91],
  kcr: [22, 24, 21, 19, 20, 18, 17, 15, 14, 16, 18, 17, 19, 18, 17, 16, 15, 14, 16, 18, 17, 16, 17, 18],
  owaisi: [4, 5, 6, 5, 7, 9, 11, 10, 12, 14, 13, 15, 17, 19, 18, 20, 22, 21, 24, 26, 28, 27, 29, 30],
  bandi: [10, 12, 11, 13, 12, 14, 16, 15, 18, 20, 22, 24, 23, 26, 28, 30, 32, 31, 33, 35, 37, 36, 38, 40],
  musi: [6, 8, 12, 16, 22, 28, 35, 42, 50, 58, 62, 68, 72, 76, 80, 82, 85, 88, 90, 92, 94, 95, 96, 98],
  dharani: [18, 20, 22, 19, 21, 24, 26, 25, 28, 32, 36, 40, 44, 48, 52, 56, 58, 62, 65, 68, 70, 72, 74, 76],
  kalesh: [4, 5, 6, 8, 10, 14, 18, 24, 32, 42, 54, 68, 80, 88, 92, 95, 97, 98, 96, 94, 92, 90, 88, 86],

  // Story velocity sparks
  story1: [2, 3, 4, 5, 4, 6, 7, 9, 11, 14, 18, 23, 30, 38, 46, 54, 62, 70, 80, 92, 110, 124, 138, 147],
  story2: [3, 4, 5, 7, 9, 13, 18, 24, 31, 38, 44, 50, 56, 60, 64, 67, 70, 72, 74, 75, 76, 77, 78, 78],
  story3: [1, 2, 2, 3, 3, 4, 5, 6, 7, 8, 10, 13, 17, 22, 28, 34, 40, 46, 52, 58, 62, 66, 68, 71],
  story4: [12, 13, 14, 13, 15, 17, 19, 22, 26, 32, 38, 45, 52, 58, 65, 72, 80, 88, 94, 100, 108, 114, 119, 124],
  story5: [6, 7, 6, 8, 7, 9, 8, 10, 9, 11, 10, 12, 11, 13, 12, 14, 13, 15, 14, 16, 15, 17, 16, 18],
};

export const STORIES = [
  {
    rank: "01",
    stance: "critical",
    headline: "CM Revanth Reddy frames Musi Rejuvenation as core first-term legacy",
    summary:
      "The Chief Minister doubled down on ₹1,500 crore Phase 1 outlays during a Khammam rally, but Telugu vernaculars led with land-acquisition grievances from displaced residents along the river corridor.",
    spark: "story1",
    metrics: { articles: 147, outlets: 18, vs: "+340%" },
    coverage: { crit: 60, neu: 25, sup: 15 },
    lens: [
      { outlet: "Eenadu", lang: "telugu", stance: "critical", quote: "ఇది భూసేకరణ అన్యాయం — voices from Musi corridor unheard." },
      { outlet: "V6 News", lang: "telugu", stance: "critical", quote: "Costly displacement experiment in name of green renewal." },
      { outlet: "The Hindu", lang: "english", stance: "neutral", quote: "Funding question dominates Phase 1 cabinet note." },
      { outlet: "Times of India", lang: "english", stance: "neutral", quote: "Cabinet clears ₹1,500 crore tranche for first phase." },
      { outlet: "Deccan Chronicle", lang: "english", stance: "supportive", quote: "Long-overdue urban renewal finally on the move." },
    ],
    caption: "Heavy critical framing in Telugu press; English coverage descriptive.",
    principalQuote: {
      text: "Musi rejuvenation is not a project — it is the renewal contract this government signed with the people on day one.",
      attribution: "Revanth Reddy",
      role: "Chief Minister · INC",
      source: "Khammam Rally",
      timestamp: "12 May · 16:20 IST",
    },
  },
  {
    rank: "02",
    stance: "critical",
    headline: "KTR's Kaleshwaram cost-overrun tweet sets overnight tone",
    summary:
      "A 02:14 IST tweet citing the ₹85,000 crore overrun figure was amplified 14× in five hours, forcing a defensive response from irrigation officials before sunrise.",
    spark: "story2",
    metrics: { articles: 78, outlets: 14, vs: "+1,240%" },
    coverage: { crit: 72, neu: 18, sup: 10 },
    lens: [
      { outlet: "Sakshi", lang: "telugu", stance: "critical", quote: "₹85,000 కోట్లు — accountability still pending." },
      { outlet: "NTV", lang: "telugu", stance: "critical", quote: "Probe panel report buried by ruling government." },
      { outlet: "The Hindu", lang: "english", stance: "neutral", quote: "Engineering review cited but unreleased." },
      { outlet: "Indian Express", lang: "english", stance: "neutral", quote: "BRS demands white paper on irrigation spends." },
      { outlet: "ETV", lang: "telugu", stance: "critical", quote: "ప్రాజెక్ట్ నిర్వహణలో పారదర్శకత లేదు." },
    ],
    caption: "Tweet-led; Telugu vernaculars carry the heaviest weight by morning.",
    principalQuote: {
      text: "₹85,000 crore disappeared into Kaleshwaram pillars. Who audits the auditors of the audit committee?",
      attribution: "K. T. Rama Rao",
      role: "Working President · BRS",
      source: "Twitter / X",
      timestamp: "12 May · 02:14 IST",
    },
  },
  {
    rank: "03",
    stance: "neutral",
    headline: "Revanth's Khammam rally repeats 'BRS wasted ₹40,000 crore' line",
    summary:
      "The Chief Minister returned to a familiar attack line tying BRS to fiscal mismanagement; English desks treated it as routine, Hindi outlets picked up the figure verbatim.",
    spark: "story3",
    metrics: { articles: 71, outlets: 12, vs: "+180%" },
    coverage: { crit: 32, neu: 48, sup: 20 },
    lens: [
      { outlet: "Eenadu", lang: "telugu", stance: "neutral", quote: "Rally speech echoes earlier Karimnagar themes." },
      { outlet: "Dainik Bhaskar", lang: "hindi", stance: "neutral", quote: "₹40,000 करोड़ का आरोप दोहराया।" },
      { outlet: "The Hindu", lang: "english", stance: "neutral", quote: "CM repeats fiscal-mismanagement charge at rally." },
      { outlet: "TV9", lang: "telugu", stance: "supportive", quote: "Revanth lays out accountability roadmap clearly." },
      { outlet: "Mint", lang: "english", stance: "neutral", quote: "Specific projects cited not in current audit." },
    ],
    caption: "Descriptive English desks; Hindi outlets quote the headline figure intact.",
  },
  {
    rank: "04",
    stance: "critical",
    headline: "Dharani portal errors recirculated; opposition Twitter at 14× volume",
    summary:
      "Screenshots of corrupted survey records resurfaced overnight; BRS-aligned handles drove a co-ordinated push at 14× the platform's seven-day baseline.",
    spark: "story4",
    metrics: { articles: 124, outlets: 16, vs: "+1,420%" },
    coverage: { crit: 78, neu: 17, sup: 5 },
    lens: [
      { outlet: "V6 News", lang: "telugu", stance: "critical", quote: "Farmers wait months — Dharani fix not in sight." },
      { outlet: "Sakshi", lang: "telugu", stance: "critical", quote: "రైతుల భూముల వివరాలు తప్పుగా నమోదు." },
      { outlet: "Deccan Herald", lang: "english", stance: "critical", quote: "Land-records overhaul stalls under new dispensation." },
      { outlet: "ABN", lang: "telugu", stance: "neutral", quote: "Revenue dept promises audit within fortnight." },
      { outlet: "The Hindu", lang: "english", stance: "neutral", quote: "Ministerial committee to review portal Friday." },
    ],
    caption: "Co-ordinated push: 14× baseline volume from opposition-aligned accounts.",
    principalQuote: {
      text: "Farmers in three districts still cannot access mutation records flagged for correction in February.",
      attribution: "Sakshi Field Desk",
      role: "Field reporting",
      source: "Field Report",
      timestamp: "12 May · 06:55 IST",
    },
  },
  {
    rank: "05",
    stance: "supportive",
    headline: "Adilabad farmer-loan-waiver announcement underreported",
    summary:
      "A second-tranche ₹2,000 crore waiver announced at Mancherial received scant attention outside Telugu state-pages; English national press did not cover it.",
    spark: "story5",
    metrics: { articles: 18, outlets: 4, vs: "−45%" },
    coverage: { crit: 12, neu: 30, sup: 58 },
    lens: [
      { outlet: "Eenadu", lang: "telugu", stance: "supportive", quote: "₹2,000 కోట్ల రెండో విడత విడుదల." },
      { outlet: "Andhra Jyothy", lang: "telugu", stance: "supportive", quote: "Adilabad farmers welcome the second instalment." },
      { outlet: "TV9 Telugu", lang: "telugu", stance: "neutral", quote: "Eligibility list publication awaited from district." },
      { outlet: "Deccan Chronicle", lang: "english", stance: "neutral", quote: "Tranche announced; rollout details thin." },
      { outlet: "—", lang: "english", stance: "neutral", quote: "No English national-press coverage detected." },
    ],
    caption: "Underreported relative to political weight; favourable for the principal.",
  },
];

export const ENTITIES = [
  {
    name: "Revanth Reddy",
    role: "Chief Minister · INC",
    init: "RR",
    ring: "violet",
    mentions: 47, change: "+12%",
    sentiment: -0.18,
    spark: "rev",
    latest: {
      stance: "neutral",
      quote: "Musi rejuvenation is not a project — it is the renewal contract this government signed with the people.",
      ctx: "Khammam rally · 12 May · 16:20 IST",
    },
    live: true,
  },
  {
    name: "K. T. Rama Rao",
    role: "Working President · BRS",
    init: "KT",
    ring: "rose",
    mentions: 91, change: "+1,240%",
    sentiment: -0.55,
    spark: "ktr",
    latest: {
      stance: "critical",
      quote: "₹85,000 crore disappeared into Kaleshwaram pillars. Who audits the auditors of the audit committee?",
      ctx: "Twitter / X · 12 May · 02:14 IST",
    },
    tweet: {
      handle: "@KTRBRS",
      time: "02:14 IST",
      body: 'The Kaleshwaram cost-overrun is now public record. <span class="hash">#₹85000Cr</span> <span class="hash">#KaleshwaramFailures</span> — three engineers, two reports, one missing minister.',
      hasImage: true,
    },
    live: true,
  },
  {
    name: "K. Chandrasekhar Rao",
    role: "Former CM · BRS",
    init: "KCR",
    ring: "amber",
    mentions: 18, change: "−8%",
    sentiment: 0.02,
    spark: "kcr",
    latest: {
      stance: "neutral",
      quote: "When history examines who built modern Telangana, the answer will not require footnotes.",
      ctx: "Erravalli farmhouse statement · 11 May · 19:10 IST",
    },
  },
  {
    name: "Akbaruddin Owaisi",
    role: "MLA Chandrayangutta · AIMIM",
    init: "AO",
    ring: "teal",
    mentions: 30, change: "+62%",
    sentiment: -0.1,
    spark: "owaisi",
    latest: {
      stance: "neutral",
      quote: "Old City infrastructure deserves the same budgetary urgency the rest of the city has enjoyed for twenty years.",
      ctx: "Assembly intervention · 12 May · 14:05 IST",
    },
  },
  {
    name: "Bandi Sanjay Kumar",
    role: "Union MoS · BJP",
    init: "BS",
    ring: "purple",
    mentions: 40, change: "+180%",
    sentiment: -0.32,
    spark: "bandi",
    latest: {
      stance: "critical",
      quote: "Congress promises in Telangana have a half-life shorter than a press conference.",
      ctx: "Karimnagar press meet · 12 May · 11:30 IST",
    },
  },
  {
    name: "Musi Rejuvenation",
    role: "Issue · Flagship Project",
    icon: "wave",
    ring: "emerald",
    mentions: 98, change: "+540%",
    sentiment: -0.42,
    spark: "musi",
    latest: {
      stance: "critical",
      quote: "Phase 1 displacement has begun without rehabilitation schedules being published or shared.",
      ctx: "V6 News investigation · 12 May · 08:40 IST",
    },
    live: true,
  },
  {
    name: "Dharani Portal",
    role: "Issue · Land Records",
    icon: "database",
    ring: "blue",
    mentions: 76, change: "+1,420%",
    sentiment: -0.6,
    spark: "dharani",
    latest: {
      stance: "critical",
      quote: "Farmers in three districts still cannot access mutation records flagged for correction in February.",
      ctx: "Sakshi field report · 12 May · 06:55 IST",
    },
  },
  {
    name: "Kaleshwaram",
    role: "Issue · Irrigation",
    icon: "droplet",
    ring: "pink",
    mentions: 86, change: "+2,140%",
    sentiment: -0.5,
    spark: "kalesh",
    latest: {
      stance: "critical",
      quote: "The pillar-subsidence report from 2023 has now been confirmed by the comptroller's preliminary audit.",
      ctx: "PTI wire · 12 May · 04:22 IST",
    },
  },
];

export const HORIZON = [
  { day: "TUE", date: "13", today: true, events: [
    { title: "Cabinet briefing · Musi review", type: "cabinet", src: "Sec. — internal note" },
    { title: "ENS opposition presser", type: "press", src: "Eenadu calendar" },
  ]},
  { day: "WED", date: "14", events: [
    { title: "KTR press conference", type: "press", src: "BRS calendar" },
    { title: "Cabinet meeting prep", type: "cabinet", src: "PMO memo" },
  ]},
  { day: "THU", date: "15", events: [
    { title: "Court hearing prep · Dharani", type: "court", src: "HC roster" },
    { title: "KTR scheduled press meet", type: "press", src: "Party release" },
  ]},
  { day: "FRI", date: "16", events: [
    { title: "Cabinet meeting", type: "cabinet", src: "Sec. memo" },
    { title: "Pre-positioned irrigation attack", type: "press", src: "Twitter monitor" },
  ]},
  { day: "SAT", date: "17", events: [
    { title: "ENS Adilabad visit", type: "rally", src: "CM office" },
    { title: "Farmer protest · Mancherial", type: "rally", src: "AIKS calendar" },
  ]},
  { day: "SUN", date: "18", events: [
    { title: "CM Karimnagar rally", type: "rally", src: "PCC calendar" },
    { title: "Mid-Manair recirculation", type: "press", src: "V6 monitor" },
  ]},
  { day: "MON", date: "19", events: [
    { title: "Dharani High Court hearing", type: "court", src: "Cause list" },
  ]},
];

export const VOICES_DELETED = []; // MO-3: Voices Overnight removed; quotes migrated into STORIES[].principalQuote

export const CLIMBING = [
  {
    spark: "climb_a",
    headline: "Pillar-subsidence report referenced in three Telugu evening bulletins",
    mentions: 92, vs: "+2,140%", window: "4H",
    rec: "BRACE FOR EVENING BULLETIN",
    recType: "brace",
  },
  {
    spark: "climb_b",
    headline: "Dharani screenshots circulating in BRS WhatsApp networks since 04:00",
    mentions: 66, vs: "+1,420%", window: "5H",
    rec: "RESPOND NOW",
    recType: "respond",
  },
  {
    spark: "climb_c",
    headline: "Kothagudem displacement vlog crosses 240k Telugu views overnight",
    mentions: 61, vs: "+840%", window: "6H",
    rec: "MONITOR",
    recType: "monitor",
  },
];

export const BLINDSPOT = {
  telugu_led: [
    { title: "Adilabad farmer-loan-waiver second tranche announced at Mancherial.", t: 6, e: 0 },
    { title: "Kothagudem displacement testimony published as long-form by V6.", t: 5, e: 0 },
    { title: "Karimnagar SC commission report on caste violence in March.", t: 4, e: 0 },
    { title: "Nizamabad turmeric MSP rollback — front-page Eenadu, ignored nationally.", t: 7, e: 1 },
  ],
  english_led: [
    { title: "Mint analysis: Telangana fiscal deficit at 4.2% — sectoral implications.", t: 0, e: 4 },
    { title: "Indian Express op-ed reading Kaleshwaram in national-FDI frame.", t: 0, e: 3 },
    { title: "Reuters wire on Hyderabad data-centre power-load forecasts.", t: 1, e: 5 },
    { title: "FT comment on TSRTC privatisation discussion at GoI level.", t: 0, e: 3 },
  ],
};

export const RECOMMENDED = [
  {
    outlet: "hindu",
    name: "The Hindu",
    byline: "Editorial Desk · 5 MIN READ",
    headline: "What the Musi rejuvenation tells us about urban governance in flagship states",
    summary:
      "A measured analysis of how funding architecture, rehabilitation timelines, and political signalling intersect in Phase 1 of the corridor.",
    meta: "5 MIN · SUPPORTIVE STANCE · 1,247 WORDS",
  },
  {
    outlet: "toi",
    name: "Times of India",
    byline: "Op-Ed · 4 MIN READ",
    headline: "The fiscal arithmetic behind a second farm-loan-waiver tranche",
    summary:
      "Why the ₹2,000 crore Adilabad announcement is more politically calibrated than fiscally constraining — and what it signals before the by-elections.",
    meta: "4 MIN · NEUTRAL STANCE · 982 WORDS",
  },
  {
    outlet: "mint",
    name: "Mint",
    byline: "Long Read · 8 MIN READ",
    headline: "Telangana's irrigation balance sheet, line by line",
    summary:
      "A forensic read of three audit reports, two engineering reviews, and what the Kaleshwaram cost-overrun actually means for the state's borrowing room.",
    meta: "8 MIN · CRITICAL STANCE · 2,156 WORDS",
  },
];

/* MO-5: Refresh timing */
export const REFRESH_INTERVAL_MS = 15 * 60 * 1000;
export const nextRefreshAt = Date.now() + REFRESH_INTERVAL_MS;
