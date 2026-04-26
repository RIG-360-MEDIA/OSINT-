interface FilterRowProps {
  label: string
  children: React.ReactNode
}

export function FilterRow({ label, children }: FilterRowProps) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
      <span
        className="rig-kicker"
        style={{ opacity: 0.7, minWidth: '78px' }}
      >
        {label}
      </span>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
        {children}
      </div>
    </div>
  )
}
