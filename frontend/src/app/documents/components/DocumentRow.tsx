import { useState } from 'react'

import { GEO_KICKER, URGENCY_TONE, formatShortDate } from '../lib/constants'
import type { DocumentItem } from '../lib/types'

import { TagChip } from './TagChip'

interface DocumentRowProps {
  doc: DocumentItem
  index: number
  onOpen: () => void
}

export function DocumentRow({ doc, index, onOpen }: DocumentRowProps) {
  const [hover, setHover] = useState(false)
  const urgencyTone = doc.urgency ? URGENCY_TONE[doc.urgency] : null
  const urgencyColor =
    urgencyTone === 'alert' ? 'var(--rig-oxblood)' :
    urgencyTone === 'gold' ? 'var(--rig-gold)' :
    'transparent'

  return (
    <article
      onClick={onOpen}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: 'grid',
        gridTemplateColumns: '48px 1fr auto',
        gap: '20px',
        padding: '22px 14px 22px',
        cursor: 'pointer',
        borderBottom: '1px solid var(--rig-rule-hair)',
        borderLeft: `2px solid ${urgencyColor}`,
        marginLeft: '-14px',
        background: hover
          ? 'color-mix(in srgb, var(--rig-paper-2) 55%, transparent)'
          : 'transparent',
        transition: 'background 0.15s',
      }}
    >
      {/* Numeral */}
      <span
        style={{
          fontFamily: 'var(--font-serif)',
          fontStyle: 'italic',
          fontWeight: 400,
          fontSize: '26px',
          color: 'var(--rig-ink-3)',
          lineHeight: 1,
          paddingTop: '4px',
        }}
      >
        {String(index).padStart(2, '0')}
      </span>

      {/* Body */}
      <div style={{ minWidth: 0 }}>
        {/* Kicker line */}
        <div
          className="rig-byline"
          style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '6px', flexWrap: 'wrap' }}
        >
          <span style={{ color: 'var(--rig-copper)' }}>
            {GEO_KICKER[doc.source_geography] ?? doc.source_geography}
          </span>
          <span aria-hidden="true" style={{ opacity: 0.4 }}>·</span>
          <span>{doc.document_type.replace(/_/g, ' ')}</span>
          <span aria-hidden="true" style={{ opacity: 0.4 }}>·</span>
          <span>{doc.source_name}</span>
          {doc.urgency && (
            <>
              <span aria-hidden="true" style={{ opacity: 0.4 }}>·</span>
              <span style={{ color: urgencyColor !== 'transparent' ? urgencyColor : undefined }}>
                {doc.urgency} urgency
              </span>
            </>
          )}
        </div>

        {/* Title */}
        <h2
          className="rig-headline"
          style={{
            margin: 0,
            fontSize: '19px',
            lineHeight: 1.3,
            color: 'var(--rig-ink)',
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }}
        >
          {doc.title}
        </h2>

        {/* Why it matters or preview */}
        {doc.why_it_matters ? (
          <p
            style={{
              margin: '8px 0 0',
              fontFamily: 'var(--font-serif)',
              fontStyle: 'italic',
              fontSize: '14px',
              color: 'var(--rig-copper)',
              lineHeight: 1.45,
              display: '-webkit-box',
              WebkitLineClamp: 2,
              WebkitBoxOrient: 'vertical',
              overflow: 'hidden',
            }}
          >
            {doc.why_it_matters}
          </p>
        ) : (
          <p
            style={{
              margin: '8px 0 0',
              fontFamily: 'var(--font-serif)',
              fontSize: '14px',
              color: 'var(--rig-ink-2)',
              lineHeight: 1.5,
              display: '-webkit-box',
              WebkitLineClamp: 2,
              WebkitBoxOrient: 'vertical',
              overflow: 'hidden',
            }}
          >
            {doc.summary || doc.summary_preview || ''}
          </p>
        )}

        {/* Footer tags */}
        {(doc.topic_category || doc.geo_primary) && (
          <div
            style={{
              display: 'flex',
              gap: '6px',
              flexWrap: 'wrap',
              marginTop: '10px',
            }}
          >
            {doc.topic_category && <TagChip label={doc.topic_category} />}
            {doc.geo_primary && <TagChip label={doc.geo_primary} />}
          </div>
        )}
      </div>

      {/* Right rail */}
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'flex-end',
          justifyContent: 'space-between',
          gap: '10px',
          minWidth: '80px',
        }}
      >
        {doc.score_final != null && (
          <span
            style={{
              fontFamily: 'var(--font-serif)',
              fontStyle: 'italic',
              fontWeight: 500,
              fontSize: '22px',
              lineHeight: 1,
              color: 'var(--rig-gold)',
            }}
          >
            {doc.score_final.toFixed(2)}
          </span>
        )}
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '9px',
            letterSpacing: '0.2em',
            textTransform: 'uppercase',
            color: 'var(--rig-ink-3)',
          }}
        >
          {formatShortDate(doc.collected_at)}
        </span>
        <span
          aria-hidden="true"
          style={{
            fontFamily: 'var(--font-serif)',
            fontStyle: 'italic',
            color: hover ? 'var(--rig-gold)' : 'var(--rig-ink-3)',
            fontSize: '16px',
            transition: 'color 0.15s',
          }}
        >
          →
        </span>
      </div>
    </article>
  )
}

