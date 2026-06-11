# Curated Latin-abbreviation dictionary for posture.py — summary (2026-06-04)

**JSON deliverable:** `scratch/sq/posture_alias_dictionary_2026-06-04.json`
**Scope:** read-only curation; **no DB writes**, no AEM matview rebuild, no migration. Feeds product chat's posture.py body-presence matcher widening.

## What's in the JSON
- **40 curated entities** with safe aliases (additive) + `rejected_unsafe` array with reason per rejected candidate.
- 18 organizations (parties + institutions) + 22 individuals (national + state leaders).
- Discipline: **never bare common-noun ("Congress", "Party", "Samithi"), never bare given-name ("Ali", "Shah", "Singh", "Kumar")**. Every rejection carries a one-line reason — this is the audit trail for the alias-cleanup-v2 v2 spec.

## Validation pass — 10 sampled entities

| label    | AEM total | canonical_only | widened | added | widened% | spot-read FP |
|----------|----------:|---------------:|--------:|------:|---------:|-------------|
| **TMC**  | 4446      | 133            | 1237    | +1104 | 27.8%    | 0 in 3      |
| **BJP**  | 3291      | 1048           | 2777    | +1729 | 84.4%    | 0 in 3      |
| Modi     | 2131      | 1623           | 1948    | +325  | 91.4%    | 0 in 3      |
| **DMK**  | 733       | 192            | 641     | +449  | 87.4%    | ~1 borderline |
| **INC**  | 703       | 34             | 84      | +50   | 11.9%    | **3/3 FPs — "INC" alias REMOVED** |
| **BRS**  | 661       | 115            | 464     | +349  | 70.2%    | 0 in 3      |
| AAP      | 228       | 134            | 207     | +73   | 90.8%    | 0 in 3      |
| KCR      | 210       | 9              | 67      | +58   | 31.9%    | 0 in 3      |
| Kejriwal | 101       | 90             | 96      | +6    | 95.0%    | 1-2 borderline |
| Owaisi   | 40        | 35             | 35      | 0     | 87.5%    | n/a         |

### Threshold check (per spec)
| threshold | result |
|---|---|
| BJP widened ≥2500 | **PASS** (2777) |
| INC widened ≥100 | **FAIL** (84) — root cause is **AEM alias-overreach** ("Congress" maps to INC, so US-Congress + Indian-Inc-corp articles attribute to INC; widening can't recover these because the bodies genuinely don't mention INC). Structural fix only via alias-cleanup-v2. |
| Iran/Modi/Tesla unchanged | **PASS** (94.3% / 91.4% / 100%) |

## The "INC" alias removal (the one correction the spot-read forced)
The original curation had `"INC"` and `"I.N.C."` in the safe list. All 3 sampled posture.py-recoverable INC articles were false positives:
1. "For TP comparability, functional similarity and scale of operations were cr…" — transfer-pricing business text matching "Inc."
2. "India Inc. ramps up FY27 investments…" — "India Inc." is a journalistic term for the Indian corporate sector
3. "Diana Shipping Inc. Comments On Genco Shipping & Trading's Rejection…" — "Diana Shipping Inc." corp name

→ "INC" moved to `rejected_unsafe` with reason "matches 'Inc.' corporation suffix in business news — spot-read 3/3 FPs". This is the discipline working as intended.

## Entities the spec named that we **deliberately couldn't widen**
- Chief Minister (aem=2247) — role-title, not an entity
- DK Shivakumar (aem=735) — already merged via mig 095/096; the canonical is 'D.K. Shivakumar' which is already in curated set
- Trinamool Congress (aem=397) — duplicate of All India Trinamool Congress; should be merged in alias-cleanup-v2
- Rajya Sabha (aem=327) — institution name is uniquely matchable already; aliases like 'Upper House' borderline
- Lok Sabha (aem=305) — institution name uniquely matchable already; aliases like 'Lower House' borderline
- Piyush Goyal (aem=221) — bare 'Goyal' would match unrelated people; no safe widening beyond canonical

Plus the **6 high-volume entities** with no safe widening:

## What this lifts (estimated, conservatively)
If posture.py adopts the widened dictionary:
- **BJP retention 34% → ~84%** (1129 → 2777 / 3289) — the big unlock.
- **TMC retention** climbs proportionally (the 1104 additional catches come from "TMC" / "Trinamool" / "AITC" hits posture.py was missing).
- **BRS, DMK, AAP, AIMIM** all see similar lifts.
- **Modi/Kejriwal/Owaisi** marginal lift (their canonical already matches most of their body presence).
- **INC remains low** — the 703 AEM attributions are mostly the alias-overreach class (US-Congress / India-Inc corp news mapped onto the INC entity via the "Congress" alias in entity_dictionary). The 84-article retention IS approximately the truth for INC after honest filtering.
- **Mir Zulfeqar Ali stays near zero** — not in the curated set because his bare "Ali" alias is the AEM-overreach root cause for all 1483 attributions. Not a script-coverage problem; an alias-overreach problem.

## What's still pending (NOT solved by this widening — alias-cleanup-v2 territory)
1. **Bare common-noun aliases still live in entity_dictionary**: "Ali" (→Mir Zulfeqar), "Congress" (→INC), "Party" (→BJP), "Samithi" (→BRS), "MLA X" patterns. These pollute AEM at ingest time, so posture.py can only filter the symptom, not the cause.
2. **Posture.py matcher gets tactical lift, AEM matview gets nothing.** The matview keeps polluting at refresh. To stop the pollution at source: clean the aliases.

## Hand-off to product chat
- **JSON path:** `scratch/sq/posture_alias_dictionary_2026-06-04.json` (on `rig-surveillance` repo, not yet committed).
- **What to do:** load it on posture.py startup; widen the per-mention body-presence check to use `canonical_name + safe_aliases[]` for any entity present in the dictionary; fall back to current behavior for entities not in the dictionary (~99% of the dict).
- **Expected delta on retention:** BJP 34% → ~84%, TMC sharply up, BRS/DMK/AAP/AIMIM substantially up. **INC stays low — explain it as the documented AEM-overreach class, not a posture.py failure.**
- **What to re-run after deploying:** the same per-entity retention check on a sample of dossiers (BJP, INC, BRS, Mir Zulfeqar, T. Raja Singh + controls Iran/Modi/Tesla). If observed-vs-expected diverges, ping me.

## What's deliberately out of scope (per spec)
- No `entity_dictionary.aliases` writes — upstream cleanup is alias-cleanup-v2.
- No AEM matview rebuild.
- No migration this pass.
- No non-political entities (companies, athletes, etc.).
- No script enrichment — Read 1 disproved the hypothesis.
