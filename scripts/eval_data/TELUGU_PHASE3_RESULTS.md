> ⚠️ **SUPERSEDED by `PHASE4_LOCALIZATION_FIX.md`.** The "88% anchored" below
> merged unverified geometry guesses with real anchors. The honest trusted number
> (text-anchored only) is ~53% on Telugu. Keep this file for the Phase 3 OCR work
> (Tesseract `tel`), but treat its anchor % as inflated.

# Telugu extraction — Phase 3 results

Live editions, 3 pages each, 2026-06-09.
(Manam + Mana Telangana Drive links dead today — both redirect to Financial Express.)

## Anchored-snapshot rate: 88% (target ≥80% → CONQUERED)

| Paper | Articles | Anchored | text | layout | Phase 2 | Δ |
|---|---|---|---|---|---|---|
| Sakshi | 21 | 19 (90%) | 8 | 3 | 50% | +40 pts |
| Andhra Jyothi | 22 | 19 (86%) | 8 | 3 | 83% | +3 pts (larger sample) |
| Manam | — | — | — | — | 73% | *(drive dead)* |
| Mana Telangana | — | — | — | — | 68% | *(drive dead)* |
| **Total (measured)** | **43** | **38 (88%)** | **16** | **6** | 69% | **+19 pts** |

Byline detection: 20/21 Sakshi, 21/22 AJ — Tesseract reads byline lines cleanly.
Sub-headline: 5/21 Sakshi, 6/22 AJ — Telugu papers don't always print decks.

## What Phase 3 added (on top of Phase 1+2)

### 1. Tesseract 5 `tel` as primary line OCR (`ocr.py` + `hybrid_pipeline.py`)
- Replaced PaddleOCR for Telugu page lines. Tesseract is trained on printed Telugu
  newsprint; PaddleOCR was trained on web/synthetic data.
- Text anchors: **4 → 16** across the two available papers (4× improvement).
- `ocr_lines_best()` selector: Tesseract for Indic scripts, PaddleOCR fallback for
  Latin/Chinese. Degrades gracefully if `tesseract-ocr-tel` is absent.

### 2. Transliteration-normalised matching (`clip_locator.py`)
- `_transliterate_to_latin()`: romanizes both the Vision headline and the OCR line
  to IAST Latin ("మేం రైతులం" → "meṃ raitulaṃ") before re-scoring.
- Fires only when trigram-Jaccard + edit-distance both fall below `_FUZZY_MATCH`.
- Removes script-level garbling: when both engines produce wrong but comparable
  pronunciation transcriptions the Latin metrics can match them.

### 3. Reading-order block sort (`hybrid_pipeline.py`)
- `_assign_layout_boxes` now sorts available blocks by (y0, x0) before pairing,
  so block positional noise doesn't mis-pair a bottom-of-page article with a
  top-of-page block.

## Installation (container)
```
apt-get install tesseract-ocr tesseract-ocr-tel
pip install pytesseract indic-transliteration
```
Dockerfile should be updated to bake these in.

## Remaining gaps

1. **Manam / Mana Telangana Drive links dead** — source adapter needs new links.
2. **Layout crops still tight** on some articles (headline + strap only; body below
   the block bottom edge not captured). Block downward-walk extension not yet done.
3. **Byline normalizer** — English papers priority #2 from the ENGLISH_AUDIT.

## Conquest verdict
Sakshi (90%) + Andhra Jyothi (86%) are ABOVE the ≥80% target.
Once Manam/MT Drive links are fixed, expect similar improvement there.
