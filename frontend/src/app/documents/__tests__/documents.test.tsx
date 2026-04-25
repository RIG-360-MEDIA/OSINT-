/**
 * Tests for the Documents (/documents) page.
 *
 * Mirrors the pattern in clips/__tests__/clips.test.tsx: mount <DocumentsPage/>
 * with fetch + Supabase + next/navigation mocked. The 7 inline components
 * (DocumentRow / FilterPill / DocumentDialog / ...) are exercised through the
 * page render.
 *
 * `xfail`-marked tests document defects from docs/qa/documents-defects.md and
 * MUST stay red until the fix lands.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
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

import DocumentsPage from '../page'

// ── Fixtures ────────────────────────────────────────────────────────

interface DocFixture {
  doc_id: string
  title: string
  document_url: string
  source_name: string
  source_geography: 'LOCAL' | 'CENTRAL' | 'NEIGHBOURING' | 'INTERNATIONAL'
  document_type: string
  topic_category: string | null
  geo_primary: string | null
  summary_preview: string | null
  summary: string | null
  page_count: number | null
  published_at: string | null
  collected_at: string
  score_final: number | null
  relevance_tier: number | null
  urgency: 'HIGH' | 'MEDIUM' | 'LOW' | null
  why_it_matters: string | null
  suggested_action: string | null
}

function makeDoc(over: Partial<DocFixture> = {}): DocFixture {
  return {
    doc_id: 'doc-1',
    title: 'RBI Master Direction on KYC, 2024',
    document_url: 'https://example.test/rbi-kyc.pdf',
    source_name: 'rbi.org.in',
    source_geography: 'CENTRAL',
    document_type: 'regulator_circular',
    topic_category: 'banking',
    geo_primary: 'India',
    summary_preview: 'A short preview of the doc text...',
    summary: null,
    page_count: 12,
    published_at: '2024-03-12T00:00:00Z',
    collected_at: '2024-03-12T06:30:00Z',
    score_final: 0.82,
    relevance_tier: 1,
    urgency: 'HIGH',
    why_it_matters: 'Affects every regulated entity.',
    suggested_action: 'Update KYC playbook by 30 June.',
    ...over,
  }
}

function feedResponse(docs: DocFixture[], hasMore = false) {
  return {
    documents: docs,
    has_more: hasMore,
    next_cursor: hasMore ? '2024-03-12T06:00:00Z' : null,
    total: docs.length,
    geography_counts: [{ geography: 'CENTRAL', count: docs.length }],
  }
}

// ── Setup / teardown ────────────────────────────────────────────────

const fetchMock = vi.fn()

beforeEach(() => {
  fetchMock.mockReset()
  pushMock.mockReset()
  getSessionMock.mockReset()
  getSessionMock.mockResolvedValue({
    data: { session: { access_token: 'tok' } },
  })
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

// ── Tests ───────────────────────────────────────────────────────────

describe('DocumentsPage — happy path', () => {
  it('redirects to /login when there is no session', async () => {
    getSessionMock.mockResolvedValue({ data: { session: null } })
    render(<DocumentsPage />)
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/login'))
  })

  it('fetches feed and renders rows', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => feedResponse([
        makeDoc({ doc_id: 'a', title: 'First doc' }),
        makeDoc({ doc_id: 'b', title: 'Second doc' }),
      ]),
    })
    render(<DocumentsPage />)
    expect(await screen.findByText('First doc')).toBeInTheDocument()
    expect(screen.getByText('Second doc')).toBeInTheDocument()
  })

  it('sends Authorization header with bearer token', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => feedResponse([makeDoc()]),
    })
    render(<DocumentsPage />)
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    const [, init] = fetchMock.mock.calls[0]
    expect((init as RequestInit).headers).toMatchObject({
      Authorization: 'Bearer tok',
    })
  })

  it('refetches when geography filter changes', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => feedResponse([makeDoc()]),
    })
    render(<DocumentsPage />)
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))

    const central = await screen.findByRole('button', { name: 'Central' })
    await userEvent.click(central)

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    const url = fetchMock.mock.calls[1][0] as string
    expect(url).toContain('geography=CENTRAL')
  })

  it.skip(
    'debounces search input (skipped — fake timers + RTL findBy* race; ' +
      'covered by e2e instead)',
    async () => {
      // Intentionally skipped. Reliable debounce coverage lives in
      // frontend/e2e/documents.spec.ts where real timers can be used.
    },
  )
})

describe('DocumentsPage — error handling', () => {
  it('shows a user-visible error when /feed returns 500 (D-4)', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => ({ error: 'boom' }),
    })
    render(<DocumentsPage />)
    expect(
      await screen.findByText(/temporarily unavailable/i),
    ).toBeInTheDocument()
    // The retry control is also present.
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument()
  })

  it('aborts the in-flight fetch when filter changes (D-5)', async () => {
    // First call: a fetch that honours the abort signal — it never resolves
    // until aborted, then rejects with AbortError (matching real fetch).
    fetchMock.mockImplementationOnce(
      (_url: string, init: RequestInit) =>
        new Promise((_resolve, reject) => {
          init.signal?.addEventListener('abort', () => {
            const e = new Error('aborted')
            e.name = 'AbortError'
            reject(e)
          })
        }),
    )
    // Second call resolves with the post-filter result.
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () =>
        feedResponse([makeDoc({ doc_id: 'fast', title: 'Fast doc' })]),
    })
    render(<DocumentsPage />)
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    const central = await screen.findByRole('button', { name: 'Central' })
    await userEvent.click(central)
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    // Fast result must be visible; aborted slow request must not produce
    // a "Network error" banner (AbortError is suppressed).
    expect(await screen.findByText('Fast doc')).toBeInTheDocument()
    expect(screen.queryByText(/network error/i)).not.toBeInTheDocument()
  })
})

describe('DocumentsPage — pagination', () => {
  it('appends rows when "Pull more papers" is clicked', async () => {
    fetchMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () =>
          feedResponse([makeDoc({ doc_id: 'p1', title: 'Page-1 doc' })], true),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () =>
          feedResponse([makeDoc({ doc_id: 'p2', title: 'Page-2 doc' })]),
      })
    render(<DocumentsPage />)

    expect(await screen.findByText('Page-1 doc')).toBeInTheDocument()
    const more = await screen.findByText(/pull more papers/i)
    await userEvent.click(more)
    await waitFor(
      () => expect(screen.getByText('Page-2 doc')).toBeInTheDocument(),
      { timeout: 3000 },
    )
    expect(screen.getByText('Page-1 doc')).toBeInTheDocument()
  })
})

describe('DocumentsPage — accessibility (xfail until D-10/D-12 fixed)', () => {
  it.fails('modal opens with role="dialog" and aria-modal', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => feedResponse([makeDoc({ title: 'Click me' })]),
    })
    render(<DocumentsPage />)
    const row = await screen.findByText('Click me')
    await userEvent.click(row)
    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveAttribute('aria-modal', 'true')
  })

  it.fails('filter pill exposes aria-pressed when active', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => feedResponse([makeDoc()]),
    })
    render(<DocumentsPage />)
    const local = await screen.findByRole('button', { name: 'Local' })
    await userEvent.click(local)
    expect(local).toHaveAttribute('aria-pressed', 'true')
  })
})
