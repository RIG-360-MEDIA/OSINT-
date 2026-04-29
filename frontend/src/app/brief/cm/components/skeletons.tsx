'use client'

const SHIM = {
  background: 'linear-gradient(90deg, var(--rig-paper-2) 0%, var(--rig-paper-3) 50%, var(--rig-paper-2) 100%)',
  backgroundSize: '200% 100%',
  animation: 'rig-shimmer 1.6s ease-in-out infinite',
} as const

export function BarSkeleton({ width = '100%', height = 12 }: { width?: string; height?: number }) {
  return (
    <div
      style={{
        width,
        height,
        ...SHIM,
        borderRadius: 2,
      }}
      aria-hidden
    />
  )
}

export function RowsSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
          <BarSkeleton width="42%" height={16} />
          <BarSkeleton width="14%" height={10} />
          <BarSkeleton width="20%" height={10} />
        </div>
      ))}
    </div>
  )
}

export function GridSkeleton({ tiles = 6 }: { tiles?: number }) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
        gap: 16,
      }}
    >
      {Array.from({ length: tiles }).map((_, i) => (
        <div key={i} style={{ ...SHIM, height: 120, borderRadius: 4 }} aria-hidden />
      ))}
    </div>
  )
}

export function SparklineSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <BarSkeleton width="28%" height={14} />
          <BarSkeleton width="48%" height={6} />
          <BarSkeleton width="16%" height={10} />
        </div>
      ))}
    </div>
  )
}

export function GlobalSkeletonStyles() {
  return (
    <style>{`
      @keyframes rig-shimmer {
        0%   { background-position: -100% 0; }
        100% { background-position:  100% 0; }
      }
    `}</style>
  )
}
