# Client API — Build Spec (mapped to the shared API-doc sections)

Grounded in a code audit (July 2026). Tags: **[HAVE]** works today · **[PARTIAL]** exists, needs finishing · **[BUILD]** net-new.

**Base already in place** — `products/osint/backend/v1/` is the white-label surface:
per-partner keys (`rig_live_*` / `rig_test_*`, HMAC-hashed, shown once), `{data, meta}` +
`next_cursor` envelope, cursor pagination, per-org scope table (`analytics.org_api_scope`),
signed webhooks (`whsec_`, HMAC), per-org rate-limit + monthly quota, sandbox flag, tenant
isolation (IDOR-guarded). Today it exposes `articles` + `webhooks`; the rest is wiring.

---

## FOUNDATIONS (cross-cutting — do first)
- **[BUILD] `articles.api_ready_at`** — stamped only when enrichment (sentiment+entities+districts) is complete. Partner sees only ready rows; **cursor sorts by this**.
- **[BUILD] Bump-on-change** — trigger/step re-stamps `api_ready_at` (article) and `last_updated_at` (story) on any re-tag / backfill / correction. Fixes the sync cursor.
- **[BUILD] Tombstones** — soft-delete `deleted_at`; pull returns `{id, deleted:true}` so partner drops its copy.
- **[HAVE] Per-org scope + keys + isolation** — `org_api_scope`, `api_keys`.

## §1 — OUTPUTS
- **[HAVE] Top news** — `articles` (id, title, source, published_at, url, `full_text_scraped`, `language_iso`); client-settable count = query param. *Caveat: ~10% full-text NULL.*
- **[HAVE] Sentiment (per-article, directed, intensity)** — `article_stances` (stance + 0–1 intensity toward target entity).
- **[PARTIAL→BUILD] Sentiment aggregates + net_lean + daily trend** — trend = `entity_mention_daily`; expose supportive/neutral/critical + net_lean rollup (count cols in 001/007 + CM view 028).
- **[BUILD-endpoint] Source breakdown** — per-outlet volume + net-lean. Logic exists in `observe_panels.source_scorecard` → port to v1.
- **[HAVE] Entity tracking** — `entity_dictionary` + `article_entity_mentions`; per-entity sentiment = aggregate `article_stances`.
- **[HAVE, regionally scoped] Geography {state, district} + counts** — `article_districts` (gazetteer-tagged) + `districts` (`state_code`); powers the map. **Scope = Telangana v1 + AP; new state = seed gazetteer + local sources.** *Accuracy ~50–80% by language/source depth.*
- **[HAVE] Grouped stories + timeline** — `story_clusters_v8` (`member_count`, `source_count`, `last_updated_at`); timeline = order members by date. *Same-event ~76% precision / ~80% hub-purity on the confident tier; self-heals nightly. Expose confident tier only (≥3 sources).*
- **[HAVE] Mention trend (daily, week/month)** — `entity_mention_daily`.
- **[PARTIAL] Summary** — `briefs` (digest) + `narrative_drafts` (story summary); wire story summary onto the exposed cluster.
- **[HAVE] Fast-follow: quotes / claims / facts** — `article_quotes`, `article_claims`, `story_facts_v8` (single-source flag). Related-players = co-mention aggregate **[BUILD-small]**.
- **[HAVE] Stable IDs + published_at** — UUIDs. **`updated_at` → see Foundations.**
- **[BUILD / DEFER] Credibility / suspicion flag** — genuinely absent (`cm_stance` = political lean only). Net-new model or explicit fast-follow.
- **[HAVE-infra / BUILD-triggers] Webhooks** — CRUD+HMAC exist; build event detectors (below).

## §2 — WHAT WE RECORD PER CLIENT
- **[HAVE] Scope** — `org_api_scope`: entities, topics, regions, languages, all_entities.
- **[BUILD] Add fields** — mute terms, sector, per-keyword priority, alert rules, delivery prefs.
- **[PARTIAL] Programmatic provisioning** — webhook CRUD is partner-facing; **add a partner scope-write endpoint** (keys/scope still team-issued at onboarding by default).

## §3 — HISTORY
- **[PARTIAL] 30-day backfill on new keyword** — register endpoint + nightly backfill exist; **confirm/guarantee 30-day reach** on keyword registration. Old items newly-in-scope surface via the tag-timestamp cursor.

## §4 — PULL CADENCE / FRESHNESS / TZ
- **[HAVE] Freshness** — 15–30 min pillars; all timestamps `TIMESTAMPTZ` (UTC).
- **[HAVE] Cursor pull** — v1 cursor. **[BUILD] emit `X-RateLimit-*` headers** (429+Retry-After exists).

## §5 — KEYWORD FLEXIBILITY
- **[HAVE] Grouping** — entity variants (`entity_dictionary.entity_variants`); disambiguation via scope entity IDs. Keep-history-on-remove = data persists.
- **[BUILD] Priority + mute terms** — fields on scope (see §2).

## §6 — COVERAGE + LANGUAGE
- **[HAVE] Region default + global option** — `org_api_scope.regions`.
- **[PARTIAL] Original + English + lang tag** — `language_iso` + `english_translation` (substrate pass, LLM, length-capped ~1.5–8k chars). *Finish: guarantee coverage; note it's a faithful gist, not verbatim full body.*

## §7 — DELIVERY + ORDERING
- **[HAVE] JSON, OpenAPI, `{data, meta}`, sort=recent/relevant, authority (`source_tier`)**.
- **[PARTIAL] Per-item relevance signal** — `articles.relevance_score` column exists but is per-user; **define + expose an org-scoped relevance** for partners.
- **[PROCESS] Breaking-change notice + versioning discipline.**

## §8 — PRACTICAL
- **[HAVE] Sandbox** — `is_sandbox` + `rig_test_` keys.
- **[BUILD] Purge endpoint** — confirmed deletion of an org's data on offboarding.
- **[POLICY] Retention ~90d, data residency (Hetzner-DE vs India govt), content licensing** — contract.

## WEBHOOKS (§11)
- **[HAVE] Signed delivery** — HMAC (`whsec_`), CRUD, filters, `last_delivered_at`.
- **[BUILD] Event detectors** — (a) volume **spike**, (b) new **critical-sentiment** item, (c) new **high-priority story** — fire within org scope → POST full signed payload.

---

## PHASING
- **Phase 1 (makes their sync work) ~1 wk:** api_ready_at + bump + tombstones + scoped `/articles` cursor + X-RateLimit + purge.
- **Phase 2 (the live feel) ~1–2 wk:** `/stories`, `/trends`, `/sources`, `/geo`, `/entities`, summaries (port observe/brief/map); mute+priority+scope-write; 30-day backfill guarantee.
- **Phase 3:** webhook detectors; finish translation coverage.
- **Fast-follow / net-new:** credibility flag.

**Two genuine builds, everything else is wiring + a ready-stamp.** Credibility is the only item with no existing basis; translation, districts, stories, trends, source-breakdown, quotes/facts all exist and mainly need exposing through the v1 envelope.
