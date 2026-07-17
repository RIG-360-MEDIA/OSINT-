# VeriDeck / DIPR — Requirements → Validation Matrix

Every element of their 2026-07-17 scope doc, mapped to what the system actually
does. Status legend:
**✅ verified live** · **⚠️ works with a caveat** · **🔴 does not work as they expect**
· **❓ UNVERIFIED — must check before Monday**

All findings measured this session (2026-07-17) unless noted.

---

## A. Their explicit ask ("what would help most tonight") — the naming

| # | Requirement | Status | Detail / action |
|---|---|---|---|
| A1 | 19 entities resolve | ✅ | All 19 resolve vs their exact strings. Verified live. |
| A2 | Titles absorbed (`Chief Minister A. Revanth Reddy`) | ✅ | Aliases added → resolves to Revanth Reddy. |
| A3 | Initials (`T. Harish Rao`, `N. Ramchander Rao`, `G. Kishan Reddy`) | ✅ | Already worked / alias present. |
| A4 | Dash forms (`– Telangana` and `- Telangana`) | ✅ | Both shapes aliased for INC + BJP. |
| A5 | Comma form (`Department of Information and Public Relations, Telangana`) | ✅ | Aliased (their doc used comma; parenthesised canonical). |
| A6 | 5 net-new entities added + retro-tagged | ✅ | Added: Council of Ministers, DIPR, Telangana Jagruthi, Telangana Rajyadhikara Party, Teenmaar Mallanna. Retro-tag is automatic (matview). |

**Answer to send:** *send the list exactly as written — nothing to reformat.*

---

## B. Coverage quality of the 19 (what history they actually get)

| # | Requirement | Status | Detail / action |
|---|---|---|---|
| B1 | Major entities carry deep history | ✅ | Extraction→tag capture ~90% (GHMC 416/467; Kaleshwaram 402). CM/KCR/KTR/Owaisi/Kavitha/parties are high-volume. |
| B2 | Retro-tagging across the archive | ✅ | Proven: entities added 2026-06-03 carry articles back to 2026-04-22. Automatic on matview refresh. |
| B3 | Teenmaar Mallanna, Telangana Jagruthi read thin | ⚠️ | Genuinely low press volume (Mallanna 0 under full name, 36 as "Mallanna"; Jagruthi 8/12). Real, not a bug. Optional: add *carefully chosen* short-form aliases (ambiguity risk — "Mallanna" matches other Mallannas). |
| B4 | "Government of Telangana = primary entity, all directed sentiment relative to it" | ❓ | Entity resolves ✅. But **directed sentiment TOWARD it is unverified**. `sentiment_split` joins on `actor_entity_id`, and only ~45% of stance rows carry it. MUST verify Government of Telangana has real directed-sentiment coverage — this is their stated core measurement. |

---

## C. The other scope fields — most do NOT filter the way they assume

| # | Field | Status | Detail / action |
|---|---|---|---|
| C1 | `mute_terms` (film/song/cricket/US-Telangana…) | ✅ | One of only two fields that filter `/v1/articles`. Their mute list works. |
| C2 | `keywords` (~50) | 🔴 | Do NOT filter the feed. Even if wired, their list matches ~135k articles/90d = flood. **Reclassify (§E).** |
| C3 | `languages` (Telugu/English/Urdu/Hindi) | 🔴 | INERT everywhere — never passed to any query. Their explicit Urdu setting has no filtering effect. |
| C4 | Urdu coverage (their real intent behind C3) | ❓ | The need is legit (Hyderabad Urdu press). MUST verify we actually **collect Urdu sources** — if we do, they get it regardless of the field; if not, that's a real gap. |
| C5 | `regions` (Telangana; Hyderabad; 33 districts; India-when-central) | ⚠️ | INERT for `/v1/articles`; WORKS for brief / cuttings / geo. The `India (only where…central)` line is prose in a filter field — does nothing. |
| C6 | `topics` | 🔴 | INERT everywhere (relevant once generic keywords route here — §E). |

---

## D. The alerting layer — HIGHEST RISK, and it's their real value

DIPR is a government press office. Their core need is *"tell me the moment something
bad breaks."* That is the keyword-priority + critical-alert-webhook layer. It is
almost entirely **unverified end-to-end.**

| # | Requirement | Status | Detail / action |
|---|---|---|---|
| D1 | Webhook create/delete | ✅ | Tested clean in sandbox. |
| D2 | `keyword_priorities` (weighted 1–10) actually used | ❓ | Unknown whether the v1 API consumes these anywhere. MUST trace. |
| D3 | Critical-alert **rules fire a webhook** on a qualifying event (violence, communal tension, corruption, ED/CBI action, welfare failure, false claim naming CM) | ❓ **TOP RISK** | Webhook *delivery* exists; **rule evaluation firing is unverified.** Our own notes: internal `keyword_watch`/`keyword_alerts` are empty; harmful-actor detection is scaffolded, not a firing rule. If this doesn't fire, DIPR gets silence on exactly the events they care about. **Verify end-to-end before Monday.** |
| D4 | "Trigger on critical tone or rapid multi-outlet pickup" | ❓ | Depends on D3 + a spike/tone signal. Unverified. |

---

## E. The keyword strategy — route by term type (supersedes the raw keyword filter)

Their ~50 keywords are two different things. Measured this session.

| Group | Terms | Right mechanism | Status |
|---|---|---|---|
| **A — proper nouns** | Rythu Bharosa (197), Praja Palana (75), Medigadda (130), HYDRAA (261), Gruha Jyothi (29), Regional Ring Road (56), Kaleshwaram✓, GHMC✓, Abhaya Hastham, Mahalakshmi, Cheyutha, Indiramma Indlu, Six Guarantees, Annaram, Sundilla, Musi rejuvenation, Future City, Metro expansion… (~20) | **ENTITIES** — proven ~90% capture, carry history + analytics | ACTION: add as entities (this weekend) |
| **B — generic topics** | education, floods, investments, public health, irrigation, law & order, power supply, cybercrime, drought, heatwave, farm loan waiver, ration cards, caste survey, BC reservation… (~25) | **TOPIC / ALERT layer, region-scoped** — NOT entities, NOT raw keywords (they flood) | ACTION: route to §D; map onto their priority/alert rules |

**Decision: do NOT deploy the raw keyword UNION filter (commit `86ffa76`).** Once
Group A are entities and Group B are topics/alerts, nothing is left for a raw
keyword field to do. Keep the commit only for its latent-500 fix.

---

## F. Delivery mechanics

| # | Requirement | Status | Detail / action |
|---|---|---|---|
| F1 | Bulk-mirror articles / stories / cuttings | ✅ | All 200. |
| F2 | Daily brief pull 05:03 IST (hard dependency) | ⚠️ | Endpoints 200. But ❓ verify brief CONTENT reflects the new 19 entities + their regions. |
| F3 | Summary length 400 → 2000 (affects their mirror) | ⚠️ | Shipped. They must check fixed-width columns. In the email. |
| F4 | Rate limit / quota | ✅ | Live 240/min·1M; sandbox 120/min·100k. `x-ratelimit-*` headers exposed. |
| F5 | Sandbox key | ⚠️ | Tested + safe. RESTORE its scope to mirror live first (it holds a 52-keyword draft), then deliver, then `shred -u`. |
| F6 | Security / IDOR | ✅ | 401 no-key, 404 admin, 404 out-of-scope (not 403). |

---

## G. Infra the client silently depends on

| # | Item | Status | Detail / action |
|---|---|---|---|
| G1 | Ingestion healthy | ✅ (protected) | `topic_fill` rollup DISABLED to stop it stalling ingestion (KB I-21). Keep disabled until root-caused. |
| G2 | Query latency | ✅ improved | `random_page_cost` 4→1.1 (SSD) — client endpoints 2–4× faster; `stories` 7.95s→2.14s. |
| G3 | `shared_buffers` 160MB on 15.6GB box | 🔴 | Cache hit 55.9%. Needs a restart window (not near 05:03 IST). Post-Monday. |
| G4 | DNL `dnl_image_scan.py` eats 1.4GB/20min | ⚠️ | Different product on Neon, competing for RAM on this box. Escalate. |

---

## VALIDATION SEQUENCE (careful, sequenced — do NOT fan out on the live box)

**Tonight (client-facing, deadline):**
1. Send the reply — 19/19 resolve, send as written, mute terms work, summary now 2000ch.
2. Restore sandbox scope → deliver sandbox key → `shred -u`.
3. Confirm their PATCH per term when they push (`resolved_entities` vs `added_as_keywords`).

**Before Monday (the three that could embarrass us — verify in this order):**
4. 🔴 **D3 — do critical-alert webhooks actually fire?** End-to-end: qualifying event → webhook push. This is their core value.
5. ❓ **B4 — directed sentiment toward "Government of Telangana"** returns real coverage (their stated primary measurement).
6. ❓ **C4 — are Urdu sources actually being collected?** (their one explicit language ask).
7. ⚠️ **F2 — the 05:03 brief content** reflects the new 19 entities.

**This weekend (high value, low risk):**
8. Add Group-A proper-noun keywords as entities (§E) — ~20, with aliases.
9. Optional: carefully-chosen short-form aliases for the thin entities (B3).

**Post-Monday (build + infra):**
10. LLM-at-add-time alias pipeline (deterministic auto-apply, ambiguous→review).
11. Route Group-B generic topics to the topic/alert layer, region-scoped.
12. `shared_buffers` restart (G3); escalate DNL cron (G4); topic_fill root cause (G1).
13. Give the KB a git remote (currently local-only).

---

## EXECUTED VALIDATION — 2026-07-17 (sandbox set to their 19-entity scope, then restored)

Ran a full data-quality sweep with the sandbox key after setting its scope to their
exact tonight-push (19 entities, their keywords/regions/languages/mute). Sandbox
**restored to mirror live (6 entities)** afterwards.

**Confirmed working with real data:**
- ✅ **All 19 entities resolve** (0 nulls when scope set) — incl. the DIPR comma form.
- ✅ **Directed sentiment toward Government of Telangana** (their PRIMARY measurement):
  `total 698, split {supportive 25, neutral 511, critical 162}, net_lean -0.196`.
  **NOTE: `/analytics/sentiment` REQUIRES an `entity=` param** (name or id) — without it, 422. That is correct design; tell VeriDeck's dev.
- ✅ English summaries on the feed: 44/50 (88%), avg 782 chars.
- ✅ Urdu IS collected: 1,131 Urdu articles in 7d (their explicit ask is met; the languages *field* is still inert but inert = no narrowing).
- ✅ Brief (`/brief/today`,`/brief/daily`): real content, references their entities, ~8.5KB.
- ✅ topics / coverage / entities / cuttings / geo: all 200 with real data.
- ⚠️ **stories: 9.0s** — functional but slow; worth a look.

**🔴 CRITICAL FINDING — national-entity contamination (hits LIVE when they push):**
Their CURRENT 6-entity scope is clean (all Telangana-specific). Their PLANNED 19 adds
the **national "Bharatiya Janata Party" entity**, which is the problem:
- BJP entity = **5,345 articles/30d**, of which only **490 (9%) even mention Telangana/Hyderabad**. ~4,855 are pure national noise (Modi, Amit Shah, TN's Annamalai, Kerala's Satheesan).
- BJP alone would be ~60–67% of their entire feed.
- Cause: I aliased "Bharatiya Janata Party - Telangana" → the *national* BJP entity, and **`regions` is inert for the article feed** (C5), so nothing constrains it to Telangana.
- INC national resolves but is nearly empty (6 articles); AIMIM small + mostly relevant (23/12). **So the contamination is specifically the BJP national entity.**
- The Telangana people are clean: Revanth 74% TG, KCR 65%, KTR 68%, Kishan Reddy 72%.

**Recommendation (client decision, do NOT unilaterally build region-scoping pre-launch):**
For national parties, rely on the Telangana *leaders* already in their list (Kishan
Reddy + Ramchander Rao for BJP; Revanth for Congress; Owaisi for AIMIM) which capture
Telangana party activity cleanly — OR we build region-scoped party tracking as a
fast-follow. Do NOT add the raw national "Bharatiya Janata Party" entity as-is.

**🔴 CRITICAL FINDING — webhook delivery was DEAD (now restored):**
- Engine (`webhook_delivery.run_once`) is production-quality (SSRF guard, HMAC, at-least-once, retry, auto-disable) and had delivered 1,979 times historically.
- But **nothing scheduled it** — `run_once` is only in `if __name__=="__main__"`; no cron/beat/loop. It last ran 2026-07-16 07:16 and stopped.
- **FIXED**: added a flock'd cron (`*/3`, correct `-m v1.webhook_delivery` invocation — the naive `python file.py` fails on relative imports). Crontab backup `/root/crontab.bak-20260717`. Safe: 0 active webhooks, so it's a no-op until one activates.
- VeriDeck's own webhook is **disabled** (15 failures, `is_active=f`, watermark stuck at 2000-01-01) — their Cloud Run endpoint wasn't accepting during QA.
- ⚠️ **Semantic gap:** webhooks fire `coverage.matched` on an entity/topic/sentiment filter — a **coverage push, NOT** the severity/critical-tone/multi-outlet-spike alerting their doc describes. Their keyword-priority + critical-alert rules are **not implemented** as such.
- ⚠️ **Reactivation footgun:** before re-enabling their hook, RESET `last_delivered_at = now()` or the first run tries to deliver every matching article back to 2000. And confirm their endpoint accepts POSTs first.

**Fixes applied this pass:** webhook delivery cron restored; title/suffix/comma
aliases added (all 19 resolve); 5 govt-body entities added earlier. Sandbox restored
to mirror live.
