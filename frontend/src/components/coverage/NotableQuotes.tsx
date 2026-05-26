/**
 * NotableQuotes — four curated pull-quotes on HOME. Each quote card has
 * a coloured left-rule (red for adversarial, bone for neutral-or-aligned),
 * the quote in italic serif, attribution in mono, and a why-this-quote
 * line beneath.
 *
 * Sprint 1: ships with sensibly-curated placeholders.
 * Sprint 2+: reads from /api/coverage/quotes filtered by user-watched
 * entities + a Groq picker that adds why-this-quote rationale.
 */
'use client'

type QuoteTone = 'adversarial' | 'aligned' | 'neutral'

interface NotableQuote {
  id: string
  body: string
  speaker: string
  source: string
  when: string
  why: string
  tone: QuoteTone
}

const DEFAULT_QUOTES: ReadonlyArray<NotableQuote> = [
  {
    id: 'q1',
    body: '"We have a list, and we will publish every broken promise tomorrow."',
    speaker: 'Harish Rao',
    source: 'NTV TELUGU',
    when: '9 MAY · 22:14',
    why:
      'Why this quote: load-bearing for the anti-Dharani drumbeat. Carried ' +
      'by 3 other outlets within 4 hours.',
    tone: 'adversarial',
  },
  {
    id: 'q2',
    body: '"Phase 2 disbursement completed for 14,200 farmers in Khammam."',
    speaker: 'Khammam CMO',
    source: 'TELEGRAM',
    when: '10 MAY · 06:00',
    why:
      'Why this quote: counter-narrative anchor. The hard number is your ' +
      'strongest defence in any media response.',
    tone: 'aligned',
  },
  {
    id: 'q3',
    body:
      '"This government has failed in every single promise — Dharani, fee ' +
      'reimbursement, Rythu Bandhu."',
    speaker: 'KTR',
    source: 'SAKSHI TV',
    when: '9 MAY · 14:24',
    why:
      'Why this quote: triangle attack — bundles three issues. Pre-empt by ' +
      'separating them in your response.',
    tone: 'adversarial',
  },
  {
    id: 'q4',
    body:
      '"Telangana is not just a state for us — it is the cornerstone of ' +
      'South India’s economic future."',
    speaker: 'Revanth Reddy',
    source: 'SIASAT',
    when: '11 MAY · 11:00',
    why:
      'Why this quote: today’s CM positioning. Reusable as the framing ' +
      'anchor for any economic-development response.',
    tone: 'neutral',
  },
]

const ruleColor: Record<QuoteTone, string> = {
  adversarial: 'var(--onyx-red)',
  aligned: 'var(--onyx-bone-2)',
  neutral: 'var(--onyx-dim)',
}

interface NotableQuotesProps {
  quotes?: ReadonlyArray<NotableQuote>
}

export function NotableQuotes({ quotes }: NotableQuotesProps) {
  const data = quotes ?? DEFAULT_QUOTES
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        gap: '16px',
      }}
    >
      {data.map((q) => (
        <article
          key={q.id}
          style={{
            padding: '18px 18px 16px',
            background: 'linear-gradient(180deg, rgba(8,8,12,0.6), rgba(0,0,0,0.5))',
            border: '1px solid rgba(255,255,255,0.06)',
            borderLeft: `2px solid ${ruleColor[q.tone]}`,
          }}
        >
          <p
            style={{
              margin: '0 0 12px',
              fontFamily: '"Instrument Serif", Georgia, serif',
              fontStyle: 'italic',
              fontSize: '18px',
              color: 'var(--onyx-bone)',
              lineHeight: 1.42,
            }}
          >
            {q.body}
          </p>
          <div
            className="onyx-mono"
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'baseline',
              fontSize: '9px',
              letterSpacing: '0.32em',
              color: 'var(--onyx-bone-2)',
              textTransform: 'uppercase',
            }}
          >
            <span>
              <span style={{ color: 'var(--onyx-bone)' }}>{q.speaker}</span> · {q.source}
            </span>
            <span>{q.when}</span>
          </div>
          <p
            style={{
              margin: '8px 0 0',
              fontFamily: 'var(--onyx-body, "Inter", sans-serif)',
              fontStyle: 'italic',
              fontSize: '11px',
              color: 'var(--onyx-dim)',
              lineHeight: 1.45,
            }}
          >
            {q.why}
          </p>
        </article>
      ))}
    </div>
  )
}

export type { NotableQuote, QuoteTone }
