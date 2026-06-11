# DB-chat task — add Commonwealth small-state news sources to the scrape (2026-06-03)

*(Copy everything below into the DB/scraper chat. It is self-contained.)*

---

## Why this task
The OSINT brief is generic per persona (principal = the user's `primary_subject`; the engines read
`public.sources` → `articles` → `entity_dictionary`/`article_entity_mentions`). A live test persona —
**"Commonwealth Secretariat" (focus = the Commonwealth small states)** — produces an **empty brief**.

Root cause, **verified against the live DB on 2026-06-03**:
- Of the **33 Commonwealth small states**, we scrape outlets from **only 1** (Maldives — 1 outlet, ~128
  articles). The other **32 have 0 outlets**; they appear only as incidental mentions inside *other*
  countries' press (Indian/UK/Australian papers), never their own.
- A vetted source catalog (below) lists **195 LIVE sources** across these 33 states. We scrape **1**.
  **→ 194 are missing.** This is a pure scrape-coverage gap, not a code bug.

## The source catalog (vetted, ready to import)
File: `D:\global_news_dataset_PERFECTED_20260527 (2).xlsx` (a global news-source catalog, ~195 country sheets).
*(If you can't reach this path, ask the OSINT chat to export the 33 small-state sheets to CSV.)*
- Sheet **`00 - MASTER INDEX`** — per-country counts: `Country, ISO_A2, ISO_A3, Continent, Total_Sites,
  Live_Sites, Dead_Sites, Geo_Blocked_Sites, Coverage_Score, Notes`.
- **One sheet per country**, named `"<ISO2> - <Country>"`. Per-source columns:
  `website_name, url, language, category, reach_tier (1=top), http_status, is_live, access_status, final_url, last_checked, notes, founded_year, source_of_discovery`.

## The ask
Ingest the **33 small-state** sources into our scrape pipeline (the `public.sources` registry + the
RSS/HTML collectors) so the corpus starts carrying these countries' *domestic* news.

| ISO2 | state | live sources | ISO2 | state | live sources |
|---|---|---|---|---|---|
| CY | Cyprus | 15 | LS | Lesotho | 5 |
| MT | Malta | 13 | NR | Nauru | 5 |
| MU | Mauritius | 11 | LC | St Lucia | 4 |
| JM | Jamaica | 10 | WS | Samoa | 4 |
| NA | Namibia | 10 | SC | Seychelles | 4 |
| ZM | Zambia | 10 | SB | Solomon Islands | 4 |
| MV | Maldives | 9 *(we have 1)* | VU | Vanuatu | 4 |
| TT | Trinidad & Tobago | 9 | BB | Barbados | 4 |
| FJ | Fiji | 8 | BW | Botswana | 4 |
| GY | Guyana | 8 | DM | Dominica | 3 |
| GA | Gabon | 7 | VC | St Vincent & Gren. | 3 |
| BS | Bahamas | 6 | TO | Tonga | 3 |
| BZ | Belize | 6 | AG | Antigua & Barbuda | 3 |
| BN | Brunei | 6 | SZ | Eswatini | 2 |
| GM | Gambia | 5 | GD | Grenada | 2 |
| KI | Kiribati | 5 | KN | St Kitts & Nevis | 2 |
| | | | TV | Tuvalu | 1 |

**Total = 195 live; we scrape 1 → add ~194.**

**THE 33 (ISO2, paste-ready — filter the workbook to these `ISO_A2`):**
`AG, BS, BB, BZ, BW, BN, CY, DM, SZ, FJ, GA, GM, GD, GY, JM, KI, LS, MV, MT, MU, NA, NR, KN, LC, VC, WS, SC, SB, TO, TT, TV, VU, ZM`

⚠ This list is the **Commonwealth Secretariat's official "small states" designation** — an **external
curated list, NOT a data-derivable cut.** Do not try to reproduce it from the data: smallest-N,
`LOW_COVERAGE_REVIEW`, and our-zero-coverage each yield a *different* set (≈100–161 countries) — none
equal these 33. Use the list above verbatim. `MV` (Maldives) is the one source we already scrape.

*(Stretch, flag only — do NOT do yet: the file covers ~195 countries total, so it's also a ready map for
broader global expansion. Small states first — that's the persona need.)*

## Requirements (quality / no-fabrication discipline)
1. **Live + reachable only.** Import rows where `access_status = 'LIVE'`. **Skip / quarantine**
   `BLOCKED_VERIFY` (HTTP 403 etc.) and dead rows — list them for manual review, do NOT register a feed
   we can't actually fetch. (`is_live=True` is NOT enough — Cyprus Times is `is_live=True` but 403-blocked.)
2. **Dedup by domain** against existing `public.sources` (the lone Maldives outlet likely already exists —
   don't double-add). Match on registrable domain of `url`/`final_url`.
3. **Tag correctly:** `source_country = ISO2`; `language` = the sheet's `language` (several are
   non-English — e.g. Cyprus carries Greek `el`); map `reach_tier` → our `source_tier`.
4. **Resolve a feed.** Sheets give the site URL, not always an RSS feed — discover the RSS/Atom feed per
   site, or route it through the HTML collector if none, following our existing collector conventions.
5. **Idempotent + non-disruptive** — don't alter existing sources/collectors; safe to re-run.

## Downstream note (set expectations)
Adding sources → articles is **necessary but not sufficient** for the brief. The brief engines key on
**resolved entities** (`entity_dictionary` + `article_entity_mentions`), not raw text. So for these
states (and their leaders) to actually surface in a brief, the **NER / entity-resolution pipeline must
pick up these countries' entities** once their articles flow. Please confirm whether that happens
automatically on ingest or needs an entity backfill — and flag it back.

## Report back
- **Added vs skipped per country** (and why skipped: blocked / dead / duplicate).
- Confirm `source_country` tagging + that the **first scrape cycle produces articles** for these ISO2s.
- Any small states where **0 sources are usable** (all blocked/dead) — so the product can mark those as
  permanent cold-start rather than waiting on data that will never come.
