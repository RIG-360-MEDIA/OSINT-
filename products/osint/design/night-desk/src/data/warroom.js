// ============================================================================
// WAR ROOM — "THE CABLE DESK"
// Operational response console. Deliberately distinct from Home's broadsheet:
// cold mono-led chrome, one warm serif voice (the hostile claim), colour used
// ONLY as data, every figure a footnote → the shared Verify drawer.
//
// Hardcoded for the Government of Telangana / Revanth Reddy persona. Copy is
// ILLUSTRATIVE placeholder pending wiring to the live corpus — quotes/claims are
// not yet source-verified and must pass the cite-ID guardrail before release.
// Numbers are grounded in the verified directional-valence pass over the
// 47-day corpus (16 Apr – 01 Jun 2026 · ~148K articles · 130K stances).
// ============================================================================

const W = '47-day corpus (16 Apr – 01 Jun)';

// ── station strip — the live instrument header ──────────────────────────────
export const STATION = {
  desk: 'RESPONSE DESK',
  open: 9, critical: 2,
  pressure: '123.8',
  pressureNote: '▲ above 21-day baseline',
  counterSpeed: '8.4h',
  asOf: '02 JUN · 06:00 IST',
  window: '47-day window · replay clock',
  pressureMetric: {
    label: 'Weighted pressure', value: '123.8', n: 412, confidence: 'high',
    verify: {
      definition: 'Total hostile load on the subject right now — every live attack, weighted by how far it can travel.',
      formula: 'Σ (reach · negativity · outlet-tier) over open hostile stories',
      source: 'articles × register_emotion × entity_mentions × sources.source_tier',
      window: W,
      underlying: ['9 open hostile stories above response threshold', '412 hostile mentions of the subject in-window', 'baseline 21-day mean = 86.0 → current is +44%'],
    },
  },
};

// ── the lead — Crisis Watch (one storyline, full width) ─────────────────────
export const LEAD = {
  tag: 'CRISIS WATCH',
  windowEst: '~48h',
  slug: 'JANGAON ∕∕ SUPPRESSION FRAME',
  read: 'The Jangaon “farmer suppression” line is the storyline likeliest to break out. It is still Telugu-only and BRS-driven — but it fuses the two charges that travel furthest: anti-farmer and anti-dissent. The day it crosses into English or a TV cycle, it goes national.',
  trigger: 'Crossing trigger — first English Tier-1 pickup, or any TV-debate booking.',
  basis: 'BRS welding procurement delay + Jangaon arrests · 38 Telugu articles · 8× normal volume · 7 outlets in 6h.',
  caveat: 'Window is inferred from current velocity — an estimate, not a hard deadline.',
  metric: {
    label: 'Break-out likelihood', value: 'HIGH', n: 38, confidence: 'medium',
    verify: {
      definition: 'How likely a contained storyline is to cross into mainstream / national coverage in the near term.',
      formula: 'velocity-trend × cross-language-gap × tier-ceiling (still Tier-2/Telugu = headroom to climb)',
      source: 'article cluster (LaBSE) × language × sources.source_tier × daily volume series',
      window: W,
      underlying: ['38 articles, all Telugu, 0 English pickups yet', 'volume 8× the cluster’s own 21-day baseline', 'confined to Tier-2/regional — no Tier-1 or TV crossing recorded'],
    },
  },
};

// ── the threat stack — Critical Negative Stories (the spine) ────────────────
// sev drives the hairline tick + score glow. verdict = the action call.
export const CABLES = [
  {
    id: 1, sev: 'CRITICAL', verdict: 'RESPOND', score: 92, src: 7,
    date: '18 MAY', origin: 'NAMASTHE TELANGANA', who: 'KCR · KTR — BRS',
    receipt: { reach: 0.82, neg: 0.95, vel: 0.66, tier: 0.90 },
    claim: '“Congress betrayed the farmers.”',
    facets: {
      what: 'BRS has welded the procurement delays and the Jangaon arrests into a single line — anti-farmer and anti-dissent — and pushed it across 7 Telugu outlets inside 6 hours.',
      hurts: 'It poisons the one issue you own (agriculture) and reframes a law-and-order event as suppression. This is the line that defines next year’s rural fight.',
      acts: 'Lead the grain-on-mission-mode order in Telugu before noon; cite the review directly. Don’t argue “suppression” — bury it under delivery.',
      hits: ['Revanth Reddy', 'CMO', 'Agriculture dept'],
    },
    metric: {
      label: 'Threat score', value: 92, n: 38, confidence: 'high',
      verify: {
        definition: 'Priority of a hostile story — how much damage it can do and how fast.',
        formula: 'score = 100 × (0.30·reach + 0.30·negativity + 0.20·velocity + 0.20·tier)',
        source: 'articles × register_emotion × entity_mentions × sources.source_tier',
        window: W,
        underlying: ['“KCR slams Revanth Reddy over farm procurement” — Namasthe Telangana, 18 May', '“No vision in Revanth’s rule: Harish Rao” — V6, 21 May', '38 articles in this cluster · 8× normal volume'],
      },
    },
  },
  {
    id: 2, sev: 'HIGH', verdict: 'BRACE', score: 74, src: 5,
    date: '29 MAY', origin: 'THE HINDU', who: 'BJP state unit',
    receipt: { reach: 0.58, neg: 0.70, vel: 0.40, tier: 0.95 },
    claim: '“T-Wallet leak put 16 lakh users at risk.”',
    facets: {
      what: 'A data-leak claim now carrying a High Court notice — three Tier-1 outlets, both languages. The court process gives it a life of its own.',
      hurts: 'Compounding, not spiking. Your silence is reading as guilt; the legal track means it returns on every hearing date regardless of news cycle.',
      acts: 'Get ahead of it today — a transparency note: scope, fix timeline, independent audit. This is your unguarded flank. Verify specifics before you assert them.',
      hits: ['IT dept', 'CMO', 'Revanth Reddy'],
    },
    metric: {
      label: 'Threat score', value: 74, n: 14, confidence: 'high',
      verify: {
        definition: 'Priority of a hostile story — how much damage it can do and how fast.',
        formula: 'score = 100 × (0.30·reach + 0.30·negativity + 0.20·velocity + 0.20·tier)',
        source: 'articles × register_emotion × entity_mentions × sources.source_tier',
        window: W,
        underlying: ['“HC notice on T-Wallet data leak” — The Hindu, 29 May', '3 Tier-1 outlets · English + Telugu', 'court notice = structural longevity, not volume'],
      },
    },
  },
  {
    id: 3, sev: 'WATCH', verdict: 'HOLD', score: 41, src: 5,
    date: '24 MAY', origin: 'DECCAN CHRONICLE', who: 'English commentariat',
    receipt: { reach: 0.30, neg: 0.52, vel: 0.18, tier: 0.55 },
    claim: '“Who really protects the treasury?”',
    facets: {
      what: 'Op-eds questioning the government’s fiscal vigilance. Five pieces, English Tier-2, no Telugu pickup.',
      hurts: 'Loud in the commentariat, but it doesn’t move rural votes and hasn’t crossed into Telugu. Feeding it is the only thing that grows it.',
      acts: 'No response. Re-rank only if a Telugu Tier-1 outlet picks it up — your micro-vigilance record beats KTR’s on four of five metrics, ready if it escalates.',
      hits: ['Finance dept', 'Revanth Reddy'],
    },
    metric: {
      label: 'Threat score', value: 41, n: 5, confidence: 'medium',
      verify: {
        definition: 'Priority of a hostile story — how much damage it can do and how fast.',
        formula: 'score = 100 × (0.30·reach + 0.30·negativity + 0.20·velocity + 0.20·tier)',
        source: 'articles × register_emotion × entity_mentions × sources.source_tier',
        window: W,
        underlying: ['5 op-eds, English Tier-2 only', '0 Telugu pickups → contained', 'velocity flat over 6 days'],
      },
    },
  },
];

// ── the arsenal — what you say back (right rail, keyed to top cable) ─────────
export const ARSENAL = {
  forCable: 'CRITICAL ∕∕ 92',
  ammunition: [
    'Procurement review is on mission-mode — collectors personally accountable, on record in 9 outlets.',
    '₹1 crore each to drivers’ families — welfare proof landing in the same Telugu press.',
  ],
  predraft: {
    lang: 'TE', words: 80,
    flag: 'Telugu draft — machine-assisted. Desk sign-off required before release.',
    en: 'Grain procurement is on mission-mode; collectors are personally accountable and the review order is public. This government delivers for farmers — and will not be lectured by those who presided over the backlog.',
  },
  intercepts: [
    { who: 'KTR', role: 'BRS Working President', tier: 'T1', quote: 'This government has buried the farmer under file and delay.', src: 'Namasthe Telangana · 18 May' },
    { who: 'Harish Rao', role: 'BRS · ex-Finance Min', tier: 'T1', quote: 'There is no vision in Revanth’s rule — only press notes.', src: 'V6 · 21 May' },
    { who: 'KCR', role: 'BRS President', tier: 'T1', quote: 'Congress betrayed the farmers the day they took office.', src: 'Telangana Today · 16 May' },
  ],
};

// ── the field — entity intelligence band ────────────────────────────────────
// #5 Escalation + Entity Momentum
export const MOMENTUM = {
  note: 'Mention volume vs each entity’s own 21-day baseline. Surging = climbing the board.',
  items: [
    { name: 'KCR', vol: 80, neg: 35, trend: '+18', dir: 'up' },
    { name: 'KTR', vol: 36, neg: 32, trend: '+9', dir: 'up' },
    { name: 'BJP (state)', vol: 41, neg: 12, trend: '+5', dir: 'up' },
    { name: 'Harish Rao', vol: 22, neg: 14, trend: '−3', dir: 'down' },
  ],
  metric: {
    label: 'Entity momentum', value: 'KCR +18', n: 179, confidence: 'high',
    verify: {
      definition: 'Change in an entity’s hostile-mention volume against its own recent baseline.',
      formula: 'Δ = mentions(7d) − mean(mentions, trailing 21d), per entity',
      source: 'entity_mentions × register_emotion (daily series)',
      window: W,
      underlying: ['KCR 80 mentions / 35 hostile in-window', 'KTR 36 / 32 hostile', 'baselines from the daily co-mention series'],
    },
  },
};

// #6 Per-Entity Attack Map (rival × issue)
export const ATTACKMAP = {
  note: 'Which rival hits you on which issue — co-salient critical stance.',
  rivals: ['KCR', 'KTR'],
  issues: ['Farmers', 'Law & order', 'Fiscal', 'Welfare', 'Graft'],
  grid: {
    KCR: { Farmers: 3, 'Law & order': 2, Fiscal: 2, Welfare: 1, Graft: 3 },
    KTR: { Farmers: 2, 'Law & order': 1, Fiscal: 1, Welfare: 2, Graft: 2 },
  },
  foot: 'KCR spans 8 topics across 35 articles; KTR 5 topics across 32.',
};

// #7 Bloc / Coalition
export const BLOC = {
  note: 'Who attacks in concert — co-mention inside the same hostile stories.',
  edges: [{ a: 'KCR', b: 'KTR', n: 36 }],
  solo: ['BJP (state)', 'AIMIM'],
  foot: 'KCR–KTR move together in 36 stories; BJP runs a separate fiscal line.',
};

// #8 Allegiance Roster (against + neutral only — "for" is intentionally hollow)
export const ROSTER = {
  note: 'Watchlist by directional stance.',
  against: ['K. Chandrashekar Rao', 'K. T. Rama Rao', 'Harish Rao', 'Bandi Sanjay', 'BJP (state)', 'AIMIM'],
  neutral: ['Election Commission', 'High Court', 'Commentariat', 'Trade bodies'],
  forNote: 'The “for” column is intentionally empty — supportive signal in the corpus is self-coverage, not independent backing. We don’t fabricate allies.',
};

// #9 New Entrant Alert
export const NEWENTRANTS = {
  note: 'Entities newly co-salient with you in hostile stories (21d) — not seen before.',
  filtered: 46,
  items: [
    { name: 'Chamala Kiran Kumar', ctx: 'BRS — entered the Jangaon line', n: 4 },
    { name: 'Raithu Swarajya Vedika', ctx: 'farm group amplifying procurement', n: 5 },
    { name: 'T-Wallet petitioner', ctx: 'named in the data-leak PIL', n: 3 },
  ],
};

// #4 Counter-Attack Targets
export const COUNTERATTACK = {
  note: 'Where the opposition is itself under fire — your openings (volume × negativity × tier).',
  items: [
    { name: 'KCR', issue: 'LEGAL', heat: 21, line: 'Cases + ED summons give you a clean, on-record counter.' },
    { name: 'KCR', issue: 'SECURITY', heat: 12, line: 'Phone-tapping probe still live in Tier-1.' },
    { name: 'BJP (state)', issue: 'FARM DUES', heat: 9, line: 'Centre’s unpaid dues — a Telugu-press soft spot.' },
  ],
  metric: {
    label: 'Counter-attack heat', value: 'KCR · LEGAL 21', n: 21, confidence: 'high',
    verify: {
      definition: 'Hostile pressure landing on the opposition — the mirror of your own threat score, scored on them.',
      formula: 'heat = volume × negativity × outlet-tier, computed on the rival as subject',
      source: 'articles × register_emotion × entity_mentions × sources.source_tier',
      window: W,
      underlying: ['21 hostile stories with KCR as object on the LEGAL issue', 'ED summons + phone-tap probe clusters', 'both languages, Tier-1 present'],
    },
  },
};

// #3 Fact-Check → Claim Audit (contested / corroborated — never true/false)
export const CLAIMAUDIT = {
  note: 'Specific claims about you, scored by source agreement — contested vs corroborated, never “true / false.”',
  items: [
    { claim: '“State debt has crossed ₹7 lakh crore.”', verdict: 'CONTESTED', tone: 'neg', forN: 2, againstN: 4, note: '2 outlets assert; 4 cite lower CAG-linked figures.' },
    { claim: '“Procurement payments delayed 40+ days.”', verdict: 'CORROBORATED', tone: 'neu', forN: 6, againstN: 1, note: 'Carried consistently across 6 outlets — answer on delivery, not denial.' },
    { claim: '“T-Wallet leak exposed 16 lakh users.”', verdict: 'CONTESTED', tone: 'neg', forN: 3, againstN: 3, note: 'Scale disputed; the court notice is the real driver.' },
  ],
  metric: {
    label: 'Claim audit', value: '3 active', n: 3, confidence: 'medium',
    verify: {
      definition: 'How well a specific factual claim is supported across independent outlets — agreement, not a truth verdict.',
      formula: 'corroborated if asserting-sources ≥ 2× disputing; contested otherwise. We never label true/false.',
      source: 'article_claims (claim_text · subject_entity_id · object_text) × sources',
      window: W,
      underlying: ['claim_text matched + clustered by embedding', 'source agreement counted per claim', 'no model-asserted ground truth — agreement only'],
    },
  },
};
