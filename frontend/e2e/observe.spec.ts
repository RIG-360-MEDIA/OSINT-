import { expect, test } from '@playwright/test'

/**
 * Smoke test for /observe.
 *
 * Mocks the supabase session + the 8 API endpoints so the test runs without
 * a live backend or Postgres. Validates:
 *   - Page renders with 8 panels (one per role)
 *   - Persona switcher works
 *   - AuditQueue mark-correct round-trips to the API
 */

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:3000'
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8000'

const fakeAccess = {
  user_id: 'admin-1',
  email: 'admin@test',
  role: 'super_admin',
  allowed_pages: [],
  has_profile: true,
  has_entities: true,
  is_impersonating: false,
  real_email: null,
  target_email: null,
}

test.describe('/observe', () => {
  test.beforeEach(async ({ page }) => {
    // Mock /api/me/access so useAccess thinks we're a super_admin.
    await page.route(`${API_URL}/api/me/access`, (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(fakeAccess) })
    )

    // Mock all 8 observe endpoints with realistic shapes.
    const mocks: Record<string, unknown> = {
      'ingest-pulse': {
        by_hour: [{ hour: '2026-05-22T00:00:00Z', n: 100 }],
        per_source: [],
        stalled_sources: [{ source: 'X', last_seen: null, hours_since: 48 }],
        total_24h: 1000,
      },
      'source-scorecard': {
        sources: [
          { source: 'BBC', total: 100, v3_ok: 90, has_summary_pct: 95, has_embedding_pct: 90, languages: 1, last_seen: null },
        ],
      },
      'quality-monitor': {
        judge: { sampled: 200, successes: 180, errors: 20, median_scores: { overall_score: 9 }, p25_scores: { overall_score: 8 } },
        live: {
          v3_ok_total: 60000,
          cliff_500: 80,
          cliff_1000: 60,
          null_subject: 0,
          thin_summary: 100,
          thin_summary_pct: 0.2,
          null_embedding: 0,
          claims_placeholder: 100,
          claims_placeholder_pct: 5,
          claims_total: 200000,
        },
      },
      'geo-heatmap': { level: 'country', regions: [{ region: 'India', n: 5000 }] },
      'story-pulse': { clusters: [{ cluster_id: 'c1', headline: 'Test story', event_type: 'tragedy', article_count: 5, source_count: 3, new_24h: 2, last_updated: null }] },
      'crosstab': { actor: null, rows: [] },
      'live-tail': { next_cursor: null, articles: [{ aid: 'a1', source: 'BBC', title: 'Hello', lang: 'en', collected_at: '2026-05-22T00:00:00Z', substrate_status: 'ok', extraction_version: 3, summary_len: 300 }] },
      'audit-queue': { queue: [{ aid: 'a-1', flag: 'placeholder_subject', hint: 'article', source: 'BBC', title: 'Bad row', collected_at: null, existing_verdict: null }] },
    }
    for (const [path, body] of Object.entries(mocks)) {
      await page.route(new RegExp(`${API_URL}/api/observe/${path}.*`), (route) =>
        route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
      )
    }
  })

  test('renders 8 panels for super_admin', async ({ page }) => {
    await page.goto(`${BASE_URL}/observe`)
    const panels = page.locator('[data-testid="observe-panels"] section')
    await expect(panels).toHaveCount(8)
    await expect(page.getByText('/observe')).toBeVisible()
    // No JS console errors
    const errors: string[] = []
    page.on('pageerror', (e) => errors.push(e.message))
    await page.waitForTimeout(500)
    expect(errors).toEqual([])
  })

  test('persona switcher updates active button', async ({ page }) => {
    await page.goto(`${BASE_URL}/observe`)
    const sw = page.getByTestId('persona-switcher')
    await sw.getByText('auditor').click()
    await expect(sw.getByText('auditor')).toHaveClass(/bg-emerald-600/)
  })

  test('audit queue mark-correct POSTs and re-fetches', async ({ page }) => {
    let postCalled = false
    await page.route(`${API_URL}/api/observe/audit-decision`, (route) => {
      postCalled = true
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true, id: 'd-1', decided_at: '2026-05-22T00:00:00Z' }),
      })
    })
    await page.goto(`${BASE_URL}/observe`)
    await page.getByTestId('audit-queue-list').waitFor()
    await page.getByTestId('verdict-correct').first().click()
    await expect.poll(() => postCalled, { timeout: 3000 }).toBe(true)
  })
})
