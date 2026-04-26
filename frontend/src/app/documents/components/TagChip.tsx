export function TagChip({ label }: { label: string }) {
  return (
    <span
      style={{
        padding: '2px 8px',
        fontFamily: 'var(--font-mono)',
        fontSize: '9px',
        letterSpacing: '0.16em',
        textTransform: 'uppercase',
        border: '1px solid var(--rig-rule)',
        color: 'var(--rig-ink-3)',
      }}
    >
      {label}
    </span>
  )
}
