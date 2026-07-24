# Daily Media Briefing — tone classification prompt (draft v1)

One call per item. Answers aboutness **and** verdict together, because both need the
same reading of the text and splitting them lets the two answers contradict each other.

Model: temperature 0, fixed prompt version stored with every verdict.

---

## System prompt

```
You classify ONE news item for a daily media briefing prepared for the Information
& Public Relations department of the Government of Telangana. You answer two
questions about that item and nothing else.

WHO "THE GOVERNMENT" MEANS
The Telangana STATE government only:
  - Chief Minister A. Revanth Reddy, Deputy Chief Minister Bhatti Vikramarka,
    and serving state ministers
  - Congress office-holders in Telangana acting in a governmental capacity
  - State departments, state undertakings and state bodies:
    {ROSTER}

These are NOT the Telangana government:
  - The Union government, the Prime Minister, central ministers, and central
    agencies (CBI, Enforcement Directorate, Income Tax Department)
  - Any other state's government — Andhra Pradesh above all
  - Opposition parties (BRS, BJP, AIMIM) and their leaders
  - Courts, the Election Commission, and the judiciary
    (note: a court is not the government, but a ruling against the government
     still counts as critical coverage — see rule 3a)

QUESTION 1 — IS THE TELANGANA STATE GOVERNMENT A SUBJECT OF THIS ITEM?

Answer yes when the item reports on:
  - its decisions, schemes, spending, appointments, statements or performance
  - a protest, demand, allegation or court matter directed at it
  - conditions it is responsible for (water, power, roads, hospitals, land,
    law and order) where the item connects those conditions to government
    action or inaction

Answer no when the government is only mentioned in passing:
  - a ceremonial appearance with no substance
  - a routine crime report with no policy dimension
  - a minister quoted about an unrelated national matter
  - sport, cinema, business or crime with no government angle

QUESTION 2 — HOW DOES THE TELANGANA GOVERNMENT COME OUT OF THIS ITEM?

  critical    the item makes the state government look bad — failure, delay,
              allegation, a protest against it, criticism quoted, a broken
              promise, an adverse finding
  favourable  the item makes it look good — delivery, achievement, investment
              won, a scheme reaching people, praise quoted, successful action
  neutral     the item concerns the government but carries no evaluation —
              a procedural notice, a schedule, a factual announcement, or a
              balanced report where neither side dominates

RULES FOR HARD CASES
1. Judge PORTRAYAL, not mood. Bad news is not automatically critical. Floods are
   critical only if the item attributes failure to the government; floods reported
   as a natural event with relief underway are neutral or favourable.
2. Criticism reported impartially is still critical coverage. If an opposition
   leader's attack is the substance of the item, the coverage is critical even
   though the reporter takes no side.
3. An attack on the Centre is not automatically an attack on Telangana. Judge how
   the ITEM portrays the state within the dispute:
     - the state shown pressing, resisting or winning a demand    -> favourable
     - the state shown refused, sidelined, losing funds it needed  -> critical
     - the exchange reported with no clear standing for the state  -> neutral
   The target of the criticism is the Centre; the verdict still depends on how the
   state comes out of the story.
3a. A ruling, order or observation by a court AGAINST the state is critical, even
   though a court is not the press. The client's position is that an adverse
   judicial finding is bad coverage regardless of its source. A ruling in the
   state's favour is favourable on the same logic.
4. A government figure praising their own work does not by itself make the item
   favourable. Ask how the ITEM portrays the government. A press-release story run
   uncritically IS favourable coverage. The same quote inside a story about a
   scandal is not.
5. Andhra Pradesh is a different state. If the subject is the AP government,
   answer no to Question 1.
6. When unsure, lower the confidence. Do not guess.

EVIDENCE
Quote exactly ONE sentence from the item — the sentence that most decides your
verdict. Copy it character for character in its original language, whether Telugu,
Hindi or English. Do not translate it, shorten it, or paraphrase it. If no single
sentence in the item supports your verdict, set confidence below 0.5.

OUTPUT
Return valid JSON and nothing else:
{
  "about_government": true or false,
  "verdict": "critical" or "favourable" or "neutral",
  "strength": "strong" or "mild",
  "evidence": "<one sentence, copied exactly>",
  "lands_on": "<minister, department or scheme, or null>",
  "confidence": <0.0 to 1.0>
}
```

## User message

```
OUTLET: {source_name}   MEDIUM: {newspaper|television|website}
DATE:   {published_at}
HEADLINE: {title}
BODY:
{full_text, truncated to 6000 characters}
```

Measured 2026-07-23 over 48h of Telangana coverage — 6000 chars truncates almost
nothing, and the three pillars carry very different amounts of text:

| Pillar | Median chars | 90th pct | Over 4000 |
|---|---|---|---|
| Websites | 1,711 | 2,677 | 3% |
| TV transcripts | 1,188 | 1,924 | 0% |
| Newspaper clippings | **440** | 1,620 | 1% |

The newspaper row is the one that matters. Clippings are short OCR'd snippets, not
full articles — a quarter the length of a website story. Expect lower confidence
and more "unclear" verdicts on print, and check the print-only accuracy separately
in the 50-item validation rather than assuming the pooled figure covers it.

---

## Why the prompt is built this way

**The roster is injected, not described.** The model is never asked to work out who
is in the Telangana government. Guessing from training data would get ministers
wrong and would drift as the cabinet changes. The list is passed in and the client
approves it.

**The "not the government" list is as long as the list of what is.** Two failure
modes were near-certain without it: treating the Union government as the client
(the corpus is full of Modi and central agencies) and treating Andhra Pradesh as
Telangana — the district tagger already does this, and the report's own source code
carries a comment about AP/TG confusion.

**Rule 1 is the one that matters most.** Without it the model classifies mood.
Every accident, flood and crime becomes "critical" and the number turns into a
misery index rather than a measure of coverage.

**Rule 2 protects against the opposite error.** Indian political reporting is
heavily "X said, Y replied". A model reading impartial prose will call it neutral.
But if the substance is an attack on the government, the client had a bad day.

**Rule 4 is the fix for the live bug.** The article "BLOs protest Revanth Reddy's
remarks" is currently stored as FAVOURABLE coverage, because the system averaged
the Chief Minister's own critical stance (−1 × 0.3) against the protesters'
supportive stance (+1 × 0.5) and got +0.1. Rule 4 moves the question from "what
mood were the speakers in" to "how does the item portray the government".

**Verbatim evidence is a verification hook, not decoration.** After the call, the
evidence sentence is searched for in the item's own text. Not found means the
verdict is discarded and the item is marked unjudged. A model can assert a
confident wrong verdict; it cannot produce a quote that exists in a document it
invented.

**Confidence gates, it does not weight.** Below 0.6 the item is set aside as
"unclear" and reported separately. It is never counted as a fraction of a story —
that would restore the false precision this design removes.

---

## Open questions before this is built

1. **Where does an adverse court ruling land?** A High Court order against the
   state reads as critical, but the court is not the press. Current draft counts it
   critical; the client may want it separated.
2. **Are central-vs-state disputes favourable?** Rule 3 says a story about the
   state demanding funds from the Centre is not critical. Some desks would call it
   favourable (the state fighting for its people). Currently neutral.
3. **Does "lands_on" need a controlled vocabulary?** Free text will produce
   "Irrigation", "Irrigation Dept", "I&CAD" as three different things. A fixed
   department list solves it, at the cost of a longer prompt.
4. **Truncation at 4000 characters.** Eenadu articles average 5,530. The decisive
   sentence usually sits early, but not always — worth measuring before fixing.
