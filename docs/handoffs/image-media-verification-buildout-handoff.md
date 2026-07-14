# Image / Media Verification Buildout — Full Handoff

**Written 2026-07-07.** Hand this + the kickoff prompt to a new chat for full context.
Read top-to-bottom first. Sibling handoffs (done, same discipline):
`keyword-social-rebuild-handoff.md`, `osint-sources-buildout-handoff.md`,
`geospatial-satellite-buildout-handoff.md`.

---

## 0. One-paragraph situation

RIG Surveillance is a keyword/entity OSINT platform. Social collection, 10 free OSINT
sources, tenders, and satellite change-detection are built + proven. This phase adds
**image / media verification** — given an image (or a video frame), answer: *where else
has it appeared, is it old / miscaptioned, was it edited, does its metadata match its
claim, where was it taken?* This is the highest-value NEW capability because it makes the
images/videos we ALREADY collect from social **trustworthy** — it's a verification layer
on existing data, not a new firehose. Top real-world need for political/media clients:
debunking fake/recycled images fast during elections and crises.

## 1. Hard rules (do not violate)

- **VERIFY against the live services — never trust docs or my cutoff-era claims.** Free
  reverse-image endpoints change/break; confirm CURRENT behavior before relying.
- **No fabrication.** Never claim an image is fake/real/edited without the actual signals
  shown (the match hits, the EXIF, the tampering map). Report as SIGNAL not PROOF where
  detection is probabilistic. Trusted / unverified / failed reported separately.
- **Prove on TWO images** — one with a KNOWN answer (e.g. a famously recycled/miscaptioned
  photo you can confirm the tool catches as "seen earlier than claimed") AND one fresh.
- **Honesty about the ceiling (state to user):** strong on reverse-search + EXIF +
  tampering HINTS; weak on definitive AI-deepfake verdicts (free detectors are imperfect —
  "signal, not proof"). Don't oversell deepfake detection.
- **Free / no-paid this phase.** No paid reverse-image or forensics APIs — flag where they
  would help, don't buy. Secrets via env vars.
- **On-demand + persist-from-use** (`project_social_keyword_driven` rule): verify an image
  when asked; store the verdict/signals, not a copy of every image.
- **Low blast radius:** external read-only lookups + local compute; does NOT touch
  `rig-backend` ingest. Build isolated in osint-backend (httpx / Pillow / etc.).
- **Off-limits:** no facial recognition of private individuals / face-search engines
  (PimEyes-style) — that's biometric surveillance of persons. This phase is about
  verifying IMAGES, not identifying people's faces.

## 2. The four capabilities (build in this order)

1. **Reverse image search — "where else has this appeared + since when".** The core
   debunk: find earlier appearances → prove a "today" photo is actually old. Free routes
   are flaky (no clean free Google Images API): Bing Visual Search, Yandex (strong for
   this), TinEye (limited free), SearXNG images (already in our stack — `rig-searxng:8080`,
   reuse it). VET which actually return usable results from a datacenter IP.
2. **EXIF / metadata extraction — "does the metadata match the claim".** Camera model,
   capture timestamp, GPS coords, software (edited-in-Photoshop hints). Free + reliable
   (`Pillow`/`exiftool`). Note: social platforms strip EXIF on upload — works best on
   original files, flag when metadata is absent.
3. **Geolocation from image content** — reuse `geo_collector.py` (Nominatim) to resolve any
   place text/landmarks; couple with EXIF GPS when present → "where was this taken".
4. **Tampering / manipulation hints** — Error-Level Analysis (ELA) + basic forensics +
   an AI-generated-image detector. SIGNAL only. VET free repos (stars/activity/license);
   candidates to check: image-forensics/ELA tools, open AI-image detectors. Be honest it's
   probabilistic.

## 3. The fusion payoff (why this is worth it)

Image verification is the connector: **image → reverse-search (earliest date) → EXIF
(when/where) → geolocation → cross-check NEWS timing + SATELLITE change** = automated
**event verification / debunk** ("posted as today, but online since 2019" / "claims
location X, but satellite shows no such event"). It ties social + geo + news + satellite
into one answer. That's the differentiator, not any single lookup.

## 4. The plan

**Phase 0 — research + vet (FIRST, no code).** Verify which free reverse-image routes
actually work from a datacenter IP (Bing/Yandex/TinEye/SearXNG-images). Vet 2-3 free
tampering/AI-detection repos (stars/activity/license/does-it-run). Come back with a ranked
"use THESE" recommendation. (Research agent ideal.)

**Phase 1 — POC verifier.** `verify_image.py`: input = an image URL/file →
(a) reverse-search earliest-appearance hits, (b) EXIF dump, (c) geolocation if resolvable,
(d) tampering/AI signal → structured verdict with the raw signals shown. Runs on dev AND
box. **Proof bar:** ≥2 images incl. one KNOWN-recycled — confirm it's caught; real signals
shown; ceiling stated honestly. No fabrication.

**Later (deferred):** on-demand endpoint (`/api/media/verify`) in osint-backend; auto-run
on images in collected social posts; surface a "verification" badge in the dossier; wire
the fusion (image+geo+news+satellite event-verification).

## 5. Definition of done (Phase 1)

`verify_image.py` run on the box on 2 images (one known-recycled), signals + verdict pasted
back, the known case correctly flagged, deepfake limits stated honestly. No fabrication.

## 6. Context to read first

- Sibling handoffs (§ intro) — same discipline.
- Memory `~/.claude/projects/C--Users-Dell-Desktop-rig-surveillance/memory/`:
  `project_social_keyword_driven.md` (on-demand/persist rule),
  `feedback_no_fabricated_results.md`, `MEMORY.md` (index).
- Reuse: `products/osint/backend/geo_collector.py` (geolocation), SearXNG at
  `rig-searxng:8080` (image search route). CLAUDE.md — topology/foot-guns.
