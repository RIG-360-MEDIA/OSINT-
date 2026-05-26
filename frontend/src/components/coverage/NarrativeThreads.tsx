/**
 * NarrativeThreads — the "today's three dominant frames" panel on HOME.
 * Three framed cards side-by-side, each describing a frame's origin,
 * voice-share, and trajectory. Adversarial frame gets a red left-rule;
 * aligned gets bone; neutral gets dim.
 *
 * Sprint 1: hardcoded with realistic Telangana frames.
 * Sprint 2+: wires to a Groq-detected framing rollup keyed off active arcs.
 */
'use client'

type FrameTone = 'adversarial' | 'aligned' | 'neutral'

interface NarrativeThread {
  id: string
  number: string
  tone: FrameTone
  status: string
  headline: string
  detail: string
  voiceSharePct: number
}

const DEFAULT_THREADS: ReadonlyArray<NarrativeThread> = [
  {
    id: 'frame-1',
    number: 'Frame 01',
    tone: 'adversarial',
    status: 'Leading',
    headline:
      '"Dharani failure" — record-tampering as systemic governance collapse',
    detail:
      'Dominant in 8 of 12 outlets covering the arc this week. ' +
      'Originated 24 Apr on @TelanganaPolWatch. Mainstream pickup Day 14.',
    voiceSharePct: 38,
  },
  {
    id: 'frame-2',
    number: 'Frame 02',
    tone: 'aligned',
    status: 'Containing',
    headline:
      '"Khammam ground-visit recovery" — CM personally responsive to farmers',
    detail:
      'Lifted from −0.41 to −0.18 sentiment in 48h. 4 outlets carried ' +
      'positive framing.',
    voiceSharePct: 24,
  },
  {
    id: 'frame-3',
    number: 'Frame 03',
    tone: 'neutral',
    status: 'Routine',
    headline:
      '"Cabinet expansion" — procedural coverage of portfolio reassignment',
    detail:
      '12 outlets carry it as routine. No editorial slant detected. ' +
      'Likely fades within 96h unless KTR escalates.',
    voiceSharePct: 18,
  },
]

const toneColor: Record<FrameTone, string> = {
  adversarial: 'var(--onyx-red)',
  aligned: 'var(--onyx-bone-2)',
  neutral: 'var(--onyx-dim)',
}

interface NarrativeThreadsProps {
  threads?: ReadonlyArray<NarrativeThread>
}

export function NarrativeThreads({ threads }: NarrativeThreadsProps) {
  const data = threads ?? DEFAULT_THREADS
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(3, 1fr)',
        gap: '22px',
      }}
    >
      {data.map((t) => (
        <article
          key={t.id}
          style={{
            padding: '18px 16px',
            background: 'rgba(8, 8, 12, 0.5)',
            borderLeft: `2px solid ${toneColor[t.tone]}`,
          }}
        >
          <div
            className="onyx-mono"
            style={{
              fontSize: '9px',
              letterSpacing: '0.36em',
              color: toneColor[t.tone],
              textTransform: 'uppercase',
              marginBottom: '8px',
            }}
          >
            {`${t.number} · ${t.tone.toUpperCase()} · ${t.status.toUpperCase()}`}
          </div>
          <h5
            style={{
              margin: '0 0 8px',
              fontFamily: 'var(--onyx-display)',
              fontSize: '15px',
              fontWeight: 500,
              color: 'var(--onyx-bone)',
              lineHeight: 1.32,
            }}
          >
            {t.headline}
          </h5>
          <p
            style={{
              margin: 0,
              fontFamily: 'var(--onyx-body, "Inter", sans-serif)',
              fontSize: '12.5px',
              color: 'var(--onyx-bone-2)',
              lineHeight: 1.55,
            }}
          >
            {t.detail}{' '}
            <span style={{ color: 'var(--onyx-bone)' }}>
              {`Voice-share: ${t.voiceSharePct}%`}
            </span>
            .
          </p>
        </article>
      ))}
    </div>
  )
}

export type { NarrativeThread, FrameTone }
