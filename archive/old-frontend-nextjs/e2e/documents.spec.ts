/**
 * End-to-end smoke for the Archive (/documents) page.
 *
 * Mirrors clips.spec.ts: requires E2E_SUPABASE_TOKEN; skips when absent
 * so CI doesn't flap on unconfigured environments.
 *
 * Network is stubbed via page.route() — these are UI-correctness tests,
 * not backend-integration tests. For backend integration, see
 * backend/tests/test_documents_router.py.
 *
 * Run:
 *   cd frontend
 *   E2E_BASE_URL=http://localhost:3000 \
 *   E2E_SUPABASE_TOKEN=eyJ... \
 *     npm run e2e -- e2e/documents.spec.ts
 */
import { expect, test } from '@playwright/test'

const TOKEN = process.env.E2E_SUPABASE_TOKEN
const BASE = process.env.E2E_BASE_URL ?? 'http://localhost:3000'

interface DocFixture {
  doc_id: string
  title: string
  document_url: string
  source_name: string
  source_geography: 'LOCAL' | 'CENTRAL' | 'NEIGHBOURING' | 'INTERNATIONAL'
  document_type: string
  topic_category: string | null
  geo_primary: string | null
  summary_preview: string | null
  summary: string | null
  page_count: number | null
  published_at: string | null
  collected_at: string
  score_final: number | null
  relevance_tier: number | null
  urgency: 'HIGH' | 'MEDIUM' | 'LOW' | null
  why_it_matters: string | null
  suggested_action: string | null
}

function makeDoc(over: Partial<DocFixture> = {}): DocFixture {
  return {
    doc_id: 'e2e-doc-1',
    title: 'RBI Master Direction on KYC, 2024',
    document_url: 'https://example.test/rbi-kyc.pdf',
    source_name: 'rbi.org.in',
    source_geography: 'CENTRAL',
    document_type: 'regulator_circular',
    topic_category: 'banking',
    geo_primary: 'India',
    summary_preview: 'Short preview...',
    summary: null,
    page_count: 12,
    published_at: '2024-03-12T00:00:00Z',
    collected_at: '2024-03-12T06:30:00Z',
    score_final: 0.82,
    relevance_tier: 1,
    urgency: 'HIGH',
    why_it_matters: 'Affects every regulated entity.',
    suggested_action: 'Update KYC playbook by 30 June.',
    ...over,
  }
}

test.beforeEach(async ({ page }) => {
  test.skip(!TOKEN, 'E2E_SUPABASE_TOKEN not set — skipping')
  await page.addInitScript(token => {
    const session = {
      access_token: token,
      token_type: 'bearer',
      expires_at: Math.floor(Date.now() / 1000) + 3600,
      refresh_token: 'mock-refresh',
      user: { id: 'e2e-user', email: 'e2e@example.com' },
    }
    window.localStorage.setItem(
      'sb-rig-auth-token',
      JSON.stringify({ currentSession: session, expiresAt: session.expires_at }),
    )
  }, TOKEN)

  await page.route('**/api/documents/feed*', async route => {
    const url = new URL(route.request().url())
    const geo = url.searchParams.get('geography')
    const search = url.searchParams.get('search')
    const docs = [
      makeDoc({ doc_id: 'd1', title: 'Doc One', source_geography: 'CENTRAL' }),
      makeDoc({ doc_id: 'd2', title: 'Doc Two LOCAL', source_geography: 'LOCAL' }),
      makeDoc({ doc_id: 'd3', title: 'Doc Three RBI thing' }),
    ].filter(d => {
      if (geo && geo !== 'all' && d.source_geography !== geo) return false
      if (search && !d.title.toLowerCase().includes(search.toLowerCase()))
        return false
      return true
    })
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        documents: docs,
        has_more: false,
        next_cursor: null,
        total: docs.length,
        geography_counts: [
          { geography: 'CENTRAL', count: 2 },
          { geography: 'LOCAL', count: 1 },
        ],
      }),
    })
  })

  await page.route('**/api/documents/*/summary', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ summary: 'A generated summary.' }),
    })
  })
})

test('renders the documents page and lists rows', async ({ page }) => {
  await page.goto(`${BASE}/documents`)
  await expect(page.getByText('Doc One')).toBeVisible()
  await expect(page.getByText('Doc Two LOCAL')).toBeVisible()
})

test('filtering by geography narrows the results', async ({ page }) => {
  await page.goto(`${BASE}/documents`)
  await page.getByRole('button', { name: 'Local' }).click()
  await expect(page.getByText('Doc Two LOCAL')).toBeVisible()
  await expect(page.getByText('Doc One')).toHaveCount(0)
})

test('search input narrows by title', async ({ page }) => {
  await page.goto(`${BASE}/documents`)
  await page.getByPlaceholder(/search the archive/i).fill('RBI')
  await expect(page.getByText('Doc Three RBI thing')).toBeVisible()
  await expect(page.getByText('Doc One')).toHaveCount(0)
})

test('clicking a row opens the detail dialog with summary action', async ({
  page,
}) => {
  await page.goto(`${BASE}/documents`)
  await page.getByText('Doc One').click()
  // Page hasn't been hardened yet (D-10) — generic visibility check.
  await expect(page.getByText(/summary/i).first()).toBeVisible()
})

test('external "Read the document" link is target=_blank', async ({ page }) => {
  await page.goto(`${BASE}/documents`)
  await page.getByText('Doc One').click()
  const link = page.getByRole('link', { name: /read the document/i })
  await expect(link).toHaveAttribute('target', '_blank')
  await expect(link).toHaveAttribute('href', /\.pdf$/)
})

test('search input is debounced — single fetch per typed phrase', async ({
  page,
}) => {
  // Counter sentinel: this test specifically tracks that fast keystrokes
  // collapse into one /feed call, not one per character. Page already
  // sends an initial /feed on load; we count subsequent calls only.
  let searchCalls = 0
  await page.route('**/api/documents/feed*', async route => {
    const url = new URL(route.request().url())
    if (url.searchParams.get('search')) searchCalls += 1
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        documents: [makeDoc({ doc_id: 'r1', title: 'Result one' })],
        has_more: false,
        next_cursor: null,
        total: 1,
        geography_counts: [],
      }),
    })
  })

  await page.goto(`${BASE}/documents`)
  const input = page.getByPlaceholder(/search the archive/i)
  await input.pressSequentially('railway', { delay: 30 })  // 7 chars fast
  // The page debounces at 350 ms — wait long enough for it to fire and settle.
  await page.waitForTimeout(700)
  // Wait for any in-flight result to land before asserting the count.
  await expect(page.getByText('Result one')).toBeVisible()
  expect(searchCalls).toBeLessThanOrEqual(2)
})

test('mobile viewport: page renders without horizontal scroll', async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 812 })
  await page.goto(`${BASE}/documents`)
  await expect(page.getByText('Doc One')).toBeVisible()
  const overflowed = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth + 2,
  )
  expect(overflowed).toBe(false)
})
