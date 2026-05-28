# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: clips.spec.ts >> FilterPill exposes aria-pressed for screen readers (F13)
- Location: e2e\clips.spec.ts:205:1

# Error details

```
Test timeout of 30000ms exceeded.
```

```
Error: expect(locator).toHaveAttribute(expected) failed

Locator: getByRole('button', { name: 'Modi' })
Expected: "false"
Error: element(s) not found

Call log:
  - Expect "toHaveAttribute" with timeout 5000ms
  - waiting for getByRole('button', { name: 'Modi' })

```

# Page snapshot

```yaml
- generic [active] [ref=e1]:
  - main [ref=e2]:
    - generic [ref=e5]:
      - link "Rig Surveillance" [ref=e6] [cursor=pointer]:
        - /url: /
        - img [ref=e8]
        - generic [ref=e12]: Rig
        - generic [ref=e13]: Surveillance
        - generic [ref=e14]: .
      - generic [ref=e15]:
        - generic [ref=e18]: Returning Reader
        - heading "Credentials, please." [level=1] [ref=e19]:
          - text: Credentials,
          - emphasis [ref=e20]: please.
        - paragraph [ref=e21]: The room remembers you. Sign in and the brief you missed will be waiting — filed, annotated, ordered by consequence.
        - generic [ref=e22]:
          - generic [ref=e23]:
            - generic [ref=e24]: I.
            - generic [ref=e25]: The morning brief, filed by 06:00 IST
          - generic [ref=e26]:
            - generic [ref=e27]: II.
            - generic [ref=e28]: Coverage rooms across 17 languages
          - generic [ref=e29]:
            - generic [ref=e30]: III.
            - generic [ref=e31]: An analyst you can audit, line by line
          - generic [ref=e32]:
            - generic [ref=e33]: IV.
            - generic [ref=e34]: Signals weighted against their history
      - generic [ref=e35]: Scientia · Potentia · Est
    - generic [ref=e37]:
      - generic [ref=e38]: Access · Vol. I
      - heading "Sign in" [level=2] [ref=e39]:
        - text: Sign
        - emphasis [ref=e40]: in
      - paragraph [ref=e41]: Welcome back to the desk of record.
      - generic [ref=e42]:
        - generic [ref=e43]:
          - generic [ref=e44]: Email
          - textbox "Email" [ref=e45]:
            - /placeholder: you@example.com
        - generic [ref=e46]:
          - generic [ref=e47]: Passphrase
          - textbox "Passphrase" [ref=e48]:
            - /placeholder: ••••••••
        - button "Enter the room →" [ref=e49] [cursor=pointer]:
          - text: Enter the room
          - generic [ref=e50]: →
        - paragraph [ref=e51]:
          - text: No credentials yet?
          - link "Request press access" [ref=e52] [cursor=pointer]:
            - /url: /signup
  - alert [ref=e53]
  - button "Open Next.js Dev Tools" [ref=e59] [cursor=pointer]:
    - img [ref=e60]
```

# Test source

```ts
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
  176 |     route.fulfill({
  177 |       status: 200,
  178 |       contentType: 'application/json',
  179 |       body: JSON.stringify(feedBody({ user_entities: ['Modi'] })),
  180 |     }),
  181 |   )
  182 | 
  183 |   await page.goto('/clips')
  184 |   await expect(page.getByText(/No clips on the wire yet/i)).toBeVisible()
  185 | })
  186 | 
  187 | requiresAuth('500 from feed renders the desk-memo error card', async ({ page }) => {
  188 |   await page.route('**/api/clips/feed**', route =>
  189 |     route.fulfill({ status: 500, body: 'kaboom' }),
  190 |   )
  191 | 
  192 |   await page.goto('/clips')
  193 |   await expect(page.getByText(/feed is refusing to return/i)).toBeVisible()
  194 | })
  195 | 
  196 | requiresAuth('401 from feed redirects to /login (F4 fix)', async ({ page }) => {
  197 |   await page.route('**/api/clips/feed**', route =>
  198 |     route.fulfill({ status: 401, body: 'unauthorized' }),
  199 |   )
  200 | 
  201 |   await page.goto('/clips')
  202 |   await expect(page).toHaveURL(/\/login/)
  203 | })
  204 | 
  205 | requiresAuth('FilterPill exposes aria-pressed for screen readers (F13)', async ({ page }) => {
  206 |   await page.route('**/api/clips/feed**', route =>
  207 |     route.fulfill({
  208 |       status: 200,
  209 |       contentType: 'application/json',
  210 |       body: JSON.stringify(
  211 |         feedBody({
  212 |           user_entities: ['Modi'],
  213 |           clips: [SAMPLE_CLIP],
  214 |           total: 1,
  215 |         }),
  216 |       ),
  217 |     }),
  218 |   )
  219 | 
  220 |   await page.goto('/clips')
  221 |   const pill = page.getByRole('button', { name: 'Modi' })
> 222 |   await expect(pill).toHaveAttribute('aria-pressed', 'false')
      |                      ^ Error: expect(locator).toHaveAttribute(expected) failed
  223 |   await pill.click()
  224 |   await expect(pill).toHaveAttribute('aria-pressed', 'true')
  225 | })
  226 | 
```