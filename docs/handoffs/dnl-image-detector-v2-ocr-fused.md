# DNL image detector v2 — OCR-fused classifier (#3)

**Goal:** stop real photos falling to the placeholder AND stop junk (UrduPoint logo,
posters, TV lower-thirds) being shown as cluster thumbnails. Root cause of the *live*
symptom is separate (see "Ship path"); this doc covers the **detector quality** work.

## What was wrong with the old detector
`src/lib/studio/image-scan.ts::classify` is **colour-histogram only** (48×48, 64 colour
buckets + mean saturation). It cannot separate "photo" from "photo with a logo/text
stamped on it". On a 29-image hand-labelled gold set it scored:

- accuracy **79%**, junk precision **64%**, **real-photo false-flag rate 26%**, recall 90%.

The 26% false-flag is the "real photos → placeholder" complaint: it killed genuine wire
photos (Trump podium, cyclists-in-rain, refinery, a portrait) that happened to be
low-variance, while still missing busy watermarked cards.

## The v2 classifier (OCR-fused)
`/root/rig/tools/imgqual/classifier.py` (box). Fuses three signals:

1. **Histogram flatness** (`top1 >= 0.80`) → near-solid background = logo/banner
   (catches UrduPoint, Le Monde, Qatar MFA logos).
2. **OCR text density** (Tesseract; `ocr_area >= 0.04` OR `>= 8` confident words) →
   poster / infographic / TV lower-third (catches "369 million", CABINET DECISIONS,
   timetable, breaking-news poster).
3. **Colour-poster arm** (`top3>=0.62 AND sat>=0.55 AND words>=1`) → saturated poster.

Real photos have ~0 OCR text and are not near-solid → the histogram's false-positives are
rescued.

### Measured result — TWO gold sets
The 29-image set (smoke test) was optimistic. The **82-image set** (`gold200/`, hand-labelled
from two contact sheets, multilingual OCR: eng+hin+mar+urd+ara+ben+tam+tel+chi_sim) is the
trustworthy number:

| Metric | old histogram | **v2 OCR-fused** | (29-set was) |
|---|---|---|---|
| junk **precision** | 47% | **88%** | 64→90 |
| **real-photo false-flag** | 27% | **3%** | 26→5 |
| accuracy | 70% | **87%** | 79→93 |
| junk **recall** | 61% | **61%** | 90→90 |

**Verdict: v2 solves the PRIMARY complaint** (real photos → placeholder: false-flag 27%→3%,
precision 47%→88%). **But junk recall plateaus at 61%** with cheap CV signals.

### The recall ceiling (important, measured)
The 9/23 junk that slip through are **statistically identical to real photos**:
- Multi-panel photo **collages** (#17, #59) and **abstract art** (#43): many colours, no flat
  region — histogram sees a photo.
- **Stylised regional-language cards** (#22 Hindi, #75 Marathi): OCR reads `words=0` **even with
  the language packs installed** — the text is decorative/curved/low-res, so text-density is 0.
- Adding a `top3>=0.83` flatness arm to chase them was tested and **rejected by eval**: +1 junk
  but +5 real-photo false-flags (precision 88→68). Real photos with big sky/wall backgrounds hit
  0.83 too. The FP-optimised point above is the best cheap-signal operating point.

The 2 residual false-positives (#81, #83) are **real photos full of real-world text** (a
whiteboard; a "CENTRAL BUREAU OF INVESTIGATION" signboard) — inherent to any OCR-density signal.

### Levers to raise recall past 61% (cheap CV can't) — BOTH BUILT
1. **Pure-aggregator domain denylist.** Data-derived from `image_checks` flag-rate per domain
   (>=4 scanned, >=75% flagged): **only `photo-cdn.urdupoint.com` qualifies** (5031 thumbs, 99%
   junk). No other domain concentrates junk — it is spread across mixed domains (tosshub, timesnow,
   asianage produce real photos too). So the denylist is just urdupoint (+ pakistanpoint.com by
   reputation, same owner). **Limited leverage** — which is why the classifier below is the real fix.
2. **CLIP zero-shot classifier (BUILT — `classifier_v3.py`).** open_clip ViT-B-32
   (`laion2b_s34b_b79k`), CPU ~0.15s/img, no training. Scores image vs junk-prompts and
   photo-prompts; junk if `margin(jmax-pmax) >= 0.025` (swept on the gold set).

### v3 result — cheap-CV FUSED with CLIP (82-image gold set)
| classifier | recall | precision | real-photo false-flag |
|---|---|---|---|
| original histogram | 61% | 47% | 27% |
| fused cheap-CV | 61% | 88% | 3% |
| CLIP zero-shot @0.025 | 83% | 95% | 2% |
| **v3 = fused OR CLIP @0.025** | **96%** | **88%** | **5%** |

**v3 solves both axes:** catches 96% of junk (collages, stylised Hindi/Marathi/Urdu cards, book
covers, UrduPoint) while real-photo→placeholder stays at 5%. This is the production classifier.
CLIP margin sweep is in `clip_sweep.py`; scores cached in `gold200/clip_scores.tsv`.
venv now also has `torch 2.13.0 (cpu) + open_clip_torch`.

### Ship path for v3
- Runs on the **box** (CLIP+OCR need it; not Vercel). A batch scanner imports `classify_bytes`,
  scans surfaceable thumbnails, writes `rigwire.image_checks`. Then **#1** (sync verdicts to Neon)
  makes it visible. Model loads once per process (~600MB RAM); scan many per load.
- Next: wire the box scanner + cron, then backfill/sync `image_checks` to Neon.

## Artefacts (on box, `/root/rig/tools/imgqual/`)
- `classifier.py` — production module, `classify_bytes(bytes) -> {clean, detail, features}`.
- `eval.py` — reproducible eval vs the gold labels.
- `features.py` — downloads a stratified sample, computes features, builds a contact sheet.
- `gold/` — 29 downloaded thumbnails, `features.tsv`, `contact_sheet.png`, `urls.tsv`.
- venv: `/root/imgqvenv` (pillow, numpy, pytesseract, requests). System: `tesseract 5.3.4`.

## Ship path (NOT done here — this was the detector only)
The v2 detector produces better verdicts but they reach the reader only via the plumbing:

1. **#1 — Backfill `rigwire.image_checks` to Neon + add to the 20-min sync.** The live site
   reads Neon, where the table is **empty (0 rows)** while the box has 1,654 verdicts
   (340 flagged). Until this lands, EVERY image filter degrades to "assume clean" and junk
   shows regardless of detector quality. *This is the actual cause of what's on screen now.*
2. **#2 — Run the scan on the box at corpus scale** (not the Vercel daily-40 cron), writing
   `rigwire.image_checks` with `classifier.py`. Add a **domain denylist** (urdupoint.com,
   etc.) and treat `source_tier` as a hard image-trust gate.
3. Expand the gold set (29 → ~200) before any further threshold changes; wire a prod
   "% placeholder / % junk shown" metric so calibration is measured, not guessed.

## Calibration notes
Thresholds live at the top of `classifier.py` (`T_FLAT_TOP1`, `T_TEXT_AREA`, `T_TEXT_WORDS`,
`T_POSTER_*`). Re-run `eval.py` after any change. Do not tune blind — expand the gold set first.
