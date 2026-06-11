// HOME = the textual situation report. Voice: sharp desk officer, no AI fluff.
// Mirrors textual.py + posture.py + relevance core. Illustrative copy for
// Revanth Reddy / Telangana. Numbers live inside sentences, not as tiles.

// kept for other pages: Dispatch imports BLUF, Analytics imports NARRATIVE_DNA,
// Ticker imports BREAKING.
export const BLUF =
  'Revanth Reddy is running a two-front narrative offensive — accusing the BJP of a “divide-and-rule” line while countering BRS charges that Congress failed the farmers. Momentum is positive but cooling, and opposition pressure is concentrating in the Telugu-language press.';

export const NARRATIVE_DNA = [
  { n: 'FRAME 01', t: 'Development-driven reformer fixing governance', pct: 46, fill: 'supportive' },
  { n: 'FRAME 02', t: 'The Congress that failed the farmers', pct: 34, fill: 'hostile' },
  { n: 'FRAME 03', t: 'Victim of the Centre’s divide-and-rule', pct: 20, fill: 'rival' },
];

export const BREAKING = [
  'Jangaon: 3 BRS leaders detained',
  'HC notice on T-Wallet data',
  'CM to chair grain review 11:00',
  'Centre clears ₹2,300 cr for irrigation',
];

// ───────────────────────── ① THE BRIEFING ─────────────────────────
export const BRIEFING = {
  bottomLine: [
    { k: 'Where You Stand', v: 'Holding, slipping in Telugu. Winning governance, losing the farmer story.' },
    { k: 'Know This', v: 'The Jangaon arrests became the opposition’s best weapon overnight.' },
    { k: 'The Attack', v: 'BRS: “Congress betrayed the farmers.” Loudest in Namasthe Telangana.' },
    { k: 'Your Move', v: 'Put the procurement line out in Telugu before noon.', action: true },
  ],
  whatHappened: [
    { date: '28 May', text: 'Three BRS leaders detained in Jangaon; party called it “suppression.”', src: 'Namasthe Telangana, V6 Velugu' },
    { date: '29 May', text: 'High Court notice on the T-Wallet leak hitting 16 lakh users.', src: 'The Hindu' },
    { date: '30 May', text: 'You ordered salaries on the 1st; pitched as fiscal discipline.', src: 'Telangana Today' },
    { date: '30 May', text: '₹1 crore each to drivers’ families from TGSRTC, Union Bank.', src: 'Siasat' },
  ],
  whatItMeans:
    'The BRS is welding two stories into one. Jangaon gives them “suppression”; the procurement delays give them “betrayed the farmers.” Together the line is simple — Congress is anti-farmer and anti-dissent — and they’re building it in Telugu, where an English desk never sees it. This isn’t noise: KTR and Harish Rao amplify within the hour of Namasthe running it.',
  whyItMatters:
    'Your whole pitch is welfare delivery. If “anti-farmer” sets before your procurement answer lands, it poisons the one issue you own and hands the BRS a rural line into next year. The data leak is a second front you’re not fighting — silence there reads as guilt.',
  whatsNext: {
    text: 'Watch the language jump. “Suppression” is Telugu-only today; the day it reaches an English daily or a TV panel it goes national. That’s the trigger — likely inside 48 hours if Jangaon stays alive.',
    confidence: 'medium',
  },
  howToPlay:
    'Lead in Telugu, not English — that’s where the fire is. Contest finance; your silence on the leak is costing you. Leave the op-eds alone. Don’t argue “suppression” — bury it under procurement news.',
  otherSide:
    'The case you’re wrong: most of this is one outlet, Namasthe Telangana, doing what it always does. Strip it out and the week is roughly even. The farmer story may die on its own once payments land, and over-responding gives Jangaon oxygen. What would flip the call: a second Tier-1 outlet picking up “suppression.” It hasn’t, yet.',
};

// ───────────────────────── ② TOP STORIES FOR YOU ─────────────────────────
// img: placeholder photos for the mockup — real article images (article_media, 83%) replace these on wiring.
export const TOP_STORIES = [
  { tone: 'hostile', headline: 'HC issues notice on T-Wallet leak hitting 16 lakh users', source: 'The Hindu', age: '6h', img: 'https://picsum.photos/seed/twallet-osint/720/440', forYou: 'Your unguarded flank. Three Tier-1 papers and now a court behind it. Every hour you stay quiet, “the government is hiding something” writes itself. Get ahead of this one today.' },
  { tone: 'hostile', headline: 'BRS leaders detained in Jangaon; party cries “suppression”', source: 'V6 Velugu', age: '14h', img: 'https://picsum.photos/seed/jangaon-osint/720/440', forYou: 'The arrests are being turned into a story about you, not law and order — the seed of the “anti-dissent” frame. Still walled inside Telugu. Don’t feed it.' },
  { tone: 'supportive', headline: 'CM orders salaries on the 1st of every month', source: 'Telangana Today', age: '9h', img: 'https://picsum.photos/seed/salaries-osint/720/440', forYou: 'A clean governance win landing positive but far too quietly. While farmer attacks own Telugu, this is the discipline story your office should be pushing — in Telugu, not English.' },
  { tone: 'supportive', headline: '₹1 crore each to drivers’ families', source: 'Siasat', age: '11h', img: 'https://picsum.photos/seed/drivers-osint/720/440', forYou: 'Welfare optics that are working regionally. Small story, strong emotional pickup — a photo-op follow would stretch it another day.' },
  { tone: 'supportive', headline: 'Centre clears ₹2,300 cr for Telangana irrigation', source: 'The Hindu', age: '6h', img: 'https://picsum.photos/seed/irrigation-osint/720/440', forYou: 'A ready-made “we deliver for farmers” counter to the BRS line — but it’s stuck in an English paper your farmer critics never read. Translate it and push it in Telugu.' },
  { tone: 'neutral', headline: 'Op-ed: Telangana’s farm math doesn’t add up', source: 'Deccan Chronicle', age: '1d', img: 'https://picsum.photos/seed/farmmath-osint/720/440', forYou: 'Elite English skepticism. Loud in the commentariat, but it doesn’t move rural votes. Note it; don’t chase it.' },
];

// ───────────────────────── ③ PEOPLE TO WATCH ─────────────────────────
export const PLAYERS = [
  {
    name: 'K. Chandrashekar Rao', rel: 'BRS · your principal rival', stance: 'hostile',
    verdict: 'Hostile, and hardening', score: '−64', trend: '↓ from −51',
    summary: 'KCR has spent the week turning the farmer into his entire case against you. He led the procurement-delay dharna himself, then moved fast on the Jangaon arrests, recasting a law-and-order action as “suppression of dissent” — and KTR and Harish Rao had that framing across Telugu outlets within the hour. The coordination is the real signal: this isn’t a leader reacting to events, it’s a party running a tested playbook, and you’re the trial run for next year’s rural campaign.',
    why: 'Nine straight critical pieces in Namasthe Telangana, most at high intensity; his quotes outnumber yours three-to-one in V6 Velugu. It isn’t worse only because NTV is playing your procurement reviews straight.',
    watch: 'The moment “suppression” reaches an English daily or a TV panel, he’s gone national. It hasn’t crossed yet — that’s your window.',
  },
  {
    name: 'K. T. Rama Rao', rel: 'BRS · the amplifier', stance: 'hostile',
    verdict: 'Hostile, fast', score: '−38', trend: 'steady',
    summary: 'KTR is the distribution arm of the attack, not its author. He rarely originates a line; he takes KCR’s and makes it travel, usually within the hour, across Telugu TV and a large personal following. This week his job was the farmer story, and he’s quoted in nearly every Telugu piece carrying “betrayed the farmers.” His danger isn’t what he says — it’s the speed at which he moves it.',
    why: 'Present in seven of the nine Namasthe farmer pieces; he sets the pace, not the agenda.',
    watch: 'If KTR personally takes up the data leak, the BRS has decided finance is a winnable second front.',
  },
  {
    name: 'Namasthe Telangana', rel: 'Telugu daily · your sharpest critic', stance: 'hostile',
    verdict: 'Hostile, and the source', score: '−50', trend: 'at the floor',
    summary: 'This is where most of the week’s damage starts. It runs the farmer and Jangaon lines first and hardest, quotes your critics three-to-one, and the rest of the Telugu ecosystem takes its cue from it. Treat it as the BRS’s house paper rather than a neutral outlet — arguing with it only amplifies it.',
    why: 'Eighteen critical mentions this window, the most of any outlet; almost none of your own framing carried.',
    watch: 'It’s already at the floor. The risk isn’t Namasthe getting worse — it’s a second outlet matching it.',
  },
  {
    name: 'Harish Rao', rel: 'BRS · ex-finance minister', stance: 'hostile',
    verdict: 'Hostile, technical', score: '−29', trend: 'rising',
    summary: 'Harish Rao is the BRS’s numbers man on this offensive — he’s the one putting figures to the “failed farmers” charge, citing procurement backlogs and Rythu Bandhu delays. He’s more credible to neutral readers than the louder voices, which makes him the harder one to dismiss.',
    why: 'Drives the finance-and-procurement angle in Telangana Today and Andhra Jyothy; quoted with specifics, not slogans.',
    watch: 'He’s the bridge to the finance front. If your data-leak silence holds, expect him to widen it.',
  },
  {
    name: 'BJP State Unit', rel: 'opposition · second front', stance: 'hostile',
    verdict: 'Opportunistic', score: '−22', trend: 'steady',
    summary: 'The BJP is running its own track, separate from the BRS — built around the T-Wallet data leak and governance competence, aimed more at English and national coverage than Telugu. It’s lower-volume but better-placed: it lands in the papers that shape the national read of you.',
    why: 'Concentrated in The Hindu and Deccan Chronicle on the data leak; low Telugu footprint.',
    watch: 'If the BRS farmer line and the BJP leak line ever merge into one week, that’s your worst case.',
  },
];

// ───────────────────────── THE SIX ─────────────────────────
export const SIX = [
  {
    kicker: 'The Hard Truth', title: 'Where you’re actually losing',
    body: 'You’re being told you had a good week. You didn’t. The salary order your office is circulating is real, but it isn’t what anyone is talking about — the room is on Jangaon and the data leak, and you’ve answered neither. You’ve also quietly conceded finance: the opposition has put it in front of voters 119 times this week and you’ve responded once. Underneath all of it is language. You’re comfortably ahead in the English press, which is what your desk reads, and losing badly in Telugu, which is what your voters read — by roughly twenty points, and widening. No one on your team will put the week this bluntly. That’s why it’s here.',
    print: 'built from coverage counts — it reads the press, not the public.',
  },
  {
    kicker: 'Real or Noise?', title: 'What’s actually worth reacting to',
    items: [
      { verdict: 'HOLD', vtone: 'neu', text: '“Suppression” frame — it’s everywhere you look, but everywhere you look is two Telugu outlets and one district. No English pickup, no TV, no document behind it. Loud, not dangerous.' },
      { verdict: 'RESPOND', vtone: 'neg', text: 'T-Wallet leak — quieter in tone but structurally serious: three Tier-1 outlets, both languages, and a court notice that gives it a life of its own. This is the one that compounds if you ignore it. Today.' },
    ],
  },
  {
    kicker: 'Are You Being Heard?', title: 'Are they quoting you, or speaking for you',
    body: 'Being covered and being heard are not the same thing, and right now you’re covered but not heard. Across the week the opposition is quoted 2.4 times for every once you are — they are, in plain terms, speaking for you inside your own coverage. It’s worst where it costs most: in V6 Velugu, a high-reach Telugu outlet, it runs seven of their quotes to two of yours. The only place your words are carried at parity is NTV. The fix isn’t more coverage — you have plenty. It’s that the coverage you have is letting the other side define you, in the language your voters read.',
  },
  {
    kicker: 'The Coverage Split', title: 'Telugu press vs English press',
    body: 'The week looks like two different weeks depending on which press you read — and your desk reads the wrong one. In English you’re barely scratched (−1): national papers see a government delivering salaries and irrigation money. In Telugu you’re being hammered (−22) over farmers and Jangaon. The ground splits the same way: Khammam runs warm where procurement leads, Jangaon runs hot where the arrests do. Brief the boss off the English clippings and you’ll call it a quiet week. It was a quiet week in English and a bad one in Telugu.',
    print: 'press-by-region, not public opinion — we don’t read social media.',
  },
  {
    kicker: 'Who To Call', title: 'Which outlet to work today',
    body: 'Treat your outlet relationships as decisions, not a chart. Give the procurement exclusive to NTV Telugu — it’s the one major Telugu outlet warming toward you (+32) and it has carried your framing straight all week, so a clean win lands cleanly. Eenadu is genuinely neutral right now; that’s worth a background call to keep, not a hard pitch. Don’t spend a minute on Namasthe Telangana — at −50 and falling, it isn’t yours to win this cycle, and engaging only feeds it. One name on the desk: Meena R. at NTV has been consistently fair on procurement; if you’re placing a story, she’s your reporter.',
    print: 'outlet calls are solid; we name a reporter only where the byline is in the data.',
  },
  {
    kicker: 'Ready For You', title: 'Drafts waiting for your sign-off',
    items: [
      { verdict: 'STATEMENT', vtone: 'pos', text: 'Telugu + English, built around procurement and aimed at the “failed farmers” line — 80 words, ready to go or be killed.' },
      { verdict: 'COUNTER-LINE', vtone: 'pos', text: 'For the leak: “Our own audit flagged it; the fix is already running.” Gets you ahead of it honestly.' },
      { verdict: 'TRANSLATED', vtone: 'neu', text: 'V6 Velugu’s lead attack in English, so your national desk sees exactly what’s being said.' },
    ],
    print: 'drafts only — nothing leaves without your sign-off.',
  },
];
