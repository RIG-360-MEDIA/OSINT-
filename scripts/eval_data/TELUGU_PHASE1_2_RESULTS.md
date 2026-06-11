# Telugu extraction — Phase 1 + 2 results

Live editions, 3 pages each, 2026-06-09.

## Anchored-snapshot rate: 25% → ~69% aggregate

| Paper | Articles | Anchored | by text | by layout |
|---|---|---|---|---|
| Andhra Jyothi | 6 | 5 (83%) | 2 | 3 |
| Manam | 19 | 14 (73%) | 1 | 13 |
| Mana Telangana | 29 | 20 (68%) | 2 | 18 |
| Sakshi | 10 | 5 (50%) | 2 | 3 |
| **Total** | **64** | **44 (69%)** | **7** | **37** |

Baseline (Sakshi, pre-phase): 3/12 = 25%. Language: 100% `te` across all papers.

## What changed
**Phase 1 (`clip_locator.py`):** edit-distance similarity added alongside trigram
Jaccard (`_fuzzy = max(...)`), coverage gate now passes on the best single matched
line (not the diluted cluster), threshold 0.38. OCR render raised 150→220 DPI
(`hybrid_pipeline.py`) so stylised Telugu banners recognise better.

**Phase 2 (`hybrid_pipeline.py`):** PP-Structure layout was useless on newspapers
(~1 region / 0 article-boxes — its model is academic-paper-trained). Replaced with
`_blocks_from_lines`: article-region boxes derived from OCR **line geometry** (a
markedly-larger-than-body line = headline; walk its column down). Furniture filter
excludes logo/masthead-scale fonts and full-width banner blocks. Unanchored Vision
articles are assigned a block by reading order. Mis-anchor guard rejects sliver
crops and de-duplicates nested/overlapping boxes.

**Layout blocks do the heavy lifting** (37 of 44 anchors) — Telugu headline *text*
still OCRs too noisily to anchor by text (only 7 text anchors). Geometry is the win.

## Verified correct
Pulled crops visually: after the furniture filter, layout crops are real article
headers (e.g. the "మేం రైతులం కాదా?" farmers story), masthead/nameplate no longer
mis-anchored.

## Honest remaining gaps (to reach English-level ~85%)
1. ~31% still unanchored.
2. Layout crops are often **tight** (headline + strap; body not always fully
   captured) — block downward-walk needs body-extension tuning.
3. Reading-order block→article assignment can mis-pair when block count ≠ Vision
   article count; furniture filter reduced this but residual risk remains.
4. Sub-headline capture low (1–5/paper) — Vision prompt tuning for Telugu decks.
5. Vision article count varies run-to-run (non-deterministic), so % is noisy ±10pts.

## To finish the job (Phase 3+)
- Stronger Telugu OCR (Tesseract `tel` / Google Vision / Bhashini) → more reliable
  *text* anchors and better block→article pairing.
- Interpolate block assignment between text-anchored articles instead of blind
  reading-order zip.
- Body-extension on layout blocks for fuller crops.

## State
Changes are local + uncommitted (branch `feat/directional-sentiment-relevance-geo`),
`docker cp`'d into `rig-backend` for verification only (revert on restart). Live
deployed task untouched.
