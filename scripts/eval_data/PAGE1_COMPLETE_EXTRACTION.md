# PAGE 1 — HONEST EXTRACTION REPORT (post-fix)

> **This file replaces an earlier version that contained FABRICATED body text.**
> The previous version invented sentence-completions and details beyond the real
> 300-char preview the system stores. Everything below is the system's actual
> output from a live run on the Financial Express front page (the PDF Manam's
> dead Drive link redirects to). Nothing here is hand-written.

## Two independent quality axes (don't conflate them)

1. **Localization** — *where* the snapshot was cropped. Three outcomes:
   `text` (matched the real headline → TRUSTED), `layout` (geometry-block guess →
   UNVERIFIED), `none` (couldn't locate → no crop).
2. **Text** — headline/body come from the Vision LLM reading the whole page.
   **Vision paraphrases and sometimes hallucinates** (see caveats below), and its
   output varies run-to-run. Correct text does NOT imply a correct crop, and vice
   versa.

## This run: 6 articles, honest split

| Localization | Count |
|---|---|
| `text` (TRUSTED) | 4 |
| `layout` (UNVERIFIED) | 1 |
| `none` (no crop) | 1 |

(The earlier "100% anchored / production-ready" claim was wrong — it counted
layout guesses as wins. art0 below proves why that's unsafe.)

---

## Article-by-article (verbatim system output)

### #0 — Bombay HC strikes down ₹22,000-cr spectrum levy
- **Localization:** `layout` ⚠️ UNVERIFIED — box `[1134.7, 947.5, 1480.6, 1382.7]`
  (far-right column). The shape filter stopped the old infographic mis-crop, but
  the layout path still can't guarantee this box is *this* article's column. Treat
  the snapshot as unconfirmed.
- **Subheadline:** "No legal basis for retrospective charge, says bench"
- **Byline:** Urvi Malaviya & Rishi Raj  *(paper prints "MALVANIA" — Vision misread)*
- **body_head (300 chars, raw):** "The Bombay High Court on Monday struck down the Centre's 2012 decision to levy a one-time spectrum charge (OTSC) on telecom operators for spectrum holdings beyond 6.2 MHz. The judgment is significant as it ends a long-drawn litigation that had already led to Bharti Airtel and Vodafone Idea to provis"

### #1 — Ceasefire faces its toughest test
- **Localization:** `text` ✅ TRUSTED — box `[194.7, 1020.1, 927.8, 1185.1]`
- **Subheadline:** "Iran, Israel trade strikes for 1st time since April; Trump plea leads to a halt"
- **Byline:** Reuters
- **body_head:** "Iran and Israel said on Monday they had halted attacks on each other after an Israeli air strike on Iranian military facilities and Iran's subsequent missile strikes on Israeli military targets on the outskirts of Beirut. The wave of attacks over 24 hours were the most direct clashes between Israel "
- ⚠️ **Vision caveat:** "outskirts of Beirut" looks hallucinated for an Iran–Israel strike story.

### #2 — India sees surprise current account surplus in Jan-Mar
- **Localization:** `none` ❌ NO CROP — fell back to full page. Honest miss.
- **Byline:** FE Bureau
- **body_head:** "The country is said to witness a 'balance of payments' surplus in FY25. Even as the current account deficit (CAD) in the fourth quarter of 2015-16 widened to 3.4% of GDP from 1.1% a year ago, the Reserve Bank of India (RBI) on Monday showed a surplus of $4.8 billion and a surplus of $13.4 billion in"
- ⚠️ **Vision caveat:** "2015-16" is wrong (story is Jan-Mar of the current year) — Vision hallucinated the year.

### #3 — Tata Trusts meet skips contentious flashpoints
- **Localization:** `text` ✅ TRUSTED — box `[944.5, 950.1, 1120.3, 1140.2]`
- **Byline:** Urvi Malavania  *(Vision misspelling)*
- **body_head:** "A MEETING of the Sir Dorabji Tata Trust on Monday steered clear of the contentious issues confronting the Tata Group, focusing instead on routine business. The board did not take up sensitive subjects currently pending over the Tata Sons Chairman Cyrus Mistry's removal and replacement by Natarajan C"
- ⚠️ **Vision caveat:** "Cyrus Mistry's removal" is stale context (years old) — likely Vision filling in from training, not the page.

### #4 — IndiGo expects FY27 growth in single digits
- **Localization:** `text` ✅ TRUSTED — box `[944.8, 1632.4, 1258.7, 2272.6]` (full tall column)
- **Byline:** Akbar Merchant
- **body_head:** "The country's largest airline IndiGo expects capacity growth to remain in single digits in FY27, which will be lower than the 62% growth it had in FY24. The airline's capacity growth trajectory for the next few years is expected to be 22% in FY24, 13% in FY25, 10% in FY26 and single digits in FY27.\n"
- ⚠️ **Vision caveat:** "62% growth in FY24" is implausible — numbers vary across runs; treat figures as unverified.

### #5 — AI for everything until the hefty bill comes
- **Localization:** `text` ✅ TRUSTED — box `[9.8, 1925.0, 925.5, 2392.7]` (wide opinion strip)
- **Byline:** Vishal Sikka, Swarna Bapat
- **body_head:** "We do not believe in micro-managing individual employee tokens (for AI coding tools), which risk stifling the very innovation we are trying to unlock like a second headquarters. The corporate professions have been remarkable in their candour. Uber reportedly exhausted its annual budget for generativ"

---

## Bottom line

- **Localization is fixed where it matters:** no more infographic-cell or sliver
  crops. 4/6 are trusted text anchors with correct boxes; 1 is an honest
  unverified layout guess; 1 is an honest miss.
- **Vision text quality is a separate, open problem.** Several body previews
  contain hallucinated facts (Beirut, 2015-16, Cyrus Mistry, 62%). The snapshot
  image is the source of truth for what was printed; the Vision body is a
  paraphrase that needs its own guardrails before it can be trusted as content.
- **Honest headline metric = text-anchored only.** Across Sakshi + Andhra Jyothi
  (2 pages each) that is **10/19 = 53%**, not the previously-claimed 88%.
