/**
 * Tests for the Signal Room — daily summary edition layout.
 *
 * The previous cluster-card tests have been retired alongside the
 * cluster grid. These cover the new typewriter document, editions
 * rail, and topic drilldown.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// ── Hoisted mocks ─────────────────────────────────────────────────────

const supabaseMocks = vi.hoisted(() => {
  const unsubscribe = vi.fn()
  const getSession = vi.fn(async () => ({
    data: { session: { access_token: 'fake-jwt' } },
  }))
  const onAuthStateChange = vi.fn(() => ({
    data: { subscription: { unsubscribe } },
  }))
  return { getSession, onAuthStateChange, unsubscribe }
})

const pushMock = vi.fn()
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
}))

vi.mock('@/lib/supabase/client', () => ({
  createClient: () => ({
    auth: {
      getSession: supabaseMocks.getSession,
      onAuthStateChange: supabaseMocks.onAuthStateChange,
    },
  }),
}))

vi.mock('@/components/Navigation', () => ({
  default: () => <nav data-testid="nav" />,
}))

import SignalsPage from '../page'

// scrollIntoView isn't implemented in jsdom — stub it.
beforeEach(() => {
  Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
    value: vi.fn(),
    writable: true,
  })
})

// ── Fixtures ──────────────────────────────────────────────────────────

const SAMPLE_BODY = `DAILY SIGNAL SUMMARY    27 APR 2026    EDITION 005    OPEN
═══════════════════════════════════════════════════════════════════════

¶1  PHRASING REPETITION                                   270411Z APR 26
      MIB repeated 7× in 36h — "West Asia evolving situation".
      CORROBORATED across rewordings.  CONF: HIGH.

¶2  OFFICIAL SILENCE                                      270411Z APR 26

      Subject is being discussed by non-official sources, but no tracked government channel has spoken about it yet.

      BRS drew 3 non-official mentions in 24h; no tracked official
      channel has spoken to it in ≥6h. INDICATOR. FOLLOW.

¶3  NEW ON THE RADAR  (subjects not on watchlist)

      "Hyderabad metro Phase 2"  ·  n=6 / 3 src   PROPOSE ADD
      "Kaleshwaram"  ·  n=12 / 3 src   PROPOSE ADD
                                                              — END —`

interface SummaryFixture {
  id: string
  edition: number
  classification: string
  generated_at: string
  window_hours: number
  body: string
  sources_used: string[]
  event_count: number
}

function makeSummary(over: Partial<SummaryFixture> = {}): SummaryFixture {
  return {
    id: 'sum-1',
    edition: 5,
    classification: 'OPEN',
    generated_at: new Date().toISOString(),
    window_hours: 24,
    body: SAMPLE_BODY,
    sources_used: ['R/INDIA', 'TG-MIBINDIA'],
    event_count: 4,
    ...over,
  }
}

interface FetchOpts {
  summary?: SummaryFixture | null
  editions?: SummaryFixture[]
  topicPosts?: Array<{
    post_id: string
    platform: 'reddit' | 'telegram'
    post_text: string
    post_text_translated: string | null
    post_language: string
    relevance_score: number
  }>
  summaryStatus?: number
}

function installFetchRouter(opts: FetchOpts = {}) {
  const summary = opts.summary === undefined ? makeSummary() : opts.summary
  const editions = opts.editions ?? [makeSummary()]
  const topicPosts = opts.topicPosts ?? []
  const summaryStatus = opts.summaryStatus ?? 200

  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.includes('/api/signals/summary/editions')) {
      return {
        ok: true,
        status: 200,
        json: async () => ({ editions }),
      } as Response
    }
    if (url.includes('/api/signals/summary/latest')) {
      return {
        ok: summaryStatus >= 200 && summaryStatus < 300,
        status: summaryStatus,
        json: async () => ({ summary }),
      } as Response
    }
    if (url.match(/\/api\/signals\/summary\/[^/]+$/)) {
      return {
        ok: true,
        status: 200,
        json: async () => ({ summary: editions[0] }),
      } as Response
    }
    if (url.includes('/api/signals/topic/')) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          kind: 'entity',
          key: 'Hyderabad metro Phase 2',
          posts: topicPosts.map(p => ({
            ...p,
            author_username: 'someone',
            post_url: 'https://x',
            upvotes: 4,
            comment_count: 1,
            share_count: 0,
            forward_count: 0,
            forwarded_from: null,
            has_document: false,
            sentiment_score: 0.0,
            matched_entities: [],
            monitor_name: 'r/india',
            posted_at: new Date().toISOString(),
            collected_at: new Date().toISOString(),
          })),
        }),
      } as Response
    }
    throw new Error(`Unhandled fetch: ${url}`)
  }) as unknown as typeof fetch
  ;(globalThis as unknown as { fetch: typeof fetch }).fetch = fetchMock
  return fetchMock as unknown as ReturnType<typeof vi.fn>
}

beforeEach(() => {
  pushMock.mockReset()
  supabaseMocks.getSession.mockReset()
  supabaseMocks.getSession.mockResolvedValue({
    data: { session: { access_token: 'fake-jwt' } },
  })
  supabaseMocks.onAuthStateChange.mockReset()
  supabaseMocks.onAuthStateChange.mockReturnValue({
    data: { subscription: { unsubscribe: supabaseMocks.unsubscribe } },
  })
})

afterEach(() => {
  vi.restoreAllMocks()
})

// ── Tests ─────────────────────────────────────────────────────────────

describe('SignalsPage auth gate', () => {
  it('redirects to /login when no Supabase session', async () => {
    supabaseMocks.getSession.mockResolvedValueOnce({
      data: { session: null },
    })
    installFetchRouter({})
    render(<SignalsPage />)
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/login'))
  })

  it('attaches Bearer header to summary + editions calls', async () => {
    const fetchMock = installFetchRouter({})
    render(<SignalsPage />)
    await waitFor(() =>
      expect(fetchMock.mock.calls.length).toBeGreaterThanOrEqual(2),
    )
    for (const call of fetchMock.mock.calls) {
      const opts = call[1] as RequestInit | undefined
      const auth =
        opts?.headers && (opts.headers as Record<string, string>).Authorization
      expect(auth).toBe('Bearer fake-jwt')
    }
  })

  it('redirects to /login on 401 from /summary/latest', async () => {
    installFetchRouter({ summaryStatus: 401 })
    render(<SignalsPage />)
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/login'))
  })
})

describe('SignalsPage typewriter render', () => {
  it('shows DeskMemo when no edition has been composed', async () => {
    installFetchRouter({ summary: null, editions: [] })
    render(<SignalsPage />)
    expect(
      await screen.findByText(/No edition composed yet/i),
    ).toBeInTheDocument()
  })

  it('renders the parsed summary sections', async () => {
    installFetchRouter({})
    render(<SignalsPage />)
    // Title block
    expect(
      await screen.findByText(/Daily Signal Summary/i),
    ).toBeInTheDocument()
    // Section headings (now React, sentence-case from parser)
    expect(
      screen.getByText(/Phrasing repetition/i),
    ).toBeInTheDocument()
    // "Official silence" appears as a section heading AND a chip-group
    // label — getAllByText handles both.
    expect(screen.getAllByText(/Official silence/i).length).toBeGreaterThan(0)
  })

  it('shows past-edition rail with at least one entry', async () => {
    installFetchRouter({
      editions: [
        makeSummary({ id: 'sum-1', edition: 5 }),
        makeSummary({ id: 'sum-2', edition: 4 }),
      ],
    })
    render(<SignalsPage />)
    // wait for editions to render
    await screen.findByText(/DAILY SIGNAL SUMMARY/i)
    expect(screen.getByText(/^Editions$/i)).toBeInTheDocument()
    expect(screen.getByText(/005 ·/)).toBeInTheDocument()
    expect(screen.getByText(/004 ·/)).toBeInTheDocument()
  })

  it('renders error UX on HTTP 500', async () => {
    installFetchRouter({ summaryStatus: 500 })
    render(<SignalsPage />)
    expect(
      await screen.findByText(/Summary unavailable \(HTTP 500\)/i),
    ).toBeInTheDocument()
  })
})

describe('SignalsPage drilldown', () => {
  it('clicking a "Drill into" subject button opens drilldown', async () => {
    const fetchMock = installFetchRouter({
      topicPosts: [
        {
          post_id: 'p1',
          platform: 'reddit',
          post_text: 'real post text',
          post_text_translated: null,
          post_language: 'en',
          relevance_score: 30,
        },
      ],
    })
    render(<SignalsPage />)
    await screen.findByText(/DAILY SIGNAL SUMMARY/i)

    // The "Drill into:" suggestions panel should pull subjects out of
    // the body. We expect "Hyderabad metro Phase 2" or "Kaleshwaram".
    // "Kaleshwaram" shows up in two places now — in the New-on-radar
    // section and in the chip row. Take the first match.
    const buttons = await screen.findAllByRole('button', {
      name: /^Kaleshwaram$/i,
    })
    const button = buttons[0]
    const user = userEvent.setup()
    await user.click(button)

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(c =>
          String(c[0]).includes('/api/signals/topic/'),
        ),
      ).toBe(true)
    })
    expect(await screen.findByText('real post text')).toBeInTheDocument()
  })
})
