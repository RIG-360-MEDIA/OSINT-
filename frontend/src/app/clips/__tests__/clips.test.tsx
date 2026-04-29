/**
 * Tests for the Clip Room (/clips) page.
 *
 * Strategy: mount <ClipsPage/> with fetch + Supabase + next/navigation mocked.
 * Components ClipCard / FilterPill / LoadingState / DeskMemo are defined
 * inline in page.tsx so they're tested through the page render.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// ── Hoisted mocks ───────────────────────────────────────────────────

const pushMock = vi.fn()
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
}))

const getSessionMock = vi.fn()
vi.mock('@/lib/supabase/client', () => ({
  createClient: () => ({
    auth: { getSession: getSessionMock },
  }),
}))

vi.mock('@/lib/domainColor', () => ({
  formatTimeAgo: (_iso: string) => '2 hours ago',
}))

vi.mock('@/components/Navigation', () => ({
  default: () => <nav data-testid="nav" />,
}))
vi.mock('@/components/Dateline', () => ({
  Dateline: ({ issueNumber, extra }: { issueNumber: number; extra?: string[] }) => (
    <div data-testid="dateline">
      <span data-testid="issue">{issueNumber}</span>
      {extra?.map(e => <span key={e}>{e}</span>)}
    </div>
  ),
}))

// Pull in the page after mocks are registered.
import ClipsPage from '../page'

// ── Test helpers ────────────────────────────────────────────────────

interface ClipFixture {
  clip_id: string
  video_id: string
  video_title: string
  channel_name: string
  channel_id: string
  video_url: string
  embed_url: string
  clip_start_seconds: number
  clip_end_seconds: number
  transcript_segment: string
  transcript_translated: string | null
  matched_entity: string
  transcript_language: string
  video_published_at: string | null
  collected_at: string
}

function makeClip(overrides: Partial<ClipFixture> = {}): ClipFixture {
  return {
    clip_id: 'clip-1',
    video_id: 'abc123',
    video_title: 'Modi addresses parliament',
    channel_name: 'NDTV',
    channel_id: 'UCx',
    video_url: 'https://youtube.com/watch?v=abc123',
    embed_url: 'https://youtube.com/embed/abc123?start=60&end=90',
    clip_start_seconds: 60,
    clip_end_seconds: 90,
    transcript_segment: 'Modi spoke about reforms.',
    transcript_translated: 'Modi spoke about reforms.',
    matched_entity: 'Modi',
    transcript_language: 'hi',
    video_published_at: '2026-04-25T12:00:00Z',
    collected_at: '2026-04-25T13:00:00Z',
    ...overrides,
  }
}

function feedResponse(opts: {
  clips?: ClipFixture[]
  channels?: Array<{ channel_id: string; channel_name: string; clip_count: number }>
  user_entities?: string[]
  total?: number
} = {}) {
  return {
    clips: opts.clips ?? [],
    channels: opts.channels ?? [],
    user_entities: opts.user_entities ?? [],
    total: opts.total ?? 0,
    has_more: false,
    next_cursor: null,
  }
}

function mockFetchOnce(body: unknown, status = 200) {
  ;(globalThis as unknown as { fetch: typeof fetch }).fetch = vi.fn(
    async () =>
      ({
        ok: status >= 200 && status < 300,
        status,
        json: async () => body,
      }) as Response,
  ) as unknown as typeof fetch
}

beforeEach(() => {
  pushMock.mockReset()
  getSessionMock.mockReset()
  getSessionMock.mockResolvedValue({
    data: { session: { access_token: 'fake-jwt' } },
  })
})

afterEach(() => {
  vi.restoreAllMocks()
})

// ─────────────────────────────────────────────────────────────────────
// Auth gate
// ─────────────────────────────────────────────────────────────────────

describe('ClipsPage auth gate', () => {
  it('redirects to /login when no Supabase session', async () => {
    getSessionMock.mockResolvedValueOnce({ data: { session: null } })
    mockFetchOnce(feedResponse())

    render(<ClipsPage />)
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/login'))
  })

  it('sends Authorization: Bearer header on fetch', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => feedResponse({ user_entities: ['Modi'] }),
    })) as unknown as typeof fetch
    ;(globalThis as unknown as { fetch: typeof fetch }).fetch = fetchMock

    render(<ClipsPage />)
    await waitFor(() =>
      expect((fetchMock as unknown as ReturnType<typeof vi.fn>)).toHaveBeenCalled(),
    )
    const call = (fetchMock as unknown as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(call[0]).toMatch(/\/api\/clips\/feed\?limit=40/)
    expect(call[1].headers.Authorization).toBe('Bearer fake-jwt')
  })
})

// ─────────────────────────────────────────────────────────────────────
// Loading & error & empty states
// ─────────────────────────────────────────────────────────────────────

describe('ClipsPage states', () => {
  it('shows the loading state initially', async () => {
    let resolve: (v: unknown) => void = () => {}
    ;(globalThis as unknown as { fetch: typeof fetch }).fetch = vi.fn(
      () => new Promise(r => (resolve = r)),
    ) as unknown as typeof fetch

    render(<ClipsPage />)
    await screen.findByText(/Cueing up the footage/i)

    // Resolve to clean up
    await act(async () => {
      resolve({
        ok: true,
        status: 200,
        json: async () => feedResponse(),
      })
    })
  })

  it('renders the "no clips" desk memo when feed is empty', async () => {
    mockFetchOnce(feedResponse({ user_entities: ['Modi'] }))

    render(<ClipsPage />)
    expect(
      await screen.findByText(/No clips on the wire yet/i),
    ).toBeInTheDocument()
  })

  it('renders the error desk memo on HTTP 500', async () => {
    mockFetchOnce({ detail: 'kaboom' }, 500)

    render(<ClipsPage />)
    expect(
      await screen.findByText(/feed is refusing to return/i),
    ).toBeInTheDocument()
  })

  it('redirects to /login on HTTP 401 (F4 fix)', async () => {
    mockFetchOnce({ detail: 'unauthorized' }, 401)

    render(<ClipsPage />)
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/login'))
  })

  it('survives a malformed response with no clips field (F3 fix)', async () => {
    mockFetchOnce({})  // no `clips` key

    render(<ClipsPage />)
    // Should not crash; should fall through to empty desk memo.
    expect(
      await screen.findByText(/No clips on the wire yet/i),
    ).toBeInTheDocument()
  })
})

// ─────────────────────────────────────────────────────────────────────
// Happy path render
// ─────────────────────────────────────────────────────────────────────

describe('ClipsPage rendering', () => {
  it('renders 3 numbered clip cards', async () => {
    mockFetchOnce(
      feedResponse({
        user_entities: ['Modi'],
        clips: [
          makeClip({ clip_id: '1', video_id: 'v1', video_title: 'Headline 1' }),
          makeClip({ clip_id: '2', video_id: 'v2', video_title: 'Headline 2' }),
          makeClip({ clip_id: '3', video_id: 'v3', video_title: 'Headline 3' }),
        ],
        total: 3,
      }),
    )

    render(<ClipsPage />)
    expect(await screen.findByText('Headline 1')).toBeInTheDocument()
    expect(screen.getByText('Headline 2')).toBeInTheDocument()
    expect(screen.getByText('Headline 3')).toBeInTheDocument()
    // Numerals 01/02/03
    expect(screen.getByText('01')).toBeInTheDocument()
    expect(screen.getByText('02')).toBeInTheDocument()
    expect(screen.getByText('03')).toBeInTheDocument()
    // Dateline reflects total
    expect(screen.getByTestId('issue').textContent).toBe('3')
  })

  it('shows entity filter pills from user_entities', async () => {
    mockFetchOnce(
      feedResponse({
        user_entities: ['Modi', 'Adani'],
        clips: [makeClip()],
        total: 1,
      }),
    )

    render(<ClipsPage />)
    await screen.findByText('Modi addresses parliament')
    expect(screen.getByRole('button', { name: 'Modi' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Adani' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'All' })).toBeInTheDocument()
  })

  it('shows channel filter pills with clip counts', async () => {
    mockFetchOnce(
      feedResponse({
        user_entities: ['Modi'],
        clips: [makeClip()],
        channels: [
          { channel_id: 'UCa', channel_name: 'NDTV', clip_count: 5 },
          { channel_id: 'UCb', channel_name: 'Republic', clip_count: 2 },
        ],
        total: 1,
      }),
    )

    render(<ClipsPage />)
    await screen.findByText('Modi addresses parliament')
    expect(screen.getByRole('button', { name: /NDTV · 5/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Republic · 2/ })).toBeInTheDocument()
  })
})

// ─────────────────────────────────────────────────────────────────────
// ClipCard interactions
// ─────────────────────────────────────────────────────────────────────

describe('ClipCard interactions', () => {
  it('clicking the thumbnail loads the iframe with autoplay', async () => {
    const user = userEvent.setup()
    mockFetchOnce(
      feedResponse({ user_entities: ['Modi'], clips: [makeClip()], total: 1 }),
    )

    const { container } = render(<ClipsPage />)
    const playBtn = await screen.findByRole('button', { name: /play clip/i })
    await user.click(playBtn)

    const iframe = container.querySelector('iframe') as HTMLIFrameElement
    expect(iframe).toBeTruthy()
    expect(iframe.src).toContain('autoplay=1')
    expect(iframe.src).toContain('start=60')
  })

  it('"Roll the tape" button also triggers iframe', async () => {
    const user = userEvent.setup()
    mockFetchOnce(
      feedResponse({ user_entities: ['Modi'], clips: [makeClip()], total: 1 }),
    )

    const { container } = render(<ClipsPage />)
    await screen.findByText('Modi addresses parliament')
    await user.click(screen.getByRole('button', { name: /roll the tape/i }))
    expect(container.querySelector('iframe')).toBeTruthy()
  })

  it('shows "Show original" toggle when translation differs from original', async () => {
    mockFetchOnce(
      feedResponse({
        user_entities: ['Modi'],
        clips: [
          makeClip({
            transcript_language: 'hi',
            transcript_translated: 'English version',
            transcript_segment: 'हिंदी संस्करण',
          }),
        ],
        total: 1,
      }),
    )

    render(<ClipsPage />)
    await screen.findByText('Modi addresses parliament')
    expect(
      screen.getByRole('button', { name: /show original \(HI\)/i }),
    ).toBeInTheDocument()
    // English summary is the primary content shown by default
    expect(screen.getByText(/English version/)).toBeInTheDocument()
  })

  it('hides "Show original" toggle when no translation', async () => {
    mockFetchOnce(
      feedResponse({
        user_entities: ['Modi'],
        clips: [
          makeClip({ transcript_language: 'en', transcript_translated: null }),
        ],
        total: 1,
      }),
    )

    render(<ClipsPage />)
    await screen.findByText('Modi addresses parliament')
    expect(screen.queryByRole('button', { name: /show original/i })).toBeNull()
  })

  it('clicking "Show original" reveals the original-language transcript', async () => {
    const user = userEvent.setup()
    mockFetchOnce(
      feedResponse({
        user_entities: ['Modi'],
        clips: [
          makeClip({
            transcript_language: 'hi',
            transcript_translated: 'English version',
            transcript_segment: 'Hindi version',
          }),
        ],
        total: 1,
      }),
    )

    render(<ClipsPage />)
    await screen.findByText(/English version/)
    expect(screen.queryByText(/Hindi version/)).toBeNull()
    await user.click(screen.getByRole('button', { name: /show original \(HI\)/i }))
    expect(screen.getByText(/Hindi version/)).toBeInTheDocument()
    // Toggle now reads "Hide"
    expect(
      screen.getByRole('button', { name: /hide HI original/i }),
    ).toBeInTheDocument()
  })

  it('"Take to Analyst" pushes to /analyst with composed question', async () => {
    const user = userEvent.setup()
    mockFetchOnce(
      feedResponse({ user_entities: ['Modi'], clips: [makeClip()], total: 1 }),
    )

    render(<ClipsPage />)
    await screen.findByText('Modi addresses parliament')
    await user.click(screen.getByRole('button', { name: /take to analyst/i }))
    expect(pushMock).toHaveBeenCalledWith(
      expect.stringMatching(/^\/analyst\?question=.+Modi/),
    )
  })

  it('"Full broadcast" link uses video_url with t=N timestamp', async () => {
    mockFetchOnce(
      feedResponse({ user_entities: ['Modi'], clips: [makeClip()], total: 1 }),
    )

    render(<ClipsPage />)
    const link = await screen.findByRole('link', { name: /full broadcast/i })
    expect(link.getAttribute('href')).toBe(
      'https://youtube.com/watch?v=abc123&t=60',
    )
    expect(link.getAttribute('target')).toBe('_blank')
    expect(link.getAttribute('rel')).toBe('noopener noreferrer')
  })
})

// ─────────────────────────────────────────────────────────────────────
// Filter interactions
// ─────────────────────────────────────────────────────────────────────

describe('ClipsPage filters', () => {
  it('clicking entity pill refetches with entity= param', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.fn().mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () =>
        feedResponse({
          user_entities: ['Modi', 'Adani'],
          clips: [makeClip()],
          total: 1,
        }),
    }).mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () =>
        feedResponse({
          user_entities: ['Modi', 'Adani'],
          clips: [makeClip({ matched_entity: 'Adani' })],
          total: 1,
        }),
    })
    ;(globalThis as unknown as { fetch: typeof fetch }).fetch =
      fetchMock as unknown as typeof fetch

    render(<ClipsPage />)
    await screen.findByText('Modi addresses parliament')
    await user.click(screen.getByRole('button', { name: 'Adani' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    const secondUrl = fetchMock.mock.calls[1][0] as string
    expect(secondUrl).toContain('entity=Adani')
  })

  it('clicking the same entity pill twice clears the filter', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () =>
        feedResponse({
          user_entities: ['Modi'],
          clips: [makeClip()],
          total: 1,
        }),
    }))
    ;(globalThis as unknown as { fetch: typeof fetch }).fetch =
      fetchMock as unknown as typeof fetch

    render(<ClipsPage />)
    await screen.findByText('Modi addresses parliament')
    await user.click(screen.getByRole('button', { name: 'Modi' }))
    await user.click(screen.getByRole('button', { name: 'Modi' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3))
    const calls = fetchMock.mock.calls as unknown as Array<[string, unknown]>
    const thirdUrl = calls[2][0]
    expect(thirdUrl).not.toContain('entity=')
  })

  it('FilterPill exposes aria-pressed when active (F13 fix)', async () => {
    const user = userEvent.setup()
    mockFetchOnce(
      feedResponse({
        user_entities: ['Modi'],
        clips: [makeClip()],
        total: 1,
      }),
    )

    render(<ClipsPage />)
    const pill = await screen.findByRole('button', { name: 'Modi' })
    expect(pill.getAttribute('aria-pressed')).toBe('false')
    await user.click(pill)
    expect(pill.getAttribute('aria-pressed')).toBe('true')
  })
})
