# Documentation Consolidation Plan

Generated 2026-05-28 · Analyzed **127** real project docs (excluding `.claude/` agent prompts).

## Goal

Reduce 127 docs → ~25-40 canonical docs. Each topic should have ONE source of truth.

## A. Onboarding / Memory (18 files)

| File | Modified | Size | Title |
|---|---|---|---|
| `brief-app/README.md` | 2026-05-23 | 1.3KB | Boss's Morning Brief — local dev |
| `docs/quality/README.md` | 2026-05-22 | 3.8KB | V3 Data Quality Audit |
| `docs/content-platform/01-prd.md` | 2026-05-20 | 34KB | RIG News — Product Requirements Document (v1) |
| `docs/new-chat-prompts/README.md` | 2026-05-17 | 2.9KB | Opening prompts for new Claude chats |
| `docs/onboarding/00-README.md` | 2026-05-17 | 6.5KB | 00 - Onboarding README |
| `docs/onboarding/01-architecture.md` | 2026-05-17 | 9.7KB | 01 - System Architecture |
| `docs/onboarding/02-substrate-pipeline.md` | 2026-05-17 | 10KB | 02 - Substrate Pipeline (v3 Extraction) |
| `docs/onboarding/03-relevance-system.md` | 2026-05-17 | 6.9KB | 03 - Relevance System |
| `docs/onboarding/04-scrapers.md` | 2026-05-17 | 8.6KB | 04 - Scrapers / Ingestion |
| `docs/onboarding/05-llm-infrastructure.md` | 2026-05-17 | 10KB | 05 - LLM Infrastructure |
| `docs/onboarding/06-operations-runbook.md` | 2026-05-17 | 8.6KB | 06 - Operations Runbook |
| `docs/onboarding/07-known-issues.md` | 2026-05-17 | 9KB | 07 - Known Issues |
| `docs/onboarding/08-future-plans.md` | 2026-05-17 | 7.3KB | 08 - Future Plans |
| `docs/onboarding/09-todos-prioritized.md` | 2026-05-17 | 7.3KB | 09 - Prioritised Backlog |
| `docs/onboarding/10-context-from-may-2026-session.md` | 2026-05-17 | 9.2KB | 10 - Context From the May 2026 Session |
| `docs/onboarding/REQUIREMENTS.md` | 2026-05-17 | 12.8KB | Onboarding Requirements — living document |
| `CLAUDE.md` | 2026-05-17 | 7KB | CLAUDE.md |
| `backend/.pytest_cache/README.md` | 2026-04-25 | 0.3KB | pytest cache directory # |

## B. Architecture / Design (8 files)

| File | Modified | Size | Title |
|---|---|---|---|
| `docs/TRIJYA-7_SYSTEM_DOCUMENTATION.md` | 2026-05-27 | 5.7KB | TRIJYA-7 (RTX 4090) — Compute Resource Documentation |
| `docs/PIPELINE_DATA_READINESS.md` | 2026-05-25 | 4.8KB | Narrative Pipeline — Data Readiness Audit |
| `docs/new-chat-prompts/05-historical-pipeline.md` | 2026-05-17 | 8.4KB | Opening prompt — Chat 5: Historical Pipeline Database (NEW, separate from RIG) |
| `docs/design/cm-room-redesign-prompts.md` | 2026-05-02 | 4.1KB | CM Room — Redesign Image Prompts |
| `docs/qa/analyst-pipeline-health.md` | 2026-04-28 | 6.6KB | Analyst Pillar — Pipeline Health (Phase A) |
| `docs/qa/analyst-scraper-sweep.md` | 2026-04-28 | 8.1KB | Analyst Pillar — Scraper / Pipeline Sweep (Phase F) |
| `docs/qa/worldmonitor-audit-2026-04-28/02_workers.md` | 2026-04-28 | 4.8KB | 02 — Worker + queue topology (Step 2) |
| `docs/qa/brief-redesign-mockup.md` | 2026-04-27 | 23.4KB | Brief Page — Redesign Mockup (Step-through edition) |

## C. Data Quality Audits (32 files)

| File | Modified | Size | Title |
|---|---|---|---|
| `docs/DATA_QUALITY_AUDIT_2026-05-28.md` | 2026-05-27 | 11.4KB | Full Statistical Data Quality Audit — 2026-05-28 |
| `docs/DB_AUDIT_2026-05-26_v2.md` | 2026-05-26 | 147.6KB | RIG-Surveillance Database Quality Audit |
| `docs/DB_COLUMN_PROFILE_2026-05-26.md` | 2026-05-26 | 44.5KB | RIG-Surveillance Per-Column Quality Profile (fast pass) |
| `docs/DATA_QUALITY_AUDIT_2026-05-26.md` | 2026-05-25 | 6.6KB | Comprehensive Data Quality Audit — 2026-05-26 |
| `docs/DATA_QUALITY_TEMPORAL_ANALYSIS.md` | 2026-05-25 | 4.1KB | Temporal Quality Analysis — Is breakage chronic or recent? |
| `docs/FIELD_BY_FIELD_DEEP_AUDIT.md` | 2026-05-25 | 9KB | Field-by-Field Deep Audit + Quality Drilldown — 2026-05-26 |
| `docs/SCHEMA_REDUNDANCY_AND_WASTE.md` | 2026-05-25 | 6KB | Schema Redundancy & Waste Audit — 2026-05-26 |
| `docs/LLM_QUOTA_AUDIT_2026-05-24.md` | 2026-05-24 | 1.8KB | LLM Daily Quota Audit — 2026-05-24 |
| `docs/brief-feature-readiness.md` | 2026-05-23 | 6.2KB | `/brief` Frontend — Feature × Data-Readiness Audit |
| `docs/rig-news-frontend-audit.md` | 2026-05-23 | 12.1KB | `rig-news` Frontend — Complete Feature Audit |
| `docs/quality/v3-deep-audit-2026-05-22.md` | 2026-05-22 | 20.9KB | V3 Deep Audit — 2026-05-22 |
| `docs/qa/analyst-audit-summary.md` | 2026-04-28 | 9.1KB | Analyst Pillar — Production Audit Summary |
| `docs/qa/brief-audit-2026-04-28.md` | 2026-04-28 | 27.1KB | Brief Pillar — Production-Readiness Audit |
| `docs/qa/clips-prod-readiness-2026-04-28.md` | 2026-04-28 | 22.7KB | Clips (YouTube) — Production-Readiness Audit |
| `docs/qa/coverage-audit-2026-04-28.md` | 2026-04-28 | 11.4KB | Coverage Pillar — Production-Readiness Audit (2026-04-28) |
| `docs/qa/cuttings-audit-2026-04-28.md` | 2026-04-28 | 41.6KB | Cuttings Pillar — Production-Readiness Audit |
| `docs/qa/cuttings-audit-report.md` | 2026-04-28 | 11.8KB | Cuttings (Clippings) Pillar — Production-Readiness Audit |
| `docs/qa/signals-audit-2026-04-28.md` | 2026-04-28 | 12.6KB | Signals Page — Production-Readiness Audit |
| `docs/qa/signals-audit-2026-04-29.md` | 2026-04-28 | 12.5KB | Signals Page — Final Audit & Fix Report |
| `docs/qa/worldmonitor-audit-2026-04-28/00_baseline.md` | 2026-04-28 | 3.6KB | 00 — Baseline (Step 0) |
| `docs/qa/worldmonitor-audit-2026-04-28/01_db_seed.md` | 2026-04-28 | 5.2KB | 01 — DB schema + seed sanity (Step 1) |
| `docs/qa/worldmonitor-audit-2026-04-28/03_endpoints.md` | 2026-04-28 | 6KB | 03 — Backend endpoint smoke (Step 3) |
| `docs/qa/worldmonitor-audit-2026-04-28/04_frontend.md` | 2026-04-28 | 4.7KB | 04 — Frontend smoke (Step 4) |
| `docs/qa/worldmonitor-audit-2026-04-28/05_failure_paths.md` | 2026-04-28 | 1.5KB | 05 — Fallback + failure paths (Step 5) |
| `docs/qa/worldmonitor-audit-2026-04-28/06_content_quality.md` | 2026-04-28 | 7.4KB | 06 — Content quality verification (Step 6) |
| `docs/qa/worldmonitor-audit-2026-04-28/07_caching.md` | 2026-04-28 | 2.1KB | 07 — Caching + concurrency (Step 7) |
| `docs/qa/worldmonitor-audit-2026-04-28/08_tests.md` | 2026-04-28 | 2.3KB | 08 — Test coverage (Step 8) |
| `docs/qa/worldmonitor-audit-2026-04-28/09_security.md` | 2026-04-28 | 3.8KB | 09 — Security + auth surface (Step 9) |
| `docs/qa/worldmonitor-audit-2026-04-28/DEFECTS.md` | 2026-04-28 | 6.9KB | DEFECTS — Globe Page (WorldMonitor) Production Audit |
| `docs/qa/worldmonitor-audit-2026-04-28/VERDICT.md` | 2026-04-28 | 5.5KB | VERDICT — Globe Page (WorldMonitor) Production Audit |
| `docs/qa/documents-backend-audit.md` | 2026-04-25 | 6.1KB | Backend Audit — `documents_router.py` |
| `docs/qa/documents-frontend-audit.md` | 2026-04-25 | 6KB | Frontend Audit — `/documents` page |

## E. Runbooks / Ops (5 files)

| File | Modified | Size | Title |
|---|---|---|---|
| `docs/PAUSE_INGEST_RUNBOOK.md` | 2026-05-27 | 4.3KB | Pause / Resume RSS Ingest Runbook |
| `docs/BRIEF_APP_PRODUCTION_PLAN.md` | 2026-05-23 | 7.8KB | Brief App — Production Deployment Plan |
| `docs/RUNBOOK_DEPLOY.md` | 2026-04-29 | 8.5KB | Production Deploy Runbook |
| `docs/RUNBOOK_SUPER_ADMIN_BOOTSTRAP.md` | 2026-04-29 | 5KB | Runbook: Bootstrapping the first super-admin |
| `docs/PROJECT_OVERVIEW_AND_DEPLOYMENT.md` | 2026-04-28 | 20.9KB | RIG Surveillance — Project Overview & Cloud Deployment Guide |

## F. Sprint plans / PRDs (9 files)

| File | Modified | Size | Title |
|---|---|---|---|
| `docs/RECONCILIATION_PLAN_2026-05-26.md` | 2026-05-26 | 5.5KB | Branch Reconciliation Plan — 2026-05-26 |
| `docs/UNIFICATION_PLAN_2026-05-26.md` | 2026-05-26 | 6.7KB | Branch Unification + Code Cleanup Plan |
| `docs/DATA_REPAIR_MASTER_PLAN.md` | 2026-05-25 | 11.1KB | Data Repair Master Plan — Every Fix Needed |
| `docs/BRIEF_APP_BUILD_PLAN.md` | 2026-05-23 | 5.6KB | Boss's Brief — Build Plan |
| `docs/quality/data-fix-execution-plan.md` | 2026-05-23 | 5.4KB | Data-Fix Execution Plan — `/brief` Readiness |
| `docs/quality/source-side-fixes-plan.md` | 2026-05-23 | 7.7KB | Source-Side Fixes — Stop the bleeding for NEW articles |
| `docs/qa/brief-remediation-plan.md` | 2026-04-29 | 8.8KB | Brief Pillar — Production Remediation Plan |
| `docs/plans/rbac-and-impersonation.md` | 2026-04-28 | 12.5KB | RBAC + Per-User Data Isolation + Super Admin Impersonation |
| `docs/qa/fix-plan.md` | 2026-04-25 | 10KB | Archive (`/documents`) — Full Fix Plan |

## G. QA defect registers (27 files)

| File | Modified | Size | Title |
|---|---|---|---|
| `docs/qa/auth-rbac-defects.md` | 2026-04-29 | 22.3KB | Auth / RBAC / Access-Limit Defect Register |
| `docs/qa/analyst-backend-findings.md` | 2026-04-28 | 16.3KB | Analyst Pillar — Backend Findings (Phase B) |
| `docs/qa/analyst-frontend-findings.md` | 2026-04-28 | 6.9KB | Analyst Pillar — Frontend Findings (Phase D) |
| `docs/qa/analyst-live-verification.md` | 2026-04-28 | 8.7KB | Analyst Pillar — Live Verification (Phase G) |
| `docs/qa/analyst-quality-eval.md` | 2026-04-28 | 5.9KB | Analyst Pillar — Quality Eval (Phase E + G) |
| `docs/qa/analyst-test-gaps.md` | 2026-04-28 | 7.2KB | Analyst Pillar — Test Gaps (Phase C) |
| `docs/qa/brief-monitoring-mode-mockup.md` | 2026-04-28 | 8.8KB | Brief Page — Monitoring Mode (companion to Intelligence Mode) |
| `docs/qa/coverage-defects.md` | 2026-04-28 | 6.5KB | Coverage — Defect Register (2026-04-28) |
| `docs/qa/coverage-source-health.md` | 2026-04-28 | 4KB | Coverage — Source Health Matrix (2026-04-28) |
| `docs/qa/documents-defects.md` | 2026-04-28 | 8.3KB | Defects Register — `/documents` page |
| `docs/qa/monitor-wires-flow-mockup.md` | 2026-04-28 | 6.3KB | Top of the Wires — Flowing / Live / Critical (mockup) |
| `docs/qa/brief-coverage-matrix.md` | 2026-04-26 | 5.5KB | Brief — Pillar Coverage & Govt-Sources Matrix |
| `docs/qa/brief-defects.md` | 2026-04-26 | 11.2KB | Brief — Defect Register |
| `docs/qa/brief-live-session.md` | 2026-04-26 | 3.9KB | Brief — Live UX Walkthrough Log |
| `docs/qa/brief-quality-scorecard.md` | 2026-04-26 | 2.9KB | Brief — Output Quality Scorecard |
| `docs/qa/signals-data-quality-report.md` | 2026-04-26 | 4.4KB | Signals — Data Quality Report |
| `docs/qa/signals-defects.md` | 2026-04-26 | 7.7KB | Defects Register — `/signals` page (The Signal Room) |
| `docs/qa/signals-live-session.md` | 2026-04-26 | 8.5KB | Signals — Live Debugging Session |
| `docs/qa/signals-per-source-verdict.md` | 2026-04-26 | 6KB | Signals — Per-Source Verdict |
| `docs/qa/signals-quality-scorecard.md` | 2026-04-26 | 5.6KB | Signals — Quality Scorecard |
| `docs/qa/clips-data-quality-report.md` | 2026-04-25 | 9.1KB | Clips — Data Quality Report |
| `docs/qa/clips-debug-report.md` | 2026-04-25 | 12.1KB | Clips Page — Debug & QA Report |
| `docs/qa/documents-live-session.md` | 2026-04-25 | 5.9KB | Live QA Session — `/documents` |
| `docs/qa/documents-quality-scorecard.md` | 2026-04-25 | 3.8KB | Quality Scorecard — `/documents` page |
| `docs/qa/govt-sources-inventory.md` | 2026-04-25 | 4.8KB | Government Source Inventory |
| `docs/qa/sources-per-source-verdict.md` | 2026-04-25 | 8.8KB | Per-source verdict — all 47 govt adapters |
| `docs/qa/sources-why-broken.md` | 2026-04-25 | 9.1KB | Why some govt sources work and others give nothing / wrong data |

## I. Tests / coverage (8 files)

| File | Modified | Size | Title |
|---|---|---|---|
| `frontend/test-results/clips--Roll-the-tape-loads-YouTube-iframe-with-autoplay/error-context.md` | 2026-04-28 | 10.9KB | Instructions |
| `frontend/test-results/clips--Take-to-Analyst-navigates-to-analyst-with-question/error-context.md` | 2026-04-28 | 9.1KB | Instructions |
| `frontend/test-results/clips-500-from-feed-renders-the-desk-memo-error-card/error-context.md` | 2026-04-28 | 8.1KB | Instructions |
| `frontend/test-results/clips-clips-page-loads-and-sends-Bearer-auth-on-feed-request/error-context.md` | 2026-04-28 | 8.1KB | Instructions |
| `frontend/test-results/clips-empty-feed-renders-the-No-clips-on-the-wire-memo/error-context.md` | 2026-04-28 | 8.5KB | Instructions |
| `frontend/test-results/clips-entity-filter-click-reloads-feed-with-entity-param/error-context.md` | 2026-04-28 | 9.9KB | Instructions |
| `frontend/test-results/clips-FilterPill-exposes-a-efec9-sed-for-screen-readers-F13-/error-context.md` | 2026-04-28 | 7KB | Instructions |
| `frontend/test-results/clips-renders-3-clip-cards-with-numerals-01-02-03/error-context.md` | 2026-04-28 | 11.1KB | Instructions |

## K. Scratch / temp (5 files)

| File | Modified | Size | Title |
|---|---|---|---|
| `scratch/event-eval/GRADED.md` | 2026-05-21 | 60.8KB | Event-clustering validation — graded report |
| `scratch/event-eval-v2/GRADED.md` | 2026-05-21 | 75.5KB | Event-clustering validation — graded report |
| `scratch/cluster-eval-v2/GRADED.md` | 2026-05-20 | 52.3KB | 500-article v2 validation — graded report |
| `scratch/cluster-eval-prod/GRADED.md` | 2026-05-19 | 65.3KB | 500-article validation — graded report |
| `scratch/cluster-eval/REVIEW.md` | 2026-05-17 | 30.8KB | Clustering eval — manual review |

## L. Misc historical (1 files)

| File | Modified | Size | Title |
|---|---|---|---|
| `docs/incidents/2026-05-20-drain-stall.md` | 2026-05-20 | 3.4KB | Drain stall — 2026-05-20 |

## Z. Uncategorized (14 files)

| File | Modified | Size | Title |
|---|---|---|---|
| `docs/PROJECT_DOCS_INDEX.md` | 2026-05-28 | 65.1KB | Project Documentation Index |
| `docs/BEST_SOURCES_GLOBAL.md` | 2026-05-27 | 2KB | Global news dataset — best sources by tier |
| `docs/PHASE1_20_COUNTRIES.md` | 2026-05-27 | 46.2KB | Phase 1 — 20-country flagships |
| `docs/ARTICLE_EXTRACTION_FIELDS.md` | 2026-05-25 | 4.5KB | Article Extraction — Complete Field Reference |
| `docs/BOSS_BRIEF_GAP_ANALYSIS.md` | 2026-05-23 | 8.6KB | Boss's OSINT Brief Frontend — Feature Gap Analysis |
| `docs/quality/regression-baseline.md` | 2026-05-22 | 2.7KB | Gold-set regression — operator manual |
| `docs/future-todo.md` | 2026-05-17 | 24.7KB | Future TODO |
| `docs/mistakes.md` | 2026-05-17 | 44.6KB | Mistakes log |
| `docs/new-chat-prompts/01-brief.md` | 2026-05-17 | 7.7KB | Opening prompt — Chat 1: Brief page (RIG frontend) |
| `docs/new-chat-prompts/02-map.md` | 2026-05-17 | 7.1KB | Opening prompt — Chat 2: Map page (RIG frontend) |
| `docs/new-chat-prompts/03-analytics.md` | 2026-05-17 | 9.5KB | Opening prompt — Chat 3: Analytics page (RIG frontend) |
| `docs/new-chat-prompts/04-content-platform.md` | 2026-05-17 | 8.8KB | Opening prompt — Chat 4: Content Generation Platform (NEW separate codebase) |
| `docs/newsroom/IMPLEMENTATION_PROMPT.md` | 2026-05-17 | 29.7KB | THE NEWSROOM — Implementation Prompt (zero-context briefing) |
| `docs/readout/IMPLEMENTATION_PROMPT.md` | 2026-05-17 | 42.4KB | THE READOUT — Implementation Prompt (zero-context briefing) |

