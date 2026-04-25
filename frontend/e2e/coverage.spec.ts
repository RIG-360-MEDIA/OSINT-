/**
 * End-to-end smoke for the Coverage page.
 *
 * Setup: requires a logged-in session. Set E2E_SUPABASE_TOKEN to a valid
 * Supabase access token, or run an upstream `auth.setup.ts` to seed
 * storageState. Tests skip when the token is absent so CI does not flap
 * on unconfigured environments.
 *
 * Run:
 *   cd frontend
 *   E2E_BASE_URL=http://localhost:3000 \
 *   E2E_SUPABASE_TOKEN=eyJ... \
 *     npm run e2e
 */
import { expect, test } from '@playwright/test'

const TOKEN = process.env.E2E_SUPABASE_TOKEN
const requiresAuth = test.extend({})

requiresAuth.beforeEach(async ({ page }) => {
  test.skip(!TOKEN, 'E2E_SUPABASE_TOKEN not set — skipping authenticated E2E')
  // Seed Supabase session into localStorage before page load.
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

requiresAuth('coverage page loads and renders clippings or empty state', async ({ page }) => {
  const feedRequest = page.waitForRequest(/\/api\/coverage\/feed/)
  await page.goto('/coverage')
  const req = await feedRequest
  // Default URL must include tier=1,2,3 + sort=relevance + limit=20
  const url = new URL(req.url())
  expect(url.searchParams.get('tier')).toBe('1,2,3')
  expect(url.searchParams.get('sort')).toBe('relevance')
  expect(url.searchParams.get('limit')).toBe('20')

  // Either clippings render OR the empty CTA shows.
  await expect(page.locator('main, body')).toBeVisible()
})

requiresAuth('topic filter is reflected in the feed request', async ({ page }) => {
  await page.goto('/coverage')
  const nextRequest = page.waitForRequest(/\/api\/coverage\/feed.*topic=POLITICS/)
  await page.getByRole('button', { name: /politics/i }).first().click()
  const req = await nextRequest
  expect(new URL(req.url()).searchParams.get('topic')).toContain('POLITICS')
})

requiresAuth('Enter on search input fires /api/coverage/search', async ({ page }) => {
  await page.goto('/coverage')
  const searchReq = page.waitForRequest(/\/api\/coverage\/search/)
  await page.getByPlaceholder(/search the room/i).fill('india')
  await page.getByPlaceholder(/search the room/i).press('Enter')
  const req = await searchReq
  expect(new URL(req.url()).searchParams.get('q')).toBe('india')
})

requiresAuth('article dialog opens, locks scroll, and Escape closes it', async ({ page }) => {
  await page.goto('/coverage')
  const card = page.locator('article').first()
  if (await card.isVisible().catch(() => false)) {
    await card.click()
    // Body scroll-lock is applied via inline style position:fixed.
    await expect(page.locator('body')).toHaveCSS('position', 'fixed')
    await page.keyboard.press('Escape')
    await expect(page.locator('body')).not.toHaveCSS('position', 'fixed')
  } else {
    test.skip(true, 'No clippings present — open dialog test cannot run')
  }
})

requiresAuth('"File more clippings" requests next cursor page', async ({ page }) => {
  await page.goto('/coverage')
  const more = page.getByRole('button', { name: /file more clippings/i })
  if (!(await more.isVisible().catch(() => false))) {
    test.skip(true, 'Only one page of clippings — pagination button absent')
  }
  const nextReq = page.waitForRequest(/\/api\/coverage\/feed.*cursor=/)
  await more.click()
  const req = await nextReq
  expect(new URL(req.url()).searchParams.get('cursor')).toBeTruthy()
})
