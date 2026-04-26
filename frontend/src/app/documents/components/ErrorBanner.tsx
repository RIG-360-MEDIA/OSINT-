interface ErrorBannerProps {
  message: string
  onRetry: () => void
}

export function ErrorBanner({ message, onRetry }: ErrorBannerProps) {
  return (
    <div
      role="alert"
      style={{
        padding: '20px 24px',
        margin: '0 0 24px',
        border: '1px solid var(--rig-alert, #b1442d)',
        background: 'rgba(177, 68, 45, 0.06)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: '16px',
      }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
        <span className="rig-kicker" style={{ color: 'var(--rig-alert, #b1442d)' }}>
          Stop press
        </span>
        <span
          style={{
            fontFamily: 'var(--font-serif)',
            fontSize: '17px',
            color: 'var(--rig-ink-1)',
            lineHeight: 1.45,
          }}
        >
          {message}
        </span>
      </div>
      <button
        type="button"
        onClick={onRetry}
        className="rig-button"
        style={{
          fontSize: '12px',
          letterSpacing: '0.18em',
          textTransform: 'uppercase',
          padding: '8px 16px',
          border: '1px solid var(--rig-rule)',
          background: 'var(--rig-paper)',
          color: 'var(--rig-ink-1)',
          cursor: 'pointer',
          whiteSpace: 'nowrap',
        }}
      >
        Try again
      </button>
    </div>
  )
}
