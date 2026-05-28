/**
 * End-to-end smoke for the Signal Room (/signals) page.
 *
 * Setup: requires a logged-in session. Set E2E_SUPABASE_TOKEN to a valid
 * Supabase access token. Tests skip when absent so CI does not flap on
 * unconfigured environments.
 *
 * Run:
 *   cd frontend
 *   E2E_BASE_URL=http://localhost:3000 \
 *   E2E_SUPABASE_TOKEN=eyJ... \
 *     npm run e2e -- e2e/signals.spec.ts
 *
 * Coverage: per-platform matrix (all / twitter / reddit / telegram),
 * pagination, sentiment ledger, plus xfail-tagged regressions for
 * SIG-2 (401 sentiment redirect) per docs/qa/signals-defects.md.
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
      JSON.stringify({
        currentSession: session,
        expiresAt: session.expires_at,
      }),
    )
  }, TOKEN)
})

// ── Fixtures ─────────────────────────────────────────────────────────

interface SignalPostFixture {
  post_id: string
  platform: 'twitter' | 'reddit' | 'telegram'
  author_username: string | null
  post_text: string
  post_text_translated: string | null
  post_url: string | null
  upvotes: number
  comment_count: number
  share_count: number
  forward_count: number
  forwarded_from: string | null
  has_document: boolean
  sentiment_score: number | null
  matched_entities: string[]
  monitor_name: string | null
  posted_at: string | null
  collected_at: string
}

function makePost(
  overrides: Partial<SignalPostFixture> = {},
): SignalPostFixture {
  return {
    post_id: `e2e-${Math.random().toString(36).slice(2, 9)}`,
    platform: 'reddit',
    author_username: 'someone',
    post_text: 'Generic signal text.',
    post_text_translated: null,
    post_url: 'https://example.com/p/1',
    upvotes: 5,
    comment_count: 1,
    share_count: 0,
    forward_count: 0,
    forwarded_from: null,
    has_document: false,
    sentiment_score: 0.2,
    matched_entities: [],
    monitor_name: 'r/india',
    posted_at: new Date().toISOString(),
    collected_at: new Date().toISOString(),
    ...overrides,
  }
}

function feedBody(
  posts: SignalPostFixture[] = [],
  hasMore = false,
  nextCursor: string | null = null,
) {
  return { posts, has_more: hasMore, next_cursor: nextCursor }
}

const SENTIMENT_BODY = {
  sentiment_by_monitor: [
    {
      platform: 'reddit',
      display_name: 'r/india',
      identifier: 'india',
      post_count: 12,
      avg_sentiment: 0.18,
      positive_count: 7,
      negative_count: 2,
      neutral_count: 3,
    },
  ],
}

// ── Auth / Bearer / nav ──────────────────────────────────────────────

requiresAuth(
  'signals page loads and sends Bearer auth on feed request',
  async ({ page }) => {
    const feedRequest = page.waitForRequest(/\/api\/signals\/feed/)
    await page.goto('/signals')
    const req = await feedRequest

    expect(req.headers().authorization).toMatch(/^Bearer /)
  },
)

// ── Per-platform matrix ──────────────────────────────────────────────

const platformMatrix: Array<{
  tabName: RegExp
  platformQuery: string
  expectedText: string
}> = [
  { tabName: /All wires/i, platformQuery: 'all', expectedText: 'ALL_FIXTURE' },
  {
    tabName: /Forums/i,
    platformQuery: 'reddit',
    expectedText: 'REDDIT_FIXTURE',
  },
  {
    tabName: /Channels/i,
    platformQuery: 'telegram',
    expectedText: 'TELEGRAM_FIXTURE',
  },
]

for (const { tabName, platformQuery, expectedText } of platformMatrix) {
  requiresAuth(
    `tab "${platformQuery}" mounts and shows fixture`,
    async ({ page }) => {
      await page.route('**/api/signals/feed**', route => {
        const url = new URL(route.request().url())
        const platform = url.searchParams.get('platform') ?? 'all'
        const post = makePost({
          platform: (platform === 'all'
            ? 'reddit'
            : platform) as SignalPostFixture['platform'],
          post_text: `${platform.toUpperCase()}_FIXTURE`,
        })
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(feedBody([post])),
        })
      })
      await page.route('**/api/signals/sentiment**', route =>
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(SENTIMENT_BODY),
        }),
      )

      await page.goto('/signals')
      // Click the tab — initial load mostly shows ALL_FIXTURE; subsequent
      // tab clicks change platform query.
      if (platformQuery !== 'all') {
        await page.getByRole('button', { name: tabName }).first().click()
      }

      await expect(page.getByText(expectedText)).toBeVisible({
        timeout: 5000,
      })
    },
  )
}

// ── Pagination ───────────────────────────────────────────────────────

requiresAuth(
  'Pull more dispatches appends posts and hides when done',
  async ({ page }) => {
    let feedCalls = 0
    await page.route('**/api/signals/feed**', route => {
      feedCalls += 1
      const body =
        feedCalls === 1
          ? feedBody(
              [makePost({ post_id: 'p1', post_text: 'BATCH_ONE' })],
              true,
              new Date(Date.now() - 1000).toISOString(),
            )
          : feedBody(
              [makePost({ post_id: 'p2', post_text: 'BATCH_TWO' })],
              false,
            )
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(body),
      })
    })
    await page.route('**/api/signals/sentiment**', route =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(SENTIMENT_BODY),
      }),
    )

    await page.goto('/signals')
    await expect(page.getByText('BATCH_ONE')).toBeVisible()

    await page.getByRole('button', { name: /Pull more dispatches/i }).click()
    await expect(page.getByText('BATCH_TWO')).toBeVisible()
    await expect(page.getByText('BATCH_ONE')).toBeVisible()
    await expect(
      page.getByRole('button', { name: /Pull more dispatches/i }),
    ).toHaveCount(0)
  },
)

// ── Sentiment ledger ─────────────────────────────────────────────────

requiresAuth(
  'sentiment ledger shows monitor sentiment from /sentiment',
  async ({ page }) => {
    await page.route('**/api/signals/feed**', route =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(feedBody([makePost()])),
      }),
    )
    await page.route('**/api/signals/sentiment**', route =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(SENTIMENT_BODY),
      }),
    )

    await page.goto('/signals')
    await expect(page.getByText('r/india')).toBeVisible()
  },
)

// ── Empty state ──────────────────────────────────────────────────────

requiresAuth(
  'shows DeskMemo "street is quiet" when feed is empty',
  async ({ page }) => {
    await page.route('**/api/signals/feed**', route =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(feedBody()),
      }),
    )
    await page.route('**/api/signals/sentiment**', route =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ sentiment_by_monitor: [] }),
      }),
    )

    await page.goto('/signals')
    await expect(page.getByText(/The street is quiet/i)).toBeVisible()
  },
)

// ── SIG-2 regression: 401 from sentiment ─────────────────────────────

requiresAuth(
  'SIG-2: 401 from sentiment redirects to /login (xfail)',
  async ({ page }) => {
    test.fail(
      true,
      'SIG-2 — current code swallows 401 from /sentiment instead of redirecting',
    )
    await page.route('**/api/signals/feed**', route =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(feedBody([makePost()])),
      }),
    )
    await page.route('**/api/signals/sentiment**', route =>
      route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'unauthorized' }),
      }),
    )

    await page.goto('/signals')
    await page.waitForURL(/\/login/, { timeout: 4000 })
  },
)
