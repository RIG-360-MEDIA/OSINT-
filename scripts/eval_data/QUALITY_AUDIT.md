# Full quality audit — text + snapshots (go/no-go)

**Date:** 2026-06-10. Two independent axes, measured separately. No fabricated
numbers — text faithfulness is set-intersection against OCR'd page text; snapshot
verdicts are from eyeballing every rendered crop.

## Axis 1 — Snapshot / localization quality: **GOOD ENOUGH ✅**

Across Financial Express + Sakshi + Andhra Jyothi (3 pages each, 48 articles,
every emitted crop rendered and inspected):

- **0 wrong-location crops.** The dangerous failure mode (metadata says story A,
  image shows region B / an infographic) is eliminated.
- **~65% of articles get a content-anchored crop** (`text` or `body`); the rest
  are honestly left uncropped (`none`) rather than mis-cropped.
- **Provenance is labelled** (`clip_source` = text/body/none) so a consumer knows
  the trust level of every snapshot.

Residual imperfections (quality nits, NOT wrong crops):
- A full-width headline can make the box wide enough to include an adjacent
  boxed side-item (AJ #6 pulled in a related "US strike on ship" box).
- Some crops capture headline + lead only when the body wraps across columns.
- A narrow single-column article can clip the wider headline's right edge (AJ #5).

**Verdict:** production-acceptable. The image is the source of truth for what was
printed, and no snapshot is confidently wrong.

## Axis 2 — Vision text faithfulness: **NOT GOOD ENOUGH as stored fact ⚠️**

Measured on Financial Express (English) against Tesseract-OCR'd page text as
ground truth. NB: FE's embedded PDF text layer is font-encoded gibberish (no
Unicode map) — unusable — so OCR is the only ground truth.

| Metric | Result | Reading |
|---|---|---|
| Mean token_recall | **0.93** (min 0.81) | prose mostly uses words actually on the page |
| Numbers grounded | **40/51 = 78%** | **~1 in 5 figures does not appear on the page** |

- token_recall is a **lenient upper bound** (a word counts if it appears anywhere
  on the 3 pages), so true per-article faithfulness is lower than 0.93.
- The 78% number-grounding is a **lower bound** (some ungrounded figures are OCR
  misreads of the truth, not Vision fabrication) — but the direction is clear:
  **numbers are materially less reliable than prose.**
- Corroborated by manual reads earlier: semantic hallucinations with real words
  but wrong facts — "outskirts of Beirut" (Iran–Israel story), "2015-16" (wrong
  year), "Cyrus Mistry" (stale, years old), "62% growth". These pass token_recall
  but are factually wrong.
- **Telugu byline extraction = 0** (English = 19/20). Telugu text is at least as
  risky as English (same Vision model, harder script).

**Verdict:** Vision body text is fluent and mostly word-grounded, but injects
wrong numbers and stale/incorrect facts. **Storing it as authoritative content is
unsafe for an intelligence product.**

## Recommendation — move forward, but change the text source

1. **Ship the snapshots** as-is (with `clip_source` labels). The image is ground
   truth; the localization axis is sound.
2. **Do NOT store Vision body text as fact.** Two options:
   - **(Preferred) Store OCR text within the crop bbox as `body_text`.** We
     already run OCR for localization; OCR text is grounded by construction (it
     is literally what is on the page). Vision keeps only what it is good at:
     segmentation + headline + section. OCR garbling is visibly low-trust;
     Vision fabrication is invisibly high-trust — for intelligence, real-but-
     garbled beats fluent-but-fake.
   - Or store Vision text flagged `unverified`, with the snapshot as the
     authoritative artifact and numbers stripped/whitelisted against OCR.
3. **Headline** stays Vision (near-verbatim, high quality) — optionally
   cross-checked against the top OCR line of the crop.

## Bottom line
- **Snapshots: GO.** No wrong crops; honest coverage; labelled provenance.
- **Text-as-stored: NO-GO until the body source changes** from Vision prose to
  OCR-within-bbox (or Vision-flagged-unverified). The fix is architectural, not a
  tuning knob.
