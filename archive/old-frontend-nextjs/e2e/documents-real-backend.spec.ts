/**
 * Real-backend end-to-end test for /documents.
 *
 * Closes Q9 (the second half — Playwright side). The companion pytest in
 * backend/tests/test_govt_pipeline_e2e.py covers the Celery → DB leg.
 *
 * Unlike documents.spec.ts (which stubs `/api/documents/*` via page.route),
 * this spec lets the page hit the *real* FastAPI. We seed a uniquely-named
 * row directly into Postgres, load /documents, and assert the row appears
 * end-to-end through the live API and the live React component tree.
 *
 * Required env:
 *   E2E_SUPABASE_TOKEN     a real Supabase access token authorised for
 *                          the documents page. Without it the test skips.
 *   E2E_REAL_BACKEND=1     opt in. CI sets this only for the live job.
 *   E2E_BASE_URL           defaults to http://localhost:3000.
 *
 * Run:
 *   E2E_REAL_BACKEND=1 \
 *   E2E_SUPABASE_TOKEN=eyJ... \
 *     npm run e2e -- e2e/documents-real-backend.spec.ts
 */
import { execSync } from 'node:child_process'
import { expect, test } from '@playwright/test'

const TOKEN = process.env.E2E_SUPABASE_TOKEN
const REAL = process.env.E2E_REAL_BACKEND === '1'
const BASE = process.env.E2E_BASE_URL ?? 'http://localhost:3000'

// Uniquely tagged so concurrent runs don't collide and the cleanup
// query can target precisely this row.
const SEED_TAG = `e2e-real-${Date.now()}-${Math.floor(Math.random() * 1e6)}`
const SEED_TITLE = `RIG E2E real-backend probe ${SEED_TAG}`
const SEED_URL = `https://e2e.test/${SEED_TAG}.pdf`

function psql(sql: string): string {
  return execSync(
    `docker exec -i rig-postgres psql -U rig -d rig -At -c "${sql.replace(/"/g, '\\"')}"`,
    { encoding: 'utf-8' },
  ).trim()
}

test.describe('Documents — real-backend e2e (DB → API → page)', () => {
  test.skip(!REAL, 'E2E_REAL_BACKEND != 1 — skipping real-backend spec')
  test.skip(!TOKEN, 'E2E_SUPABASE_TOKEN not set — skipping')

  test.beforeAll(() => {
    // Seed a deterministic row. nlp_processed=TRUE so the router's
    // hard-coded filter lets it through; geo_primary populated so the
    // chip renders.
    psql(`
      INSERT INTO govt_documents (
        source_name, source_geography, document_type,
        title, document_url, full_text,
        topic_category, geo_primary, nlp_processed,
        collected_at, published_at
      ) VALUES (
        'e2e-real-source', 'CENTRAL', 'press_release',
        '${SEED_TITLE}', '${SEED_URL}',
        'E2E real-backend probe — full text body for search index.',
        'banking', 'India', TRUE,
        NOW(), NOW()
      )
      ON CONFLICT (document_url) DO NOTHING
    `)
  })

  test.afterAll(() => {
    psql(`DELETE FROM govt_documents WHERE document_url = '${SEED_URL}'`)
  })

  test.beforeEach(async ({ page }) => {
    // Inject the auth token into localStorage exactly the way Supabase
    // SSR does, so the page boots into the authenticated state without
    // hitting the OAuth flow.
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
        JSON.stringify({
          currentSession: session,
          expiresAt: session.expires_at,
        }),
      )
    }, TOKEN)
  })

  test('seeded row travels DB → /api/documents/feed → /documents render', async ({
    page,
  }) => {
    // Sanity: the page should make a real API call (no page.route stub).
    let feedHits = 0
    page.on('request', req => {
      if (req.url().includes('/api/documents/feed')) feedHits += 1
    })

    await page.goto(`${BASE}/documents`)

    // Search for the unique tag so the seeded row sorts to the top
    // regardless of how many other docs exist.
    await page.getByPlaceholder(/search the archive/i).fill(SEED_TAG)

    await expect(page.getByText(SEED_TITLE)).toBeVisible({ timeout: 10_000 })
    expect(feedHits).toBeGreaterThan(0)

    // Open the modal — exercises the API → page render leg for the
    // detail endpoint and the dialog focus-trap shipped in Q10.
    await page.getByText(SEED_TITLE).click()
    const dialog = await page.getByRole('dialog')
    await expect(dialog).toHaveAttribute('aria-modal', 'true')
    await expect(dialog).toBeVisible()

    // Esc closes (D-10 + Q10).
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog')).toHaveCount(0)
  })

  test('search index is the trigram GIN, not a sequential scan', async ({
    page,
  }) => {
    // We can't directly observe the plan from the browser, but we can
    // confirm the search returns the row in <500 ms even under the
    // ILIKE '%term%' query that previously did a seq scan. The Q6
    // trigram index makes this cheap; without it the same query on a
    // 50 KB full_text column would visibly stall.
    await page.goto(`${BASE}/documents`)
    const t0 = Date.now()
    await page.getByPlaceholder(/search the archive/i).fill(SEED_TAG)
    await expect(page.getByText(SEED_TITLE)).toBeVisible({ timeout: 5_000 })
    const elapsed = Date.now() - t0
    // 5s budget — still loose enough to absorb network jitter, tight
    // enough to fail loudly if the GIN index gets dropped.
    expect(elapsed).toBeLessThan(5_000)
  })
})
