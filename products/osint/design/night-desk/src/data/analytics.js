// ============================================================================
// ANALYTICS — "The Instrument Panel". A data dashboard: 20 cards in 3 bands,
// each with a plain name + subline + a source line + an ⓘ-explain (Verify drawer).
// PURE DATA ONLY — counts/distributions/cross-tabs, no LLM at render.
// Numbers are the real verified figures from the 2026-06-02 sweep over the
// personalized universe = 12,904 articles mentioning the Revanth Reddy watchlist.
// Directional cards (for/against, issue battlefield, outlet lean) use
// article_stances — never register_emotion (alarm = event-emotion, not hostility).
// ============================================================================

const W = '47-day window · 12,904 articles mentioning your watchlist';
const v = (definition, formula, source, underlying) => ({ definition, formula, source, window: W, underlying });

export const DASH = {
  asOf: 'AS OF 01 JUN 2026 · 06:00 IST',
  base: '12,904',
  window: '47-DAY WINDOW',
};

export const MODULES = [
  // ── BAND 1 · THE BIG PICTURE ──────────────────────────────────────────────
  {
    id: 'volume', band: 'THE BIG PICTURE', span: 2, viz: 'area',
    name: 'Coverage Volume', sub: 'How many stories mention you each day — with spike alerts',
    source: 'articles.published_at',
    data: {
      labels: ['19', '20', '21', '22', '23', '24', '25', '26', '27', '28', '29', '30', '31', '01'],
      series: [195, 502, 331, 352, 182, 210, 462, 320, 300, 294, 353, 520, 730, 1006],
      note: '20 May ran 3.8× the 7-day average (502 vs 133). Coverage is climbing into June.',
    },
    metric: { label: 'Coverage Volume', value: '12,904', n: 12904, confidence: 'high',
      verify: v('Number of articles mentioning any watchlist entity, per day.',
        'count(articles) grouped by published_at::date, with a 7-day moving average',
        'article_entity_mentions ▸ articles.published_at',
        ['12,904 articles in-window', '20 May spike = 502 vs MA7 133 (3.8×)', 'smoothed with a 7-day MA to absorb collection gaps']) },
  },
  {
    id: 'topics', band: 'THE BIG PICTURE', span: 1, viz: 'rank',
    name: 'What They’re Talking About', sub: 'Your coverage, broken down by topic',
    source: 'articles.topic_category',
    data: { unit: 'articles', foot: 'Plus 5,072 uncategorised (OTHER) — excluded from the bars.',
      items: [
        { label: 'Politics', value: 2421 }, { label: 'Security', value: 1084 }, { label: 'Legal', value: 741 },
        { label: 'Sports', value: 710 }, { label: 'Social', value: 516 }, { label: 'Health', value: 424 },
        { label: 'Infrastructure', value: 400 }, { label: 'Finance', value: 370 }, { label: 'Governance', value: 280 }, { label: 'Agriculture', value: 210 },
      ] },
    metric: { label: 'Topic breakdown', value: '10 topics', n: 12904, confidence: 'high',
      verify: v('Share of your coverage in each topic category.', 'count(articles) grouped by topic_category',
        'articles.topic_category (98.8% populated)', ['Politics 2,421 · Security 1,084 · Legal 741', 'OTHER bucket = 5,072 (39%), shown separately', 'topic_category covers 98.8% of articles']) },
  },
  {
    id: 'rising', band: 'THE BIG PICTURE', span: 1, viz: 'smallmult',
    name: 'Issues Rising & Falling', sub: 'Which topics are climbing or fading, week by week',
    source: 'articles.topic_category × week',
    data: { rows: [
      { label: 'Politics', series: [7, 221, 868, 460, 99], trend: 'cooling', dir: 'down' },
      { label: 'Security', series: [1, 120, 178, 66, 328], trend: 'surging', dir: 'up' },
      { label: 'Legal', series: [5, 66, 123, 64, 310], trend: 'surging', dir: 'up' },
      { label: 'Agriculture', series: [1, 13, 56, 30, 50], trend: 'steady', dir: 'up' },
    ] },
    metric: { label: 'Topic momentum', value: 'Security ▲ Legal ▲', n: 12904, confidence: 'medium',
      verify: v('Weekly article volume per topic, to see which issues rise or fall.', 'count(articles) grouped by (week, topic_category)',
        'articles.published_at × topic_category', ['Politics peaked 4 May (868) then fell to 99', 'Security rose late (66→328)', 'Legal surged 18 May (310)']) },
  },
  {
    id: 'forvsagainst', band: 'THE BIG PICTURE', span: 1, viz: 'stack',
    name: 'For You vs Against You', sub: 'Supportive, neutral or critical — overall',
    source: 'article_stances.stance',
    data: { foot: 'Directional stance, not emotion. Roughly balanced — neutral leads.',
      segments: [
        { label: 'Supportive', value: 35, color: 'supportive' },
        { label: 'Neutral', value: 35, color: 'muted' },
        { label: 'Critical', value: 30, color: 'hostile' },
      ] },
    metric: { label: 'Overall stance', value: '35 / 35 / 30', n: 9999, confidence: 'medium',
      verify: v('Share of stance-tagged coverage that is supportive vs neutral vs critical toward your side.',
        'count grouped by article_stances.stance ÷ total tagged', 'article_stances (34.7% of articles carry a stance)',
        ['supportive ≈ 35% · neutral ≈ 35% · critical ≈ 30%', 'uses article_stances, NOT register_emotion', 'stance covers ~35% of articles']) },
  },
  {
    id: 'battlefield', band: 'THE BIG PICTURE', span: 1, viz: 'lean',
    name: 'Issues — Praised vs Attacked', sub: 'Which issues you’re supported on vs hit on',
    source: 'topic_category × article_stances',
    data: { foot: 'Net lean = supportive − critical, by issue. You own delivery; you’re hit on legal.',
      items: [
        { label: 'Governance', pos: 166, neg: 71 }, { label: 'Finance', pos: 75, neg: 33 },
        { label: 'Agriculture', pos: 99, neg: 112 }, { label: 'Security', pos: 247, neg: 293 },
        { label: 'Politics', pos: 1365, neg: 1564 }, { label: 'Legal', pos: 147, neg: 239 },
      ] },
    metric: { label: 'Issue battlefield', value: 'Legal −24%', n: 4400, confidence: 'medium',
      verify: v('For each issue, whether coverage skews supportive or critical toward you.',
        'net lean = (supportive − critical) ÷ (supportive + critical), per topic', 'topic_category × article_stances',
        ['Governance +40% · Finance +39% (you own these)', 'Legal −24% · Security −9% (attack vectors)', 'stance-based, not emotion-based']) },
  },
  {
    id: 'sov', band: 'THE BIG PICTURE', span: 1, viz: 'rank',
    name: 'You vs Your Rivals', sub: 'Your share of the conversation against the opposition',
    source: 'article_entity_mentions',
    data: { unit: 'articles', foot: 'Distinct articles mentioning each figure.',
      items: [
        { label: 'BJP', value: 849 }, { label: 'Congress (INC)', value: 678 }, { label: 'Revanth Reddy', value: 468, you: true },
        { label: 'KCR', value: 329 }, { label: 'KTR', value: 226 }, { label: 'Harish Rao', value: 122 }, { label: 'Owaisi', value: 41 },
      ] },
    metric: { label: 'Share of voice', value: 'Revanth 468', n: 2713, confidence: 'high',
      verify: v('How much coverage your principal gets vs rival figures.', 'count(distinct articles) per entity_id',
        'article_entity_mentions (curated watchlist entity_ids)', ['Revanth 468 · KCR 329 · KTR 226 · BJP 849', 'counted by entity_id (deduped), not raw name', 'parties out-mention individuals (recent national news)']) },
  },

  // ── BAND 2 · WHO & WHERE ──────────────────────────────────────────────────
  {
    id: 'outlets', band: 'WHO & WHERE', span: 1, viz: 'rank',
    name: 'Who’s Covering You', sub: 'The outlets writing about you, ranked',
    source: 'articles.source_id ▸ sources',
    data: { unit: 'articles', foot: 'Top two outlets = 42% of all your coverage.',
      items: [
        { label: 'Telangana Today', value: 2122 }, { label: 'Namasthe Telangana', value: 1982 }, { label: 'Siasat Daily', value: 1409 },
        { label: 'Mana Telangana', value: 586 }, { label: 'V6 Velugu', value: 527 }, { label: 'The Hindu', value: 454 },
        { label: 'Eenadu', value: 376 }, { label: 'Andhra Jyothy', value: 374 }, { label: 'HMTV', value: 277 }, { label: 'TV9 Telugu', value: 226 },
      ] },
    metric: { label: 'Outlet coverage', value: '993 sources', n: 12904, confidence: 'high',
      verify: v('Which outlets cover you and how much.', 'count(articles) grouped by source, joined to sources.name',
        'articles.source_id ▸ sources', ['Telangana Today 2,122 · Namasthe Telangana 1,982', 'top-2 = 42% of coverage', '993 sources total in the system']) },
  },
  {
    id: 'outletlean', band: 'WHO & WHERE', span: 1, viz: 'lean',
    name: 'Outlets — Friendly vs Hostile', sub: 'Which papers lean supportive vs critical of you',
    source: 'sources × article_stances',
    data: { foot: 'Net lean by outlet. Telangana Today friendly; Namasthe Telangana hostile (BRS press).',
      items: [
        { label: 'TV9 Telugu', pos: 107, neg: 38 }, { label: 'HMTV', pos: 101, neg: 50 }, { label: 'The Hindu', pos: 309, neg: 203 },
        { label: 'Telangana Today', pos: 1092, neg: 730 }, { label: 'Eenadu', pos: 332, neg: 267 }, { label: 'Siasat', pos: 624, neg: 560 },
        { label: 'Mana Telangana', pos: 132, neg: 137 }, { label: 'Namasthe Telangana', pos: 650, neg: 852 },
      ] },
    metric: { label: 'Outlet lean', value: '+48 … −13', n: 9000, confidence: 'medium',
      verify: v('Whether each outlet’s coverage of you skews supportive or critical.',
        'net lean = (supportive − critical) ÷ (supportive + critical), per source', 'sources × article_stances',
        ['TV9 +48% (friendliest) → Namasthe Telangana −13% (most hostile)', 'editorially correct: govt paper supportive, BRS paper critical', 'stance-based — earlier emotion version was contaminated by event-"alarm"']) },
  },
  {
    id: 'language', band: 'WHO & WHERE', span: 1, viz: 'donut',
    name: 'English vs Telugu', sub: 'The language split of your coverage',
    source: 'articles.language_iso',
    data: { centerLabel: 'EN', centerValue: '59%', foot: 'Bilingual battle — Telugu is a third of your coverage.',
      segments: [
        { label: 'English', value: 59, color: 'cool' }, { label: 'Telugu', value: 34, color: 'gold' }, { label: 'Other / none', value: 7, color: 'muted' },
      ] },
    metric: { label: 'Language mix', value: 'en 59 / te 34', n: 12904, confidence: 'high',
      verify: v('Share of your coverage by detected language.', 'count(articles) grouped by language_iso',
        'articles.language_iso (84% populated)', ['English 7,593 (59%) · Telugu 4,425 (34%)', 'Hindi 114 · Kannada 75 · none 572', 'Telugu coverage is the opposition’s home turf']) },
  },
  {
    id: 'langbyissue', band: 'WHO & WHERE', span: 1, viz: 'groupbars',
    name: 'Telugu vs English by Issue', sub: 'Which issues live in which language',
    source: 'topic_category × language_iso',
    data: { foot: 'Farming is Telugu-majority; finance is English-heavy.',
      items: [
        { label: 'Agriculture', en: 75, te: 87 }, { label: 'Politics', en: 882, te: 880 }, { label: 'Legal', en: 311, te: 283 },
        { label: 'Security', en: 521, te: 403 }, { label: 'Governance', en: 87, te: 45 }, { label: 'Finance', en: 113, te: 41 },
      ] },
    metric: { label: 'Issue × language', value: 'Agri = Telugu', n: 12904, confidence: 'high',
      verify: v('For each issue, the English vs Telugu volume.', 'count(articles) grouped by (topic_category, language_iso)',
        'articles.topic_category × language_iso', ['Agriculture is Telugu-majority (te 87 / en 75)', 'Finance is English-heavy (en 113 / te 41)', 'the farm story reaches voters in Telugu, not English desks']) },
  },
  {
    id: 'districts', band: 'WHO & WHERE', span: 1, viz: 'rank',
    name: 'Where It’s Landing', sub: 'Your coverage by Telangana district',
    source: 'article_districts.district_id',
    data: { unit: 'mentions', foot: 'Hyderabad dominates (capital). District map view available.',
      items: [
        { label: 'Hyderabad', value: 7915 }, { label: 'Nalgonda', value: 713 }, { label: 'Karimnagar', value: 303 },
        { label: 'Rangareddy', value: 253 }, { label: 'Khammam', value: 246 }, { label: 'Warangal', value: 210 },
        { label: 'Nizamabad', value: 195 }, { label: 'Medchal', value: 194 }, { label: 'Adilabad', value: 191 }, { label: 'Mahbubnagar', value: 138 },
      ] },
    metric: { label: 'District coverage', value: 'Hyderabad-led', n: 20264, confidence: 'medium',
      verify: v('Where your coverage is geographically datelined, by district.', 'count(article_districts) grouped by district_id',
        'article_districts (13.6% of articles geo-tagged to a district)', ['Hyderabad 7,915 (capital, dominates)', 'Nalgonda 713 · Karimnagar 303 · Warangal 210', 'district choropleth is the reliable map (lat/lng only 20% geocoded)']) },
  },
  {
    id: 'quoted', band: 'WHO & WHERE', span: 1, viz: 'list',
    name: 'Who’s Being Quoted', sub: 'The voices quoted most in your coverage',
    source: 'article_quotes.speaker_name',
    data: { unit: 'quotes', foot: '5,761 quotes across 2,702 articles; 65% speaker-resolved.',
      items: [
        { label: 'Narendra Modi', value: 152 }, { label: 'Revanth Reddy', value: 126 }, { label: 'Harish Rao', value: 77 },
        { label: 'K.T. Rama Rao', value: 68 }, { label: 'Donald Trump', value: 48 }, { label: 'Rahul Gandhi', value: 42 },
        { label: 'Bandi Sanjay', value: 35 }, { label: 'Mamata Banerjee', value: 29 },
      ] },
    metric: { label: 'Top speakers', value: 'Modi · Revanth', n: 5761, confidence: 'high',
      verify: v('Who is quoted most in articles about you.', 'count(article_quotes) grouped by speaker_name',
        'article_quotes (28% of articles carry a quote)', ['Modi 152 · Revanth 126 · Harish 77 · KTR 68', '5,761 quotes / 2,702 articles', '65% resolved to a speaker entity_id']) },
  },
  {
    id: 'writers', band: 'WHO & WHERE', span: 1, viz: 'list',
    name: 'Who’s Writing', sub: 'The journalists bylined on your coverage',
    source: 'articles.author_name',
    data: { unit: 'articles', foot: '352 named writers — but 83% of coverage is wire / unbylined.',
      items: [
        { label: 'Vishnu P', value: 77 }, { label: 'Somaiah Aithagoni', value: 67 }, { label: 'Chandra Mouli', value: 55 },
        { label: 'Sakina Fatima', value: 53 }, { label: 'Rasti Amena', value: 52 }, { label: 'Sameer Khan', value: 50 },
        { label: 'A Ravi', value: 45 }, { label: 'Arun Chilukuri', value: 43 },
      ] },
    metric: { label: 'Bylined writers', value: '352 writers', n: 1626, confidence: 'medium',
      verify: v('The journalists who put their name to coverage of you.', 'count(articles) grouped by author_name (non-blank)',
        'articles.author_name', ['352 distinct writers across 1,626 bylined articles', 'only ~17% of coverage is bylined (mostly Tier-1)', 'the other 83% is wire / agency copy — Telugu regional papers rarely byline']) },
  },

  // ── BAND 3 · THE DETAIL ───────────────────────────────────────────────────
  {
    id: 'tone', band: 'THE DETAIL', span: 1, viz: 'rank',
    name: 'Tone of Coverage', sub: 'How the stories sound — descriptive, not a verdict',
    source: 'articles.register_emotion',
    data: { unit: '%', descriptive: true, foot: '⚠ Register of coverage, NOT hostility — “alarm” = alarming events, not stance.',
      items: [
        { label: 'Neutral', value: 46 }, { label: 'Alarm (events)', value: 21 }, { label: 'Approval', value: 10 },
        { label: 'Urgency', value: 6 }, { label: 'Curiosity', value: 5 }, { label: 'Lament', value: 3 }, { label: 'Admiration', value: 2 },
      ] },
    metric: { label: 'Tone register', value: 'neutral-led', n: 9400, confidence: 'medium',
      verify: v('The emotional register of the writing — a descriptive tag, not a stance.',
        'count grouped by register_emotion ÷ tagged total', 'articles.register_emotion (73% populated)',
        ['neutral 46% · alarm 21% · approval 10%', '“alarm” tags alarming EVENTS (floods, crime), not hostility to you', 'for direction use For-You-vs-Against (stance), not this']) },
  },
  {
    id: 'upcoming', band: 'THE DETAIL', span: 1, viz: 'eventcal',
    name: 'What’s Coming Up', sub: 'Upcoming dated events that involve you',
    source: 'article_events (is_future)',
    data: { foot: '2,929 future-dated events detected. Illustrative — pending live wiring.',
      items: [
        { date: '03 JUN', label: 'Assembly monsoon-session date expected', type: 'announcement' },
        { date: '05 JUN', label: 'High Court — T-Wallet PIL next hearing', type: 'legal' },
        { date: '08 JUN', label: 'Grain procurement review (CM-chaired)', type: 'meeting' },
        { date: '12 JUN', label: 'Rythu Bandhu disbursal window opens', type: 'release' },
      ] },
    metric: { label: 'Upcoming events', value: '2,929 future', n: 2929, confidence: 'medium',
      verify: v('Events with a future date extracted from coverage — a forward calendar.', 'article_events WHERE is_future = true',
        'article_events.event_date / is_future', ['2,929 future-dated events in-window', 'typed (legal/meeting/release/announcement)', 'specific items illustrative pending live wiring']) },
  },
  {
    id: 'events', band: 'THE DETAIL', span: 1, viz: 'rank',
    name: 'What’s Happening', sub: 'Events in your coverage, by type',
    source: 'article_events.event_type',
    data: { unit: 'events', foot: '19,994 events extracted across your coverage.',
      items: [
        { label: 'Announcement', value: 3988 }, { label: 'Statement', value: 2615 }, { label: 'Accident', value: 2282 },
        { label: 'Release', value: 2080 }, { label: 'Meeting', value: 2073 }, { label: 'Legal', value: 1193 }, { label: 'Protest', value: 817 },
      ] },
    metric: { label: 'Event types', value: '19,994 events', n: 19994, confidence: 'high',
      verify: v('What kinds of events your coverage describes.', 'count(article_events) grouped by event_type',
        'article_events (69% of articles carry an event)', ['announcement 3,988 · statement 2,615 · meeting 2,073', 'legal 1,193 · protest 817', '~2 events per covered article']) },
  },
  {
    id: 'quotes', band: 'THE DETAIL', span: 1, viz: 'quotes',
    name: 'In Their Words', sub: 'Actual quotes from your coverage, with who said them',
    source: 'article_quotes.quote_text',
    data: { foot: 'Original-language verbatim. Illustrative selection.',
      items: [
        { q: 'This government has buried the farmer under file and delay.', who: 'K.T. Rama Rao', role: 'BRS', src: 'Namasthe Telangana · 18 May' },
        { q: 'There is no vision in Revanth’s rule — only press notes.', who: 'Harish Rao', role: 'BRS', src: 'V6 Velugu · 21 May' },
        { q: 'Procurement is on mission-mode; collectors are accountable.', who: 'Revanth Reddy', role: 'CM', src: 'Telangana Today · 19 May' },
      ] },
    metric: { label: 'Quotes', value: '5,761 quotes', n: 5761, confidence: 'high',
      verify: v('Verbatim quotes and their speakers, as collected.', 'article_quotes.quote_text + speaker_name',
        'article_quotes', ['5,761 quotes / 2,702 articles (28%)', '100% have a speaker name, 84% direct quotes', 'shown in original language (English translation is <1%)']) },
  },
  {
    id: 'claims', band: 'THE DETAIL', span: 1, viz: 'claims',
    name: 'What’s Being Claimed', sub: 'Specific claims and statements made about you',
    source: 'article_claims',
    data: { foot: '14,660 claim-triples across 4,526 articles (47%).',
      items: [
        { text: 'State debt has crossed ₹7 lakh crore', pred: 'alleged', src: 'opposition press' },
        { text: 'Procurement payments delayed 40+ days', pred: 'reported', src: '6 outlets' },
        { text: 'T-Wallet leak exposed 16 lakh users', pred: 'alleged', src: 'The Hindu' },
        { text: '₹1 crore each to drivers’ families', pred: 'announced', src: 'Siasat' },
      ] },
    metric: { label: 'Claims', value: '14,660 claims', n: 14660, confidence: 'medium',
      verify: v('Subject–predicate–object claims extracted from coverage about you.', 'article_claims.claim_text / predicate / object_text',
        'article_claims (47% of your articles carry claims)', ['14,660 claim-triples / 4,526 articles', '95% have predicate + object; 37% subject-resolved', 'shown verbatim — no true/false verdict applied']) },
  },
  {
    id: 'figures', band: 'THE DETAIL', span: 1, viz: 'figures',
    name: 'The Numbers in the News', sub: 'Figures mentioned in your coverage, with context',
    source: 'article_numbers',
    data: { foot: '170K figures extracted; 86% carry a unit.',
      items: [
        { value: '₹2,300 cr', ctx: 'cleared for irrigation' }, { value: '16 lakh', ctx: 'T-Wallet users at risk' },
        { value: '202', ctx: 'NDA seats (national)' }, { value: '₹1 cr', ctx: 'each to drivers’ families' },
        { value: '40+ days', ctx: 'procurement payment delay' }, { value: '₹7 lakh cr', ctx: 'alleged state debt' },
      ] },
    metric: { label: 'Figures', value: '170K extracted', n: 170381, confidence: 'high',
      verify: v('Numeric facts mentioned in coverage, with their sentence context.', 'article_numbers.value + unit + context',
        'article_numbers (33% of articles)', ['170,381 figures extracted', '86% carry a unit (₹/crore/lakh/%/seats)', '100% carry context — shown verbatim']) },
  },
  {
    id: 'pictures', band: 'THE DETAIL', span: 1, viz: 'images',
    name: 'The Picture Wall', sub: 'Images from your coverage',
    source: 'article_media (is_hero)',
    data: { foot: '9,101 of your articles carry a hero image (94%).',
      items: [
        { src: 'https://picsum.photos/seed/tg1/240/150', tone: 'hostile' }, { src: 'https://picsum.photos/seed/tg2/240/150', tone: 'supportive' },
        { src: 'https://picsum.photos/seed/tg3/240/150', tone: 'neutral' }, { src: 'https://picsum.photos/seed/tg4/240/150', tone: 'gold' },
        { src: 'https://picsum.photos/seed/tg5/240/150', tone: 'neutral' }, { src: 'https://picsum.photos/seed/tg6/240/150', tone: 'supportive' },
      ] },
    metric: { label: 'Media', value: '94% have image', n: 9101, confidence: 'high',
      verify: v('Hero images attached to your coverage.', 'count(distinct articles) in article_media WHERE is_hero',
        'article_media', ['9,101 of your articles have a hero image (94%)', '1.85M media rows system-wide', 'captions are ~0% — image only']) },
  },
];
