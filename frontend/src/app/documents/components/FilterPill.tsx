interface FilterPillProps {
  label: string
  active: boolean
  onClick: () => void
}

export function FilterPill({ label, active, onClick }: FilterPillProps) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={active}
      aria-pressed={active}
      onClick={onClick}
      style={{
        padding: '5px 12px',
        cursor: 'pointer',
        fontFamily: 'var(--font-mono)',
        fontSize: '10px',
        letterSpacing: '0.2em',
        textTransform: 'uppercase',
        border: '1px solid',
        borderColor: active ? 'var(--rig-ink)' : 'var(--rig-rule)',
        background: active
          ? 'color-mix(in srgb, var(--rig-paper) 70%, transparent)'
          : 'transparent',
        color: active ? 'var(--rig-ink)' : 'var(--rig-ink-3)',
        transition: 'all 0.15s',
      }}
    >
      {label}
    </button>
  )
}
