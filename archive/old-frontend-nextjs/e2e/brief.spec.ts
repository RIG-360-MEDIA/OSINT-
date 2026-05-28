/**
 * End-to-end smoke for the Daily Intelligence Brief (/brief) page.
 *
 * Strategy: mock all four /api/brief/* endpoints with page.route() so the test
 * runs without a populated DB, without Groq spend, and without the
 * 15–30s real generation latency. A separate "live" tag (commented at the
 * bottom) can run against a real backend when E2E_BRIEF_LIVE=1 is set.
 *
 * Run:
 *   cd frontend
 *   E2E_BASE_URL=http://localhost:3000 \
 *   E2E_SUPABASE_TOKEN=eyJ... \
 *     npm run e2e -- e2e/brief.spec.ts
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

// ── Fixtures ────────────────────────────────────────────────────────────────

const SAMPLE_BRIEF_MD = `# DAILY INTELLIGENCE BRIEF
## Sunday, 26 April 2026
*Generated for: Senior analyst, Hyderabad*

---

## SITUATION STATUS

The political mood in Telangana is restive after the budget speech.

---

## KEY DEVELOPMENTS

① Budget tabled
  Finance minister presented a Rs 2.9 lakh crore outlay.
② Police reshuffle
  Three IPS officers were transferred overnight.

---

## ENTITIES TODAY

CM Revanth Reddy
Delivered the budget speech.

---

## SIGNALS TO WATCH

⚑ Coalition strain
  Two MLAs hinted at floor-cross.

---

## FINANCIAL PULSE

Markets closed up 0.6%; rupee held at 83.4 against the dollar.

---

## SOURCE COVERAGE

The Hindu — politics; Mint — markets; Deccan Chronicle — local.

---
*30 articles · llama-3.3-70b-versatile · RIG SURVEILLANCE*`

function briefPayload(overrides: Partial<{
  content: string
  brief_date: string
  articles_used: number
  generated_at: string
}> = {}) {
  return {
    content: overrides.content ?? SAMPLE_BRIEF_MD,
    brief_date: overrides.brief_date ?? '2026-04-26',
    articles_used: overrides.articles_used ?? 30,
    generated_at: overrides.generated_at ?? new Date().toISOString(),
  }
}

// ── Tests ───────────────────────────────────────────────────────────────────

requiresAuth('brief page renders all six sections from /today', async ({ page }) => {
  await page.route('**/api/brief/today', route =>
    route.fulfill({ status: 200, body: JSON.stringify(briefPayload()) }),
  )
  await page.route('**/api/brief/history/list', route =>
    route.fulfill({ status: 200, body: JSON.stringify({ briefs: [] }) }),
  )

  await page.goto('/brief')

  await expect(page.getByText('SITUATION STATUS')).toBeVisible()
  await expect(page.getByText('KEY DEVELOPMENTS')).toBeVisible()
  await expect(page.getByText('ENTITIES TODAY')).toBeVisible()
  await expect(page.getByText('SIGNALS TO WATCH')).toBeVisible()
  await expect(page.getByText('FINANCIAL PULSE')).toBeVisible()
  await expect(page.getByText('SOURCE COVERAGE')).toBeVisible()
  await expect(page.getByText('Budget tabled')).toBeVisible()
  await expect(page.getByText('Coalition strain')).toBeVisible()
})

requiresAuth('shows EmptyState when /today returns 404', async ({ page }) => {
  await page.route('**/api/brief/today', route =>
    route.fulfill({ status: 404, body: JSON.stringify({ detail: 'No brief for today' }) }),
  )
  await page.route('**/api/brief/history/list', route =>
    route.fulfill({ status: 200, body: JSON.stringify({ briefs: [] }) }),
  )

  await page.goto('/brief')

  await expect(page.getByRole('button', { name: /generate/i })).toBeVisible()
})

requiresAuth('shows too-early state when /generate returns 425', async ({ page }) => {
  await page.route('**/api/brief/today', route =>
    route.fulfill({ status: 404, body: JSON.stringify({ detail: 'No brief for today' }) }),
  )
  await page.route('**/api/brief/history/list', route =>
    route.fulfill({ status: 200, body: JSON.stringify({ briefs: [] }) }),
  )
  await page.route('**/api/brief/generate', route =>
    route.fulfill({
      status: 425,
      body: JSON.stringify({ detail: 'Only 5 relevant articles found.' }),
    }),
  )

  await page.goto('/brief')
  await page.getByRole('button', { name: /generate/i }).click()
  await expect(page.getByText(/feed.*warming|preparing|too early|few minutes/i)).toBeVisible({
    timeout: 5000,
  })
})

requiresAuth('shows error state on 500 from /today', async ({ page }) => {
  await page.route('**/api/brief/today', route =>
    route.fulfill({ status: 500, body: JSON.stringify({ detail: 'boom' }) }),
  )
  await page.route('**/api/brief/history/list', route =>
    route.fulfill({ status: 200, body: JSON.stringify({ briefs: [] }) }),
  )

  await page.goto('/brief')
  await expect(page.getByText(/try again|error|failed/i)).toBeVisible({ timeout: 5000 })
})

requiresAuth('history strip fetches a past brief on click', async ({ page }) => {
  await page.route('**/api/brief/today', route =>
    route.fulfill({ status: 200, body: JSON.stringify(briefPayload()) }),
  )
  await page.route('**/api/brief/history/list', route =>
    route.fulfill({
      status: 200,
      body: JSON.stringify({
        briefs: [
          { date: '2026-04-25', articles_used: 28, generated_at: new Date().toISOString() },
          { date: '2026-04-24', articles_used: 22, generated_at: new Date().toISOString() },
        ],
      }),
    }),
  )

  let pastFetched = 0
  await page.route('**/api/brief/2026-04-25', route => {
    pastFetched++
    return route.fulfill({
      status: 200,
      body: JSON.stringify(briefPayload({ brief_date: '2026-04-25', articles_used: 28 })),
    })
  })

  await page.goto('/brief')
  await page.getByText(/2026-04-25|25/).first().click()
  await expect.poll(() => pastFetched, { timeout: 5000 }).toBeGreaterThan(0)
})

// ── Defect-tracking spec (D-BRIEF-8: no debounce on Generate) ──────────────

requiresAuth(
  'D-BRIEF-8: rapid double-click on Generate fires only one POST [currently FAILS]',
  async ({ page }) => {
    await page.route('**/api/brief/today', route =>
      route.fulfill({ status: 404, body: JSON.stringify({ detail: 'No brief for today' }) }),
    )
    await page.route('**/api/brief/history/list', route =>
      route.fulfill({ status: 200, body: JSON.stringify({ briefs: [] }) }),
    )

    let postCount = 0
    await page.route('**/api/brief/generate', async route => {
      postCount++
      await new Promise(r => setTimeout(r, 200))
      return route.fulfill({ status: 200, body: JSON.stringify(briefPayload()) })
    })

    await page.goto('/brief')
    const btn = page.getByRole('button', { name: /generate/i })
    await Promise.all([btn.click(), btn.click()])
    await page.waitForTimeout(500)

    // Will currently fail — D-BRIEF-8 lets both clicks through.
    expect(postCount).toBe(1)
  },
)
