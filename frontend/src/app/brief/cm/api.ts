/**
 * Fetch wrappers for /api/cm/*. Every call carries the Supabase Bearer
 * token. Returns parsed JSON or throws an Error with the response status
 * for the section-level error states to render.
 */
import type { CMDashboardResponse, CMSectionName } from './types'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface FetchOpts {
  state?: string | null
  window?: string
  limit?: number
  mode?: 'attackers' | 'on-message'
  signal?: AbortSignal
}

function buildUrl(path: string, opts: FetchOpts): string {
  const url = new URL(`${API_BASE}/api/cm${path}`)
  if (opts.state) url.searchParams.set('state', opts.state)
  if (opts.window) url.searchParams.set('window', opts.window)
  if (typeof opts.limit === 'number') url.searchParams.set('limit', String(opts.limit))
  if (opts.mode) url.searchParams.set('mode', opts.mode)
  return url.toString()
}

export async function fetchCMSection<T>(
  path: string,
  token: string,
  opts: FetchOpts = {},
): Promise<T> {
  const res = await fetch(buildUrl(path, opts), {
    headers: { Authorization: `Bearer ${token}` },
    cache: 'no-store',
    signal: opts.signal,
  })
  if (!res.ok) {
    let detail = ''
    try {
      const body = await res.text()
      detail = body.slice(0, 200)
    } catch {
      /* ignore */
    }
    throw new Error(`${res.status} ${res.statusText} ${detail}`.trim())
  }
  return (await res.json()) as T
}

export async function fetchDashboard(
  token: string,
  opts: FetchOpts = {},
): Promise<CMDashboardResponse> {
  return fetchCMSection<CMDashboardResponse>('/dashboard', token, opts)
}

export const CM_ENDPOINTS: Record<CMSectionName, string> = {
  pulse: '/pulse',
  issues: '/issues',
  silence: '/silence',
  spokespersons: '/spokespersons',
  cabinet_onmessage: '/cabinet-onmessage',
  dissent: '/dissent',
  trajectory: '/trajectory',
  heatmap: '/heatmap',
  promises: '/promises',
  counter_narratives: '/counter-narratives',
  risk_window: '/risk-window',
  quotes: '/quotes',
  voice_share: '/voice-share',
  language_divergence: '/divergence/language',
  medium_divergence: '/divergence/medium',
}
