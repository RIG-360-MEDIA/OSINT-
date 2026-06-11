# English newspaper extraction — quality audit (hybrid extractor)

Date: 2026-06-09. Live editions, 4 pages each. 12-agent adversarial workflow,
60 confirmed per-article defects. Verified against `scripts/eval_data/eval_*.json`.

## Overall: 5.5/10 — ship for BULK INGESTION with guardrails; NOT for per-article display or author attribution yet.

## Snapshot-anchoring (localization) by paper
| Paper | Articles | Anchored | Notes |
|---|---|---|---|
| Mint | 14 | 93% | cleanest; crops visually correct |
| Deccan Chronicle | 46 | 89% | but 9/41 crops <8KB; nested/sliver anchors |
| Times of India | 31 | 84% | 16% unanchored; 2 shared-banner mis-anchors |
| Financial Express | 12 | 75% | crops visually correct |
| The Hindu | 23 | 0% | Google-translated **Hindi** PDF mis-tagged en |
| Clean total | 103 | 86% | ~4% mis-anchor pairs |

## Per-field grades (adversarially verified)
- **Headline — mostly-clean.** 3 real defects, all DC, all co-located with geometry breaks (i=20 two headlines merged; i=27 OCR no→to; i=33 photo caption promoted). All-caps/coined opinion titles correctly NOT flagged.
- **Sub-headline — noisy.** Systematic byline→subheadline swap on a DC page-2 block (i=13,14,16-20 hold credit strings, ~15% of DC). TOI non-decks (ALL-CAPS labels).
- **Byline — BROKEN (worst field).** Credit stranded in subheadline (DC); body text leaking into byline (TOI i=13/14); OCR-garbled agency tags (TOI i=10 "Tatws News Network"); name+email+dateline fusion (Mint i=7). Needs a dedicated normalizer.
- **Body — noisy, with one high-severity mode: cross-article CONTENT BLEED.** Mint i=8 injects SEBI/securities text into a TB-vaccine story; TOI i=18/i=24 swap verbatim aviation/oil boilerplate. Plus truncation/OCR noise, paragraph flattening, DC lang=te mis-tag on English bodies i=22-31.
- **Localization — noisy, worst on DC.** Sliver crops (i=15 3.3KB ~106×18px), nested anchors (i⊂j), shared-banner mis-anchors (TOI i16/i19 ~99.8% IoU on one 0.5MB crop).

## Biggest risk
Silent **cross-article body bleed** — fluent, plausible text landing in the field that feeds entity/stance/clustering/RAG. No surface signal; fabricates entity-event associations. Corrupts meaning, not just presentation.

## Fix priority
1. Cross-article bleed detector (adjacent-body n-gram overlap + entity/section incongruity) → quarantine/re-extract.
2. Byline normalizer (strip BY/email/dateline, OCR-correct agencies, recover credit from subheadline).
3. Treat subheadline as untrusted until (2).
4. Crop-size floor + containment check; treat shared-banner pairs as unanchored.
5. Fix lang tags (DC i=22-31 te→en; The Hindu en→hi) + run Devanagari OCR for non-Latin pages.

Paper-dependence: **Mint closest to display-ready → TOI middling → DC needs the most remediation.** Gate per-paper if phasing.
