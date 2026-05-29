# Entity Dictionary Seeds — by country

Hand-curated entity lists, one YAML file per country. Loaded into
`entity_dictionary` via `load_seeds.py`. Idempotent — re-run anytime,
duplicates by `(canonical_name, entity_type, country)` are skipped.

## Why this exists

The substrate-extracted entity_dictionary is **biased toward Indian
electoral politics** (state-level personalities, Lok Sabha
constituencies, regional party leaders). Most non-Indian articles end
up with `subject_entity_id = NULL` because the dictionary doesn't have
matching entries.

These seed files give us a **dense baseline of the world's most-cited
entities per country**, so the trigram backfill
(`scripts/maintenance/backfill_entity_fks.py`) can link claims, quotes,
and stances about non-Indian topics.

## File layout

```
scripts/entity_seeds/
├── README.md             — this file
├── load_seeds.py         — YAML → entity_dictionary loader
└── by_country/
    ├── _TEMPLATE.yaml    — copy this to start a new country
    ├── US.yaml           — United States
    ├── GB.yaml           — United Kingdom
    ├── CN.yaml           — China
    ├── RU.yaml           — Russia
    ├── ...
```

## YAML format

```yaml
country: US                    # ISO 3166-1 alpha-2
version: v1                    # bump when you do a major revision
notes: |
  Free-text notes (sources used, gaps, etc.)

persons:
  - name: "Donald Trump"
    aliases: ["Trump", "Donald J. Trump", "DJT"]
    role: "President"          # optional, free-text
    party: "Republican"         # optional
    notes: "47th US President"  # optional, free-text

organizations:
  - name: "Federal Bureau of Investigation"
    aliases: ["FBI"]
    notes: "Federal law enforcement"

constituencies:
  - name: "California"
    aliases: ["CA"]
    notes: "US state / 2 Senate seats"

locations:
  - name: "Washington, D.C."
    aliases: ["DC", "Washington"]
    notes: "Federal capital"

roles:
  - name: "Secretary of State"
    aliases: []
    notes: "Cabinet-level"
```

All five sections are optional; you can have just `persons` or just
`locations`.

## How to add a country

1. Copy `by_country/_TEMPLATE.yaml` to `by_country/<ISO>.yaml`
2. Fill in entries (start with top 50-100 per section, expand later)
3. Run loader: `python load_seeds.py --dsn $PG_DSN by_country/<ISO>.yaml`
4. Re-run backfill: `python ../maintenance/backfill_entity_fks.py --dsn $PG_DSN`

## What "dense enough" looks like

Per country, aim for at minimum:

| Section | Initial floor | Stretch |
|---|---|---|
| persons | 50 | 500+ |
| organizations | 30 | 200+ |
| constituencies | 0 (most countries don't need) | varies |
| locations | 50 (top cities + states) | 500+ |
| roles | 10 (titles likely cited) | 30 |

US/UK/CN/RU/IN should each reach 500+ total entries over time.
Smaller countries 100-200 is fine.

## Sources to mine

- **Wikidata SPARQL** — bulk export persons by country+role, orgs, places
- **Wikipedia "List of …" pages** — political officeholders, top companies
- **Government org charts** — official titles, agency names
- **GeoNames** — populated places ≥10k pop per country
- **News-source country list** — sources we already collect (see
  `sources.country` after migration 075)

## Provenance

Every seeded row is tagged in `entity_dictionary.source` as
`seed:<country>_v<N>` (e.g. `seed:us_v1`). This lets you:

- Re-load a country (loader UPDATEs rows where source matches)
- Audit "where did this entity come from?"
- Delete a seed cleanly: `DELETE FROM entity_dictionary WHERE source = 'seed:us_v1';`
