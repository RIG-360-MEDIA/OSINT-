interface DeskMemoProps {
  kicker: string
  headline: string
  body: string
}

export function DeskMemo({ kicker, headline, body }: DeskMemoProps) {
  return (
    <div
      style={{
        padding: '56px 32px',
        textAlign: 'center',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: '12px',
        border: '1px solid var(--rig-rule)',
        background: 'var(--rig-paper-2)',
      }}
    >
      <span className="rig-kicker">{kicker}</span>
      <span
        className="rig-headline"
        style={{ fontStyle: 'italic', fontSize: '22px', color: 'var(--rig-ink-2)' }}
      >
        {headline}
      </span>
      <span
        style={{
          fontFamily: 'var(--font-sans)',
          fontSize: '14px',
          color: 'var(--rig-ink-3)',
          maxWidth: '460px',
          lineHeight: 1.55,
        }}
      >
        {body}
      </span>
    </div>
  )
}
