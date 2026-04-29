/**
 * End-to-end smoke for the Clip Room (/clips) page.
 *
 * Setup: requires a logged-in session. Set E2E_SUPABASE_TOKEN to a valid
 * Supabase access token. Tests skip when the token is absent so CI does
 * not flap on unconfigured environments.
 *
 * Run:
 *   cd frontend
 *   E2E_BASE_URL=http://localhost:3000 \
 *   E2E_SUPABASE_TOKEN=eyJ... \
 *     npm run e2e -- e2e/clips.spec.ts
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

const SAMPLE_CLIP = {
  clip_id: 'e2e-1',
  video_id: 'dQw4w9WgXcQ',
  video_title: 'Modi at parliament',
  channel_name: 'NDTV',
  channel_id: 'UCe2eTestChannelId000001',
  video_url: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
  embed_url: 'https://www.youtube.com/embed/dQw4w9WgXcQ?start=60&end=90',
  clip_start_seconds: 60,
  clip_end_seconds: 90,
  transcript_segment: 'Modi spoke about reforms and growth.',
  transcript_translated: 'Modi spoke about reforms and growth.',
  matched_entity: 'Modi',
  transcript_language: 'en',
  video_published_at: new Date().toISOString(),
  collected_at: new Date().toISOString(),
}

function feedBody(opts: {
  clips?: typeof SAMPLE_CLIP[]
  user_entities?: string[]
  channels?: Array<{ channel_id: string; channel_name: string; clip_count: number }>
  total?: number
} = {}) {
  return {
    clips: opts.clips ?? [],
    has_more: false,
    next_cursor: null,
    total: opts.total ?? 0,
    channels: opts.channels ?? [],
    user_entities: opts.user_entities ?? [],
  }
}

// ── Tests ────────────────────────────────────────────────────────────

requiresAuth('clips page loads and sends Bearer auth on feed request', async ({ page }) => {
  const feedRequest = page.waitForRequest(/\/api\/clips\/feed/)
  await page.goto('/clips')
  const req = await feedRequest

  expect(new URL(req.url()).searchParams.get('limit')).toBe('20')
  expect(req.headers().authorization).toMatch(/^Bearer /)
})

requiresAuth('renders 3 clip cards with numerals 01/02/03', async ({ page }) => {
  await page.route('**/api/clips/feed**', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(
        feedBody({
          user_entities: ['Modi'],
          clips: [
            { ...SAMPLE_CLIP, clip_id: 'a', video_title: 'Headline A' },
            { ...SAMPLE_CLIP, clip_id: 'b', video_title: 'Headline B' },
            { ...SAMPLE_CLIP, clip_id: 'c', video_title: 'Headline C' },
          ],
          total: 3,
        }),
      ),
    }),
  )

  await page.goto('/clips')
  await expect(page.getByText('Headline A')).toBeVisible()
  await expect(page.getByText('Headline B')).toBeVisible()
  await expect(page.getByText('Headline C')).toBeVisible()
  await expect(page.getByText('01')).toBeVisible()
  await expect(page.getByText('02')).toBeVisible()
  await expect(page.getByText('03')).toBeVisible()
})

requiresAuth('"Roll the tape" loads YouTube iframe with autoplay', async ({ page }) => {
  await page.route('**/api/clips/feed**', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(
        feedBody({ user_entities: ['Modi'], clips: [SAMPLE_CLIP], total: 1 }),
      ),
    }),
  )

  await page.goto('/clips')
  await page.getByRole('button', { name: /roll the tape/i }).click()

  const iframe = page.locator('iframe').first()
  await expect(iframe).toBeVisible()
  const src = await iframe.getAttribute('src')
  expect(src).toContain('autoplay=1')
  expect(src).toContain('start=60')
})

requiresAuth('entity filter click reloads feed with entity= param', async ({ page }) => {
  await page.route('**/api/clips/feed**', route => {
    const url = new URL(route.request().url())
    const entity = url.searchParams.get('entity')
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(
        feedBody({
          user_entities: ['Modi', 'Adani'],
          clips: [{ ...SAMPLE_CLIP, matched_entity: entity || 'Modi' }],
          total: 1,
        }),
      ),
    })
  })

  await page.goto('/clips')
  await expect(page.getByText('Modi at parliament')).toBeVisible()

  const nextReq = page.waitForRequest(/\/api\/clips\/feed.*entity=Adani/)
  await page.getByRole('button', { name: 'Adani' }).click()
  const req = await nextReq
  expect(new URL(req.url()).searchParams.get('entity')).toBe('Adani')
})

requiresAuth('"Take to Analyst" navigates to /analyst with question', async ({ page }) => {
  await page.route('**/api/clips/feed**', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(
        feedBody({ user_entities: ['Modi'], clips: [SAMPLE_CLIP], total: 1 }),
      ),
    }),
  )

  await page.goto('/clips')
  await page.getByRole('button', { name: /take to analyst/i }).click()
  await expect(page).toHaveURL(/\/analyst\?question=.+Modi/)
})

requiresAuth('empty feed renders the "No clips on the wire" memo', async ({ page }) => {
  await page.route('**/api/clips/feed**', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(feedBody({ user_entities: ['Modi'] })),
    }),
  )

  await page.goto('/clips')
  await expect(page.getByText(/No clips on the wire yet/i)).toBeVisible()
})

requiresAuth('500 from feed renders the desk-memo error card', async ({ page }) => {
  await page.route('**/api/clips/feed**', route =>
    route.fulfill({ status: 500, body: 'kaboom' }),
  )

  await page.goto('/clips')
  await expect(page.getByText(/feed is refusing to return/i)).toBeVisible()
})

requiresAuth('401 from feed redirects to /login (F4 fix)', async ({ page }) => {
  await page.route('**/api/clips/feed**', route =>
    route.fulfill({ status: 401, body: 'unauthorized' }),
  )

  await page.goto('/clips')
  await expect(page).toHaveURL(/\/login/)
})

requiresAuth('FilterPill exposes aria-pressed for screen readers (F13)', async ({ page }) => {
  await page.route('**/api/clips/feed**', route =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(
        feedBody({
          user_entities: ['Modi'],
          clips: [SAMPLE_CLIP],
          total: 1,
        }),
      ),
    }),
  )

  await page.goto('/clips')
  const pill = page.getByRole('button', { name: 'Modi' })
  await expect(pill).toHaveAttribute('aria-pressed', 'false')
  await pill.click()
  await expect(pill).toHaveAttribute('aria-pressed', 'true')
})
