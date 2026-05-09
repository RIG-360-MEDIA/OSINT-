'use client'

interface Props {
  label: string
  variant?: 'default' | 'language' | 'beat' | 'live' | 'breaking'
}

const STYLE_BY_VARIANT: Record<NonNullable<Props['variant']>, React.CSSProperties> = {
  default:  { color: 'var(--onyx-bone-2)', borderColor: 'rgba(168,173,184,0.32)' },
  language: { color: 'var(--onyx-bone-2)', borderColor: 'rgba(168,173,184,0.22)' },
  beat:     { color: 'var(--onyx-bone-2)', borderColor: 'rgba(168,173,184,0.22)' },
  live:     { color: 'var(--onyx-red)',    borderColor: 'var(--onyx-red)' },
  breaking: { color: 'var(--onyx-red)',    borderColor: 'var(--onyx-red)' },
}

export function EntityChip({ label, variant = 'default' }: Props) {
  return (
    <span
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 6,
        padding: '3px 8px',
        font: '500 10px/1 var(--onyx-mono)',
        letterSpacing: '0.14em',
        textTransform: 'uppercase',
        border: '1px solid',
        borderRadius: 0,
        ...STYLE_BY_VARIANT[variant],
      }}
    >
      {label}
    </span>
  )
}
