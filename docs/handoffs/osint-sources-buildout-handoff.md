# Free OSINT Sources Buildout — Full Handoff (start-of-chat context)

**Written 2026-07-07.** Hand this + the kickoff prompt to a new chat so it picks up
with full context. Read top-to-bottom first. Sibling doc (already done, for reference):
`docs/handoffs/keyword-social-rebuild-handoff.md` (social collection).

---

## 0. One-paragraph situation

RIG Surveillance is a keyword/entity OSINT platform. **Social media keyword collection
is now built + proven** (Reddit, TikTok, YouTube, Twitter, Instagram, WeChat, Telegram,
VK — see the sibling handoff). This next phase adds the **free, high-leverage
NON-social OSINT sources**, keyword/entity-driven, same discipline: real verified output,
not thin metadata. **Critical honesty note:** thin collector stubs for MOST of these
ALREADY EXIST in `products/osint/backend/` — they return shallow one-liners and were only
ever tested on "Modi". The job is NOT to build from zero; it is to **verify each against
the live source, upgrade thin→useful, make them keyword/entity-driven, and PROVE each on
two real inputs.** Do not trust the existing code works — test it.

## 1. Hard rules (do not violate)

- **VERIFY against the live source/DB — never trust docs, schema files, or existing code
  comments.** This whole rebuild exists because a past session trusted a checklist. Run
  the call. Read the actual file. Test a real input.
- **No fabrication.** Never claim "works" without proof. Report trusted / unverified /
  failed separately. Paste real output.
- **Prove each source on TWO inputs** — one common/expected AND one fresh/niche picked at
  test time. The "Modi-only" test is what caused the last collapse.
- **Free / no-key only this phase.** If a source needs a paid key, flag it and skip —
  don't half-build it. Secrets via env vars only, never hardcoded.
- **These are read-only lookups** (external public APIs) — none touch `rig-backend` core
  ingest, so blast radius is low. They live in `osint-backend`
  (`products/osint/backend/`, `analytics_user` role, httpx/curl_cffi only).
- **Off-limits:** people-search brokers, breach dumps, dark-web, private personal data.

## 2. What already exists (verify before building — thin stubs, tested only on Modi)

All in `products/osint/backend/`, wired into `routers/keywords.py` as `/api/keywords/*`:

| Source | File | Free API | Current state (VERIFY) |
|---|---|---|---|
| **Company / ownership** | `company_collector.py` | GLEIF (LEI registry) | returns LEI count + top match; verify real, add officers/jurisdiction/status |
| **Infrastructure** | `infra_collector.py` | RDAP + DNS-over-HTTPS | registration + live DNS; verify, add subdomains/ASN/passive-DNS if free |
| **Web history** | `archive_collector.py` | Wayback Machine | first-seen + snapshot count; verify + surface useful snapshots |
| **Academic / patents** | `academic_collector.py` | OpenAlex | papers/authors/institutions; verify real, keyword-driven |
| **Econ / trade stats** | `stats_collector.py` | World Bank | GDP/pop/growth by country ISO2; verify |
| **Geolocation** | `geo_collector.py` | OSM Nominatim | place → lat/lon; needs User-Agent header |
| **Encyclopedic** | `wiki_collector.py` | Wikipedia/Wikidata | one-line + QID; verify |
| **Worldwide news** | `gdelt_collector.py` | GDELT DOC 2.0 | KNOWN-SLOW: 2 sequential calls + 5.5s sleep + 12s timeouts → often times out / "no global coverage" even for Modi. Needs a rework (parallelize, cache, better fail handling) — the worst offender. |

**Not yet built (free, worth adding this phase):**
- **Web search / discovery** — SearXNG is ALREADY in the stack (`rig-searxng:8080`,
  multi-engine meta-search, no key). Build a collector that queries it for a keyword →
  ranked results + source discovery + dork support (`site:`, `filetype:`). Reuse the
  SearXNG pattern already used elsewhere (e.g. Instagram discovery in prior work).

## 3. Architecture you must know

- **osint-backend** = `products/osint/backend/` — separate baked FastAPI image, DB role
  `analytics_user` (read-only public.*, RW analytics.*), httpx/curl_cffi. All these
  collectors live here and are surfaced via `routers/keywords.py` → `/api/keywords/{name}`.
- **SearXNG** = `rig-searxng` container, reachable on the internal Docker network at
  `http://rig-searxng:8080` (no key). From osint-backend, call it directly.
- **Hetzner:** `ssh -i ~/.ssh/rig_hetzner root@178.105.63.154`; osint-backend container is
  baked (not bind-mounted like rig-backend) — code changes need a rebuild OR hot-patch +
  bake. Confirm the deploy path before assuming hot-reload. curl_cffi 0.15.0 + Py3.11.
- **Tasking brain** (`products/osint/backend/tasking_brain.py`): classifies a keyword
  (person/org/location/topic) → picks which sources are relevant. Each source here should
  slot into that plan so a keyword auto-routes to the right lookups (person→wiki+academic,
  org→company+infra, location→geo+stats, domain→infra+archive).

## 4. The plan (this phase)

**Phase 1 — verify + upgrade each free source, prove standalone.** For each source above:
(a) call the live API from the box, (b) fix/upgrade thin output to genuinely useful fields,
(c) make it keyword/entity-driven and slot into the tasking-brain source plan, (d) handle
errors/timeouts honestly (especially GDELT). **Deliverable = one verifier**
`verify_osint_sources.py` that takes a keyword/entity (and where needed a domain/country/
ISO2) and prints per source: API used, ok/fail, and 2-3 real result fields. Run on dev AND
Hetzner. **Proof bar:** ≥2 inputs (common + niche); each source returns REAL data OR an
honest labeled limitation (e.g. "World Bank needs a country code", "GDELT slow"). Nothing
silently empty = "done". **GDELT gets a real fix**, not a shrug.

**Priority order (value × cheapness):** SearXNG web-search (new, high value, in-stack) →
Company/GLEIF → Infrastructure → Wayback → Academic/OpenAlex → World Bank stats → fix
GDELT last. Wiki/Geo are already ok — just verify.

**Deferred (later, not this phase):** merging these into the dossier UI + evidence-linking
+ the cross-source fusion (e.g. Social×Infra bot-network unmasking). Depth layer comes
after collection is proven — same discipline as social.

## 5. Definition of done

`verify_osint_sources.py` run on the box, on 2 inputs, output pasted back, each source
returning real data or an honest labeled limit. GDELT no longer times out on a common
keyword. No source silently empty. THEN move to fusion/UI.

## 6. Memory + context to read first

- `docs/handoffs/keyword-social-rebuild-handoff.md` — the social sibling (same discipline).
- Memory dir `~/.claude/projects/C--Users-Dell-Desktop-rig-surveillance/memory/`:
  `project_social_keyword_driven.md` (the keyword-driven HARD rule),
  `feedback_no_fabricated_results.md`, `MEMORY.md` (index).
- `products/osint/backend/routers/keywords.py` — where all these endpoints register.
- `products/osint/backend/tasking_brain.py` — the classify→source-plan router.
- CLAUDE.md (repo root) — deployment topology, foot-guns.
