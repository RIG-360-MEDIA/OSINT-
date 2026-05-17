/**
 * EditorsNote — the textual interpretation block that sits beneath
 * Today's Reading on HOME. Single italic-serif paragraph + a one-line
 * "since you last visited" delta in mono.
 *
 * Sprint 1: copy is hardcoded sensibly. Sprint 2+ wires it to a daily
 * Groq-written summary keyed off the user's profile + active arcs.
 */
'use client'

interface EditorsNoteProps {
  note?: string
  sinceLastVisit?: string
}

const DEFAULT_NOTE =
  'Editor’s note — the Dharani arc has crossed Day 17. KTR’s ' +
  '"47-item failure list" framing is now carried by 12 outlets, up from 4 a ' +
  'week ago. National pickup confirmed today. Khammam recovery sentiment is ' +
  'offsetting it slightly. Watch the cabinet-reshuffle thread in the brewing ' +
  'horizon — Stage 2 of 4 and accelerating.'

const DEFAULT_DELTA =
  'Since you last visited 8H AGO · 47 new articles · 3 new quotes · ' +
  '1 brewing story moved to Stage 3 · 2 watched entities crossed sentiment threshold'

export function EditorsNote({ note, sinceLastVisit }: EditorsNoteProps) {
  return (
    <div>
      <p
        style={{
          margin: '18px 0 0',
          fontFamily: 'var(--onyx-italic)',
          fontStyle: 'italic',
          fontSize: '16px',
          lineHeight: 1.55,
          color: 'var(--onyx-bone-2)',
          maxWidth: '68ch',
        }}
      >
        {note ?? DEFAULT_NOTE}
      </p>
      <p
        className="onyx-mono"
        style={{
          margin: '14px 0 0',
          fontSize: '10.5px',
          letterSpacing: '0.28em',
          color: 'var(--onyx-dim)',
          textTransform: 'uppercase',
        }}
      >
        {sinceLastVisit ?? DEFAULT_DELTA}
      </p>
    </div>
  )
}
