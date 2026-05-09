'use client'

import { useEffect, useState } from 'react'

import { useAuthedFetch } from './useNewsroomApi'
import type { NewsroomBriefResponse } from '@/types/newsroom'

export function BriefMode() {
  const { ready, fetcher } = useAuthedFetch()
  const [brief, setBrief] = useState<NewsroomBriefResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notFound, setNotFound] = useState(false)

  useEffect(() => {
    if (!ready) return
    fetcher<NewsroomBriefResponse>('/api/newsroom/brief')
      .then((b) => { setBrief(b); setNotFound(false) })
      .catch((e: unknown) => {
        const msg = e instanceof Error ? e.message : String(e)
        if (msg.startsWith('404')) setNotFound(true)
        else setError(msg)
      })
  }, [ready, fetcher])

  if (notFound) {
    return (
      <div style={{
        padding: '60px 24px', textAlign: 'center',
        font: '400 12px/1.5 var(--onyx-mono)',
        color: 'var(--onyx-dim)',
        letterSpacing: '0.18em',
        textTransform: 'uppercase',
      }}>
        brief not yet generated · runs daily 06:00 ist
      </div>
    )
  }
  if (error) return <p style={{ color: 'var(--onyx-red)', font: '400 12px var(--onyx-mono)' }}>{error}</p>
  if (!brief) return <ModeMessage>· loading brief ·</ModeMessage>

  const briefDate = new Date(brief.for_date).toLocaleDateString('en-IN', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric',
  })
  const generatedAt = new Date(brief.generated_at).toLocaleString('en-IN')

  return (
    <article style={{ padding: '24px 0 48px', maxWidth: 880, margin: '0 auto' }}>
      <header style={{ borderBottom: '2px solid var(--onyx-red)', paddingBottom: 18, marginBottom: 32 }}>
        <p style={{
          margin: 0,
          font: '500 10px/1 var(--onyx-mono)',
          color: 'var(--onyx-red)',
          letterSpacing: '0.32em',
          textTransform: 'uppercase',
        }}>The Newsroom · Daily Brief</p>
        <h1 style={{
          margin: '12px 0 6px',
          font: '600 36px/1.1 var(--onyx-display)',
          color: 'var(--onyx-bone)',
          letterSpacing: '-0.01em',
        }}>{briefDate}</h1>
        <p style={{
          margin: 0,
          font: '400 11px/1 var(--onyx-mono)',
          color: 'var(--onyx-dim)',
          letterSpacing: '0.18em',
          textTransform: 'uppercase',
        }}>
          {brief.story_count} stories · {brief.source_segment_count} segments
          across {brief.source_channel_count} channels · generated {generatedAt}
        </p>
      </header>

      {brief.stories.length === 0 ? (
        <p style={{
          font: '400 14px/1.6 var(--onyx-italic)', fontStyle: 'italic',
          color: 'var(--onyx-bone-2)',
        }}>The day's broadcasts produced no anchored stories.</p>
      ) : (
        <ol style={{ listStyle: 'none', margin: 0, padding: 0, counterReset: 'story' }}>
          {brief.stories.map((s, i) => (
            <li key={i} style={{ marginBottom: 40 }}>
              <p style={{
                margin: 0,
                font: '500 10px/1 var(--onyx-mono)',
                color: 'var(--onyx-dim)',
                letterSpacing: '0.32em',
                textTransform: 'uppercase',
              }}>Story {String(i + 1).padStart(2, '0')}</p>
              <h2 style={{
                margin: '8px 0 14px',
                font: '600 22px/1.25 var(--onyx-display)',
                color: 'var(--onyx-bone)',
              }}>{s.headline}</h2>
              <p style={{
                margin: 0,
                font: '400 15px/1.7 var(--onyx-italic)',
                color: 'var(--onyx-bone-2)',
                whiteSpace: 'pre-wrap',
              }}>{s.summary}</p>
              {s.source_segment_ids?.length > 0 && (
                <p style={{
                  margin: '12px 0 0',
                  font: '400 9px/1.4 var(--onyx-mono)',
                  color: 'var(--onyx-dim)',
                  letterSpacing: '0.18em',
                  textTransform: 'uppercase',
                }}>
                  sources:{' '}
                  {s.source_segment_ids.slice(0, 4).map((sid, j) => (
                    <span key={sid}>{j > 0 && ' · '}<a
                      href={`/clips?segment=${sid}`}
                      style={{ color: 'var(--onyx-red)', textDecoration: 'none' }}
                    >[{j + 1}]</a></span>
                  ))}
                </p>
              )}
            </li>
          ))}
        </ol>
      )}
    </article>
  )
}

function ModeMessage({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      padding: '60px 24px', textAlign: 'center',
      font: '400 12px/1.5 var(--onyx-mono)',
      color: 'var(--onyx-dim)',
      letterSpacing: '0.18em',
      textTransform: 'uppercase',
    }}>{children}</div>
  )
}
