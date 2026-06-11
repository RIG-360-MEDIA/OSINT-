# Conquering Telugu newspaper extraction — plan

## Where we stand (measured, Sakshi today, 3 pages)
- Language: 12/12 correctly `te`. Headlines/bodies: clean Telugu (Vision-side solved).
- Sub-headline: 4/12. Byline: 0/12 (Telugu papers rarely print Western bylines).
- **Snapshot/localization: ~25% (3/12)** ← the only real blocker. Verified: when it anchors, the crop is the correct article. So this is a RECALL problem, not a correctness problem.
- Available te sources: Sakshi, Andhra Jyothi, Manam, Mana Telangana. No live PDF today: Eenadu, Namaste Telangana (source-adapter issue).

## Root cause
Localization works by matching the Vision headline text to PaddleOCR line text to get pixel boxes. For Telugu, Vision and PaddleOCR each garble the same stylised banner headline *differently*, so text overlap is low → no anchor → no crop. Body Telugu OCRs okay; large display headlines OCR poorly. **The OCR-text bridge is the bottleneck.**

## Plan (in priority order)

### Phase 1 — Cheap recall wins (hours) — target 25% → ~50%
1. **Raise OCR render DPI** for the line pass (150 → ~220) in `hybrid_pipeline.py`/`ocr.py`. Higher resolution markedly improves Telugu rec on banner type. Cost: slower OCR.
2. **Transliteration-normalised matching** in `clip_locator.py`: romanise both Telugu strings (indic→Latin, e.g. `indic-transliteration`/`aksharamukha`) and compare — far more robust to script-level OCR noise than raw trigrams.
3. **Third anchor = first body sentence** (already do headline + subhead) — body OCRs better than headlines, so it anchors when the headline fails.
4. **Lower fuzzy threshold** 0.30 → ~0.22, but ONLY paired with the mis-anchor guard (Phase 4 #1) so recall rises without wrong crops.
→ Re-screen all 4 live te papers, measure.

### Phase 2 — Robust localization (1–2 days) — target ~50% → ~85%
**Use PP-Structure layout regions as a SPATIAL anchor (language-agnostic).** The layout model is visual — it finds article/title/text region boxes on a Telugu page regardless of script. Plan:
- Run PP-Structure layout (en model, visual only) to get candidate region boxes.
- Match Vision articles to regions by **reading order + position** (top-to-bottom, column-aware), NOT by OCR text.
- This sidesteps noisy OCR-text matching entirely — the real ceiling-breaker.

### Phase 3 — Best-in-class Telugu OCR (optional, if Phase 1–2 short of target)
Swap the anchor-text OCR for a stronger Telugu engine: Tesseract `tel`, Google Cloud Vision, or Bhashini/Indic OCR. Use only for the headline-anchor text; keep Vision for content.

### Phase 4 — Quality parity + guards (shared with English)
1. **Mis-anchor guard**: reject sliver crops (size floor) and dedupe nested/overlapping boxes (IoU/containment) — lets us loosen matching safely.
2. **Telugu sub-headline** prompt tuning (Vision) to lift 4/12.
3. **Cross-article body-bleed guard** (the audit's #1 risk) — applies to Telugu too.
4. **Source fix**: Eenadu/Namaste Telangana CareersWave adapter (no Drive link today).

## Validation / definition of "conquered"
On Sakshi + Andhra Jyothi + Manam + Mana Telangana:
- ≥80% articles with a tight, correct single-article snapshot
- <5% mis-anchor (verified by bbox-overlap + visual spot-check)
- sub-headline ≥60% where printed; bodies clean; lang 100% `te`
- bleed guard active

## Recommended first move
Phase 1 (#1 DPI + #2 transliteration match) is the highest value-per-hour. I can implement + re-screen the 4 live te papers in one pass and report the new anchored%.
