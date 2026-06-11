/**
 * Builds docs/OSINT_one_pager.docx — a one-page primer on Open-Source Intelligence
 * with a placeholder area for the user's RIG OSINT Morning Brief screenshot.
 */
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, LevelFormat, HeadingLevel, BorderStyle, WidthType,
  ShadingType, PageOrientation,
} = require("docx");

const OUT = path.resolve(__dirname, "..", "..", "docs", "OSINT_one_pager.docx");

// ── Helpers ────────────────────────────────────────────────────────────────
const accent = "0F5BA7";   // editorial blue
const muted  = "555555";
const soft   = "888888";
const rule   = { style: BorderStyle.SINGLE, size: 4, color: accent };

const h1 = (text) => new Paragraph({
  heading: HeadingLevel.HEADING_1,
  spacing: { before: 0, after: 80 },
  children: [new TextRun({ text, bold: true, size: 44, color: "1A1A1A", font: "Calibri" })],
});

const eyebrow = (text) => new Paragraph({
  spacing: { after: 40 },
  children: [new TextRun({ text, bold: true, size: 16, color: accent, characterSpacing: 60, font: "Calibri" })],
});

const sectionTitle = (text) => new Paragraph({
  spacing: { before: 160, after: 50 },
  border: { bottom: { ...rule, space: 1 } },
  children: [new TextRun({ text: text.toUpperCase(), bold: true, size: 20, color: accent, font: "Calibri", characterSpacing: 40 })],
});

const body = (text, opts = {}) => new Paragraph({
  spacing: { after: 60, line: 280 },
  children: [new TextRun({ text, size: 18, color: "222222", font: "Calibri", ...opts })],
});

const bullet = (text) => new Paragraph({
  numbering: { reference: "bullets", level: 0 },
  spacing: { after: 20, line: 260 },
  children: [new TextRun({ text, size: 18, color: "222222", font: "Calibri" })],
});

// ── Page content ───────────────────────────────────────────────────────────
const doc = new Document({
  creator: "RIG OSINT",
  title: "OSINT — A Primer",
  numbering: {
    config: [{
      reference: "bullets",
      levels: [{
        level: 0,
        format: LevelFormat.BULLET,
        text: "•",
        alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 360, hanging: 240 } } },
      }],
    }],
  },
  styles: {
    default: { document: { run: { font: "Calibri", size: 18 } } },
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },                    // US Letter
        margin: { top: 900, right: 900, bottom: 900, left: 900 }, // ~0.62" margins for one-page fit
      },
    },
    children: [
      // ── Masthead ───
      eyebrow("RIG OSINT  ·  ONE-PAGE PRIMER"),
      h1("OSINT — Open-Source Intelligence"),
      body("A working introduction for anyone reading a daily intelligence brief.", { italics: true, color: muted }),

      // ── Section 1 ───
      sectionTitle("1. What is OSINT?"),
      body(
        "Open-Source Intelligence (OSINT) is the practice of collecting and analysing information " +
        "that is legally and publicly available — news articles, government documents, social-media " +
        "posts, satellite imagery, broadcast transcripts, court filings, financial disclosures, and " +
        "more — and turning it into structured, decision-grade knowledge. It is intelligence built " +
        "from what anyone could, in theory, read; the craft lies in finding it, verifying it, and " +
        "fusing it at scale faster and more rigorously than a human alone can."
      ),

      // ── Section 2 ───
      sectionTitle("2. What is OSINT used for?"),
      bullet("Journalism & newsrooms — corroborating leaks, tracking developing stories across sources, surfacing under-covered events."),
      bullet("National security & defence — early warning, monitoring foreign rhetoric, tracking troop movements via satellite + social posts."),
      bullet("Corporate due diligence — vetting partners, supply chains, sanctions exposure, reputational risk."),
      bullet("Crisis response — disaster mapping, refugee flows, infrastructure damage, real-time situational awareness."),
      bullet("Civil society & investigations — human-rights documentation, financial-crime tracing, election integrity."),
      bullet("Policy & analyst desks — country briefs, sentiment tracking, narrative shifts across language communities."),

      // ── Section 3 ───
      sectionTitle("3. Advantages of OSINT"),
      bullet("Legally collectable — no clandestine sources required; every claim is auditable."),
      bullet("Scales — machines can read millions of items per day; humans focus on judgement, not retrieval."),
      bullet("Diverse vantage points — multiple sources, languages, and ideologies surface contradictions classified channels miss."),
      bullet("Citeable — every conclusion ties to a publicly verifiable URL, document, or transcript."),
      bullet("Cost-effective — orders of magnitude cheaper than HUMINT or SIGINT, with much of the same coverage on geopolitical questions."),

      // ── Section 4 ───
      sectionTitle("4. How it works"),
      body(
        "A modern OSINT pipeline runs five stages: (1) Collect — pull from RSS, sitemaps, social APIs, " +
        "government portals, broadcast feeds. (2) Normalise — strip boilerplate, detect language, " +
        "deduplicate. (3) Extract — large language models pull claims, quotes, actors, dates, locations, " +
        "numbers, and stance into a structured schema. (4) Cluster — group the same story across " +
        "outlets and languages by semantic similarity and event-date agreement. (5) Surface — score " +
        "importance, flag contradictions, generate briefs, and route to analysts. The dashboard below " +
        "shows this loop in action — 247 articles synthesised overnight into one readable file."
      ),

      // ── Image placeholder ───
      new Paragraph({
        spacing: { before: 100, after: 100 },
        alignment: AlignmentType.CENTER,
        border: {
          top:    { style: BorderStyle.DASHED, size: 6, color: accent, space: 6 },
          bottom: { style: BorderStyle.DASHED, size: 6, color: accent, space: 6 },
          left:   { style: BorderStyle.DASHED, size: 6, color: accent, space: 6 },
          right:  { style: BorderStyle.DASHED, size: 6, color: accent, space: 6 },
        },
        children: [
          new TextRun({ text: "📊  ", size: 24 }),
          new TextRun({
            text: "[ Insert RIG OSINT Morning Brief screenshot here ]",
            bold: true, size: 18, color: accent, font: "Calibri",
          }),
          new TextRun({ break: 1 }),
          new TextRun({
            text: "Drag-and-drop the dashboard image into this box · 247 articles · 18 outlets · 3 languages · sentiment & overnight synthesis",
            size: 14, color: soft, italics: true, font: "Calibri",
          }),
        ],
      }),

      // ── Section 5 ───
      sectionTitle("5. Why it matters"),
      body(
        "Decision-makers — editors, ministers, analysts, founders — drown in news but starve for " +
        "signal. OSINT, done well, compresses a day's worth of global activity into a few hundred " +
        "rows of structured, cited, comparable facts. It democratises intelligence: a journalist " +
        "with a laptop can now triangulate evidence that, twenty years ago, required a state agency. " +
        "Most importantly, every claim leads back to its source — making the work auditable, " +
        "reproducible, and trustworthy."
      ),
      new Paragraph({
        spacing: { before: 100 },
        children: [new TextRun({
          text: "RIG OSINT — Filed by morning. Auditable by line.",
          italics: true, size: 16, color: accent, font: "Calibri",
        })],
        alignment: AlignmentType.CENTER,
      }),
    ],
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, buf);
  console.log("Wrote", OUT, "·", buf.length, "bytes");
});
