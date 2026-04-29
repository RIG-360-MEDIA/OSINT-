'use client'

import { useState } from 'react'
import { HighlightsBand } from './HighlightsBand'
import { MonitorStripe } from './MonitorStripe'
import {
  normalizeArticles,
  normalizeClips,
  normalizeDocuments,
  normalizeNewspapers,
  normalizeSocial,
} from './normalizers'
import type { Pillar } from './types'

interface MonitorViewProps {
  apiBase: string
  token: string | null
}

interface StripeConfig {
  pillar: Pillar
  endpoint: string
  staggerOffsetMs: number
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  normalize: (raw: unknown) => any
}

export function MonitorView({ apiBase, token }: MonitorViewProps) {
  const [paused, setPaused] = useState(false)

  // Per-pillar windows tuned to actual collection cadence so each shelf
  // looks alive: papers and govt docs don't land every day, so a 1-day
  // window often shows 0 (data: 124 papers / 113 docs in last 7 days but
  // 0 today). Articles and clips churn fast enough that a wider window
  // just gives us more recent items to surface, sorted desc by timestamp
  // client-side. Limits raised to 20 so each shelf reads dense.
  const stripes: StripeConfig[] = [
    {
      pillar: 'articles',
      // ROOT CAUSE FIX: /api/coverage/feed defaults to sort=relevance
      // (score DESC), which buries today's freshly-collected articles
      // under older high-scoring ones. We explicitly request
      // sort=recency so newest published_at leads the response. Without
      // this param the shelf showed 1-3 day old items even though 500+
      // articles were collected in the last 24h.
      endpoint: `${apiBase}/api/coverage/feed?sort=recency&limit=40`,
      staggerOffsetMs: 0,
      normalize: normalizeArticles,
    },
    {
      pillar: 'newspaper',
      // Backend orders by relevance_score DESC then collected_at DESC,
      // so we pull max limit (50) and client-side recency sort wins.
      endpoint: `${apiBase}/api/clippings/feed?days=14&limit=50`,
      staggerOffsetMs: 6_000,
      normalize: normalizeNewspapers,
    },
    {
      pillar: 'social',
      endpoint: `${apiBase}/api/signals/feed?days=2&limit=20`,
      staggerOffsetMs: 12_000,
      normalize: normalizeSocial,
    },
    {
      pillar: 'clips',
      // Same root cause as articles/newspaper: backend ORDER BY
      // relevance_score DESC buries today's clips under older
      // high-scoring ones. Pull max limit (50) and let client-side
      // recency sort surface the freshest. Window narrowed to 7 days so
      // the candidate pool is tilted toward recent.
      endpoint: `${apiBase}/api/clips/feed?days=7&limit=50`,
      staggerOffsetMs: 18_000,
      normalize: normalizeClips,
    },
    {
      pillar: 'documents',
      endpoint: `${apiBase}/api/documents/feed?days=14&limit=20`,
      staggerOffsetMs: 24_000,
      normalize: normalizeDocuments,
    },
  ]

  return (
    <div>
      <HighlightsBand apiBase={apiBase} token={token} paused={paused} />

      {stripes.map((s) => (
        <MonitorStripe
          key={s.pillar}
          pillar={s.pillar}
          endpoint={s.endpoint}
          token={token}
          paused={paused}
          staggerOffsetMs={s.staggerOffsetMs}
          normalize={s.normalize}
        />
      ))}

      <div
        style={{
          marginTop: '60px',
          padding: '28px 0',
          borderTop: '1px solid var(--rig-rule)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '18px',
        }}
      >
        <span className="rig-byline">
          Monitoring · 5 pillars · 30s refresh
          <span className="sep">·</span>
          {paused ? 'paused' : 'live'}
        </span>
        <button
          onClick={() => setPaused((p) => !p)}
          className="rig-btn-ghost"
          aria-pressed={paused}
        >
          {paused ? '▶ Resume live' : '❚❚ Pause live'}
        </button>
      </div>
    </div>
  )
}
