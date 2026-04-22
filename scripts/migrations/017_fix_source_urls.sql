-- 017_fix_source_urls.sql
-- F2 URL fixes — Apr 2026 audit.
--
-- Several seeded portal URLs (migrations 010-016) returned HTTP 404 / 400 / 503
-- in the Apr-2026 discovery probe because the upstream portals reorganised
-- their information architecture. This migration UPDATEs portal_url for the
-- sources where a current working URL was discovered via WebSearch.
--
-- Out of scope (handled by F3):
--   - DNS-failing hosts (finmin.nic.in, tserc.gov.in, tspsc.gov.in)
--   - 403 bot-blocks that need Playwright (ADB India, IMF, UN India, MCA)
--
-- This migration intentionally does NOT touch is_active. Activation/deactivation
-- decisions are out of scope for the URL-fix sweep.

BEGIN;

-- =====================================================================
-- Telangana state portals (migration 010)
-- =====================================================================

-- TS Gazette: gad.telangana.gov.in/Gazette → 404 + SSL mismatch.
-- Telangana State Portal exposes a dedicated gazette index page.
UPDATE govt_document_sources
SET portal_url = 'https://www.telangana.gov.in/gazette/'
WHERE name = 'TS Gazette';

-- GHMC Tenders: tenders.aspx → 404. New page is Tenderspage.aspx.
UPDATE govt_document_sources
SET portal_url = 'https://www.ghmc.gov.in/Tenderspage.aspx'
WHERE name = 'GHMC Tenders';

-- HMDA Notifications: /circulars-and-notifications/ → 404.
-- HMDA no longer publishes a dedicated circulars index; the "Tenders"
-- section is the closest live notifications-style listing the site exposes.
-- Keep the site root as the portal_url so the adapter can still extract
-- "What's New" links until HMDA restores a notifications index.
UPDATE govt_document_sources
SET portal_url = 'https://www.hmda.gov.in/'
WHERE name = 'HMDA Notifications';

-- =====================================================================
-- Courts (migration 012)
-- =====================================================================

-- Telangana High Court: /recent_orders → 400. Live "show list" endpoint
-- (id=1 is the recent-orders/notifications listing) works in browser tests.
-- NOTE: this is the only Telangana High Court row; it is seeded under the
-- 'Supreme Court of India' / NCLT / NCLAT / NGT / eCourts set in 012, and
-- if a 'Telangana High Court' row exists it was added outside the migration
-- chain — UPDATE is a no-op when not present.
UPDATE govt_document_sources
SET portal_url = 'https://tshc.gov.in/showList?id=1'
WHERE name = 'Telangana High Court';

-- Supreme Court of India: main.sci.gov.in/judgments returned 503 (rate
-- limit during probe, page itself is live). Migrate to the new sci.gov.in
-- "Judgement Date" listing which is the canonical recent-judgments page
-- on the redesigned site and is not subject to the same rate-limit on
-- main.sci.gov.in. F3 may still need browser headers / Playwright on top.
UPDATE govt_document_sources
SET portal_url = 'https://www.sci.gov.in/judgements-judgement-date/'
WHERE name = 'Supreme Court of India';

-- NGT: /orders-judgements → 404. New listing is /judgementOrder/zonalbenchwise.
UPDATE govt_document_sources
SET portal_url = 'https://www.greentribunal.gov.in/judgementOrder/zonalbenchwise'
WHERE name = 'NGT';

-- =====================================================================
-- Parliament (migration 013)
-- =====================================================================

-- Lok Sabha Bills: /ls/legislation/bills-introduced → 404. The Digital
-- Sansad redesign collapsed "introduced" / "passed" tabs into a single
-- /ls/legislation/bills page with client-side filters.
UPDATE govt_document_sources
SET portal_url = 'https://sansad.in/ls/legislation/bills'
WHERE name = 'Lok Sabha Bills';

-- Rajya Sabha Bills: /rs/legislation/bills-pending → 404. Same redesign.
UPDATE govt_document_sources
SET portal_url = 'https://sansad.in/rs/legislation/bills'
WHERE name = 'Rajya Sabha Bills';

-- Rajya Sabha Debates: /rs/proceedings/synopsis → 404. The official
-- debates listing now lives at /rs/debates/officials.
UPDATE govt_document_sources
SET portal_url = 'https://sansad.in/rs/debates/officials'
WHERE name = 'Rajya Sabha Debates';

-- Parl. Committee Reports: /ls/committees/committee-reports → 404.
-- Replaced by the Lok Sabha "Subjects, Reports & Press Release" page.
UPDATE govt_document_sources
SET portal_url = 'https://sansad.in/ls/committee/subjects-reports'
WHERE name = 'Parl. Committee Reports';

-- =====================================================================
-- IP / regulatory permits (migration 014)
-- =====================================================================

-- IP India Patents: /recently-granted-patents.htm → 404.
-- IP India deprecated the static "recently-granted" page; the canonical
-- granted-patents data source is now the InPASS public search backed by
-- the patents Journal listing.
UPDATE govt_document_sources
SET portal_url = 'https://www.ipindia.gov.in/journal-patents.htm'
WHERE name = 'IP India Patents';

-- IP India Trademarks: /journal-tm.htm → 404 (currently inactive).
-- The trademarks Journal moved to the search subdomain.
UPDATE govt_document_sources
SET portal_url = 'https://search.ipindia.gov.in/IPOJournal/Journal/Trademark'
WHERE name = 'IP India Trademarks';

-- IP India GI Tags: /recent-news-gi.htm → 404.
-- Closest current canonical listing is the registered-GIs index; the
-- GI Public Search subdomain (search.ipindia.gov.in/GIRPublic/) hosts
-- the live application register but renders via JS, so prefer the static
-- registered-GIs HTML page for the static-HTML adapter.
UPDATE govt_document_sources
SET portal_url = 'https://www.ipindia.gov.in/registered-gls.htm'
WHERE name = 'IP India GI Tags';

-- CDSCO Notifications: .../Notifications/Notice/ → 404.
-- New notifications index is /Notifications/Public-Notices/.
UPDATE govt_document_sources
SET portal_url = 'https://cdsco.gov.in/opencms/opencms/en/Notifications/Public-Notices/'
WHERE name = 'CDSCO Notifications';

-- =====================================================================
-- International (migration 015)
-- =====================================================================

-- ILO India: /asia/countries/india/publications/lang--en/index.htm → 404.
-- ILO migrated to a new IA in 2024. The India country page now lives at
-- /regions-and-countries/asia-and-pacific/india with a "publications"
-- filter. Use the country root — the adapter can follow into publications.
UPDATE govt_document_sources
SET portal_url = 'https://www.ilo.org/regions-and-countries/asia-and-pacific/india'
WHERE name = 'ILO India';

-- =====================================================================
-- Cross-ministry notifications (migration 016)
-- =====================================================================

-- NITI Aayog Reports: /reports-publications → 404.
-- Canonical reports listing is now /documents/reports.
UPDATE govt_document_sources
SET portal_url = 'https://www.niti.gov.in/documents/reports'
WHERE name = 'NITI Aayog Reports';

-- MHA Notifications: /en/notifications → 404 (parent path no longer renders).
-- MHA splits notifications into /notice and /circular leaves; "notice" is
-- the higher-volume feed and the better default for collector seed.
UPDATE govt_document_sources
SET portal_url = 'https://www.mha.gov.in/en/notifications/notice'
WHERE name = 'MHA Notifications';

-- =====================================================================
-- Sources NOT updated (no working replacement found, or out of scope)
-- =====================================================================

-- TGERC Tariff Orders: tserc.gov.in DNS-fail in environment. Telangana SERC
-- canonical host is tgerc.telangana.gov.in (per the discovered Open-Access
-- Regulation Gazette PDF on that host). Likely fix is host-only, not
-- path-only — leaving for F3 to confirm under DNS / network resolution.
--
-- TSPSC Notifications: www.tspsc.gov.in DNS-fail in environment, page exists
-- in browser. F3 / DNS concern, not a stale-URL issue.
--
-- MoF Notifications: www.finmin.nic.in DNS-fail in environment. The MoF
-- canonical host is dea.gov.in / dor.gov.in / cbic.gov.in per division —
-- there is no single "MoF notifications" page. F3 / Playwright + per-
-- division split is needed; leaving URL as-is.
--
-- Telangana GO.Ms Portal: goir.telangana.gov.in returns 0 useful — page
-- requires server-side form POST (department + GO type + date range) and
-- has no flat listing. Adapter rewrite needed, not a URL fix. Leaving as-is.
--
-- MEA Press Releases: page exists, returned 0 useful only because the
-- adapter doesn't follow the ?51%2FPress_Releases= query-string variant.
-- URL itself is correct (/press-releases.htm). Leaving as-is — this is an
-- adapter-side fix that belongs to F1.
--
-- ADB India / IMF India Reports / UN India / MCA Notifications: 403 bot-
-- blocks. URLs are correct; F3 must rescue with Playwright + realistic
-- browser headers. No URL change.

COMMIT;
