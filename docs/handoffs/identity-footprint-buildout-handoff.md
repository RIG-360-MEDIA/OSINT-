# Identity / People Footprint Buildout — Full Handoff

**Written 2026-07-07.** Hand this + the kickoff prompt to a new chat for full context.
Read top-to-bottom first. Sibling handoffs (done, same discipline): social,
osint-sources, geospatial, image-media-verification (`docs/handoffs/`).

---

## 0. One-paragraph situation

RIG Surveillance is a keyword/entity OSINT platform. Social, 10 OSINT sources, tenders,
satellite, and image verification are built. This phase adds **identity footprint** —
given ONE selector (a username, email, or phone), map the PUBLIC account footprint tied
to it. Legitimate use: vet a source, map a public figure's presence, or take a hostile
account found in the social feed and see its OTHER public accounts (coordinated-persona
detection). This is a NARROW capability with a HARD ethical line — read §1 before
anything.

## 1. THE ETHICAL LINE (read first — non-negotiable, overrides any "make it work" urge)

**IN SCOPE (public account traces only — legal, standard OSINT):**
- **Username → cross-platform accounts.** Check which sites have an account with that
  exact username (Sherlock/Maigret-style). Public presence only.
- **Email → public registration traces + breach-*notification*.** Which services show an
  account, linked public profiles, and whether the email appears in a breach per a
  notification service (HaveIBeenPwned "yes it was in breach X" — the FACT, never the
  leaked data).
- **Phone → validation/carrier/type** (valid? country? carrier? VoIP/burner?).

**OFF-LIMITS (do NOT build, do NOT call, refuse if asked):**
- **Data-broker people-search** — home address, relatives, DOB, aggregated PII of private
  individuals. (Legal landmines: GDPR / India DPDP. Ethically wrong.)
- **Breach DUMPS** — the actual leaked passwords/records. Only the "was-it-in-a-breach"
  boolean is allowed, never the credential data.
- **Face search / facial recognition** (PimEyes-style upload-a-face-find-them) —
  biometric surveillance of private persons. Hard no.
- **Dark-web crawling** for a person's data.

**The test:** mapping what someone chose to make PUBLIC (their accounts) = OK.
De-anonymizing or dossiering a PRIVATE individual via broker/breach/face data = NOT OK.
If a request crosses into the second, STOP and say so — do not quietly build it.

## 2. Hard rules (in addition to §1)

- **VERIFY against live services — never trust docs/my claims.** Username-check sites
  change; many produce false positives (a username "exists" page that's really a soft-404).
  Confirm real hits, flag confidence.
- **No fabrication.** A "found account" must be a real reachable profile, not a guessed
  URL. Report confirmed / probable / false-positive separately.
- **Prove on TWO selectors** — one KNOWN (a public figure's real handle you can confirm
  the found accounts are theirs) AND one fresh. Watch for the classic failure: same
  username = DIFFERENT people across platforms (do NOT assert they're one person without
  corroboration + a confidence score).
- **Free / no-paid this phase.** Secrets via env vars.
- **On-demand + persist-from-use** (`project_social_keyword_driven`): run on request,
  store the footprint result, not a scrape of everything.
- **Low blast radius:** external read-only lookups; does NOT touch `rig-backend` ingest.
  Build isolated in osint-backend (httpx only).

## 3. The building blocks (VET before relying — stars/activity/license/does-it-run)

- **Username:** `sherlock` and `maigret` (maigret is richer) — check a username across
  hundreds of sites. Both free, Python. Beware false positives; verify a sample.
- **Email:** HaveIBeenPwned (breach-notification — has a free tier / rate limits; the
  paid API is fuller — flag if needed, don't buy this phase); `holehe`-style
  "which sites is this email registered on" (public signup tells). Public only.
- **Phone:** `phonenumbers` (Google libphonenumber port) for validate/carrier/type — free,
  offline, reliable. No owner-identification.
- **Fusion hook:** this pairs with the social phase — a hostile/coordinated account found
  in the feed → run its username here → surface its other public accounts → feeds the
  coordinated-persona / SNA analysis.

## 4. The plan

**Phase 0 — research + vet (FIRST, no code).** Confirm maigret/sherlock actually return
low-false-positive results from the box; check HIBP free-tier terms + a free
email-registration checker; confirm `phonenumbers`. Rank "use THESE". (Research agent.)

**Phase 1 — POC verifier.** `verify_identity_footprint.py`: input = a username / email /
phone → confirmed public accounts (username), registration + breach-boolean (email),
validation/carrier (phone) → structured footprint with a per-hit confidence and the
same-username-≠-same-person caveat surfaced. Runs on dev AND box. **Proof bar:** ≥2
selectors incl. one KNOWN public figure — confirm the found accounts are actually theirs;
false positives flagged, not asserted. No fabrication.

**Later (deferred):** on-demand endpoint (`/api/identity/footprint`); wire into the social
coordinated-persona detection; surface in the dossier for an account under investigation.

## 5. Definition of done (Phase 1)

`verify_identity_footprint.py` run on the box on 2 selectors (one known), output pasted
back, real accounts confirmed, false positives flagged, §1 boundaries respected
(nothing off-limits touched). No fabrication.

## 6. Context to read first

- Sibling handoffs (§ intro). Memory dir:
  `project_social_keyword_driven.md`, `feedback_no_fabricated_results.md`, `MEMORY.md`.
- Reuse the cheap_stack / osint-backend httpx patterns. CLAUDE.md — topology/foot-guns.
- **Re-read §1 before writing any code.**
