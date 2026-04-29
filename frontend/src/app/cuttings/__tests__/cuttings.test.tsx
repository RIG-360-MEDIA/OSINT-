/**
 * Tests for the Cutting Room redesign (/cuttings).
 *
 * Covers:
 *   - Newsstand renders mastheads from /api/clippings/papers
 *   - Language filter narrows the rack
 *   - Click → modal opens, deep-links via router.push
 *   - ClippingCard bilingual variant for non-English papers
 *   - "Full edition ↗" mounts iframe with PDF blob
 *   - Esc closes the modal
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// ── Hoisted mocks ───────────────────────────────────────────────────

const pushMock = vi.fn()
const searchParamsMock = { get: vi.fn(() => null), toString: () => '' }
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  useSearchParams: () => searchParamsMock,
}))

const getSessionMock = vi.fn(async () => ({ data: { session: { access_token: 'tok' } } }))
const onAuthStateChangeMock = vi.fn(() => ({
  data: { subscription: { unsubscribe: vi.fn() } },
}))
vi.mock('@/lib/supabase/client', () => ({
  createClient: () => ({
    auth: {
      getSession: getSessionMock,
      onAuthStateChange: onAuthStateChangeMock,
    },
  }),
}))

vi.mock('@/components/Navigation', () => ({
  default: () => <nav data-testid="nav" />,
}))
vi.mock('@/components/Dateline', () => ({
  Dateline: ({ extra }: { extra?: string[] }) => (
    <div data-testid="dateline">{extra?.join(' · ')}</div>
  ),
}))

import CuttingsPage from '../page'
import { Newsstand, type PaperSummary } from '../Newsstand'
import { EditionModal, type Clipping } from '../EditionModal'

// ── Helpers ─────────────────────────────────────────────────────────

const PAPERS: PaperSummary[] = [
  {
    newspaper_id: 'paper-1',
    name: 'Times of India',
    language: 'en',
    edition_date: '2026-04-25',
    clip_count: 12,
    pdf_available: true,
  },
  {
    newspaper_id: 'paper-2',
    name: 'Sakshi',
    language: 'te',
    edition_date: '2026-04-25',
    clip_count: 4,
    pdf_available: true,
  },
]

const CLIPS_EN: Clipping[] = [
  {
    clipping_id: 'c-1',
    newspaper_name: 'Times of India',
    newspaper_language: 'en',
    edition_date: '2026-04-25',
    page_number: 3,
    headline: 'Modi addresses parliament on reforms',
    headline_translated: null,
    text_preview: 'The Prime Minister outlined four key economic priorities…',
    translated_preview: null,
    has_image: true,
    relevance_score: 0.92,
    relevance_explanation: 'Matched Modi — your top priority entity',
    collected_at: '2026-04-25T07:30:00Z',
  },
]

const CLIPS_TE: Clipping[] = [
  {
    clipping_id: 'c-2',
    newspaper_name: 'Sakshi',
    newspaper_language: 'te',
    edition_date: '2026-04-25',
    page_number: 1,
    headline: 'మోదీ పార్లమెంటులో మాట్లాడారు',
    headline_translated: 'Modi speaks in parliament',
    text_preview: 'మోదీ గారు ప్రధాన ఆర్థిక...',
    translated_preview: 'PM Modi spoke about reforms…',
    has_image: false,
    relevance_score: 0.88,
    relevance_explanation: 'Matched Modi — your top priority entity',
    collected_at: '2026-04-25T07:30:00Z',
  },
]

function mockFetch(handler: (url: string) => unknown) {
  global.fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString()
    const out = handler(url)
    return {
      ok: true,
      status: 200,
      json: async () => out,
      blob: async () => new Blob(['%PDF-1.4'], { type: 'application/pdf' }),
    } as Response
  }) as unknown as typeof fetch
}

beforeEach(() => {
  pushMock.mockClear()
  searchParamsMock.get.mockReturnValue(null)
  // jsdom does not implement URL.createObjectURL
  Object.defineProperty(URL, 'createObjectURL', {
    value: vi.fn(() => 'blob:mock-pdf'),
    writable: true,
  })
  Object.defineProperty(URL, 'revokeObjectURL', {
    value: vi.fn(),
    writable: true,
  })
})

afterEach(() => {
  vi.restoreAllMocks()
})

// ── Newsstand component ─────────────────────────────────────────────

describe('<Newsstand>', () => {
  it('renders one masthead card per paper sorted by props order', () => {
    const onClick = vi.fn()
    render(
      <Newsstand
        papers={PAPERS}
        langFilter="all"
        onLangFilterChange={() => {}}
        onPaperClick={onClick}
      />,
    )
    const cards = screen.getAllByTestId('masthead-card')
    expect(cards).toHaveLength(2)
    expect(cards[0]).toHaveAttribute('data-paper-name', 'Times of India')
    expect(cards[1]).toHaveAttribute('data-paper-name', 'Sakshi')
  })

  it('emits paper click on masthead activation', async () => {
    const onClick = vi.fn()
    render(
      <Newsstand
        papers={PAPERS}
        langFilter="all"
        onLangFilterChange={() => {}}
        onPaperClick={onClick}
      />,
    )
    await userEvent.click(screen.getAllByTestId('masthead-card')[0]!)
    expect(onClick).toHaveBeenCalledWith(PAPERS[0])
  })

  it('hides papers outside the active language filter', () => {
    render(
      <Newsstand
        papers={PAPERS}
        langFilter="te"
        onLangFilterChange={() => {}}
        onPaperClick={() => {}}
      />,
    )
    const cards = screen.getAllByTestId('masthead-card')
    expect(cards).toHaveLength(1)
    expect(cards[0]).toHaveAttribute('data-paper-name', 'Sakshi')
  })

  it('shows desk memo when no papers match', () => {
    render(
      <Newsstand
        papers={[]}
        langFilter="all"
        onLangFilterChange={() => {}}
        onPaperClick={() => {}}
      />,
    )
    expect(
      screen.getByText(/no editions on the desk today/i),
    ).toBeInTheDocument()
  })
})

// ── EditionModal — bilingual rendering ──────────────────────────────

describe('<EditionModal> bilingual rendering', () => {
  it('English path: only the primary headline + relevance reason, no original block', () => {
    render(
      <EditionModal
        paper={PAPERS[0]!}
        clippings={CLIPS_EN}
        loading={false}
        error={null}
        token="tok"
        onClose={() => {}}
      />,
    )
    const card = screen.getByTestId('clipping-card')
    expect(card).toHaveAttribute('data-language', 'en')
    expect(screen.getByTestId('primary-headline').textContent).toMatch(
      /modi addresses parliament/i,
    )
    expect(screen.queryByTestId('original-headline')).not.toBeInTheDocument()
    expect(screen.getByTestId('relation-block').textContent).toMatch(
      /matched modi/i,
    )
  })

  it('Non-English path: original-script headline + bold English translation + relation', () => {
    render(
      <EditionModal
        paper={PAPERS[1]!}
        clippings={CLIPS_TE}
        loading={false}
        error={null}
        token="tok"
        onClose={() => {}}
      />,
    )
    expect(screen.getByTestId('clipping-card')).toHaveAttribute(
      'data-language',
      'te',
    )
    expect(screen.getByTestId('original-headline').textContent).toMatch(
      /మోదీ/,
    )
    expect(screen.getByTestId('primary-headline').textContent).toMatch(
      /modi speaks in parliament/i,
    )
    expect(screen.getByTestId('relation-block')).toBeInTheDocument()
  })

  it('Esc key closes the modal', () => {
    const onClose = vi.fn()
    render(
      <EditionModal
        paper={PAPERS[0]!}
        clippings={CLIPS_EN}
        loading={false}
        error={null}
        token="tok"
        onClose={onClose}
      />,
    )
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('Backdrop click closes the modal', () => {
    const onClose = vi.fn()
    render(
      <EditionModal
        paper={PAPERS[0]!}
        clippings={CLIPS_EN}
        loading={false}
        error={null}
        token="tok"
        onClose={onClose}
      />,
    )
    fireEvent.click(screen.getByTestId('edition-modal'))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('"Full edition" toggle fetches PDF and mounts iframe', async () => {
    let fetchedUrl = ''
    global.fetch = vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input.toString()
      fetchedUrl = url
      return {
        ok: true,
        status: 200,
        blob: async () => new Blob(['%PDF-1.4'], { type: 'application/pdf' }),
      } as Response
    }) as unknown as typeof fetch

    render(
      <EditionModal
        paper={PAPERS[0]!}
        clippings={CLIPS_EN}
        loading={false}
        error={null}
        token="tok"
        onClose={() => {}}
      />,
    )
    await userEvent.click(screen.getByTestId('full-edition-button'))
    await waitFor(() =>
      expect(screen.getByTestId('full-edition-iframe')).toBeInTheDocument(),
    )
    expect(fetchedUrl).toMatch(/\/api\/newspapers\/paper-1\/pdf\?date=2026-04-25/)
  })
})

// ── End-to-end page wiring ──────────────────────────────────────────

describe('<CuttingsPage>', () => {
  it('renders mastheads from the papers endpoint and pushes URL on click', async () => {
    let papersHits = 0
    mockFetch(url => {
      if (url.includes('/api/clippings/papers')) {
        papersHits += 1
        return { papers: PAPERS }
      }
      if (url.includes('/api/clippings/feed')) {
        return { clippings: CLIPS_EN, has_more: false, next_cursor: null }
      }
      return {}
    })

    render(<CuttingsPage />)
    await waitFor(() =>
      expect(screen.getAllByTestId('masthead-card')).toHaveLength(2),
    )
    expect(papersHits).toBe(1)

    await userEvent.click(
      screen.getAllByTestId('masthead-card').find(c =>
        c.getAttribute('data-paper-name') === 'Times of India',
      )!,
    )
    expect(pushMock).toHaveBeenCalledWith(
      expect.stringMatching(/^\/cuttings\?paper=paper-1$/),
      { scroll: false },
    )
  })

  it('opens modal directly when ?paper=<id> present on mount', async () => {
    searchParamsMock.get.mockImplementation(
      ((key: string) => (key === 'paper' ? 'paper-2' : null)) as () => null,
    )
    mockFetch(url => {
      if (url.includes('/api/clippings/papers')) {
        return { papers: PAPERS }
      }
      if (url.includes('/api/clippings/feed')) {
        return { clippings: CLIPS_TE, has_more: false, next_cursor: null }
      }
      return {}
    })

    render(<CuttingsPage />)
    await waitFor(() =>
      expect(screen.getByTestId('edition-modal')).toBeInTheDocument(),
    )
    expect(screen.getByTestId('clipping-card')).toHaveAttribute(
      'data-language',
      'te',
    )
  })
})
