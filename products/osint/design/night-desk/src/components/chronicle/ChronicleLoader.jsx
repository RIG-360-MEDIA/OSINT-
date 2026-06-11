function SkeletonCard({ wide }) {
  return (
    <div className="chron-skel-node">
      <div className="chron-skel-dot" />
      <div className="chron-skel-card">
        <div className="chron-skel-line w40" />
        <div className="chron-skel-line tall w90" />
        <div className="chron-skel-line w70" />
        <div className="chron-skel-line w60" />
        {wide && <div className="chron-skel-line w90" />}
      </div>
    </div>
  );
}

export default function ChronicleLoader() {
  return (
    <div className="chron-loader">
      <div className="chron-skel-spine" />
      <SkeletonCard wide />
      <SkeletonCard />
      <SkeletonCard wide />
      <div className="chron-generating">
        <div className="chron-spinner" />
        <span>Reading article content across time windows — 2–3 min on first analysis</span>
      </div>
    </div>
  );
}
