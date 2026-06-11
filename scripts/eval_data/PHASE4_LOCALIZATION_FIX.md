# Newspaper localization — final fix + honest metric (authoritative)

**Date:** 2026-06-10. Supersedes the "88% anchored" claim in
`TELUGU_PHASE3_RESULTS.md` / `PHASE3_RESULTS_SUMMARY.md`, which counted
unverified geometry guesses as successes.

## The bug (found by inspecting a snapshot, not a number)

A snapshot whose metadata read "Bombay HC strikes down ₹22,000-cr spectrum levy"
actually showed a small CASE FILE infographic cell. Two paths diverge:

- **Text** (headline/body) comes from the Vision LLM reading the whole page
  (`hybrid_pipeline.py` `"text": a["body"]`). It is independent of the crop.
- **The crop box** for unmatched articles came from `_assign_layout_boxes`, a
  geometry guess. `clip_anchored=True` only meant "a box was assigned," not "the
  right box." The reported "anchored %" merged these guesses with real anchors.

## The five fixes (in order of impact)

1. **Native-resolution OCR** (`_ocr_zoom_for_page`). The Telugu PDFs embed a
   ~2300px scan inside a ~555pt page box; a fixed 220 DPI rendered only ~1700px,
   **downsampling the source ~27% before OCR**. We now render at the embedded
   image's native resolution (floor 220 DPI, cap 600). This roughly **doubled**
   the Telugu text-anchor rate (AJ 27%→54%; Sakshi text 9→11, body 1→3 on the
   same pages).
2. **Body-text probe fallback** (`locate_clip_box_by_body`). When the headline
   can't be matched (multi-column display type, heavy garbling), match the
   article's body tokens to OCR lines and bound to the **densest contiguous
   cluster** of matched lines (so it can't swallow stacked articles). Adds a
   verifiable `body` source.
3. **Headline→body gap fix** (`locate_clip_box`). A big headline carries extra
   leading before its body, so the first gap exceeded `gap_break` and the walk
   stopped at the headline — emitting a **headline-only sliver**. The first
   transition now tolerates `5×body_h`, then tightens to `2.4×body_h` between
   body lines. Turned 31pt slivers into full article crops.
4. **Layout fallback DISABLED** (`_ENABLE_LAYOUT_FALLBACK = False`). Even with a
   neighbour constraint, layout assignment mis-cropped AJ #8 onto AJ #6's region
   (a confidently-wrong snapshot). It fires for almost nothing once OCR runs at
   native resolution, so it is off: unmatched articles stay honestly unanchored.
5. **Honest split metric + guards** (`verify_hybrid_extraction.py`,
   `_apply_anchor_guards`). Reports `text` / `body` / `layout` / `none`
   separately — never merged. Stricter area floor (8000pt²), a ≥1%-of-page floor
   and min width/height for any layout box, text-anchored wins de-dup. OUTDIR is
   cleared per run (crops no longer mix across papers) and overlays render at
   2.5× so every box is eyeballable.

## Verification (live, overlays + crops visually confirmed)

3 pages each, 2026-06-10. Every emitted crop was rendered and eyeballed; AJ #11
(was a sliver) now captures headline+subhead+bullets+photo+body; the one prior
layout mis-crop is gone.

| Paper | Articles | text | body | layout | none | **Trusted** |
|---|---|---|---|---|---|---|
| Financial Express | 20 | 13 | 0 | 0 | 7 | **65%** |
| Sakshi | 18 | 11 | 1 | 0 | 6 | **67%** |
| Andhra Jyothi | 10 | 6 | 0 | 0 | 4 | **60%** |
| **Total** | **48** | **30** | **1** | **0** | **17** | **65%** |

## The honest number

**Trusted localization ≈ 65%, with ZERO wrong/unverifiable crops.** Every emitted
snapshot is content-anchored (headline or body matched to the page's own OCR).
Unmatched articles are honestly left uncropped rather than mis-cropped. The rate
varies run-to-run because Vision returns a different article set each call
(non-deterministic) — the invariant that holds across all runs is **0 wrong
crops**.

## Still open (separate from localization)

- **Telugu byline extraction = 0** (FE = 19/20). Vision isn't returning bylines
  for Telugu editions this run — a Vision-prompt issue, not localization.
- **Vision body text hallucinates** (wrong years, stale context, varying numbers
  run-to-run) — needs its own guardrail; the snapshot image is the source of truth.
- **Completeness**: some correctly-located crops capture headline + lead only
  when the body wraps across several columns; multi-column body stitching is a
  larger, separate problem.
- **Manam / Mana Telangana** Drive links dead (redirect to Financial Express).
- **Dockerfile** must bake in `tesseract-ocr tesseract-ocr-tel pytesseract
  indic-transliteration` (currently only docker-cp'd into the running container).
