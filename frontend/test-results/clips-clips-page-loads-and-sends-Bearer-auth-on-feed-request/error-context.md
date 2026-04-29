# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: clips.spec.ts >> clips page loads and sends Bearer auth on feed request
- Location: e2e\clips.spec.ts:74:1

# Error details

```
Test timeout of 30000ms exceeded.
```

```
Error: page.goto: net::ERR_ABORTED; maybe frame was detached?
Call log:
  - navigating to "http://localhost:4000/clips", waiting until "load"

```

```
Error: page.waitForRequest: Test timeout of 30000ms exceeded.
=========================== logs ===========================
waiting for request /\/api\/clips\/feed/
============================================================
```

# Test source

```ts
  1   | /**
  2   |  * End-to-end smoke for the Clip Room (/clips) page.
  3   |  *
  4   |  * Setup: requires a logged-in session. Set E2E_SUPABASE_TOKEN to a valid
  5   |  * Supabase access token. Tests skip when the token is absent so CI does
  6   |  * not flap on unconfigured environments.
  7   |  *
  8   |  * Run:
  9   |  *   cd frontend
  10  |  *   E2E_BASE_URL=http://localhost:3000 \
  11  |  *   E2E_SUPABASE_TOKEN=eyJ... \
  12  |  *     npm run e2e -- e2e/clips.spec.ts
  13  |  */
  14  | import { expect, test } from '@playwright/test'
  15  | 
  16  | const TOKEN = process.env.E2E_SUPABASE_TOKEN
  17  | const requiresAuth = test.extend({})
  18  | 
  19  | requiresAuth.beforeEach(async ({ page }) => {
  20  |   test.skip(!TOKEN, 'E2E_SUPABASE_TOKEN not set — skipping authenticated E2E')
  21  |   await page.addInitScript(token => {
  22  |     const session = {
  23  |       access_token: token,
  24  |       token_type: 'bearer',
  25  |       expires_at: Math.floor(Date.now() / 1000) + 3600,
  26  |       refresh_token: 'mock-refresh',
  27  |       user: { id: 'e2e-user', email: 'e2e@example.com' },
  28  |     }
  29  |     window.localStorage.setItem(
  30  |       'sb-rig-auth-token',
  31  |       JSON.stringify({ currentSession: session, expiresAt: session.expires_at }),
  32  |     )
  33  |   }, TOKEN)
  34  | })
  35  | 
  36  | // ── Fixtures ─────────────────────────────────────────────────────────
  37  | 
  38  | const SAMPLE_CLIP = {
  39  |   clip_id: 'e2e-1',
  40  |   video_id: 'dQw4w9WgXcQ',
  41  |   video_title: 'Modi at parliament',
  42  |   channel_name: 'NDTV',
  43  |   channel_id: 'UCe2eTestChannelId000001',
  44  |   video_url: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
  45  |   embed_url: 'https://www.youtube.com/embed/dQw4w9WgXcQ?start=60&end=90',
  46  |   clip_start_seconds: 60,
  47  |   clip_end_seconds: 90,
  48  |   transcript_segment: 'Modi spoke about reforms and growth.',
  49  |   transcript_translated: 'Modi spoke about reforms and growth.',
  50  |   matched_entity: 'Modi',
  51  |   transcript_language: 'en',
  52  |   video_published_at: new Date().toISOString(),
  53  |   collected_at: new Date().toISOString(),
  54  | }
  55  | 
  56  | function feedBody(opts: {
  57  |   clips?: typeof SAMPLE_CLIP[]
  58  |   user_entities?: string[]
  59  |   channels?: Array<{ channel_id: string; channel_name: string; clip_count: number }>
  60  |   total?: number
  61  | } = {}) {
  62  |   return {
  63  |     clips: opts.clips ?? [],
  64  |     has_more: false,
  65  |     next_cursor: null,
  66  |     total: opts.total ?? 0,
  67  |     channels: opts.channels ?? [],
  68  |     user_entities: opts.user_entities ?? [],
  69  |   }
  70  | }
  71  | 
  72  | // ── Tests ────────────────────────────────────────────────────────────
  73  | 
  74  | requiresAuth('clips page loads and sends Bearer auth on feed request', async ({ page }) => {
> 75  |   const feedRequest = page.waitForRequest(/\/api\/clips\/feed/)
      |                            ^ Error: page.waitForRequest: Test timeout of 30000ms exceeded.
  76  |   await page.goto('/clips')
  77  |   const req = await feedRequest
  78  | 
  79  |   expect(new URL(req.url()).searchParams.get('limit')).toBe('20')
  80  |   expect(req.headers().authorization).toMatch(/^Bearer /)
  81  | })
  82  | 
  83  | requiresAuth('renders 3 clip cards with numerals 01/02/03', async ({ page }) => {
  84  |   await page.route('**/api/clips/feed**', route =>
  85  |     route.fulfill({
  86  |       status: 200,
  87  |       contentType: 'application/json',
  88  |       body: JSON.stringify(
  89  |         feedBody({
  90  |           user_entities: ['Modi'],
  91  |           clips: [
  92  |             { ...SAMPLE_CLIP, clip_id: 'a', video_title: 'Headline A' },
  93  |             { ...SAMPLE_CLIP, clip_id: 'b', video_title: 'Headline B' },
  94  |             { ...SAMPLE_CLIP, clip_id: 'c', video_title: 'Headline C' },
  95  |           ],
  96  |           total: 3,
  97  |         }),
  98  |       ),
  99  |     }),
  100 |   )
  101 | 
  102 |   await page.goto('/clips')
  103 |   await expect(page.getByText('Headline A')).toBeVisible()
  104 |   await expect(page.getByText('Headline B')).toBeVisible()
  105 |   await expect(page.getByText('Headline C')).toBeVisible()
  106 |   await expect(page.getByText('01')).toBeVisible()
  107 |   await expect(page.getByText('02')).toBeVisible()
  108 |   await expect(page.getByText('03')).toBeVisible()
  109 | })
  110 | 
  111 | requiresAuth('"Roll the tape" loads YouTube iframe with autoplay', async ({ page }) => {
  112 |   await page.route('**/api/clips/feed**', route =>
  113 |     route.fulfill({
  114 |       status: 200,
  115 |       contentType: 'application/json',
  116 |       body: JSON.stringify(
  117 |         feedBody({ user_entities: ['Modi'], clips: [SAMPLE_CLIP], total: 1 }),
  118 |       ),
  119 |     }),
  120 |   )
  121 | 
  122 |   await page.goto('/clips')
  123 |   await page.getByRole('button', { name: /roll the tape/i }).click()
  124 | 
  125 |   const iframe = page.locator('iframe').first()
  126 |   await expect(iframe).toBeVisible()
  127 |   const src = await iframe.getAttribute('src')
  128 |   expect(src).toContain('autoplay=1')
  129 |   expect(src).toContain('start=60')
  130 | })
  131 | 
  132 | requiresAuth('entity filter click reloads feed with entity= param', async ({ page }) => {
  133 |   await page.route('**/api/clips/feed**', route => {
  134 |     const url = new URL(route.request().url())
  135 |     const entity = url.searchParams.get('entity')
  136 |     route.fulfill({
  137 |       status: 200,
  138 |       contentType: 'application/json',
  139 |       body: JSON.stringify(
  140 |         feedBody({
  141 |           user_entities: ['Modi', 'Adani'],
  142 |           clips: [{ ...SAMPLE_CLIP, matched_entity: entity || 'Modi' }],
  143 |           total: 1,
  144 |         }),
  145 |       ),
  146 |     })
  147 |   })
  148 | 
  149 |   await page.goto('/clips')
  150 |   await expect(page.getByText('Modi at parliament')).toBeVisible()
  151 | 
  152 |   const nextReq = page.waitForRequest(/\/api\/clips\/feed.*entity=Adani/)
  153 |   await page.getByRole('button', { name: 'Adani' }).click()
  154 |   const req = await nextReq
  155 |   expect(new URL(req.url()).searchParams.get('entity')).toBe('Adani')
  156 | })
  157 | 
  158 | requiresAuth('"Take to Analyst" navigates to /analyst with question', async ({ page }) => {
  159 |   await page.route('**/api/clips/feed**', route =>
  160 |     route.fulfill({
  161 |       status: 200,
  162 |       contentType: 'application/json',
  163 |       body: JSON.stringify(
  164 |         feedBody({ user_entities: ['Modi'], clips: [SAMPLE_CLIP], total: 1 }),
  165 |       ),
  166 |     }),
  167 |   )
  168 | 
  169 |   await page.goto('/clips')
  170 |   await page.getByRole('button', { name: /take to analyst/i }).click()
  171 |   await expect(page).toHaveURL(/\/analyst\?question=.+Modi/)
  172 | })
  173 | 
  174 | requiresAuth('empty feed renders the "No clips on the wire" memo', async ({ page }) => {
  175 |   await page.route('**/api/clips/feed**', route =>
```