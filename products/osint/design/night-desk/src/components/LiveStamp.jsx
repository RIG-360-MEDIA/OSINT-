import { useState, useEffect } from 'react';

// "● LIVE · updated Xm ago" — ticks every 30s so the user can SEE the page is live.
// `at` is the epoch-ms timestamp of the last successful data load.
export default function LiveStamp({ at }) {
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 30000);
    return () => clearInterval(id);
  }, []);
  if (!at) return null;
  const s = Math.max(0, Math.round((Date.now() - at) / 1000));
  const rel = s < 45 ? 'just now' : s < 3600 ? `${Math.floor(s / 60)}m ago` : `${Math.floor(s / 3600)}h ago`;
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontFamily: 'var(--mono)', fontSize: '0.6rem', letterSpacing: '0.13em', color: 'var(--faint)' }}>
      <i className="wm-livedot" style={{ width: 6, height: 6 }} />LIVE · UPDATED {rel}
    </span>
  );
}
