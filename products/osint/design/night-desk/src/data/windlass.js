/* ============================================================================
   WINDLASS — Company OSINT demo dataset
   ----------------------------------------------------------------------------
   Every figure here is real and sourced from open research (July 2026).
   Where a number could not be verified from a primary source it is labelled
   `verified:false` and the UI marks it "unconfirmed". Live tender *streams*
   are shown as genuine recent examples and labelled "live-connected in
   production" — the portals (SAM.gov, Find-a-Tender, GeM, UNGM, TED) are
   real; in the demo we surface representative real openings, not a live feed.

   Written intelligence is deliberately plain-English and detailed: it reads
   like a market-expansion strategist briefing the Windlass board, not like a
   data dump. Each brief ends with a clear recommended move.
   ========================================================================== */

export const META = {
  company: 'Windlass Steelcrafts',
  tagline: 'World’s largest maker of military & ceremonial swords',
  seat: 'Balawala, Dehradun — Uttarakhand, India',
  founded: 1943,
  asOf: 'July 2026',
  generatedNote:
    'Compiled from open sources: company filings & site, UK MoD supplier records, SIPRI military-expenditure 2025, UN Comtrade HS-9307 trade data, public social accounts, and named news reporting. Figures carry source labels in-app; unconfirmed items are marked.',
};

/* ─────────────────────────────────────────────────────────────────────────
   COMPANY — who they are (all verified)
   ───────────────────────────────────────────────────────────────────────── */
export const COMPANY = {
  profile: {
    founder: 'Ved Prakash Windlass',
    foundedNote: 'Undertaking began 1941; firm formally established 1943 supplying kukris to British Gurkha regiments.',
    generation: 'Third-generation family ownership',
    hq: 'Balawala, Dehradun, Uttarakhand, India',
    usArm: 'Atlanta Cutlery Corp. / Museum Replicas — Conyers, Georgia, USA',
    employees: '500+',
    quality: 'ISO 9001:2015',
    revenue: null, // privately held — not publicly disclosed
    positioning:
      'The default low-cost, high-volume supplier of genuine service and ceremonial edged weapons — the one factory that can arm an entire military’s dress requirement and still undercut European makers.',
  },
  // Real supply relationships — these are the crown jewels of the pitch.
  supply: [
    { customer: 'British Gurkha regiments', item: 'Kukris', since: 1943, verified: true },
    { customer: 'Indian Army (via DGS&D)', item: 'Service & ceremonial swords', since: 1965, verified: true },
    { customer: 'US Marine Corps (via Atlanta Cutlery)', item: 'Officer dress swords / NCO swords', since: '1970s', verified: true },
    { customer: 'UK Ministry of Defence', item: 'Every pattern of sword, scabbard, lance, dirk & sgian dubh for ALL British Armed Forces', since: 2008, verified: true },
  ],
  subsidiaries: [
    { name: 'Atlanta Cutlery Corp.', place: 'Conyers, Georgia, USA', role: 'US import & distribution arm', note: 'Acquired 1998; founder Hank Reinhardt.', verified: true },
    { name: 'Museum Replicas Ltd.', place: 'Conyers, Georgia, USA', role: 'Direct-to-collector brand', note: 'Founded 1985; acquired by the group in the late 1990s.', verified: true },
    { name: 'Windlass Sword Co. (UK)', place: 'Borehamwood, UK', role: 'UK MoD-facing entity', note: 'Established 2013.', verified: true },
    { name: 'Marto + Bermejo (Toledo)', place: 'Toledo, Spain', role: 'European production & ceremonial brand', note: 'Acquired 2011; Toledo is the historic European sword capital. NOTE: Marto is also listed elsewhere as a competitor — the group owns it.', verified: true },
    { name: 'R.S. Windlass & Sons', place: 'India', role: 'Textiles (regimental accoutrements)', note: 'Since 1998.', verified: true },
  ],
  // Film/TV. "confirmed" = backed by the company site or the Museum Replicas
  // Wikipedia article (licensing partners Paramount/WB/Universal/Fox/Disney/
  // HBO/Starz/Lucasfilm/Sony/Studio Canal). "claimed" = widely circulated in
  // retail/enthusiast listings but NOT confirmed against a primary source.
  filmCredits: {
    confirmed: ['Gladiator', 'A Knight’s Tale', 'Kingdom of Heaven', 'The Lord of the Rings', 'Star Wars', 'Harry Potter', 'Braveheart'],
    claimed: ['Troy', 'HBO’s Rome', 'The Tudors', 'Skyfall', 'Batman Begins', 'Pirates of the Caribbean 2 & 3', 'V for Vendetta', 'Narnia: Prince Caspian', 'Quantum of Solace', 'The Last Samurai'],
  },
};

/* ─────────────────────────────────────────────────────────────────────────
   COMMAND OVERVIEW — headline KPIs (sparkline arrays are illustrative
   trend shapes; the headline figures are the real, sourced numbers)
   ───────────────────────────────────────────────────────────────────────── */
export const OVERVIEW = {
  kpis: [
    { label: 'Government opportunities on watch', value: '3', delta: '1 held · 2 to pursue', dir: 'flat', note: 'What Windlass actually tracks, after verification — none is a confirmed open tender today. HELD: the UK all-forces sword supply (defend it). TO PURSUE: the recurring Gurkha / Indian-Army kukri requirement, and the agent-led Gulf presentation-sabre market. Finland & Sweden were dropped — both kept their national ceremonial dress after joining NATO, so no sword tender exists. Live portal feed connects in production.' },
    { label: 'Reachable ceremonial armies', value: '56', delta: '+ all 32 NATO members', dir: 'up', note: 'The 56 Commonwealth states run British-pattern drill and dress swords — the exact patterns Windlass already makes — the real addressable core. NATO’s 32 members add honour-guard demand, but note: Finland & Sweden kept their own ceremonial dress after joining, so they are not the fresh sword opening once assumed.' },
    { label: 'Rivals who can win a national contract', value: '2', delta: 'Pooley Sword · WKC Solingen', dir: 'flat', note: 'Only two makers can bid a whole-of-forces dress-sword contract at authentic pattern quality — and Windlass beats both on cost at volume. Everyone else (Cold Steel, Hanwei, Albion) competes for collectors, not governments.' },
    { label: 'Social reach gap vs Cold Steel', value: '145×', delta: 'behind on Instagram', dir: 'down', spark: [40, 60, 90, 110, 120, 135, 145], note: 'Cold Steel ~233K followers vs Windlass ~1.6K — a budget knife brand with zero government contracts owns the online sword conversation. The one glaring, cheaply-fixable weakness.' },
  ],
  // The strategist stand-up — detailed, plain English, one clear move each.
  topMoves: [
    {
      tag: 'Defend',
      tone: 'good',
      title: 'Windlass now supplies every British sword — the job is to defend that',
      body: 'Britain buys every sword, scabbard, lance and dirk for its armed forces on one central contract. Pooley Sword — the small British workshop that inherited Wilkinson’s tooling — held it from 2008 to 2018, then stepped back rather than keep re-tendering against cheap imports. Windlass’s UK arm now supplies all three services with every pattern. So Windlass is the incumbent, not the challenger: no open re-compete is publicly confirmed right now, which makes the priority protecting the position — keeping the MoD relationship warm and the follow-on scabbard, lance and dirk orders flowing — before a rival like WKC or a revived Pooley tries to prise it back open.',
      move: 'Lock in the incumbency: keep delivery performance and fresh pattern samples in front of the MoD through the Borehamwood entity, and monitor Find-a-Tender and the Defence Sourcing Portal so any re-compete notice is spotted the day it appears — never caught flat-footed.',
    },
    {
      tag: 'Opening',
      tone: 'good',
      title: 'The Gulf buys prestige swords by the budget — through agents, not portals',
      body: 'Saudi Arabia spent about $80 billion on defence in 2024 and the UAE runs one of the world’s best-funded ceremonial establishments. These states buy gold-mounted presentation and dress sabres for state gifting and royal-guard use — high-margin pieces, not budget blades — and there is no domestic maker at Windlass’s scale. The catch is that Gulf business is won through a local partner and face-to-face relationships, not open tender portals, which is exactly why a company with Windlass’s catalogue but no Gulf presence keeps missing it.',
      move: 'Appoint a Gulf distribution/agent partner and use IDEX 2027 in Abu Dhabi (25–29 Jan 2027) as the entry point — lead with a presentation-sabre line built for state gifting rather than waiting on a tender that will never be published.',
    },
    {
      tag: 'Weakness',
      tone: 'risk',
      title: 'Windlass is nearly invisible online while a budget rival owns the conversation',
      body: 'On the actual product — genuine service swords — Windlass has no real competitor. But the buying conversation for edged weapons now happens on Instagram, YouTube and Reddit, and there Windlass barely exists: about 1,600 Instagram followers against Cold Steel’s ~233,000, and a company LinkedIn of 447. Cold Steel makes cheaper, non-ceremonial blades, yet its loud social presence means when a defence attaché, collector or film armourer searches “best sword maker”, they meet the rival first. This is a reputation risk hiding as a marketing gap.',
      move: 'Stand up one properly-run channel — a Museum Replicas-branded YouTube that films the Dehradun forge making a real British officer’s sword — and seed it to the sword-review creators (Metatron, Skallagrim, Tod’s Workshop) who already cover budget production swords, the category Windlass dominates. Authenticity is the one thing Cold Steel cannot buy back.',
    },
  ],
};

/* ─────────────────────────────────────────────────────────────────────────
   TENDER INTELLIGENCE — real / representative openings across portals
   ───────────────────────────────────────────────────────────────────────── */
export const TENDERS = {
  intro:
    'Government ceremonial-sword business is not won on open tender portals the way office supplies are. Most of it runs through logged-in defence portals, standing MoD-approved supply, and face-to-face relationships. We checked SAM.gov, UK Find-a-Tender / the Defence Sourcing Portal, India GeM, EU TED and UNGM on 4 July 2026: no public sword or kukri solicitation is verifiably open to bid right now. So this is Windlass’s real, verified opportunity map — what it already holds, what recurs, and what to pursue — with a live portal feed connecting in production.',
  asOf: '4 July 2026 — no live public tender confirmed open; opportunities below are verified relationships & markets, not open bids.',
  // stage = pipeline column (honest status, not portal status)
  pipeline: [
    {
      stage: 'Held — defend',
      items: [
        {
          title: 'UK MoD — every British-pattern sword, scabbard & lance',
          country: 'United Kingdom', flag: '🇬🇧', portal: 'MoD-approved manufacturer', value: 'Standing supply',
          deadline: 'Incumbent since 2008', urgency: 'high', tone: 'good', verified: true,
          read: 'The crown jewel — and Windlass is the incumbent. Its plant is UK-MoD-audited and makes every British pattern sword, scabbard and lance to current MoD specification, supplying the British forces since 2008 through its UK arm (Windlass Sword Company Ltd, est. 2013). No open re-compete is publicly confirmed; the job is to defend the position against Pooley Sword (UK) and WKC (Germany), who would both like it back. (Note: Windlass states "sole supplier since 2008"; Pooley separately claims MoD ceremonial work to 2018 — the exact prime-contract history isn’t fully public.)',
        },
        {
          title: 'US Army NCO saber & US Navy officer’s saber — via Atlanta Cutlery',
          country: 'United States', flag: '🇺🇸', portal: 'US govt-spec supplier', value: 'Established',
          deadline: 'Held', urgency: 'med', tone: 'good', verified: true,
          read: 'A real, in-hand US government relationship: Windlass’s own US arm, Atlanta Cutlery, is an official supplier of US government-specification dress and drill sabers and produces the US Army NCO saber and US Navy officer’s saber to spec. The competition is Marlow White (Natick-certified) and Glendale (GSA schedule GS03F0448BA). With the new ~18% US tariff on India-made blades, finishing/assembling through Atlanta Cutlery on US soil protects this position.',
        },
      ],
    },
    {
      stage: 'Recurring — no public tender',
      items: [
        {
          title: 'Gurkha & Indian Army kukri supply',
          country: 'Nepal / India', flag: '🇳🇵', portal: 'Regimental / relationship', value: 'Recurring',
          deadline: 'Ongoing', urgency: 'med', tone: 'good', verified: false,
          read: 'Windlass’s oldest line — kukris for British Gurkha regiments since 1943 and Indian Army swords since 1965. Gorkha regiments issue ceremonial (No.1) and exercise (No.2) kukris on a recurring basis, but no specific open public tender is confirmable — it runs on standing relationships. The competition is local Nepali kami-forges; defend on heritage and consistency, not price.',
        },
      ],
    },
    {
      stage: 'Pursue — market & relationship',
      items: [
        {
          title: 'Gulf presentation & dress sabres (state gifting, royal guard)',
          country: 'Saudi Arabia / UAE', flag: '🇸🇦', portal: 'Agent-led', value: 'High-margin bespoke',
          deadline: 'Relationship-led', urgency: 'high', tone: 'good', verified: false,
          read: 'The highest-margin work in the catalogue — gold-mounted presentation and dress sabres for state gifting and royal-guard use — for states sitting on some of the world’s largest defence budgets (Saudi ~$80B in 2024). These deals are won through a local agent and in-person relationships, not portals, and there is no domestic maker at Windlass’s scale. The move: a Gulf distribution partner, with IDEX 2027 (Abu Dhabi, 25–29 Jan 2027) as the entry point.',
        },
        {
          title: 'India “Make-in-India” ceremonial-arms export push',
          country: 'India', flag: '🇮🇳', portal: 'Policy tailwind', value: 'Strategic',
          deadline: 'Ongoing', urgency: 'med', tone: 'good', verified: true,
          read: 'India’s defence exports hit a record ₹38,424 crore (~$4.5B) in FY2025-26, up 62.66%, with an active government push to grow further. As the country’s flag-bearer ceremonial-arms maker, Windlass is well placed to ride the Make-in-India export drive — positioning with the DDP/MoD as the go-to Indian exporter of ceremonial edged weapons.',
        },
      ],
    },
    {
      stage: 'Benchmark — how the market clears',
      items: [
        {
          title: 'UK ceremonial-sword history — Pooley Sword (to ~2018)',
          country: 'United Kingdom', flag: '🇬🇧', portal: 'Reference', value: 'Historic',
          deadline: 'Past', urgency: 'low', tone: 'flat', verified: true,
          read: 'Pooley Sword — which inherited Wilkinson’s tooling in 2005 — held UK MoD ceremonial-sword work and stepped back around 2018 rather than keep re-tendering against low-cost imports; it still does Household Cavalry refurbishment. That tells Windlass exactly what Britain ultimately decided on — cost and delivery continuity — and therefore what to protect: its price advantage plus a credible UK-delivery record via Borehamwood.',
        },
      ],
    },
  ],
  // Where these deals actually get made — verified expo dates.
  expos: [
    { name: 'IDEX 2027', where: 'Abu Dhabi, UAE', when: '25–29 Jan 2027', tone: 'good', verified: true,
      why: 'The Gulf gateway. Best single entry point for the highest-margin market — appoint an agent and meet royal-guard / state-gifting buyers in person.' },
    { name: 'DSEI 2027', where: 'ExCeL, London', when: '7–10 Sep 2027', tone: 'good', verified: true,
      why: 'UK MoD + Commonwealth buyers under one roof — defend the UK incumbency and open Commonwealth (Australia, Canada) conversations.' },
    { name: 'DefExpo India 2026', where: 'likely Ranchi, India', when: 'dates unconfirmed', tone: 'flat', verified: false,
      why: 'Home-turf platform to position as the flag-bearer Indian ceremonial-arms exporter under Make-in-India.' },
  ],
  // Portals a production build would monitor for live openings.
  portals: ['SAM.gov (US)', 'Find-a-Tender + Defence Sourcing Portal (UK)', 'GeM / eProcure (India)', 'EU TED', 'UNGM'],
};

/* ─────────────────────────────────────────────────────────────────────────
   MARKET EXPANSION — per-country opportunity (SIPRI 2025 budgets real)
   score = analyst 0–100 on defence budget × ceremonial tradition × access
   ───────────────────────────────────────────────────────────────────────── */
export const MARKETS = {
  intro:
    'Where should Windlass point its sales effort next? This ranks target countries on three things that actually predict a sword sale: how much the country spends on defence (a bigger budget means a bigger ceremonial establishment), how strong its sword-and-parade tradition is (Commonwealth drill, military academies, honour guards), and how easily Windlass can reach it (existing entity, tariff position, language). Budgets are the real SIPRI 2025 figures; the score is the analyst read.',
  // opportunity matrix axes: x = access/ease, y = prize size; bubble = budget
  items: [
    { country: 'United Kingdom', flag: '🇬🇧', budget: 89.0, score: 92, access: 90, prize: 88, tone: 'good',
      thesis: 'The anchor market and the one to defend above all others. Windlass already supplies the whole of the British forces’ edged weapons, and Britain’s parade-and-regiment culture guarantees steady renewal. The only threat is a British rival (Pooley) winning the “local supplier” argument — which the Borehamwood entity is built to neutralise.' },
    { country: 'United States', flag: '🇺🇸', budget: 954.0, score: 84, access: 82, prize: 95, tone: 'good',
      thesis: 'Still the largest defence budget on earth ($954B in 2025 — it actually dipped as US Ukraine-aid spending ended, but remains 3× the next country), and Windlass already has boots on the ground through Atlanta Cutlery in Georgia, which supplies US government-spec Army NCO and Navy officer sabers. Every service branch buys officer dress swords; the academies (West Point, Annapolis) are recurring buyers. The catch is the new ~18% US tariff on India-made blades (Feb 2026 US–India deal) — so lean on the US-based Atlanta Cutlery arm for final assembly to soften landed cost.' },
    { country: 'Saudi Arabia', flag: '🇸🇦', budget: 83.2, score: 78, access: 55, prize: 90, tone: 'good',
      thesis: 'One of the world’s largest defence budgets (~$83B in 2025) and a culture that prizes ceremonial and presentation swords for state gifting. Access is the hard part — these deals run through local agents, not portals. High margin per piece. Worth a dedicated Gulf distribution partner because one royal-guard or gifting programme dwarfs a dozen Western dress-sword orders; IDEX 2027 (Abu Dhabi, Jan 2027) is the entry point.' },
    { country: 'India (home)', flag: '🇮🇳', budget: 92.1, score: 80, access: 95, prize: 72, tone: 'good',
      thesis: 'Home turf, fifth-largest budget globally ($92B in 2025), and Windlass has supplied the Indian Army since 1965. “Make in India” defence-export policy is actively pushing Indian-made kit — India’s defence exports hit a record ₹38,424 crore (~$4.5B) in FY2025-26, up 62.66%. Windlass should ride that political tailwind: position as the flag-bearer Indian ceremonial-arms exporter.' },
    { country: 'Finland', flag: '🇫🇮', budget: 8.1, score: 55, access: 68, prize: 40, tone: 'warn',
      thesis: 'Reachable through the EU (Toledo) arm and a NATO member since 2023 — but the assumed “rebuilding ceremonial kit” opening did not materialise. Finland kept its national ceremonial dress; the new Nordic uniform is field kit only. A low-priority watch market: honour-guard demand exists, but there is no active sword procurement to chase.' },
    { country: 'Sweden', flag: '🇸🇪', budget: 16.5, score: 54, access: 68, prize: 40, tone: 'warn',
      thesis: 'Same picture as Finland — NATO member since 2024, EU-reachable, strong regimental tradition — but it retained its national ceremonial dress and its new service dress is not due before 2028. Watch, don’t chase.' },
    { country: 'Australia', flag: '🇦🇺', budget: 35.3, score: 70, access: 78, prize: 60, tone: 'good',
      thesis: 'Commonwealth drill tradition, British sword patterns, Duntroon academy, English-language procurement. Windlass already makes the exact patterns the ADF uses. A natural, low-friction extension of the UK relationship.' },
    { country: 'Canada', flag: '🇨🇦', budget: 37.5, score: 68, access: 76, prize: 58, tone: 'warn',
      thesis: 'Commonwealth ceremonial tradition and British-pattern swords, but a smaller and more fragmented buying picture. Good follow-on once the ANZ/UK playbook is proven.' },
    { country: 'Nigeria', flag: '🇳🇬', budget: 2.0, score: 52, access: 45, prize: 40, tone: 'warn',
      thesis: 'Commonwealth military academy and honour-guard tradition, but a small budget and harder access. A watch-list market — attractive for volume dress swords if a regional agent emerges.' },
    { country: 'South Africa', flag: '🇿🇦', budget: 2.7, score: 50, access: 48, prize: 38, tone: 'warn',
      thesis: 'Commonwealth heritage and established regiments, modest budget. Same profile as Nigeria — opportunistic, agent-led, not a priority push.' },
  ],
};

/* ─────────────────────────────────────────────────────────────────────────
   COMPETITOR WATCH — real positioning (all sourced)
   ───────────────────────────────────────────────────────────────────────── */
export const COMPETITORS = {
  intro:
    'Who else can make a real service or ceremonial sword? Fewer players than you’d think — and almost none can do it at Windlass’s combination of authenticity and volume. The table below maps each rival on price tier and on whether they actually hold government/ceremonial contracts, because that is the field Windlass competes on. The collector-only makers (Albion, Hanwei, Cold Steel) matter for brand and social share, not for tenders.',
  // price: 1=budget .. 4=premium ; contracts: govt/ceremonial supply strength 0-100
  items: [
    { name: 'Pooley Sword', country: 'UK', flag: '🇬🇧', price: 3, contracts: 85, tone: 'risk',
      note: 'The real tender rival. Formed Nov 2005 from Wilkinson’s inherited drawings/tooling; still active (Companies House 05649253), supplying swords, dirks and lances to the British Armed Forces and Commonwealth, blade/casting in Sheffield. Wins on “made in Britain” and continuity.',
      threat: 'Direct competitor for the crown-jewel UK contract. Windlass beats it on cost and volume; loses on the domestic-supplier story. Neutralise via the UK entity.' },
    { name: 'WKC (Solingen)', country: 'Germany', flag: '🇩🇪', price: 4, contracts: 78, tone: 'risk',
      note: 'Premium ceremonial house, 600+ dress-sword types. Official dress-sword supplier to the British Army’s Royal Logistic Corps and to US military academies.',
      threat: 'The prestige benchmark in Europe. Competes on craftsmanship and German finish at a higher price. Windlass wins the value argument decisively.' },
    { name: 'Marto / Bermejo (Toledo)', country: 'Spain', flag: '🇪🇸', price: 3, contracts: 70, tone: 'flat',
      note: 'Toledo house; Bermejo (since 1910) supplies military sabres to “armies of the five continents.” NOTE: the Windlass group acquired Marto+Bermejo in 2011 — this is now an in-house asset, not an outside threat.',
      threat: 'Effectively owned by Windlass. The strategic value is the Toledo name and EU footprint — use it as the European face for NATO-new markets rather than treating it as a rival.' },
    { name: 'Eickhorn-Solingen', country: 'Germany', flag: '🇩🇪', price: 3, contracts: 65, tone: 'warn',
      note: 'Bayonets and combat/rescue knives for military and police. A real government contractor: its KM2000 is the standard Bundeswehr combat knife and its SG2000 bayonet fits the G36 rifle.',
      threat: 'Competes in bayonets/combat knives, not ceremonial swords — an adjacent field Windlass could enter, not a direct dress-sword rival.' },
    { name: 'Wilkinson Sword', country: 'UK', flag: '🇬🇧', price: 2, contracts: 10, tone: 'flat',
      note: 'The famous name — but the sword factory closed in 2005; today it is a razor/grooming brand owned by Edgewell. Sword-making passed to Pooley and WKC.',
      threat: 'No longer a sword maker. Its enduring brand recognition is a trap for buyers who don’t know it exited — a story Windlass can gently correct.' },
    { name: 'Cold Steel', country: 'USA', flag: '🇺🇸', price: 2, contracts: 5, tone: 'warn',
      note: 'Budget–mid tactical knives, machetes and swords; acquired by GSM Outdoors in 2020. No known government ceremonial contracts — but a huge consumer/social following (~233K Instagram).',
      threat: 'Zero tender threat, major brand threat. Owns the online sword conversation Windlass is absent from. The reason to fix Windlass’s social presence.' },
    { name: 'Hanwei / CAS Iberia', country: 'China/US', flag: '🇨🇳', price: 2, contracts: 5, tone: 'flat',
      note: 'Paul Chen’s Dalian Hanwei; replica Japanese/Chinese/European swords via US distributor CAS Iberia. The Hanwei factory ceased operations Dec 2024 (closure announced 17 Jan 2025); CAS Iberia is continuing the brand via Frenchie Jin’s Dragon King forge in Dalian, with new product expected in 2026.',
      threat: 'Collector-market rival only — and it is mid-disruption. A real opening for Windlass/Museum Replicas to pick up displaced replica-market share while its supply is unsettled.' },
    { name: 'Albion Swords', country: 'USA', flag: '🇺🇸', price: 4, contracts: 5, tone: 'flat',
      note: 'High-end, historically accurate European reproductions for collectors and HEMA. Premium, low-volume, near-dormant socially.',
      threat: 'No tender overlap. Sets the top of the collector-authenticity market — a quality bar for a premium Museum Replicas line, not a competitor for contracts.' },
  ],
};

/* ─────────────────────────────────────────────────────────────────────────
   SOCIAL vs COMPETITORS — REAL public follower numbers (July 2026 snapshots)
   ───────────────────────────────────────────────────────────────────────── */
export const SOCIAL = {
  intro:
    'On the product, Windlass has no equal. Online, it is being out-shouted. These are real, public follower counts gathered from the brands’ own accounts. The pattern is stark: Windlass makes the swords the world’s militaries actually carry, yet a budget knife brand (Cold Steel) has roughly 145× its Instagram reach. For a company whose whole edge is authenticity, being invisible where buyers now research is the single most fixable weakness in this report.',
  // followers by platform; verified flag per number
  brands: [
    { name: 'Windlass Steelcrafts', us: true, ig: 1606, li: 313, yt: null, tone: 'you',
      note: 'IG ~1,606; LinkedIn 313. No prominent official YouTube with a surfaced sub count.' },
    { name: 'Museum Replicas (Windlass)', us: true, ig: 4173, li: null, yt: null, tone: 'you',
      note: 'The group’s collector brand — its best social asset, and still tiny. (LinkedIn sits under Atlanta Cutlery Corp.; no clean count surfaced.)' },
    { name: 'Atlanta Cutlery (Windlass)', us: true, ig: 882, li: null, yt: null, tone: 'you',
      note: 'The US distribution arm — barely present socially.' },
    { name: 'Cold Steel', us: false, ig: 233000, li: null, yt: null, tone: 'rival',
      note: 'The benchmark. ~233K IG and a large active YouTube (exact sub count unconfirmed — SocialBlade blocked).' },
    { name: 'Marto (Toledo)', us: false, ig: 2728, li: null, yt: null, tone: 'rival',
      note: 'Group-owned, but run as its own small account.' },
    { name: 'Hanwei / CAS Iberia', us: false, ig: 2530, li: null, yt: null, tone: 'rival',
      note: 'Collector rival, comparable small IG reach.' },
    { name: 'Albion Swords', us: false, ig: 274, li: 18, yt: null, tone: 'rival',
      note: 'Near-dormant socially despite a premium reputation.' },
  ],
  note: 'Wilkinson Sword’s large IG (~14–25K) is the razor/grooming brand, not the collectible-sword business — excluded to avoid a false comparison.',
  // The people who actually shape sword-buying opinion online.
  influencers: [
    { name: 'Shadiversity', subs: '~1.64M', platform: 'YouTube', note: 'Medieval arms & armour — broad reach.' },
    { name: 'Skallagrim', subs: '~1.6M', platform: 'YouTube', note: 'Knives & swords reviews; big buyer influence.' },
    { name: 'Metatron', subs: '~1.0M', platform: 'YouTube', note: 'History & arms. Like the others here he routinely reviews budget production swords — and Windlass is the dominant budget maker — so a warm, natural first target (no specific past Windlass review confirmed).' },
    { name: 'Tod’s Workshop', subs: '~575K', platform: 'YouTube', note: 'Historical accuracy, maker credibility.' },
    { name: 'scholagladiatoria (Matt Easton)', subs: '~515K', platform: 'YouTube', note: 'HEMA & antique swords; respected authority.' },
  ],
  gap: {
    title: 'Where Windlass is lagging — and the move',
    body: 'The gap is not quality, it is presence. Windlass’s reputation in the collector community (via SBG/BladeForums-type sentiment) is genuinely good — praised as the best-value real swords, with steel and heat-treat singled out; the recurring criticisms are whippy blades over ~32 inches and inconsistent hilt fit. That is a fixable QC-and-communication story, not a brand crisis. Meanwhile the one brand out-reaching Windlass 145-to-1 (Cold Steel) can’t claim a single government contract.',
    move: 'Pick one channel and win it: a Museum Replicas YouTube built around real forge footage from Dehradun and “the sword the British Army actually carries.” Seed review pieces to the sword-review creators (Metatron, Skallagrim, Tod’s Workshop) who already cover budget production swords — Windlass is the maker they most often handle. Authenticity is the moat — nobody else in the top-follower tier can film a real military contract being fulfilled.',
  },
};

/* ─────────────────────────────────────────────────────────────────────────
   BRAND & COLLECTOR PULSE
   ───────────────────────────────────────────────────────────────────────── */
export const BRAND = {
  intro:
    'Beyond governments, Windlass has a second life as the workhorse behind film swords and collector replicas — an asset most defence suppliers would kill for. The job here is to convert that heritage into present-day demand while the market for historical drama and collecting is running hot.',
  reputation: {
    label: 'Collector sentiment: positive, with fixable niggles',
    positives: ['Best-value genuine swords', 'Praised steel & heat-treat', 'Real historical patterns'],
    negatives: ['Whippy blades over ~32″', 'Inconsistent hilt/handle fit', 'Back-order & customer-service complaints (Museum Replicas)'],
    trustNote: 'Independent review consensus is positive — Birdeye shows 4.9/5 from 615 reviews; other aggregators ~4.0/5. The Trustpilot score itself stayed unconfirmed (page blocked to automated fetch).',
  },
  sentimentTrend: [62, 60, 64, 66, 63, 68, 70, 69, 72], // illustrative trend of positive-mention share
  channels: [
    { name: 'Film & TV armoury', strength: 88, note: 'Gladiator, LOTR, Kingdom of Heaven, Star Wars, Braveheart — a licensing list most suppliers can only dream of.' },
    { name: 'Collector replicas', strength: 74, note: 'Museum Replicas / Atlanta Cutlery direct-to-consumer.' },
    { name: 'HEMA & reenactment', strength: 55, note: 'Growing community; Windlass blades used as affordable entry pieces.' },
    { name: 'Social / creator', strength: 22, note: 'The weak link — almost no owned reach.' },
  ],
  // Verified 2026 historical slate — some have already premiered; all drive sword/prop demand.
  upcomingProductions: [
    { title: 'The Odyssey (Christopher Nolan)', year: 2026, note: 'Ancient Greece; theatrical 17 Jul 2026 — the biggest sword-and-shield tailwind of the year.' },
    { title: 'A Knight of the Seven Kingdoms (HBO)', year: 2026, note: 'GoT prequel; premiered 18 Jan 2026 — medieval, direct sword relevance.' },
    { title: 'House of the Dragon S3 (HBO)', year: 2026, note: 'Returns ~mid-2026 — high fantasy-arms visibility.' },
    { title: 'The Pendragon Cycle (DailyWire+)', year: 2026, note: 'Arthurian; premiered 22 Jan 2026 — classic sword demand.' },
  ],
  move: 'Film credit is dormant equity. Put the confirmed filmography on a single “as seen in” page, then pitch the armouries behind the 2026 historical slate (Nolan’s Odyssey especially) directly — a fresh on-screen credit refreshes the entire collector line for years.',
};

/* ─────────────────────────────────────────────────────────────────────────
   TRADE & REGULATORY RADAR — India HS-9307 (real UN Comtrade)
   ───────────────────────────────────────────────────────────────────────── */
export const TRADE = {
  intro:
    'Swords, cutlasses and bayonets trade globally under one customs code — HS-9307. Watching that code tells Windlass where India’s edged-weapon exports actually flow and where tariffs are about to change the maths. The headline: India’s HS-9307 exports are small but growing fast, and the US — Windlass’s biggest market — is exactly where new tariffs now bite.',
  hs9307: {
    code: 'HS 9307 — swords, cutlasses, bayonets, lances & similar arms',
    indiaExports2024: '~$8.87M',
    growthSince2019: '+~53%',
    note: 'Real UN Comtrade / WITS FOB values (2024 = $8.87M, up from $8.83M in 2023). Small absolute market — which is why one national dress-sword contract moves the needle. Full-year 2025 not yet published.',
  },
  // India HS-9307 export destinations (2024 share of value) — real Comtrade/WITS breakdown
  destinations: [
    { country: 'United States', flag: '🇺🇸', share: 38, tone: 'good' },
    { country: 'Spain', flag: '🇪🇸', share: 14, tone: 'flat' },
    { country: 'United Kingdom', flag: '🇬🇧', share: 13, tone: 'good' },
    { country: 'Germany', flag: '🇩🇪', share: 10, tone: 'flat' },
    { country: 'France', flag: '🇫🇷', share: 7, tone: 'flat' },
    { country: 'Others', flag: '🌍', share: 18, tone: 'flat' },
  ],
  regulatory: [
    { when: 'Ongoing', title: 'SCOMET — ordinary swords ship outside the munitions list', tone: 'good',
      body: 'India’s SCOMET export controls (Category 6, Munitions) cover arms “specially designed or modified for military use.” Ordinary ceremonial, service and decorative swords are exported commercially as normal HS-9307 goods, outside that regime. Caveat: there is no explicit line stating “swords are exempt,” so the basis is the not-specially-designed test — confirm per shipment before relying on it.' },
    { when: 'Feb 2026', title: 'US reciprocal tariff on Indian blades now ~18%', tone: 'risk',
      body: 'The US historically admitted HS-9307 near duty-free. The 7 Feb 2026 US–India interim trade deal set an ~18% reciprocal tariff (down from a threatened 50%), applied on top of the low base duty — so effective landed cost on India-made blades is now materially higher. Re-check the exact HTS/Chapter-99 line at ship date. This is the clearest reason to finish or assemble through Atlanta Cutlery on US soil where possible.' },
    { when: 'Ongoing', title: 'UK / EU tariffs low (~0–2.7%)', tone: 'good',
      body: 'Windlass’s European routes stay cheap. The Toledo (EU) arm ships inside the customs union tariff-free — a structural advantage for the NATO-new markets.' },
    { when: 'Policy', title: '“Make in India” defence-export tailwind', tone: 'good',
      body: 'India’s defence exports hit a record ~$2.76B in FY24–25 with a ~$6B target by 2029. Windlass can ride the political push as the flag-bearer Indian ceremonial-arms exporter.' },
  ],
  correction: 'Note: there is no Uttarakhand defence corridor — India’s corridors are Uttar Pradesh and Tamil Nadu only. Windlass (Dehradun) sits outside them; the nearest edged-weapon-relevant node is Aligarh.',
};

/* ─────────────────────────────────────────────────────────────────────────
   GEOPOLITICAL & DEFENCE SPEND — SIPRI 2025 (real)
   ───────────────────────────────────────────────────────────────────────── */
export const GEO = {
  intro:
    'Ceremonial-sword demand rises and falls with two things: how much money armies have, and how often they parade. Both are pointing up. Global defence spending is climbing at its fastest rate in a generation, and set-piece events — coronations, national-day parades, regimental anniversaries — keep generating honour-guard and dress-kit requirements.',
  world2024: { total: '$2,887B', yoy: '+2.9%', note: 'SIPRI 2025 — 11th straight annual rise; 2.5% of world GDP, the highest since 2009. (2024’s rise was +9.7%.)' },
  // SIPRI 2025 top spenders (US$ bn, calendar 2025)
  topSpenders: [
    { country: 'United States', flag: '🇺🇸', bn: 954 },
    { country: 'China', flag: '🇨🇳', bn: 336 },
    { country: 'Russia', flag: '🇷🇺', bn: 190 },
    { country: 'Germany', flag: '🇩🇪', bn: 114 },
    { country: 'India', flag: '🇮🇳', bn: 92.1 },
    { country: 'United Kingdom', flag: '🇬🇧', bn: 89 },
    { country: 'Ukraine', flag: '🇺🇦', bn: 84.1 },
    { country: 'Saudi Arabia', flag: '🇸🇦', bn: 83.2 },
  ],
  // multi-year world total trend (SIPRI, $ trillion) — real direction
  trend: [
    { y: '2020', v: 2.0 }, { y: '2021', v: 2.1 }, { y: '2022', v: 2.24 },
    { y: '2023', v: 2.48 }, { y: '2024', v: 2.72 }, { y: '2025', v: 2.89 },
  ],
  // ceremonial demand triggers — real dated events (heatmap-style calendar)
  events: [
    { date: '2023-04-04', label: 'Finland joins NATO (31st ally)', tone: 'flat', verified: true, note: 'Checked: Finland kept its national ceremonial dress — no new sword procurement resulted.' },
    { date: '2023-05-06', label: 'Coronation of King Charles III', tone: 'good', verified: true, note: 'Multiple state ceremonial swords in use — live proof of coronation-driven demand.' },
    { date: '2024-03-07', label: 'Sweden joins NATO (32nd ally)', tone: 'flat', verified: true, note: 'Checked: Sweden retained its national ceremonial dress; new service dress not due before 2028.' },
    { date: 'Annual (Jan)', label: 'India Republic Day parade', tone: 'good', verified: true, note: 'Recurring dress-sabre demand; Windlass supplies the Indian Army since 1965.' },
    { date: 'Recurring', label: 'Regimental anniversaries & academy commissioning', tone: 'flat', verified: true, note: 'Steady baseline of officer-sword orders.' },
  ],
  move: 'The macro backdrop is a genuine tailwind — rising budgets mean bigger ceremonial establishments and more parades — but it is a reason to invest in sales, not a specific opening on its own. Point the effort where the tradition is real and the patterns already fit: the Commonwealth (UK, India, Australia, Canada) and the high-margin Gulf, not the NATO-new pair.',
  unverifiedNote: 'Correction (July 2026): the assumed link from Finland/Sweden’s NATO accession to a ceremonial-sword purchase was checked and NOT supported — both nations kept their national ceremonial dress. That inference has been removed from the opportunity set.',
};

/* ─────────────────────────────────────────────────────────────────────────
   ROOM TO GROW — B2C / collector / entertainment (secondary to military)
   ───────────────────────────────────────────────────────────────────────── */
export const GROW = {
  intro:
    'The military business is the core and the priority. But Windlass sits on a consumer opportunity most defence firms never get: it already owns the factory, the film credits and two collector brands. These are the adjacent openings — real, but secondary to winning tenders.',
  openings: [
    { name: 'Creator-driven collector sales', size: 'High', effort: 'Low', tone: 'good',
      body: 'The sword-review YouTube audience is in the millions (Shadiversity ~1.64M, Skallagrim ~1.6M, Metatron ~1M). These creators constantly review budget production swords — the category Windlass dominates — so a steady review-seeding pipeline is the cheapest revenue Windlass isn’t collecting.' },
    { name: 'Film & TV armoury refresh', size: 'High', effort: 'Med', tone: 'good',
      body: 'A heavy 2026 historical slate (Nolan’s Odyssey out 17 Jul 2026, House of the Dragon S3, HBO’s Knight of the Seven Kingdoms). Each new on-screen credit refreshes the whole replica line.' },
    { name: 'HEMA & reenactment', size: 'Med', effort: 'Low', tone: 'good',
      body: 'Historical European Martial Arts is a real, growing niche — a peer-reviewed 2021 census counted ~3,186 practitioners in Germany and ~801 in Austria alone (no reliable global total exists). Windlass blades are the standard affordable entry feder/sparring pieces, so a HEMA-specific line and club partnerships convert that community into repeat orders.' },
    { name: 'Premium collector line', size: 'Med', effort: 'Med', tone: 'warn',
      body: 'Albion sets the top-authenticity bar at premium prices. A limited, numbered Museum Replicas “museum-grade” line — using the real military patterns Windlass alone makes — could climb the price ladder without new tooling.' },
  ],
  marketNote: 'No credible, independently-verified sizing of the sword/collector market exists — the dollar figures that circulate (~$0.5–2B, high-CAGR) trace to AI-generated SEO report pages with no disclosed methodology. Treat the B2C opportunity as real but unquantified; do not put a market-size number in front of the client as fact.',
  move: 'Keep this lane secondary but switched-on: one creator-seeding programme and one fresh film credit would lift the collector brands materially at almost no capital cost — fund it from marketing, not from the tender-sales budget.',
};

/* ─────────────────────────────────────────────────────────────────────────
   SIGNAL FEED — unified stream in the requested schema
   type · headline · source · country · date · opportunity|risk · urgency · action
   ───────────────────────────────────────────────────────────────────────── */
export const SIGNALS = [
  { type: 'Contract', headline: 'Windlass’s UK arm supplies every British-forces sword — incumbent position to defend', source: 'Windlass UK / MoD', country: 'UK', flag: '🇬🇧', date: 'Held', kind: 'opportunity', urgency: 'high',
    action: 'Protect the crown jewel: keep pattern samples + delivery record with the MoD; watch Find-a-Tender / the Defence Sourcing Portal for any re-compete notice.' },
  { type: 'Trade', headline: 'US import tariff on Indian HS-9307 blades now ~18% (US–India deal, Feb 2026)', source: 'White House / KPMG', country: 'USA', flag: '🇺🇸', date: '2026-02', kind: 'risk', urgency: 'high',
    action: 'Finish/assemble through Atlanta Cutlery on US soil to soften landed cost; re-check the exact HTS line at ship date.' },
  { type: 'Social', headline: 'Cold Steel out-reaches Windlass ~145× on Instagram despite zero contracts', source: 'Public IG accounts', country: 'Global', flag: '🌍', date: '2026', kind: 'risk', urgency: 'med',
    action: 'Launch a Museum Replicas forge-footage YouTube; seed to Metatron/Skallagrim/Tod’s Workshop.' },
  { type: 'Event', headline: 'IDEX 2027 defence expo — Abu Dhabi, 25–29 Jan 2027', source: 'idexuae.ae', country: 'UAE', flag: '🇦🇪', date: '2027-01', kind: 'opportunity', urgency: 'med',
    action: 'Book a stand; use it to appoint a Gulf agent and pitch presentation sabres for state gifting.' },
  { type: 'Geopolitics', headline: 'Finland & Sweden kept national ceremonial dress after joining NATO — no sword tender', source: 'Försvarsmakten / Nordic uniform programme', country: 'Nordic', flag: '🇫🇮', date: '2024–26', kind: 'risk', urgency: 'low',
    action: 'Do NOT chase a NATO-accession sword tender — none exists; the new Nordic kit is field uniform only (Sweden’s new service dress not before 2028).' },
  { type: 'Contract', headline: 'Gurkha & Indian Army kukri supply — recurring requirement, Windlass’s oldest line (since 1943)', source: 'Regimental / historical', country: 'Nepal/India', flag: '🇳🇵', date: 'Recurring', kind: 'opportunity', urgency: 'med',
    action: 'No public tender is confirmable; hold the relationship on 1943 heritage + consistency vs local kami-forges.' },
  { type: 'Market', headline: 'India defence exports hit record ₹38,424 cr (~$4.5B) in FY2025-26, +62.66%', source: 'PIB / MoD (2 Apr 2026)', country: 'India', flag: '🇮🇳', date: 'FY25-26', kind: 'opportunity', urgency: 'med',
    action: 'Position as the flag-bearer Indian ceremonial-arms exporter under Make-in-India.' },
  { type: 'Competitor', headline: 'Hanwei/CAS factory reportedly closed (2025); replica supply disrupted', source: 'CAS Iberia release', country: 'China/US', flag: '🇨🇳', date: '2025', kind: 'opportunity', urgency: 'low',
    action: 'Push Museum Replicas to capture displaced replica-market demand.' },
  { type: 'Brand', headline: 'Heavy 2026 historical film/TV slate (Nolan’s Odyssey, HotD, Knight of the Seven Kingdoms)', source: 'Production trades', country: 'Global', flag: '🌍', date: '2026', kind: 'opportunity', urgency: 'low',
    action: 'Pitch the armourers directly; a fresh on-screen credit refreshes the collector line.' },
  { type: 'Geopolitics', headline: 'World defence spend $2.89T in 2025, +2.9% — 11th straight annual rise (SIPRI)', source: 'SIPRI 2025', country: 'Global', flag: '🌍', date: '2025', kind: 'opportunity', urgency: 'low',
    action: 'Use the macro tailwind to justify front-loading sales investment now.' },
  { type: 'Market', headline: 'Gulf state-gifting demand for presentation sabres remains high-margin', source: 'SIPRI budgets / trade', country: 'Saudi/UAE', flag: '🇸🇦', date: 'Ongoing', kind: 'opportunity', urgency: 'high',
    action: 'Appoint a Gulf distribution partner; pitch gold-mounted presentation sabres.' },
  { type: 'Quality', headline: 'Collector sentiment positive but flags whippy long blades & hilt-fit', source: 'SBG / BladeForums-type', country: 'Global', flag: '🌍', date: 'Ongoing', kind: 'risk', urgency: 'low',
    action: 'Tighten QC on 32″+ blades and hilt assembly; publicise the fix.' },
];

/* ─────────────────────────────────────────────────────────────────────────
   SECTOR WATCH — external news + YouTube Windlass should monitor
   (defence, ceremonial, competitors, trade, film, collector) — real, cited.
   ───────────────────────────────────────────────────────────────────────── */
export const COVERAGE = {
  note: 'Real external signal a sword-maker’s leadership should watch — defence budgets, ceremonial events, competitors, trade shifts and the productions driving replica demand. Every item is genuine, cited and dated (mostly 2025–2026). In the live product this is a continuously-monitored feed; here it’s a curated snapshot.',
  articles: [
    { topic: 'Defence', source: 'SIPRI', date: 'Apr 2026', title: 'Global military spending rise continues as European and Asian expenditure surges', url: 'https://www.sipri.org/media/press-release/2026/global-military-spending-rise-continues-european-and-asian-expenditures-surge', blurb: 'World spend hit a record $2.89T (11th straight rise) — the tide that lifts every ceremonial-kit budget.' },
    { topic: 'Trade', source: 'The White House', date: 'Feb 2026', title: 'US–India historic trade deal: reciprocal tariff cut to ~18%', url: 'https://www.whitehouse.gov/fact-sheets/2026/02/fact-sheet-the-united-states-and-india-announce-historic-trade-deal/', blurb: 'The tariff on India-made goods drops from a peak 50% to 18% — directly lowers landed cost on Windlass’s US-bound blades.' },
    { topic: 'Defence', source: 'NATO', date: 'Jun 2025', title: 'NATO allies pledge 5% of GDP on defence at The Hague summit', url: 'https://www.nato.int/en/about-us/official-texts-and-resources/official-texts/2025/06/25/the-hague-summit-declaration', blurb: '31 of 32 allies commit to 5% by 2035 — broadens honour-guard and regimental refurbishment spending.' },
    { topic: 'Defence', source: 'UK Commons Library', date: '2025', title: 'UK to spend 2.5% of GDP on defence by 2027', url: 'https://commonslibrary.parliament.uk/uk-to-spend-2-5-of-gross-domestic-product-on-defence-by-2027/', blurb: 'Windlass’s largest legacy customer (UK MoD) is expanding — 3% next parliament, 3.5% by 2035.' },
    { topic: 'Trade', source: 'PIB India', date: '2026', title: 'Defence Atmanirbharta: record production and exports (₹38,424 cr, +62.7%)', url: 'https://www.pib.gov.in/PressReleasePage.aspx?PRID=2191937', blurb: 'India’s defence exports hit an all-time high — the Make-in-India tailwind for an Indian edged-weapons exporter.' },
    { topic: 'Ceremonial', source: 'British Army', date: 'Jun 2026', title: 'The King’s Birthday Parade — Trooping the Colour 2026', url: 'https://kbp.army.mod.uk/kingsbirthdayparade/', blurb: '1,350+ Household Division troops on parade — the flagship recurring driver of UK dress-sword demand.' },
    { topic: 'Collector', source: 'France 24 / AFP', date: 'May 2025', title: 'Napoleon’s sword sold at auction for €4.7 million', url: 'https://www.france24.com/en/live-news/20250523-napoleon-s-sword-sold-at-auction-for-4-7-mn-euros', blurb: '5× its estimate — signals a hot high-end edged-weapon collector market Windlass’s replica line feeds.' },
    { topic: 'Film', source: 'Motion Picture Assoc.', date: 'Apr 2026', title: 'CinemaCon 2026: Christopher Nolan unveils epic ‘The Odyssey’ footage', url: 'https://www.motionpictures.org/2026/04/cinemacon-2026-christopher-nolan-unveils-epic-the-odyssey-footage-shot-entirely-in-imax/', blurb: '$250m swords-and-sandals epic (17 Jul 2026) — prop, replica and licensing opportunity.' },
    { topic: 'Film', source: 'Variety', date: 'Jun 2026', title: 'House of the Dragon sets Season 3 release date at HBO', url: 'https://variety.com/2026/tv/news/house-of-the-dragon-season-3-release-date-hbo-1236731400/', blurb: 'Premiered 21 Jun 2026 — fantasy-blade fandom sustains Museum Replicas licensed/themed sword sales.' },
    { topic: 'Competitor', source: 'Forces News', date: '', title: 'Secrets of the workshop making swords for the UK Armed Forces (Pooley Sword)', url: 'https://www.forcesnews.com/heritage/history/exclusive-take-tour-uks-only-sword-shop', blurb: 'Profile of Pooley Sword (Wilkinson’s successor) — Windlass’s direct rival for UK/Commonwealth contracts.' },
    { topic: 'Expo', source: 'IDEX UAE', date: 'Jan 2027', title: 'IDEX 2027 — International Defence Exhibition, Abu Dhabi (25–29 Jan)', url: 'https://www.idexuae.ae/', blurb: '1,565+ exhibitors; the Gulf procurement hub — prime venue for royal-guard / ceremonial deals.' },
    { topic: 'Expo', source: 'DSEI', date: 'Sep 2027', title: 'DSEI UK 2027 — ExCeL London (7–10 Sep)', url: 'https://www.dsei.co.uk/', blurb: 'The UK/Commonwealth defence-procurement showcase to work for dress-uniform and edged-weapon kit.' },
  ],
  videos: [
    { channel: 'Sky News', year: 'Jun 2026', title: 'Trooping the Colour 2026 — full parade coverage', url: 'https://www.youtube.com/watch?v=ubIX-TwVqZI' },
    { channel: 'WION (Gravitas)', year: 'Apr 2026', title: 'SIPRI report: world defence budgets surged in 2025', url: 'https://www.youtube.com/watch?v=J_ENzX3WyCA' },
    { channel: 'scholagladiatoria', year: '2023', title: 'How Swords Are Made at Windlass Steelcrafts of India (factory tour)', url: 'https://www.youtube.com/watch?v=8iaS9NAyO3Y' },
    { channel: 'Shadiversity', year: '2025', title: 'Is SwordTube DEAD? — the state of the sword-review scene', url: 'https://www.youtube.com/watch?v=gJSapM_poE4' },
    { channel: 'SBG (Sword Buyers Guide)', year: '', title: 'Windlass Shrewsbury Sword — independent review', url: 'https://www.youtube.com/watch?v=UhoVpidL0G0' },
    { channel: 'Shadiversity', year: '', title: 'Medieval vs modern swords — the quality debate', url: 'https://www.youtube.com/watch?v=xTUWGbjcC_k' },
    { channel: '', year: 'Jun 2026', title: 'Trooping the Colour 2026 — full parade, no commentary', url: 'https://www.youtube.com/watch?v=93hQV3HSnQ8' },
  ],
};

/* Convenience: nav definition for the corporate product */
export const COMPANY_NAV = [
  { slug: 'overview',    label: 'Command Overview',       icon: '◉', group: 'Intelligence' },
  { slug: 'tenders',     label: 'Tender Intelligence',    icon: '⚑', group: 'Intelligence' },
  { slug: 'markets',     label: 'Market Expansion',       icon: '◈', group: 'Intelligence' },
  { slug: 'competitors', label: 'Competitor Watch',       icon: '⚔', group: 'Intelligence' },
  { slug: 'social',      label: 'Social vs Competitors',  icon: '◐', group: 'Presence' },
  { slug: 'brand',       label: 'Brand & Collector Pulse',icon: '◆', group: 'Presence' },
  { slug: 'trade',       label: 'Trade & Regulatory',     icon: '▤', group: 'Context' },
  { slug: 'geo',         label: 'Geopolitical & Defence', icon: '▲', group: 'Context' },
  { slug: 'grow',        label: 'Room to Grow',           icon: '◰', group: 'Context' },
  { slug: 'signals',     label: 'Signal Feed',            icon: '☲', group: 'Context' },
];
