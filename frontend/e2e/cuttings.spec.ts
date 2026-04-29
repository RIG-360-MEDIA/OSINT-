/**
 * End-to-end smoke for the Cutting Room (/cuttings) page.
 *
 * Setup: requires a logged-in session. Set E2E_SUPABASE_TOKEN to a valid
 * Supabase access token. Tests skip when the token is absent so CI does
 * not flap on unconfigured environments.
 *
 * Run:
 *   cd frontend
 *   E2E_BASE_URL=http://localhost:4000 \
 *   E2E_SUPABASE_TOKEN=eyJ... \
 *     npm run e2e -- e2e/cuttings.spec.ts
 *
 * Covers the contracts the Cuttings audit (2026-04-28) flagged as
 * production-readiness gates: F3 (friendlier fetch errors), F5 (filter
 * a11y), F7 (the user-visible newsstand → modal → clipping → close flow).
 */
import { expect, test } from '@playwright/test'

const TOKEN = process.env.E2E_SUPABASE_TOKEN
const requiresAuth = test.extend({})

requiresAuth.beforeEach(async ({ page }) => {
  test.skip(!TOKEN, 'E2E_SUPABASE_TOKEN not set — skipping authenticated E2E')
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
})

// ── Fixtures ─────────────────────────────────────────────────────────

const TODAY_ISO = new Date().toISOString().slice(0, 10)

const PAPER_TIMES = {
  newspaper_id: 'paper-times-of-india',
  name: 'Times of India',
  language: 'en',
  edition_date: TODAY_ISO,
  clip_count: 12,
  pdf_available: true,
}

const PAPER_SAKSHI = {
  newspaper_id: 'paper-sakshi',
  name: 'Sakshi',
  language: 'te',
  edition_date: TODAY_ISO,
  clip_count: 4,
  pdf_available: true,
}

const SAMPLE_CLIP = {
  clipping_id: 'clip-1',
  newspaper_name: 'Times of India',
  newspaper_language: 'en',
  edition_date: TODAY_ISO,
  page_number: 1,
  headline: 'Cabinet clears new policy framework',
  headline_translated: null,
  text_preview: 'The Union Cabinet on Monday cleared the new policy …',
  translated_preview: null,
  has_image: true,
  relevance_score: 0.6,
  relevance_explanation: 'Mentions Modi',
  collected_at: new Date().toISOString(),
}

function papersBody(papers = [PAPER_TIMES, PAPER_SAKSHI]) {
  return { papers }
}

function feedBody(opts: { clippings?: typeof SAMPLE_CLIP[] } = {}) {
  return {
    clippings: opts.clippings ?? [],
    has_more: false,
    next_cursor: null,
    newspapers: [
      { name: 'Times of India', language: 'en', count: 12 },
      { name: 'Sakshi', language: 'te', count: 4 },
    ],
  }
}

// ── Tests ────────────────────────────────────────────────────────────

requiresAuth('cuttings page loads and sends Bearer auth on papers request', async ({ page }) => {
  await page.route('**/api/clippings/papers**', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(papersBody()),
    }),
  )
  const papersRequest = page.waitForRequest(/\/api\/clippings\/papers/)
  await page.goto('/cuttings')
  const req = await papersRequest

  expect(new URL(req.url()).searchParams.get('days')).toBe('7')
  expect(req.headers().authorization).toMatch(/^Bearer /)
})

requiresAuth('renders a masthead per paper', async ({ page }) => {
  await page.route('**/api/clippings/papers**', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(papersBody()),
    }),
  )

  await page.goto('/cuttings')
  await expect(page.getByText('Times of India')).toBeVisible()
  await expect(page.getByText('Sakshi')).toBeVisible()
  await expect(page.locator('[data-testid="masthead-card"]')).toHaveCount(2)
})

requiresAuth('clicking a masthead opens the edition modal with that paper\'s clippings', async ({ page }) => {
  await page.route('**/api/clippings/papers**', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(papersBody()),
    }),
  )
  await page.route('**/api/clippings/feed**', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(feedBody({ clippings: [SAMPLE_CLIP] })),
    }),
  )

  await page.goto('/cuttings')
  await page.getByText('Times of India').first().click()

  const modal = page.locator('[data-testid="edition-modal"]')
  await expect(modal).toBeVisible()
  await expect(modal.getByText('Cabinet clears new policy framework')).toBeVisible()
})

requiresAuth('?paper=<id> deep-links straight to the modal on mount', async ({ page }) => {
  await page.route('**/api/clippings/papers**', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(papersBody()),
    }),
  )
  await page.route('**/api/clippings/feed**', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(feedBody({ clippings: [SAMPLE_CLIP] })),
    }),
  )

  await page.goto(`/cuttings?paper=${PAPER_TIMES.newspaper_id}`)
  await expect(page.locator('[data-testid="edition-modal"]')).toBeVisible()
})

requiresAuth('Esc closes the modal and clears ?paper from the URL', async ({ page }) => {
  await page.route('**/api/clippings/papers**', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(papersBody()),
    }),
  )
  await page.route('**/api/clippings/feed**', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(feedBody({ clippings: [SAMPLE_CLIP] })),
    }),
  )

  await page.goto(`/cuttings?paper=${PAPER_TIMES.newspaper_id}`)
  await expect(page.locator('[data-testid="edition-modal"]')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.locator('[data-testid="edition-modal"]')).not.toBeVisible()
  await expect(page).not.toHaveURL(/[?&]paper=/)
})

requiresAuth('language filter narrows the masthead set (F5 a11y rail)', async ({ page }) => {
  await page.route('**/api/clippings/papers**', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(papersBody()),
    }),
  )

  await page.goto('/cuttings')
  await expect(page.locator('[data-testid="masthead-card"]')).toHaveCount(2)

  // F5: filter rail must expose role=group with a label so screen readers
  // announce the controls as a unit.
  const rail = page.locator('[data-testid="newsstand-filter-rail"]')
  await expect(rail).toHaveAttribute('role', 'group')
  await expect(rail).toHaveAttribute('aria-label', /language/i)

  // Switching to Telugu should hide Times of India.
  await page.getByRole('button', { name: 'తెలుగు' }).click()
  await expect(page.locator('[data-testid="masthead-card"]')).toHaveCount(1)
  await expect(page.getByText('Sakshi')).toBeVisible()
})

requiresAuth('500 from /papers shows the friendly desk-memo error (F3)', async ({ page }) => {
  await page.route('**/api/clippings/papers**', route =>
    route.fulfill({ status: 500, body: 'kaboom' }),
  )

  await page.goto('/cuttings')
  // F3: status numbers must NOT bleed into the UI.
  await expect(page.getByText(/HTTP 500/i)).toHaveCount(0)
  await expect(page.getByText(/press room/i)).toBeVisible()
})

requiresAuth('empty papers response renders nothing without crashing', async ({ page }) => {
  await page.route('**/api/clippings/papers**', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ papers: [] }),
    }),
  )

  await page.goto('/cuttings')
  await expect(page.locator('[data-testid="masthead-card"]')).toHaveCount(0)
  await expect(page.getByText(/no editions on the desk today/i)).toBeVisible()
})
