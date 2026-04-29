'use client'

/**
 * The Signal Room — daily intelligence summary edition.
 *
 * Aesthetic: typewriter mono headers, serif body, cream paper, no chips,
 * no colour except black + ink-red on warnings. The page renders the
 * latest composed summary, with a left-rail of past editions and click-
 * through topic drilldowns.
 *
 * No LLM-generated prose. The summary body comes pre-composed from the
 * `tasks.compose_social_summary` Celery task.
 */
import {
  forwardRef,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import { useRouter } from 'next/navigation'
import Navigation from '@/components/Navigation'
import { createClient } from '@/lib/supabase/client'

function resolveApiBase(): string {
  const fromEnv = process.env.NEXT_PUBLIC_API_URL
  if (fromEnv) return fromEnv
  if (process.env.NODE_ENV === 'production') {
    throw new Error('NEXT_PUBLIC_API_URL is required in production')
  }
  return 'http://localhost:8000'
}

const API_BASE = resolveApiBase()

// ── Types ──────────────────────────────────────────────────────────────

interface Summary {
  id: string
  edition: number
  classification: string
  generated_at: string
  window_hours: number
  body: string
  sources_used: string[]
  event_count: number
}

interface Edition {
  id: string
  edition: number
  classification: string
  generated_at: string
  window_hours: number
}

interface TopicPost {
  post_id: string
  platform: 'reddit' | 'telegram'
  author_username: string | null
  post_text: string
  post_text_translated: string | null
  post_language: string | null
  post_url: string | null
  upvotes: number
  comment_count: number
  forward_count: number
  forwarded_from: string | null
  sentiment_score: number | null
  matched_entities: string[]
  relevance_score: number
  monitor_name: string | null
  posted_at: string | null
  collected_at: string
}

interface TopicResponse {
  kind: 'entity' | 'cluster' | 'subject'
  key: string
  posts: TopicPost[]
}

// ── Helpers ────────────────────────────────────────────────────────────

const LANG_LABEL: Record<string, string> = {
  en: 'English', te: 'Telugu', hi: 'Hindi', ta: 'Tamil', bn: 'Bengali',
  mr: 'Marathi', gu: 'Gujarati', kn: 'Kannada', ml: 'Malayalam',
  pa: 'Punjabi', or: 'Odia', ur: 'Urdu',
}

function langName(code: string | null): string {
  if (!code) return ''
  return LANG_LABEL[code] || code.toUpperCase()
}

function relativeTime(iso: string | null): string {
  if (!iso) return ''
  const t = new Date(iso).getTime()
  const diff = Date.now() - t
  if (diff < 60_000) return 'just now'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`
  return `${Math.floor(diff / 86_400_000)}d ago`
}

// Detect "PROPOSE ADD" lines in the summary body and extract the
// quoted subject so we can turn it into a clickable topic link.
function decorateBody(body: string): React.ReactNode[] {
  const lines = body.split('\n')
  const out: React.ReactNode[] = []
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    // Highlight HOSTILE / WARNING / ERROR-ish words in ink-red.
    out.push(
      <span key={i} style={{ display: 'block' }}>
        {line.split(/(HOSTILE|INDICATOR|FOLLOW|PROPOSE ADD|CORROBORATED|HIGH|MED|LOW|NIL)/g).map((seg, j) => {
          const isTag = /^(HOSTILE|INDICATOR|FOLLOW|PROPOSE ADD|CORROBORATED|HIGH|MED|LOW|NIL)$/.test(seg)
          return isTag ? (
            <strong
              key={j}
              style={{ color: 'var(--rig-oxblood, #8b1a1a)' }}
            >
              {seg}
            </strong>
          ) : (
            <span key={j}>{seg}</span>
          )
        })}
      </span>,
    )
  }
  return out
}

// ── Page ───────────────────────────────────────────────────────────────

export default function SignalsPage() {
  const router = useRouter()
  const routerRef = useRef(router)
  routerRef.current = router

  const [token, setToken] = useState<string | null>(null)
  const [summary, setSummary] = useState<Summary | null>(null)
  const [editions, setEditions] = useState<Edition[]>([])
  const [topic, setTopic] = useState<TopicResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const drilldownRef = useRef<HTMLElement | null>(null)

  const auth = useCallback(
    (t: string): HeadersInit => ({ Authorization: `Bearer ${t}` }),
    [],
  )

  // ── Load latest summary + editions ───────────────────────────
  const loadLatest = useCallback(
    async (t: string, signal: AbortSignal) => {
      setLoading(true)
      setError(null)
      try {
        const [latestRes, edRes] = await Promise.all([
          fetch(`${API_BASE}/api/signals/summary/latest`, {
            headers: auth(t), signal,
          }),
          fetch(`${API_BASE}/api/signals/summary/editions?limit=20`, {
            headers: auth(t), signal,
          }),
        ])
        if (signal.aborted) return
        if (latestRes.status === 401 || edRes.status === 401) {
          routerRef.current.push('/login')
          return
        }
        if (!latestRes.ok) {
          throw new Error(
            `Summary unavailable (HTTP ${latestRes.status}). Try again in a moment.`,
          )
        }
        const latest = (await latestRes.json()).summary as Summary | null
        const eds = edRes.ok
          ? ((await edRes.json()).editions as Edition[])
          : []
        if (signal.aborted) return
        setSummary(latest)
        setEditions(eds)
      } catch (err: unknown) {
        if (err instanceof DOMException && err.name === 'AbortError') return
        setError(
          err instanceof Error
            ? err.message
            : 'Could not reach the desk.',
        )
      } finally {
        if (!signal.aborted) setLoading(false)
      }
    },
    [auth],
  )

  const loadEdition = useCallback(
    async (t: string, id: string, signal: AbortSignal) => {
      setLoading(true)
      setError(null)
      try {
        const res = await fetch(
          `${API_BASE}/api/signals/summary/${id}`,
          { headers: auth(t), signal },
        )
        if (signal.aborted) return
        if (res.status === 401) {
          routerRef.current.push('/login')
          return
        }
        if (!res.ok) {
          throw new Error(
            `Edition unavailable (HTTP ${res.status}). Try again in a moment.`,
          )
        }
        const s = (await res.json()).summary as Summary | null
        if (signal.aborted) return
        setSummary(s)
      } catch (err: unknown) {
        if (err instanceof DOMException && err.name === 'AbortError') return
        setError(
          err instanceof Error ? err.message : 'Could not reach the desk.',
        )
      } finally {
        if (!signal.aborted) setLoading(false)
      }
    },
    [auth],
  )

  const loadTopic = useCallback(
    async (
      t: string,
      kind: TopicResponse['kind'],
      key: string,
      signal: AbortSignal,
    ) => {
      try {
        const res = await fetch(
          `${API_BASE}/api/signals/topic/${kind}/${encodeURIComponent(key)}`,
          { headers: auth(t), signal },
        )
        if (signal.aborted) return
        if (res.status === 401) {
          routerRef.current.push('/login')
          return
        }
        if (!res.ok) {
          throw new Error(
            `Drilldown unavailable (HTTP ${res.status}).`,
          )
        }
        const data = (await res.json()) as TopicResponse
        if (signal.aborted) return
        if (data.posts.some((p) => (p.platform as string) === 'twitter')) {
          throw new Error('Unexpected Twitter data in drilldown response')
        }
        setTopic(data)
        requestAnimationFrame(() => {
          drilldownRef.current?.scrollIntoView({
            behavior: 'smooth',
            block: 'start',
          })
        })
      } catch (err: unknown) {
        if (err instanceof DOMException && err.name === 'AbortError') return
        setError(
          err instanceof Error ? err.message : 'Drilldown failed.',
        )
      }
    },
    [auth],
  )

  // ── Auth + initial load ─────────────────────────────────────
  useEffect(() => {
    const supabase = createClient()
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (!session) {
        routerRef.current.push('/login')
        return
      }
      setToken(session.access_token)
    })
    const { data: sub } = supabase.auth.onAuthStateChange(
      (_event, sess) => {
        if (!sess) {
          routerRef.current.push('/login')
          return
        }
        setToken(sess.access_token)
      },
    )
    return () => sub.subscription.unsubscribe()
  }, [])

  useEffect(() => {
    if (!token) return
    const ctl = new AbortController()
    void loadLatest(token, ctl.signal)
    return () => ctl.abort()
  }, [token, loadLatest])

  return (
    <div
      style={{
        minHeight: '100vh',
        background:
          'repeating-linear-gradient(0deg, var(--rig-paper, #f5efe1) 0, var(--rig-paper, #f5efe1) 26px, rgba(0,0,0,0.025) 26px, rgba(0,0,0,0.025) 27px)',
        // typewriter ledger feel
      }}
    >
      <Navigation />
      <div
        style={{
          paddingTop: 'var(--topbar-h)',
          display: 'grid',
          gridTemplateColumns: 'minmax(200px, 240px) 1fr',
          gap: '24px',
          maxWidth: '1240px',
          margin: '0 auto',
          padding: '40px 32px 80px',
        }}
      >
        {/* Left rail — past editions */}
        <aside
          style={{
            position: 'sticky',
            top: '90px',
            alignSelf: 'flex-start',
            fontFamily: 'var(--font-mono)',
            fontSize: '11px',
            letterSpacing: '0.08em',
          }}
        >
          <div
            style={{
              textTransform: 'uppercase',
              letterSpacing: '0.28em',
              fontSize: '10px',
              color: 'var(--rig-ink-3)',
              marginBottom: '10px',
              borderBottom: '1px solid var(--rig-rule)',
              paddingBottom: '6px',
            }}
          >
            Editions
          </div>
          {editions.length === 0 ? (
            <div style={{ color: 'var(--rig-ink-3)' }}>—</div>
          ) : (
            <ol
              style={{
                listStyle: 'none',
                padding: 0,
                margin: 0,
                display: 'flex',
                flexDirection: 'column',
                gap: '4px',
              }}
            >
              {editions.map(e => (
                <li key={e.id}>
                  <button
                    type="button"
                    aria-label={`Open edition ${e.edition} from ${new Date(e.generated_at).toLocaleDateString()} (${e.classification})`}
                    aria-current={summary?.id === e.id ? 'page' : undefined}
                    onClick={() => {
                      if (!token) return
                      const ctl = new AbortController()
                      void loadEdition(token, e.id, ctl.signal)
                    }}
                    style={{
                      width: '100%',
                      textAlign: 'left',
                      background:
                        summary?.id === e.id
                          ? 'rgba(0,0,0,0.05)'
                          : 'transparent',
                      border: 'none',
                      padding: '6px 8px',
                      cursor: 'pointer',
                      fontFamily: 'inherit',
                      fontSize: 'inherit',
                      color:
                        summary?.id === e.id
                          ? 'var(--rig-ink)'
                          : 'var(--rig-ink-2, #2c2722)',
                    }}
                  >
                    {String(e.edition).padStart(3, '0')} ·{' '}
                    {new Date(e.generated_at).toLocaleDateString([], {
                      day: '2-digit',
                      month: 'short',
                    })}{' '}
                    {new Date(e.generated_at).toLocaleTimeString([], {
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </button>
                </li>
              ))}
            </ol>
          )}
        </aside>

        {/* Main column — typewriter sheet */}
        <main>
          {error && (
            <DeskMemo
              kicker="Desk memo"
              headline="The wires went silent."
              body={error}
              onRetry={() => {
                if (!token) return
                const ctl = new AbortController()
                void loadLatest(token, ctl.signal)
              }}
            />
          )}

          {!error && !summary && !loading && (
            <DeskMemo
              kicker="Desk memo"
              headline="No edition composed yet."
              body="The composer has not produced an edition. Beat fires every 6 hours, or you can trigger a run manually."
            />
          )}

          {summary && (
            <>
              <SummarySheet
                summary={summary}
                onTopic={(kind, key) => {
                  if (!token) return
                  const ctl = new AbortController()
                  void loadTopic(token, kind, key, ctl.signal)
                }}
              />
              {topic && (
                <TopicDrilldown
                  ref={drilldownRef}
                  topic={topic}
                  onClose={() => setTopic(null)}
                />
              )}
            </>
          )}

          {loading && !summary && <Loading />}
        </main>
      </div>
    </div>
  )
}

// ── SummarySheet — the typewriter document ───────────────────────────

interface SummarySheetProps {
  summary: Summary
  onTopic: (kind: TopicResponse['kind'], key: string) => void
}

// ── Parsed-section types ──────────────────────────────────────────

interface SurgeItem {
  subject: string
  posts: number
  sources: number
  confidence: 'HIGH' | 'MED' | 'LOW'
  quote: string | null
  quoteSource: string | null
}

interface NewSubjectItem {
  term: string
  occurrences: number
  sources: number
  quote: string | null
  quoteSource: string | null
}

interface SilenceItem {
  subject: string
  count: number
  gap: string
}

interface OfficialStatusItem {
  codename: string
  name: string
  age: string
}

interface SentimentExtreme {
  tone: 'FAVOURABLE' | 'HOSTILE'
  score: number
  source: string
  body: string
}

type Section =
  | { kind: 'glance'; total: number; reddit: number; telegram: number;
      sources: number; nonEnglish: number; languages: string }
  | { kind: 'headline'; body: string; source: string;
      relevance: number; engagement: number }
  | { kind: 'surge'; items: SurgeItem[] }
  | { kind: 'repetition'; description: string; quote: string;
      confidence: 'HIGH' | 'MED' | 'LOW' }
  | { kind: 'silence'; items: SilenceItem[] }
  | { kind: 'sentiment'; extremes: SentimentExtreme[] }
  | { kind: 'newSubjects'; items: NewSubjectItem[] }
  | { kind: 'official'; rows: OfficialStatusItem[] }
  | { kind: 'stationary'; items: string[] }
  | { kind: 'note'; text: string }
  | { kind: 'sources'; codenames: string[] }

// ── Body parser ──────────────────────────────────────────────────

function parseBody(body: string): Section[] {
  const lines = body.split('\n')
  const sections: Section[] = []

  // First, capture optional NOTE banner
  const noteIdx = lines.findIndex(l => l.trim().startsWith('NOTE.'))
  if (noteIdx >= 0) {
    let txt = lines[noteIdx].trim().replace(/^NOTE\.\s*/, '')
    let j = noteIdx + 1
    while (j < lines.length && lines[j].startsWith('        ')) {
      txt += ' ' + lines[j].trim()
      j++
    }
    sections.push({ kind: 'note', text: txt })
  }

  // Find ¶ section starts. Terminate the current block when we hit
  // either the closing rule (═══...) or the SOURCES/SOURCE LEGEND
  // footer — otherwise the last section silently swallows them.
  type Block = { header: string; body: string[] }
  const blocks: Block[] = []
  let cur: Block | null = null
  const isFooterStart = (l: string) =>
    /^═{5,}/.test(l) ||
    /^SOURCES?\b/i.test(l.trim()) ||
    /^SOURCE LEGEND/i.test(l.trim()) ||
    /^Pipeline cadence/i.test(l.trim()) ||
    /^—\s*END\s*—/.test(l.trim()) ||
    /^─{5,}/.test(l)
  for (const l of lines) {
    if (/^¶/.test(l)) {
      if (cur) blocks.push(cur)
      cur = { header: l, body: [] }
    } else if (isFooterStart(l)) {
      if (cur) {
        blocks.push(cur)
        cur = null
      }
    } else if (cur) {
      cur.body.push(l)
    }
  }
  if (cur) blocks.push(cur)

  for (const b of blocks) {
    const h = b.header.replace(/\s+\d{6}Z .+$/, '').trim()
    const text = b.body.join('\n')

    if (/AT A GLANCE/.test(h)) {
      // Use [\s\S]*? instead of .* + /s flag so this builds on TS targets
      // older than ES2018. Functionally identical: cross-line non-greedy.
      const m1 = text.match(
        /Posts collected \(24h\):\s*(\d+)[\s\S]*?Reddit\s*(\d+)[\s\S]*?Telegram\s*(\d+)/,
      )
      const m2 = text.match(
        /Active sources:\s*(\d+)[\s\S]*?Non-English posts:\s*(\d+)/,
      )
      const m3 = text.match(/Languages:\s*(.+)/)
      sections.push({
        kind: 'glance',
        total: m1 ? +m1[1] : 0,
        reddit: m1 ? +m1[2] : 0,
        telegram: m1 ? +m1[3] : 0,
        sources: m2 ? +m2[1] : 0,
        nonEnglish: m2 ? +m2[2] : 0,
        languages: m3 ? m3[1].trim() : '',
      })
    } else if (/HEADLINE/.test(h)) {
      // Body lines are indented 6 spaces; the last `— SOURCE  ·  relevance N/100  ·  engagement M`
      // marker line sits at the bottom.
      const meta = text.match(
        /—\s*([A-Z0-9/_-]+)\s*·\s*relevance\s*(\d+)\/100\s*·\s*engagement\s*(\d+)/,
      )
      let quoteText = text
      if (meta) {
        quoteText = text
          .split('\n')
          .filter(l => !l.includes('relevance ') || !l.includes('engagement '))
          .join('\n')
      }
      sections.push({
        kind: 'headline',
        body: quoteText.replace(/^\s+|\s+$/g, '').replace(/\s{2,}/g, ' '),
        source: meta ? meta[1] : '',
        relevance: meta ? +meta[2] : 0,
        engagement: meta ? +meta[3] : 0,
      })
    } else if (/ENTITIES UNDER SURGE/.test(h)) {
      const items: SurgeItem[] = []
      const bodyLines = b.body.filter(l => l.trim())
      // Skip first 1-2 explanatory lines
      let i = 0
      while (
        i < bodyLines.length &&
        !/posts in 24h|×.*usual/.test(bodyLines[i])
      ) {
        i++
      }
      while (i < bodyLines.length) {
        const line = bodyLines[i]
        const sm = line.match(
          /^\s+(\S.*?)\s{2,}(\d+)\s*posts in 24h\s*·\s*(\d+)\s*src\s*·\s*conf:(HIGH|MED|LOW)/,
        )
        if (sm) {
          let quote: string | null = null
          let quoteSource: string | null = null
          if (i + 1 < bodyLines.length && /↳/.test(bodyLines[i + 1])) {
            const qm = bodyLines[i + 1].match(
              /↳\s*"([^"]+)"\s*—\s*(\S+)/,
            )
            if (qm) {
              quote = qm[1]
              quoteSource = qm[2]
            }
            i++
          }
          items.push({
            subject: sm[1].trim(),
            posts: +sm[2],
            sources: +sm[3],
            confidence: sm[4] as 'HIGH' | 'MED' | 'LOW',
            quote,
            quoteSource,
          })
        }
        i++
      }
      sections.push({ kind: 'surge', items })
    } else if (/PHRASING REPETITION/.test(h)) {
      const desc = b.body
        .filter(
          l =>
            l.trim() &&
            !l.includes('CONF:') &&
            !/repeated near-identical phrasing/.test(l),
        )
        .map(l => l.trim())
        .join(' ')
        .trim()
      const quoteLines = b.body
        .filter(
          l =>
            l.trim() &&
            (/repeated/.test(l) ||
              /Pattern/.test(l) ||
              /"[^"]*"/.test(l) ||
              /^\s+[A-Z]/.test(l)),
        )
        .map(l => l.trim())
      const quote = quoteLines
        .filter(l => !l.startsWith('CONF'))
        .join(' ')
      const cm = text.match(/CONF:\s*(HIGH|MED|LOW)/)
      sections.push({
        kind: 'repetition',
        description: desc,
        quote,
        confidence: cm ? (cm[1] as 'HIGH' | 'MED' | 'LOW') : 'MED',
      })
    } else if (/OFFICIAL SILENCE/.test(h)) {
      // One subject per silence section in current composer.
      const sm = text.match(
        /(\S.*?)\s+drew\s+(\d+)\s+non-official mentions in 24h;\s*no tracked official\s*channel has spoken to it in\s*≥(\d+h)/,
      )
      if (sm) {
        // Append to last silence section if it exists, else create one.
        const last = sections[sections.length - 1]
        const item: SilenceItem = {
          subject: sm[1].trim(),
          count: +sm[2],
          gap: sm[3],
        }
        if (last && last.kind === 'silence') {
          last.items.push(item)
        } else {
          sections.push({ kind: 'silence', items: [item] })
        }
      }
    } else if (/SENTIMENT EXTREMES/.test(h)) {
      const extremes: SentimentExtreme[] = []
      const txt = b.body.join('\n')
      const m1 = txt.match(
        /MOST FAVOURABLE\s*\(([+-]?\d*\.?\d+)\)\s*—\s*(\S+)\s*\n\s*"([\s\S]*?)"/,
      )
      const m2 = txt.match(
        /MOST HOSTILE\s+\(([+-]?\d*\.?\d+)\)\s*—\s*(\S+)\s*\n\s*"([\s\S]*?)"/,
      )
      if (m1) {
        extremes.push({
          tone: 'FAVOURABLE',
          score: +m1[1],
          source: m1[2],
          body: m1[3].replace(/\s+/g, ' ').trim(),
        })
      }
      if (m2) {
        extremes.push({
          tone: 'HOSTILE',
          score: +m2[1],
          source: m2[2],
          body: m2[3].replace(/\s+/g, ' ').trim(),
        })
      }
      sections.push({ kind: 'sentiment', extremes })
    } else if (/NEW ON THE RADAR/.test(h)) {
      const items: NewSubjectItem[] = []
      const bl = b.body
      for (let i = 0; i < bl.length; i++) {
        const line = bl[i]
        const m = line.match(
          /"([^"]+)"\s*·\s*n=(\d+)\s*\/\s*(\d+)\s*src\s+PROPOSE ADD/,
        )
        if (m) {
          let quote: string | null = null
          let quoteSource: string | null = null
          if (i + 1 < bl.length && /↳/.test(bl[i + 1])) {
            const qm = bl[i + 1].match(/↳\s*"([^"]+)"\s*—\s*(\S+)/)
            if (qm) {
              quote = qm[1]
              quoteSource = qm[2]
            }
            i++
          }
          items.push({
            term: m[1],
            occurrences: +m[2],
            sources: +m[3],
            quote,
            quoteSource,
          })
        }
      }
      sections.push({ kind: 'newSubjects', items })
    } else if (/OFFICIAL CHANNEL STATUS/.test(h)) {
      const rows: OfficialStatusItem[] = []
      for (const line of b.body) {
        const m = line.match(
          /^\s+(\S+)\s{2,}(.+?)\s{2,}last:\s*(.+)$/,
        )
        if (m) {
          rows.push({
            codename: m[1],
            name: m[2].trim(),
            age: m[3].trim(),
          })
        }
      }
      sections.push({ kind: 'official', rows })
    } else if (/STATIONARY/.test(h)) {
      const STOP = new Set([
        'india', 'does', 'then', 'since', 'would', 'could', 'should',
        'your', 'looking', 'need', 'read', 'also', 'please', 'thank',
        'while', 'hello', 'farmers', 'red bull', 'indian', 'chief',
        'minister', 'director', 'twitter', 'facebook',
      ])
      const txt = b.body
        .filter(
          l =>
            l.trim() &&
            !/Subjects on the watchlist/.test(l) &&
            !/produced no surge/.test(l),
        )
        .map(l => l.trim())
        .join(' ')
      const items = txt
        .split(',')
        .map(s =>
          s
            .replace(/[═─]+/g, '')      // strip rule chars
            .replace(/^\s*\d+\s*active\)?:?.*$/i, '') // strip stray "23 active):"
            .replace(/R\/[A-Z_]+/g, '') // strip stray source codes
            .replace(/TG-[A-Z_]+/g, '')
            .trim(),
        )
        .filter(t => t && !STOP.has(t.toLowerCase()) && t.length >= 3)
      sections.push({ kind: 'stationary', items })
    }
  }

  return sections
}

// ── Styled subcomponents ─────────────────────────────────────────

function ConfBadge({ level }: { level: 'HIGH' | 'MED' | 'LOW' }) {
  const colorMap = {
    HIGH: { bg: 'rgba(184, 134, 11, 0.15)', fg: 'var(--rig-gold, #b8860b)' },
    MED: { bg: 'rgba(50, 40, 30, 0.10)', fg: 'var(--rig-ink-2, #2c2722)' },
    LOW: { bg: 'rgba(50, 40, 30, 0.06)', fg: 'var(--rig-ink-3, #888)' },
  }
  const { bg, fg } = colorMap[level]
  return (
    <span
      style={{
        display: 'inline-block',
        padding: '2px 8px',
        background: bg,
        color: fg,
        fontFamily: 'var(--font-mono)',
        fontSize: '9.5px',
        letterSpacing: '0.18em',
        fontWeight: 600,
        borderRadius: '2px',
      }}
    >
      {level}
    </span>
  )
}

function SectionHeading({
  num,
  title,
  hint,
}: {
  num: number | null
  title: string
  hint?: string
}) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'baseline',
        gap: '14px',
        marginTop: '36px',
        marginBottom: '6px',
        paddingBottom: '8px',
        borderBottom: '2px solid var(--rig-ink, #1a1410)',
      }}
    >
      {num !== null && (
        <span
          style={{
            fontFamily: 'var(--font-serif)',
            fontStyle: 'italic',
            fontSize: '22px',
            color: 'var(--rig-gold, #b8860b)',
            lineHeight: 1,
          }}
        >
          ¶{num}
        </span>
      )}
      <span
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: '11px',
          letterSpacing: '0.28em',
          textTransform: 'uppercase',
          fontWeight: 700,
          color: 'var(--rig-ink, #1a1410)',
        }}
      >
        {title}
      </span>
      {hint && (
        <span
          style={{
            fontFamily: 'var(--font-serif)',
            fontStyle: 'italic',
            fontSize: '13px',
            color: 'var(--rig-ink-3, #888)',
            marginLeft: 'auto',
          }}
        >
          {hint}
        </span>
      )}
    </div>
  )
}

function GlanceStrip({
  total, reddit, telegram, sources, nonEnglish, languages,
}: {
  total: number; reddit: number; telegram: number;
  sources: number; nonEnglish: number; languages: string;
}) {
  const Stat = ({ label, value }: { label: string; value: string | number }) => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
      <span
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: '9.5px',
          letterSpacing: '0.22em',
          textTransform: 'uppercase',
          color: 'var(--rig-ink-3, #888)',
        }}
      >
        {label}
      </span>
      <span
        style={{
          fontFamily: 'var(--font-serif)',
          fontStyle: 'italic',
          fontSize: '24px',
          fontWeight: 500,
          color: 'var(--rig-ink, #1a1410)',
          lineHeight: 1,
        }}
      >
        {value}
      </span>
    </div>
  )
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))',
        gap: '24px',
        padding: '20px 24px',
        background: 'rgba(20, 14, 6, 0.03)',
        border: '1px solid var(--rig-rule)',
        marginTop: '8px',
      }}
    >
      <Stat label="Posts (24h)" value={total} />
      <Stat label="Reddit" value={reddit} />
      <Stat label="Telegram" value={telegram} />
      <Stat label="Sources" value={sources} />
      <Stat label="Translated" value={nonEnglish} />
      <div
        style={{
          gridColumn: 'span 2',
          display: 'flex',
          flexDirection: 'column',
          gap: '4px',
        }}
      >
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '9.5px',
            letterSpacing: '0.22em',
            textTransform: 'uppercase',
            color: 'var(--rig-ink-3, #888)',
          }}
        >
          Languages
        </span>
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '12px',
            color: 'var(--rig-ink-2, #2c2722)',
          }}
        >
          {languages || '—'}
        </span>
      </div>
    </div>
  )
}

function HeadlineCard({
  body, source, relevance, engagement,
}: {
  body: string; source: string; relevance: number; engagement: number;
}) {
  return (
    <blockquote
      style={{
        margin: '12px 0 0 0',
        padding: '20px 28px',
        borderLeft: '4px solid var(--rig-gold, #b8860b)',
        background: 'rgba(255, 253, 247, 0.7)',
      }}
    >
      <p
        style={{
          fontFamily: 'var(--font-serif)',
          fontSize: '17px',
          lineHeight: 1.55,
          margin: 0,
          color: 'var(--rig-ink, #1a1410)',
        }}
      >
        {body.length > 320 ? body.slice(0, 320) + '…' : body}
      </p>
      <div
        style={{
          marginTop: '12px',
          display: 'flex',
          gap: '14px',
          fontFamily: 'var(--font-mono)',
          fontSize: '10px',
          letterSpacing: '0.16em',
          textTransform: 'uppercase',
          color: 'var(--rig-ink-3, #888)',
        }}
      >
        <span>— {source}</span>
        <span>relevance {relevance}/100</span>
        <span>engagement {engagement}</span>
      </div>
    </blockquote>
  )
}

function SurgeRow({
  item, onClickSubject,
}: {
  item: SurgeItem; onClickSubject: (s: string) => void
}) {
  return (
    <div
      style={{
        padding: '14px 0',
        borderBottom: '1px solid var(--rig-rule)',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          gap: '14px',
          flexWrap: 'wrap',
        }}
      >
        <button
          type="button"
          onClick={() => onClickSubject(item.subject)}
          style={{
            background: 'transparent',
            border: 'none',
            padding: 0,
            margin: 0,
            cursor: 'pointer',
            fontFamily: 'var(--font-serif)',
            fontSize: '17px',
            fontWeight: 500,
            color: 'var(--rig-ink, #1a1410)',
            textAlign: 'left',
            textDecorationStyle: 'dotted',
          }}
          aria-label={`Drill into ${item.subject}`}
          onMouseEnter={e =>
            ((e.currentTarget as HTMLButtonElement).style.textDecoration =
              'underline dotted var(--rig-gold)')
          }
          onMouseLeave={e =>
            ((e.currentTarget as HTMLButtonElement).style.textDecoration =
              'none')
          }
        >
          {item.subject}
        </button>
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '11px',
            color: 'var(--rig-ink-2, #2c2722)',
            letterSpacing: '0.06em',
          }}
        >
          {item.posts} posts · {item.sources} src
        </span>
        <ConfBadge level={item.confidence} />
      </div>
      {item.quote && (
        <div
          style={{
            marginTop: '6px',
            paddingLeft: '14px',
            borderLeft: '2px solid var(--rig-rule)',
          }}
        >
          <span
            style={{
              fontFamily: 'var(--font-serif)',
              fontStyle: 'italic',
              fontSize: '13.5px',
              color: 'var(--rig-ink-2, #2c2722)',
              lineHeight: 1.5,
            }}
          >
            “{item.quote}”
          </span>
          {item.quoteSource && (
            <span
              style={{
                marginLeft: '10px',
                fontFamily: 'var(--font-mono)',
                fontSize: '10px',
                letterSpacing: '0.14em',
                color: 'var(--rig-ink-3, #888)',
                whiteSpace: 'nowrap',
              }}
            >
              — {item.quoteSource}
            </span>
          )}
        </div>
      )}
    </div>
  )
}

function RepetitionCard({
  description, quote, confidence,
}: {
  description: string; quote: string; confidence: 'HIGH' | 'MED' | 'LOW'
}) {
  return (
    <div
      style={{
        marginTop: '12px',
        padding: '18px 22px',
        borderLeft: '4px solid var(--rig-oxblood, #8b1a1a)',
        background: 'rgba(255, 253, 247, 0.7)',
      }}
    >
      <p
        style={{
          fontFamily: 'var(--font-sans)',
          fontSize: '13px',
          color: 'var(--rig-ink-3, #888)',
          margin: 0,
          marginBottom: '10px',
          lineHeight: 1.5,
        }}
      >
        {description}
      </p>
      <p
        style={{
          fontFamily: 'var(--font-serif)',
          fontSize: '15px',
          lineHeight: 1.55,
          margin: 0,
          color: 'var(--rig-ink, #1a1410)',
        }}
      >
        {quote}
      </p>
      <div style={{ marginTop: '10px' }}>
        <ConfBadge level={confidence} />
      </div>
    </div>
  )
}

function SilenceList({ items }: { items: SilenceItem[] }) {
  return (
    <div style={{ marginTop: '12px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
      {items.map(it => (
        <div
          key={it.subject}
          style={{
            padding: '12px 18px',
            borderLeft: '4px solid var(--rig-ink-3, #888)',
            background: 'rgba(20, 14, 6, 0.04)',
            display: 'flex',
            alignItems: 'baseline',
            gap: '14px',
            flexWrap: 'wrap',
          }}
        >
          <span
            style={{
              fontFamily: 'var(--font-serif)',
              fontSize: '17px',
              fontWeight: 500,
              color: 'var(--rig-ink, #1a1410)',
            }}
          >
            {it.subject}
          </span>
          <span
            style={{
              fontFamily: 'var(--font-sans)',
              fontSize: '13px',
              color: 'var(--rig-ink-2, #2c2722)',
            }}
          >
            drew <strong>{it.count}</strong> non-official mentions in 24h.
            No official channel responded in {it.gap}.
          </span>
          <span
            style={{
              marginLeft: 'auto',
              fontFamily: 'var(--font-mono)',
              fontSize: '10px',
              letterSpacing: '0.18em',
              color: 'var(--rig-oxblood, #8b1a1a)',
              fontWeight: 600,
            }}
          >
            INDICATOR · FOLLOW
          </span>
        </div>
      ))}
    </div>
  )
}

function SentimentExtremes({ extremes }: { extremes: SentimentExtreme[] }) {
  return (
    <div
      style={{
        marginTop: '12px',
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
        gap: '14px',
      }}
    >
      {extremes.map(ex => {
        const accent =
          ex.tone === 'FAVOURABLE'
            ? 'var(--rig-gold, #b8860b)'
            : 'var(--rig-oxblood, #8b1a1a)'
        return (
          <div
            key={ex.tone}
            style={{
              padding: '16px 20px',
              borderTop: `3px solid ${accent}`,
              background: 'rgba(255, 253, 247, 0.7)',
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'baseline',
                marginBottom: '8px',
              }}
            >
              <span
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '10px',
                  letterSpacing: '0.24em',
                  color: accent,
                  fontWeight: 700,
                }}
              >
                MOST {ex.tone}
              </span>
              <span
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '12px',
                  color: accent,
                }}
              >
                {ex.score >= 0 ? '+' : ''}
                {ex.score.toFixed(2)}
              </span>
            </div>
            <p
              style={{
                fontFamily: 'var(--font-serif)',
                fontStyle: 'italic',
                fontSize: '14px',
                lineHeight: 1.55,
                margin: 0,
                color: 'var(--rig-ink, #1a1410)',
              }}
            >
              “{ex.body}”
            </p>
            <div
              style={{
                marginTop: '8px',
                fontFamily: 'var(--font-mono)',
                fontSize: '10px',
                letterSpacing: '0.16em',
                color: 'var(--rig-ink-3, #888)',
              }}
            >
              — {ex.source}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function NewSubjectsList({
  items, onClickSubject,
}: {
  items: NewSubjectItem[]; onClickSubject: (s: string) => void
}) {
  return (
    <div
      style={{
        marginTop: '12px',
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
        gap: '12px',
      }}
    >
      {items.map(it => (
        <div
          key={it.term}
          style={{
            padding: '12px 16px',
            background: 'rgba(20, 14, 6, 0.03)',
            border: '1px solid var(--rig-rule)',
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'baseline',
              gap: '10px',
              flexWrap: 'wrap',
            }}
          >
            <button
              type="button"
              onClick={() => onClickSubject(it.term)}
              style={{
                background: 'transparent',
                border: 'none',
                padding: 0,
                margin: 0,
                cursor: 'pointer',
                fontFamily: 'var(--font-serif)',
                fontSize: '15px',
                fontWeight: 500,
                color: 'var(--rig-ink, #1a1410)',
              }}
              onMouseEnter={e =>
                ((e.currentTarget as HTMLButtonElement).style.textDecoration =
                  'underline dotted var(--rig-gold)')
              }
              onMouseLeave={e =>
                ((e.currentTarget as HTMLButtonElement).style.textDecoration =
                  'none')
              }
            >
              {it.term}
            </button>
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '10px',
                letterSpacing: '0.06em',
                color: 'var(--rig-ink-3, #888)',
              }}
            >
              n={it.occurrences} / {it.sources} src
            </span>
            <span
              style={{
                marginLeft: 'auto',
                fontFamily: 'var(--font-mono)',
                fontSize: '9.5px',
                letterSpacing: '0.18em',
                color: 'var(--rig-gold, #b8860b)',
                fontWeight: 700,
              }}
            >
              PROPOSE ADD
            </span>
          </div>
          {it.quote && (
            <div
              style={{
                marginTop: '6px',
                paddingLeft: '12px',
                borderLeft: '2px solid var(--rig-rule)',
              }}
            >
              <span
                style={{
                  fontFamily: 'var(--font-serif)',
                  fontStyle: 'italic',
                  fontSize: '12.5px',
                  color: 'var(--rig-ink-2, #2c2722)',
                  lineHeight: 1.5,
                }}
              >
                “{it.quote}”
              </span>
              {it.quoteSource && (
                <span
                  style={{
                    marginLeft: '8px',
                    fontFamily: 'var(--font-mono)',
                    fontSize: '9.5px',
                    letterSpacing: '0.14em',
                    color: 'var(--rig-ink-3, #888)',
                  }}
                >
                  — {it.quoteSource}
                </span>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

function OfficialStatusTable({ rows }: { rows: OfficialStatusItem[] }) {
  return (
    <table
      style={{
        marginTop: '12px',
        width: '100%',
        borderCollapse: 'collapse',
        fontFamily: 'var(--font-mono)',
        fontSize: '12px',
      }}
    >
      <tbody>
        {rows.map(r => (
          <tr
            key={r.codename}
            style={{ borderBottom: '1px dotted var(--rig-rule)' }}
          >
            <td style={{ padding: '8px 12px 8px 0', color: 'var(--rig-ink-2, #2c2722)' }}>
              {r.codename}
            </td>
            <td
              style={{
                padding: '8px 12px',
                fontFamily: 'var(--font-serif)',
                fontSize: '13px',
                color: 'var(--rig-ink, #1a1410)',
              }}
            >
              {r.name}
            </td>
            <td
              style={{
                padding: '8px 0 8px 12px',
                color: 'var(--rig-ink-3, #888)',
                textAlign: 'right',
                whiteSpace: 'nowrap',
              }}
            >
              last: {r.age}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function StationaryChips({ items }: { items: string[] }) {
  return (
    <div
      style={{
        marginTop: '10px',
        display: 'flex',
        flexWrap: 'wrap',
        gap: '4px 14px',
        minWidth: 0,
        maxWidth: '100%',
        wordBreak: 'break-word',
      }}
    >
      {items.map((it, idx) => (
        <span
          key={`${it}-${idx}`}
          style={{
            fontFamily: 'var(--font-serif)',
            fontStyle: 'italic',
            fontSize: '13px',
            color: 'var(--rig-ink-3, #888)',
          }}
        >
          {it}
        </span>
      ))}
    </div>
  )
}

function NoteBanner({ text }: { text: string }) {
  return (
    <div
      role="note"
      style={{
        marginTop: '14px',
        padding: '10px 16px',
        borderLeft: '3px solid var(--rig-gold, #b8860b)',
        background: 'rgba(184, 134, 11, 0.08)',
        fontFamily: 'var(--font-sans)',
        fontSize: '12.5px',
        color: 'var(--rig-ink-2, #2c2722)',
        lineHeight: 1.5,
      }}
    >
      <strong style={{ letterSpacing: '0.1em', textTransform: 'uppercase', fontSize: '10px' }}>
        Note
      </strong>{' '}
      — {text}
    </div>
  )
}

// ── Main SummarySheet (now component-driven, not <pre>) ──────────

function SummarySheet({ summary, onTopic }: SummarySheetProps) {
  const [showRaw, setShowRaw] = useState(false)
  const sections = useMemo(() => parseBody(summary.body), [summary.body])
  const composedAt = new Date(summary.generated_at)
  let counter = 0
  const nextNum = () => ++counter

  return (
    <article
      style={{
        background: 'rgba(255, 253, 247, 0.96)',
        border: '1px solid var(--rig-rule)',
        boxShadow: '0 6px 24px rgba(20, 14, 6, 0.10)',
        padding: '32px 40px 40px',
        position: 'relative',
      }}
    >
      {/* Classification corner mark */}
      <div
        aria-hidden="true"
        style={{
          position: 'absolute',
          top: '14px',
          right: '20px',
          fontFamily: 'var(--font-mono)',
          fontSize: '9px',
          letterSpacing: '0.32em',
          color: 'var(--rig-oxblood, #8b1a1a)',
          textTransform: 'uppercase',
          fontWeight: 700,
        }}
      >
        {summary.classification} · ED {String(summary.edition).padStart(3, '0')}
      </div>

      {/* Newspaper-style title block */}
      <div style={{ marginBottom: '8px' }}>
        <h1
          style={{
            fontFamily: 'var(--font-serif)',
            fontSize: '32px',
            fontWeight: 500,
            margin: 0,
            letterSpacing: '-0.01em',
            lineHeight: 1.1,
            color: 'var(--rig-ink, #1a1410)',
          }}
        >
          Daily Signal Summary
        </h1>
        <div
          style={{
            marginTop: '8px',
            display: 'flex',
            gap: '20px',
            flexWrap: 'wrap',
            fontFamily: 'var(--font-mono)',
            fontSize: '10.5px',
            letterSpacing: '0.18em',
            textTransform: 'uppercase',
            color: 'var(--rig-ink-3, #888)',
          }}
        >
          <span>{composedAt.toLocaleDateString([], {
            day: '2-digit', month: 'short', year: 'numeric',
          })}</span>
          <span>·</span>
          <span>Window {summary.window_hours}h</span>
          <span>·</span>
          <span>Composed {composedAt.toLocaleTimeString([], {
            hour: '2-digit', minute: '2-digit',
          })}</span>
          <span>·</span>
          <span>{summary.event_count} events</span>
        </div>
      </div>

      {/* Section iterator */}
      {sections.map((s, i) => {
        if (s.kind === 'note') {
          return <NoteBanner key={i} text={s.text} />
        }
        if (s.kind === 'glance') {
          const num = nextNum()
          return (
            <section key={i}>
              <SectionHeading num={num - 1} title="At a glance" />
              <GlanceStrip
                total={s.total}
                reddit={s.reddit}
                telegram={s.telegram}
                sources={s.sources}
                nonEnglish={s.nonEnglish}
                languages={s.languages}
              />
            </section>
          )
        }
        if (s.kind === 'headline') {
          return (
            <section key={i}>
              <SectionHeading
                num={null}
                title="Headline"
                hint="highest-relevance post"
              />
              <HeadlineCard
                body={s.body}
                source={s.source}
                relevance={s.relevance}
                engagement={s.engagement}
              />
            </section>
          )
        }
        if (s.kind === 'surge') {
          const num = nextNum()
          return (
            <section key={i}>
              <SectionHeading
                num={num - 1}
                title="Entities under surge"
                hint="more chatter than usual, last 24h"
              />
              <div style={{ marginTop: '4px' }}>
                {s.items.map(it => (
                  <SurgeRow
                    key={it.subject}
                    item={it}
                    onClickSubject={subj => onTopic('entity', subj)}
                  />
                ))}
              </div>
            </section>
          )
        }
        if (s.kind === 'repetition') {
          const num = nextNum()
          return (
            <section key={i}>
              <SectionHeading
                num={num - 1}
                title="Phrasing repetition"
                hint="coordinated talking-points"
              />
              <RepetitionCard
                description={s.description}
                quote={s.quote}
                confidence={s.confidence}
              />
            </section>
          )
        }
        if (s.kind === 'silence') {
          const num = nextNum()
          return (
            <section key={i}>
              <SectionHeading
                num={num - 1}
                title="Official silence"
                hint="grassroots chatter, no government response"
              />
              <SilenceList items={s.items} />
            </section>
          )
        }
        if (s.kind === 'sentiment') {
          const num = nextNum()
          return (
            <section key={i}>
              <SectionHeading
                num={num - 1}
                title="Sentiment extremes"
                hint="strongest signal posts"
              />
              <SentimentExtremes extremes={s.extremes} />
            </section>
          )
        }
        if (s.kind === 'newSubjects') {
          const num = nextNum()
          return (
            <section key={i}>
              <SectionHeading
                num={num - 1}
                title="New on the radar"
                hint="not on watchlist — auto-promoted nightly"
              />
              <NewSubjectsList
                items={s.items}
                onClickSubject={subj => onTopic('subject', subj)}
              />
            </section>
          )
        }
        if (s.kind === 'official') {
          const num = nextNum()
          return (
            <section key={i}>
              <SectionHeading
                num={num - 1}
                title="Official channel status"
                hint="when each tracked govt source last spoke"
              />
              <OfficialStatusTable rows={s.rows} />
            </section>
          )
        }
        if (s.kind === 'stationary') {
          const num = nextNum()
          return (
            <section key={i}>
              <SectionHeading
                num={num - 1}
                title="Stationary"
                hint="watched but quiet"
              />
              <StationaryChips items={s.items} />
            </section>
          )
        }
        return null
      })}

      {/* Footer */}
      <div
        style={{
          marginTop: '40px',
          paddingTop: '14px',
          borderTop: '2px solid var(--rig-ink, #1a1410)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '14px',
          fontFamily: 'var(--font-mono)',
          fontSize: '10px',
          letterSpacing: '0.18em',
          textTransform: 'uppercase',
          color: 'var(--rig-ink-3, #888)',
        }}
      >
        <span>
          Sources:{' '}
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '11px',
              letterSpacing: '0.06em',
              color: 'var(--rig-ink-2, #2c2722)',
              textTransform: 'none',
            }}
          >
            {summary.sources_used.length} active · R/* = Reddit · TG-* = Telegram
          </span>
        </span>
        <button
          type="button"
          onClick={() => setShowRaw(!showRaw)}
          style={{
            background: 'transparent',
            border: '1px solid var(--rig-rule)',
            padding: '4px 10px',
            cursor: 'pointer',
            fontFamily: 'var(--font-mono)',
            fontSize: '10px',
            letterSpacing: '0.16em',
            color: 'var(--rig-ink-2, #2c2722)',
          }}
        >
          {showRaw ? 'Hide raw memo' : 'Show raw memo'}
        </button>
      </div>

      {showRaw && (
        <pre
          style={{
            marginTop: '14px',
            padding: '16px 20px',
            background: 'rgba(20, 14, 6, 0.04)',
            border: '1px solid var(--rig-rule)',
            fontFamily:
              'ui-monospace, "SF Mono", "Cascadia Mono", monospace',
            fontSize: '12px',
            lineHeight: 1.5,
            margin: '14px 0 0 0',
            whiteSpace: 'pre-wrap',
            color: 'var(--rig-ink, #1a1410)',
            overflow: 'auto',
          }}
        >
          {decorateBody(summary.body)}
        </pre>
      )}

      <TopicSuggestions sections={sections} onTopic={onTopic} />
    </article>
  )
}

// Group clickable subjects by category — surges (high signal),
// new-on-radar (auto-detected), stationary (watchlist quiet).
function TopicSuggestions({
  sections,
  onTopic,
}: {
  sections: Section[]
  onTopic: (kind: TopicResponse['kind'], key: string) => void
}) {
  const surgeEntities: string[] = []
  const newSubjects: string[] = []
  const stationaryEntities: string[] = []
  const silenceEntities: string[] = []

  for (const s of sections) {
    if (s.kind === 'surge') {
      for (const it of s.items) surgeEntities.push(it.subject)
    } else if (s.kind === 'newSubjects') {
      for (const it of s.items) newSubjects.push(it.term)
    } else if (s.kind === 'stationary') {
      for (const it of s.items) stationaryEntities.push(it)
    } else if (s.kind === 'silence') {
      for (const it of s.items) silenceEntities.push(it.subject)
    }
  }

  const totalCount =
    surgeEntities.length +
    newSubjects.length +
    stationaryEntities.length +
    silenceEntities.length
  if (totalCount === 0) return null

  const Pill = ({
    kind,
    label,
    accent,
  }: {
    kind: TopicResponse['kind']
    label: string
    accent?: string
  }) => (
    <button
      type="button"
      onClick={() => onTopic(kind, label)}
      style={{
        fontFamily: 'var(--font-serif)',
        fontSize: '13px',
        padding: '5px 12px',
        border: '1px solid var(--rig-rule)',
        borderLeft: accent ? `3px solid ${accent}` : '1px solid var(--rig-rule)',
        background: 'transparent',
        cursor: 'pointer',
        color: 'var(--rig-ink, #1a1410)',
        whiteSpace: 'nowrap',
      }}
      onMouseEnter={e =>
        ((e.currentTarget as HTMLButtonElement).style.background =
          'rgba(184, 134, 11, 0.08)')
      }
      onMouseLeave={e =>
        ((e.currentTarget as HTMLButtonElement).style.background =
          'transparent')
      }
    >
      {label}
    </button>
  )

  const Group = ({
    label,
    items,
    kind,
    accent,
  }: {
    label: string
    items: string[]
    kind: TopicResponse['kind']
    accent?: string
  }) => {
    if (items.length === 0) return null
    return (
      <div style={{ marginBottom: '14px' }}>
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '9.5px',
            letterSpacing: '0.24em',
            textTransform: 'uppercase',
            color: 'var(--rig-ink-3, #888)',
            marginBottom: '8px',
          }}
        >
          {label}  ·  {items.length}
        </div>
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '6px 8px',
            minWidth: 0,
            maxWidth: '100%',
          }}
        >
          {items.map(t => (
            <Pill key={t} kind={kind} label={t} accent={accent} />
          ))}
        </div>
      </div>
    )
  }
  return (
    <div
      style={{
        marginTop: '24px',
        paddingTop: '16px',
        borderTop: '1px dashed var(--rig-rule)',
      }}
    >
      <div
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: '10px',
          letterSpacing: '0.24em',
          textTransform: 'uppercase',
          color: 'var(--rig-ink-3)',
          marginBottom: '14px',
        }}
      >
        Drill into any subject  ·  {totalCount} clickable
      </div>
      <Group
        label="Under surge"
        items={Array.from(new Set(surgeEntities))}
        kind="entity"
        accent="var(--rig-gold, #b8860b)"
      />
      <Group
        label="Official silence"
        items={Array.from(new Set(silenceEntities))}
        kind="entity"
        accent="var(--rig-oxblood, #8b1a1a)"
      />
      <Group
        label="New on the radar"
        items={Array.from(new Set(newSubjects))}
        kind="subject"
      />
      <Group
        label="Watchlist — quiet"
        items={Array.from(new Set(stationaryEntities))}
        kind="entity"
      />
    </div>
  )
}

// ── Topic drilldown ────────────────────────────────────────────────

interface TopicDrilldownProps {
  topic: TopicResponse
  onClose: () => void
}

const TopicDrilldown = forwardRef<HTMLElement, TopicDrilldownProps>(
  function TopicDrilldown({ topic, onClose }, ref) {
    return (
      <section
        ref={ref}
        aria-label={`Drilldown: ${topic.key}`}
        style={{
          marginTop: '32px',
          background: 'rgba(255, 253, 247, 0.96)',
          border: '1px solid var(--rig-rule)',
          padding: '24px 28px',
          scrollMarginTop: '90px',
        }}
      >
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'baseline',
            borderBottom: '1px solid var(--rig-rule)',
            paddingBottom: '10px',
            marginBottom: '16px',
          }}
        >
          <div>
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '10px',
                letterSpacing: '0.28em',
                textTransform: 'uppercase',
                color: 'var(--rig-ink-3)',
              }}
            >
              {topic.kind === 'entity'
                ? 'Entity dossier'
                : topic.kind === 'cluster'
                  ? 'Story dossier'
                  : 'Subject dossier'}
            </span>
            <h2
              style={{
                fontFamily:
                  'ui-monospace, "SF Mono", "JetBrains Mono", monospace',
                fontWeight: 500,
                fontSize: '20px',
                margin: '4px 0 0 0',
                color: 'var(--rig-ink)',
              }}
            >
              {topic.key}
            </h2>
            <div
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '10px',
                letterSpacing: '0.18em',
                color: 'var(--rig-ink-3)',
                marginTop: '4px',
              }}
            >
              {topic.posts.length} post(s) in last 7 days
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '11px',
              letterSpacing: '0.06em',
              border: '1px solid var(--rig-rule)',
              background: 'transparent',
              padding: '4px 10px',
              cursor: 'pointer',
              color: 'var(--rig-ink, #1a1410)',
            }}
            aria-label="Close drilldown"
          >
            Close ✕
          </button>
        </div>
        {topic.posts.length === 0 ? (
          <div
            style={{
              padding: '20px',
              fontFamily: 'var(--font-mono)',
              fontSize: '11px',
              letterSpacing: '0.18em',
              color: 'var(--rig-ink-3)',
              textAlign: 'center',
            }}
          >
            No posts found for this subject in the last 7 days.
          </div>
        ) : (
          <ol
            style={{
              listStyle: 'none',
              margin: 0,
              padding: 0,
              display: 'flex',
              flexDirection: 'column',
              gap: '12px',
            }}
          >
            {topic.posts.map(p => (
              <PostRow key={p.post_id} post={p} />
            ))}
          </ol>
        )}
      </section>
    )
  },
)

function PostRow({ post }: { post: TopicPost }) {
  const showTranslated =
    post.post_text_translated &&
    post.post_language &&
    post.post_language !== 'en'
  return (
    <li
      style={{
        border: '1px solid var(--rig-rule)',
        background: 'rgba(255, 252, 245, 0.95)',
        padding: '14px 16px',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          gap: '10px',
          fontFamily: 'var(--font-mono)',
          fontSize: '10px',
          letterSpacing: '0.18em',
          textTransform: 'uppercase',
          color: 'var(--rig-ink-3)',
          marginBottom: '8px',
        }}
      >
        <span>{post.platform}</span>
        <span aria-hidden="true">·</span>
        <span>{post.monitor_name || post.author_username || '—'}</span>
        <span aria-hidden="true">·</span>
        <span>{relativeTime(post.posted_at || post.collected_at)}</span>
        {post.post_language && post.post_language !== 'en' && (
          <>
            <span aria-hidden="true">·</span>
            <span>{langName(post.post_language)} → English</span>
          </>
        )}
        <span aria-hidden="true">·</span>
        <span>rel {post.relevance_score}</span>
      </div>
      <p
        lang={showTranslated ? 'en' : (post.post_language ?? undefined)}
        style={{
          fontFamily: 'var(--font-serif)',
          fontSize: '14.5px',
          lineHeight: 1.55,
          margin: 0,
          whiteSpace: 'pre-wrap',
          color: 'var(--rig-ink)',
        }}
      >
        {showTranslated ? post.post_text_translated : post.post_text}
      </p>
      {showTranslated && (
        <details style={{ marginTop: '6px' }}>
          <summary
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '10px',
              letterSpacing: '0.18em',
              textTransform: 'uppercase',
              color: 'var(--rig-ink-3)',
              cursor: 'pointer',
            }}
          >
            Show original ({langName(post.post_language)})
          </summary>
          <p
            lang={post.post_language ?? undefined}
            style={{
              fontFamily: 'var(--font-serif)',
              fontStyle: 'italic',
              fontSize: '13px',
              color: 'var(--rig-ink-2, #2c2722)',
              marginTop: '6px',
              whiteSpace: 'pre-wrap',
            }}
          >
            {post.post_text}
          </p>
        </details>
      )}
      <div
        style={{
          marginTop: '8px',
          display: 'flex',
          gap: '12px',
          fontFamily: 'var(--font-mono)',
          fontSize: '10px',
          letterSpacing: '0.18em',
          color: 'var(--rig-ink-3)',
        }}
      >
        {post.upvotes > 0 && <span>▲ {post.upvotes}</span>}
        {post.comment_count > 0 && <span>💬 {post.comment_count}</span>}
        {post.forward_count > 0 && <span>↗ {post.forward_count}</span>}
        {post.matched_entities.length > 0 && (
          <span>
            entities: {post.matched_entities.slice(0, 3).join(', ')}
          </span>
        )}
        {post.post_url && (
          <a
            href={post.post_url}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              marginLeft: 'auto',
              color: 'var(--rig-ink-2, #2c2722)',
            }}
          >
            Open source ↗
          </a>
        )}
      </div>
    </li>
  )
}

function Loading() {
  return (
    <div
      style={{
        padding: '40px',
        textAlign: 'center',
        fontFamily: 'var(--font-mono)',
        fontSize: '11px',
        letterSpacing: '0.22em',
        textTransform: 'uppercase',
        color: 'var(--rig-ink-3)',
      }}
    >
      Composing edition…
    </div>
  )
}

interface DeskMemoProps {
  kicker: string
  headline: string
  body: string
  onRetry?: () => void
}

function DeskMemo({ kicker, headline, body, onRetry }: DeskMemoProps) {
  return (
    <div
      role="alert"
      style={{
        padding: '32px',
        border: '1px solid var(--rig-rule)',
        background: 'rgba(255, 253, 247, 0.96)',
        textAlign: 'center',
        maxWidth: '560px',
        margin: '40px auto',
      }}
    >
      <span
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: '10px',
          letterSpacing: '0.3em',
          textTransform: 'uppercase',
          color: 'var(--rig-ink-3)',
          display: 'block',
          marginBottom: '12px',
        }}
      >
        {kicker}
      </span>
      <h3
        style={{
          fontFamily: 'var(--font-serif)',
          fontWeight: 500,
          fontSize: '22px',
          margin: '0 0 12px 0',
        }}
      >
        {headline}
      </h3>
      <p
        style={{
          fontFamily: 'var(--font-sans)',
          fontSize: '14px',
          color: 'var(--rig-ink-3)',
          maxWidth: '440px',
          lineHeight: 1.55,
          margin: '0 auto',
        }}
      >
        {body}
      </p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          style={{
            marginTop: '14px',
            fontFamily: 'var(--font-mono)',
            fontSize: '11px',
            letterSpacing: '0.06em',
            border: '1px solid var(--rig-rule)',
            background: 'transparent',
            padding: '6px 14px',
            cursor: 'pointer',
            color: 'var(--rig-ink)',
          }}
        >
          Try again
        </button>
      )}
    </div>
  )
}
