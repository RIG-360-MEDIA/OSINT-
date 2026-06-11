/**
 * Builds docs/RIG_OSINT_pitch.docx — 3-page pitch deck.
 * Rich content: ~700 words per page, each section concrete + specific.
 */
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, AlignmentType, LevelFormat,
  BorderStyle, PageBreak,
} = require("docx");

const OUT = path.resolve(__dirname, "..", "..", "docs", "RIG_OSINT_pitch_v2.docx");

const accent     = "0F5BA7";
const accentDark = "0A3D6E";
const muted      = "555555";
const soft       = "888888";
const rule       = { style: BorderStyle.SINGLE, size: 6, color: accent };

const eyebrow = (text) => new Paragraph({
  spacing: { after: 40 },
  children: [new TextRun({ text, bold: true, size: 16, color: accent,
    characterSpacing: 80, font: "Calibri" })],
});

const h1 = (text) => new Paragraph({
  spacing: { before: 0, after: 100 },
  children: [new TextRun({ text, bold: true, size: 46, color: "1A1A1A", font: "Calibri" })],
});

const h2 = (text) => new Paragraph({
  spacing: { before: 180, after: 60 },
  border: { bottom: { ...rule, space: 2 } },
  children: [new TextRun({ text: text.toUpperCase(), bold: true, size: 20,
    color: accent, font: "Calibri", characterSpacing: 50 })],
});

const h3 = (text) => new Paragraph({
  spacing: { before: 100, after: 30 },
  children: [new TextRun({ text, bold: true, size: 22,
    color: accentDark, font: "Calibri" })],
});

const lead = (text) => new Paragraph({
  spacing: { after: 80, line: 280 },
  children: [new TextRun({ text, size: 22, color: "1A1A1A",
    font: "Calibri", italics: true })],
});

const body = (text) => new Paragraph({
  spacing: { after: 70, line: 280 },
  children: [new TextRun({ text, size: 19, color: "222222", font: "Calibri" })],
});

const bullet = (bold_prefix, text) => new Paragraph({
  numbering: { reference: "bullets", level: 0 },
  spacing: { after: 50, line: 270 },
  children: [
    bold_prefix
      ? new TextRun({ text: bold_prefix + " — ", size: 19, color: accentDark, font: "Calibri", bold: true })
      : null,
    new TextRun({ text, size: 19, color: "222222", font: "Calibri" }),
  ].filter(Boolean),
});

const pullquote = (text) => new Paragraph({
  spacing: { before: 80, after: 80 },
  alignment: AlignmentType.CENTER,
  border: { top: { ...rule, space: 6 }, bottom: { ...rule, space: 6 } },
  children: [new TextRun({ text: "“" + text + "”", italics: true, size: 22,
    color: accent, font: "Calibri" })],
});

const breakPage = new Paragraph({ children: [new PageBreak()] });

const doc = new Document({
  creator: "RIG OSINT",
  title: "RIG OSINT — Decision Intelligence",
  numbering: {
    config: [{
      reference: "bullets",
      levels: [{
        level: 0, format: LevelFormat.BULLET, text: "▸",
        alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 360, hanging: 240 } },
                 run: { color: accent } },
      }],
    }],
  },
  styles: { default: { document: { run: { font: "Calibri", size: 20 } } } },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1000, right: 1100, bottom: 1000, left: 1100 },
      },
    },
    children: [

      // ════════════════════════════ PAGE 1 ════════════════════════════
      eyebrow("RIG OSINT  ·  FOR LEADERSHIP DESKS"),
      h1("Decision intelligence, filed by morning."),
      lead(
        "One brief on the principal’s desk every morning at 06:00 IST. The day’s most consequential " +
        "stories about your leadership, your opposition, and your portfolio — already read, ranked, " +
        "translated, and cited so the office can act before the news cycle catches up."
      ),

      pullquote(
        "We will not build Telangana on press releases. We will build it on rivers, records, and receipts."
      ),

      body(
        "Every morning, somewhere between 5,000 and 8,000 articles land in our system from across India " +
        "and the world. Newspapers in eight languages, television bulletins, social-media handles of " +
        "every politician and journalist who matters, government gazettes, court orders, party " +
        "spokesperson statements. By 06:00 IST, that mountain has been read, compared, " +
        "cross-referenced, and compressed into a single brief — one page that tells the principal " +
        "exactly what changed overnight and what needs a decision before lunch."
      ),
      body(
        "Most monitoring tools deliver a firehose: 200 article links, sentiment graphs nobody reads, " +
        "and an inbox the principal eventually stops opening. We deliver the opposite. The brief is " +
        "curated, prioritised, and short — because intelligence that takes 40 minutes to read at " +
        "06:00 IST is intelligence that doesn’t get read."
      ),

      h2("What lands on the desk at 06:00"),
      bullet("Top stories ranked by consequence",
        "the day’s top developments across politics, governance, security, and policy — ranked by " +
        "what actually changed overnight, not by what made the loudest noise. Each story carries a " +
        "consequence score the office can interrogate."
      ),
      bullet("Leadership coverage",
        "every quote about the Chief Minister, key ministers, and named opposition figures — " +
        "attributed to source and outlet, with stance flagged: supportive, critical, or neutral. " +
        "Telugu vernacular and English national press shown side by side, so the office never sees " +
        "only half the picture."
      ),
      bullet("Counter-narratives",
        "what the opposition is saying right now, which narratives are climbing fastest, and which " +
        "of those will hit the evening bulletin if left unanswered. Often a 4-6 hour lead time " +
        "between WhatsApp circulation and prime-time pickup."
      ),
      bullet("Horizon — the next 24 hours",
        "scheduled events, hearings, press conferences, court dates. The brief tells the principal " +
        "what topics are likely to dominate the news cycle tomorrow, so the day is planned rather " +
        "than reacted to."
      ),
      bullet("Every line cited",
        "every claim in the brief points back to the article it came from. Hover, click, verify. " +
        "Nothing in the brief is editorial opinion without a sourced quote behind it."
      ),

      // ════════════════════════════ PAGE 2 ════════════════════════════
      breakPage,
      eyebrow("PAGE 2  ·  WHERE THE SIGNAL COMES FROM"),
      h1("Every voice in the room. In every language."),
      lead(
        "We listen everywhere the conversation about your leadership is actually happening — " +
        "not just where it’s loudest, but where it’s earliest, sharpest, and most likely to shape " +
        "tomorrow’s headline."
      ),
      body(
        "The way intelligence used to work: one or two trusted dailies, a clipping service, the " +
        "occasional summary from a press secretary. That model assumes the conversation about " +
        "leadership happens in English, in print, on a 24-hour delay. None of that is true anymore. " +
        "A WhatsApp video from a Kothagudem displacement camp at 02:00 IST drives the Eenadu " +
        "edit-page lede at 06:00 and the V6 bulletin by lunchtime. By the time the English national " +
        "press catches up, the narrative is already set. We listen at every layer of that chain, " +
        "from the WhatsApp tier up."
      ),

      h2("The listening posts"),
      bullet("Newspapers (300+ outlets)",
        "National dailies — Hindustan Times, The Hindu, Indian Express, Times of India, Mint, " +
        "Business Standard — read in full every morning. Regional press — Eenadu, Sakshi, Andhra " +
        "Jyothy, Namasthe Telangana, V6, Siasat — read with the same care. Page-one stories, " +
        "edits, op-eds, columns, district-page reports, classifieds even, when the signal is there."
      ),
      bullet("Television bulletins",
        "We track what the prime-time anchors are saying. Telugu (TV9, ETV, ABN, NTV, HMTV, V6), " +
        "Hindi (Aaj Tak, NDTV India), English (NDTV 24x7, India Today, Republic). When a story " +
        "moves from print to broadcast, you know within minutes — and you know which anchor framed it which way."
      ),
      bullet("Social media",
        "Twitter/X handles of every elected leader, party spokesperson, journalist, and editor. " +
        "Public Telegram channels of party workers, citizen movements, and the kind of " +
        "high-velocity discussion that often precedes mainstream news by hours. All pulled in " +
        "real time, sentiment scored, surge-flagged."
      ),
      bullet("Official documents",
        "Cabinet notes, gazette notifications, court orders, RTI replies, tribunal verdicts, " +
        "PSU disclosures, government press releases. The official record of what was decided, " +
        "by whom, on what date, with what reasoning. The paper trail behind the headline."
      ),
      bullet("Languages",
        "English, Telugu, Hindi, Tamil, Kannada, Bengali, Marathi, Urdu. Regional language " +
        "coverage is translated, normalised, and brought into the brief alongside the national " +
        "English press — so the principal sees the full picture, not the bilingual elite’s slice."
      ),

      h2("The leadership filter"),
      body(
        "Most monitoring tools dump everything. We curate by who matters to your office. Every " +
        "incoming article is read against a calibrated watch-list — the Chief Minister, the " +
        "full cabinet, the named opposition leaders, the police department, key bureaucrats, " +
        "the regulatory agencies the office must respond to. Articles that touch that watch-list " +
        "get the full extraction treatment: quotes pulled with verified speaker attribution, " +
        "stance scored on a numerical scale, dates fixed against the publication record, " +
        "locations geocoded down to district. Articles that don’t touch the watch-list are " +
        "kept on file but stay out of the morning read."
      ),
      body(
        "The watch-list is editable. As priorities shift — a new ministry takes over a portfolio, " +
        "a new opposition figure emerges, an inquiry commission is constituted — the watch-list " +
        "updates and tomorrow’s brief reflects the new focus. The result: a brief that respects " +
        "the principal’s time. The reader doesn’t see what didn’t change. They see what did."
      ),

      // ════════════════════════════ PAGE 3 ════════════════════════════
      breakPage,
      eyebrow("PAGE 3  ·  WHAT YOU DO WITH IT"),
      h1("From noise to next action."),
      lead(
        "The brief doesn’t just inform — it points. Every section ends with a recommended call: " +
        "respond, brace, defer, monitor. Intelligence that doesn’t lead to action is just news."
      ),
      body(
        "Information without a verb attached to it is wallpaper. The principal’s morning is too " +
        "short for wallpaper. Every signal we surface comes with a recommended next move — " +
        "framed not as instructions but as readiness. The office stays in charge of the call. " +
        "The brief makes sure the call is informed and timely."
      ),

      h2("Insights & alerts the office can act on"),
      bullet("Climbing-now alerts",
        "An opposition narrative is rising sharply — pillar-subsidence claims being circulated in " +
        "three Telugu evening bulletins, displacement-vlog reaching 240,000 Telugu views overnight. " +
        "We flag it 4-6 hours before it lands in mainstream press, with a recommended response window."
      ),
      bullet("Contradictions across sources",
        "Times of India says one thing, Eenadu says another, social-media chatter says a third. " +
        "We surface the disagreement — not just the volume of coverage. The office sees which " +
        "versions of the story actually need a correction, and where the consensus already exists."
      ),
      bullet("Coverage blindspots",
        "Stories that English-language press covered but Telugu vernacular missed entirely — and " +
        "vice versa. The vernacular paper that ignored a major cabinet decision is itself a signal. " +
        "So is the English daily that didn’t pick up the Khammam rally. Both tell the office " +
        "something about how the leadership is being framed by whom."
      ),
      bullet("First-time mentions",
        "Entities that surfaced today but were absent yesterday. Often the earliest signal that a " +
        "new story or new actor is entering the public conversation. The morning brief includes a " +
        "named-entity watch-list of these emergents."
      ),
      bullet("Horizon for tomorrow",
        "A one-paragraph forward look — what tomorrow’s press conferences, court hearings, party " +
        "events, and scheduled bills are likely to generate. Built from the calendar of public " +
        "events cross-referenced with the corpus’s recent momentum. So the day is planned, not " +
        "reacted to."
      ),

      // Image placeholder
      new Paragraph({
        spacing: { before: 140, after: 140 },
        alignment: AlignmentType.CENTER,
        border: {
          top:    { style: BorderStyle.DASHED, size: 8, color: accent, space: 8 },
          bottom: { style: BorderStyle.DASHED, size: 8, color: accent, space: 8 },
          left:   { style: BorderStyle.DASHED, size: 8, color: accent, space: 8 },
          right:  { style: BorderStyle.DASHED, size: 8, color: accent, space: 8 },
        },
        children: [
          new TextRun({ text: "📊  ", size: 28 }),
          new TextRun({
            text: "[ Insert RIG OSINT Morning Brief screenshot here ]",
            bold: true, size: 20, color: accent, font: "Calibri",
          }),
          new TextRun({ break: 1 }),
          new TextRun({
            text: "Drag-and-drop the dashboard image into this box — what the brief actually " +
                  "looks like on the principal’s desk at 06:00 IST.",
            size: 16, color: soft, italics: true, font: "Calibri",
          }),
        ],
      }),

      h2("What the principal trusts"),
      body(
        "Every claim has a citation. Every quote has a speaker, an outlet, and a timestamp. Every " +
        "stance is a score, not an opinion. Every story is reproducible — the principal can ask " +
        "“why did you rank this first?” and get a numbers-backed answer in seconds. The brief " +
        "doesn’t hide its working. It shows it."
      ),
      body(
        "When a regional headline turns up wrong, when a Telugu translation reads off, when an " +
        "opposition quote sounds out of context — the office can drill from the brief back to the " +
        "source article in two clicks. The audit trail is built in from the first line of code. " +
        "We have no interest in being a black box; we have every interest in being the most " +
        "trusted single document in the principal’s morning."
      ),

      new Paragraph({
        spacing: { before: 160 },
        alignment: AlignmentType.CENTER,
        children: [new TextRun({
          text: "RIG OSINT — Filed by morning. Auditable by line. Personalised to your office.",
          italics: true, size: 18, color: accent, font: "Calibri",
        })],
      }),
    ],
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, buf);
  console.log("Wrote", OUT, "·", buf.length, "bytes");
});
