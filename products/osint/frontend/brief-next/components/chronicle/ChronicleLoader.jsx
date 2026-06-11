'use client';

function SkeletonCard({ wide }) {
  return (
    <div className="chr-skeleton-node">
      <div className="chr-skeleton-card">
        <div className="chr-skeleton-line w-40" style={{ marginBottom: 16 }} />
        <div className="chr-skeleton-line h-20 w-90" />
        <div className="chr-skeleton-line w-70" />
        <div className="chr-skeleton-line w-60" style={{ marginTop: 16 }} />
        <div className="chr-skeleton-line w-90" />
        {wide && <div className="chr-skeleton-line w-70" />}
      </div>
      <div className="chr-skeleton-gap">
        <div className="chr-skeleton-gap-line" />
      </div>
    </div>
  );
}

export default function ChronicleLoader() {
  return (
    <div className="chr-skeleton">
      <div className="chr-skeleton-spine" />
      <div style={{ position: 'relative' }}>
        <div className="chr-skeleton-dot" style={{ top: 24 }} />
      </div>
      <SkeletonCard wide />
      <div style={{ position: 'relative' }}>
        <div className="chr-skeleton-dot" style={{ top: 24 }} />
      </div>
      <SkeletonCard />
      <div style={{ position: 'relative' }}>
        <div className="chr-skeleton-dot" style={{ top: 24 }} />
      </div>
      <SkeletonCard wide />

      <div className="chr-generating">
        <div className="chr-generating-spinner" />
        <span className="chr-generating-label">Analysing story — this takes 15–30 seconds</span>
      </div>
    </div>
  );
}
