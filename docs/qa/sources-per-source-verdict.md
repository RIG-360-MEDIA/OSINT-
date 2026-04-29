# Per-source verdict — all 47 govt adapters

Method: each adapter's source code was inspected programmatically (`inspect.getsource`) to detect:
- **`httpx-direct`** — uses `httpx.AsyncClient` only. Simple HTTP. Most resilient.
- **`Playwright`** — uses `render_html` from `playwright_helper`. Needs Chromium installed. Silently returns `[]` if browser missing or selector times out.
- **`Playwright + httpx-fallback`** — tries Playwright first, falls back to httpx mirror. Degrades gracefully.
- **`STUB-empty`** — wired up but always returns `[]` by design.

## At-a-glance totals

| Category | Count | Verdict |
|---|---|---|
| `httpx-direct` | 29 | Should work, IF portal HTML hasn't changed AND isn't bot-blocking |
| `Playwright (strict)` | 9 | **Silently empty if Playwright not installed** in the worker container |
| `Playwright + httpx-fallback` | 7 | Best effort; httpx mirror picks up if SPA fails |
| `STUB-empty` | 2 | Intentional no-op |
| **Total** | **47** | |

Plus universal issues affecting all 47 (see [sources-why-broken.md](sources-why-broken.md)): `published_at` is always `None`, `since_days` is never honoured, junk-rate not persisted.

---

## Full table

Legend on **Will it work?**:
- ✅ Should work in production with no extra setup
- ⚠️ Will work only if Playwright/Chromium is provisioned in the worker
- ❌ Will not produce data (intentional or known-blocked)
- 🟡 May or may not — depends on portal HTML staying stable, no SSL/bot block

### central_regulators (7)

| Adapter | URL | Transport | Will it work? | Why / risk |
|---|---|---|---|---|
| `scrape_rbi` | rbi.org.in | httpx | 🟡 | RBI HTML is stable historically; selector matches `NotificationUser` / `BS_PressReleaseDisplay` / `.pdf`. Will go quiet if RBI redesigns. |
| `scrape_sebi` | sebi.gov.in | **Playwright** | ⚠️ | SEBI is a JS SPA. Hard dependency on Playwright. No httpx fallback. |
| `scrape_cci` | cci.gov.in | httpx (SSL off) | 🟡 | CCI ships an incomplete cert chain — code uses `verify=False` (security smell). |
| `scrape_irdai` | irdai.gov.in | httpx | 🟡 | Drupal-style portal; selector matches `/document-detail` and `/web/guest/`. |
| `scrape_trai` | trai.gov.in | httpx | 🟡 | Selector relies on `/notifications/`, `/release/`, `/sites/default/files`. |
| `scrape_cerc` | cercind.gov.in | **Playwright** | ⚠️ | Current-orders page is JS-rendered. |
| `scrape_pngrb` | pngrb.gov.in | **Playwright** | ⚠️ | Regulations page is JS-rendered. |

### courts (6)

| Adapter | URL | Transport | Will it work? | Why / risk |
|---|---|---|---|---|
| `scrape_sci_judgments` | sci.gov.in | **Playwright** | ⚠️ | Daily judgments table loads via JS. No fallback. |
| `scrape_tshc` | tshc.gov.in | httpx (SSL off) | 🟡 | Telangana HC; cert chain trust disabled. |
| `scrape_nclt` | nclt.gov.in | httpx (SSL off) | 🟡 | Cert chain trust disabled. |
| `scrape_nclat` | nclat.nic.in | httpx (SSL off) | 🟡 | Cert chain trust disabled. |
| `scrape_ngt` | greentribunal.gov.in | **Playwright** | ⚠️ | Orders page JS-rendered. |
| `scrape_ecourts_stub` | ecourts.gov.in | **STUB** | ❌ | Always `[]`. eCourts is per-case-query only (CAPTCHA + state cascades). Wired up to prevent fallthrough; not implemented. |

### parliament (6)

| Adapter | URL | Transport | Will it work? | Why / risk |
|---|---|---|---|---|
| `scrape_prs_bills` | prsindia.org | httpx | 🟡 | Static HTML; should work. |
| `scrape_committee_reports` | sansad.in/ls/committees | **Playwright + httpx-fallback** | ⚠️ | sansad.in is an Angular SPA → Playwright; falls back to NIC mirror via httpx if SPA fails. Best of the lot for this portal. |
| `scrape_ls_bills` | sansad.in/ls/legislation | **Playwright + httpx-fallback** | ⚠️ | Same SPA + fallback pattern. |
| `scrape_ls_questions` | sansad.in/ls/questions | **Playwright + httpx-fallback** | ⚠️ | Same. |
| `scrape_rs_bills` | sansad.in/rs/legislation | **Playwright + httpx-fallback** | ⚠️ | Same. |
| `scrape_rs_debates` | sansad.in/rs/proceedings | **Playwright + httpx-fallback** | ⚠️ | Same. |

### notifications / ministries (7)

| Adapter | URL | Transport | Will it work? | Why / risk |
|---|---|---|---|---|
| `scrape_egazette` | egazette.gov.in | **STUB** (httpx probe) | ❌ | ASP.NET viewstate + captcha walls every request. Code returns `[]` and the source seed ships with `is_active=FALSE` so the scheduler won't poll it. |
| `scrape_mof_notifications` | finmin.nic.in | httpx | 🟡 | Should work. |
| `scrape_mea_press` | mea.gov.in | httpx | 🟡 | Should work. |
| `scrape_mod_press` | mod.gov.in | httpx | 🟡 | Selector picks `.pdf` and `/dod/` permalinks. |
| `scrape_mha_notifications` | mha.gov.in | httpx | 🟡 | Should work. |
| `scrape_niti_reports` | niti.gov.in | httpx | 🟡 | Should work. |
| `scrape_gem_circulars` | gem.gov.in | httpx | 🟡 | Should work. |

### ip_permits (6)

| Adapter | URL | Transport | Will it work? | Why / risk |
|---|---|---|---|---|
| `scrape_cdsco_notifications` | cdsco.gov.in | httpx | 🟡 | Should work. |
| `scrape_fssai_notifications` | fssai.gov.in | httpx | 🟡 | Should work. |
| `scrape_mca_notifications` | mca.gov.in | **Playwright** | ⚠️ | ASP.NET grid hydrates via JS. No httpx fallback. |
| `scrape_ip_india_trademarks` | ipindia.gov.in/journal-tm | httpx (SSL off) | 🟡 | Cert chain trust disabled. |
| `scrape_ip_india_gi` | ipindia.gov.in/recent-news-gi | httpx (SSL off) | 🟡 | Cert chain trust disabled. |
| `scrape_ip_india_patents` | ipindia.gov.in/recently-granted-patents | httpx (SSL off) | 🟡 | Cert chain trust disabled. |

### international (7)

| Adapter | URL | Transport | Will it work? | Why / risk |
|---|---|---|---|---|
| `scrape_worldbank_india` | worldbank.org | httpx | 🟡 | Should work — WB has a public API-shaped index. |
| `scrape_adb_india` | adb.org | **Playwright** | ⚠️ | Bot-blocked otherwise; needs browser fingerprint. |
| `scrape_imf_india` | imf.org | **Playwright** | ⚠️ | Bot-blocked / JS-rendered. |
| `scrape_un_india` | india.un.org | **Playwright** | ⚠️ | Drupal cards hydrate via JS. |
| `scrape_ilo_india` | ilo.org | httpx | 🟡 | Should work. |
| `scrape_wto_india` | docs.wto.org | **Playwright + httpx-fallback** | ⚠️ | Module has both transports (likely Playwright primary, httpx fallback). |
| `scrape_bis` | bis.org | **Playwright + httpx-fallback** | ⚠️ | Module has both transports. |

### telangana_state (8)

| Adapter | URL | Transport | Will it work? | Why / risk |
|---|---|---|---|---|
| `scrape_ts_gazette` | gad.telangana.gov.in | httpx | 🟡 | Should work. |
| `scrape_ts_goir` | goir.telangana.gov.in | httpx | 🟡 | Should work. |
| `scrape_ghmc_tenders` | ghmc.gov.in | httpx | 🟡 | Should work. |
| `scrape_hmda` | hmda.gov.in | httpx | 🟡 | Should work. |
| `scrape_ts_ipass` | ipass.telangana.gov.in | httpx | 🟡 | Should work. |
| `scrape_eproc_ts` | tender.telangana.gov.in | httpx | 🟡 | Should work. |
| `scrape_tserc_tariff` | tserc.gov.in | httpx | 🟡 | Should work. |
| `scrape_tspsc` | tspsc.gov.in | httpx | 🟡 | Should work. |

---

## Net summary

**Out of 47 adapters:**

- **2 will never produce data** by design (eCourts stub + eGazette captcha-walled).
- **9 will silently produce nothing if Playwright is missing** in the worker container — and you cannot tell from the registry that they're empty (SEBI, CERC, PNGRB, SCI, NGT, MCA, ADB, IMF, UN India).
- **7 have Playwright primary with httpx fallback** — the 5 Sansad parliament adapters + WTO + BIS. These degrade to "lower-quality but non-empty."
- **29 are httpx-direct** — should produce something as long as the portal HTML hasn't shifted. Most of Telangana state, the ministry notifications, RBI/IRDAI/TRAI/CCI, IP India, NCLT/NCLAT/TSHC, World Bank, ILO, and PRS.

**Best-case healthy world (Playwright installed, no portal redesigns, no captchas):** ~45 adapters produce data.

**Realistic world without Playwright:** **9 silent zeros**, 2 stubs, ~7 partial via fallback, 29 working. **That's ~36 of 47 producing data,** with no real `published_at` on any of them and no `since_days` filtering on any of them — so even the "working" 36 are scraping the whole front page every night and stamping today's date on everything.

## How to verify against your live deployment

```sql
SELECT s.name, s.portal_url, s.is_active, s.last_scraped_at,
       s.consecutive_failures,
       COALESCE(d.docs_30d, 0) AS docs_30d
FROM govt_document_sources s
LEFT JOIN (
  SELECT source_id, COUNT(*) AS docs_30d
  FROM govt_documents
  WHERE collected_at > NOW() - INTERVAL '30 days'
  GROUP BY source_id
) d ON d.source_id = s.id
ORDER BY docs_30d ASC, s.last_scraped_at NULLS FIRST;
```

The bottom of that list = your real-world dead adapters. Cross-reference with the table above to know which are dead because of design (stubs), missing infra (Playwright), portal change (selector drift), or a real bug.
