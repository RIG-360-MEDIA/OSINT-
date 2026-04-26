export function LoadingState() {
  return (
    <div
      style={{
        padding: '64px 0',
        textAlign: 'center',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: '12px',
      }}
    >
      <span
        className="rig-headline"
        style={{ fontStyle: 'italic', fontSize: '20px', color: 'var(--rig-ink-2)' }}
      >
        Opening the filing cabinet…
      </span>
      <span
        style={{
          width: '160px',
          height: '1px',
          background: 'linear-gradient(90deg, transparent, var(--rig-gold), transparent)',
        }}
      />
    </div>
  )
}
