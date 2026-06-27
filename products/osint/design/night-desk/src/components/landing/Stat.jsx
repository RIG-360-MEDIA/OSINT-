/**
 * Stat — a single number that counts up from 0 to its target on mount
 * (easeOutCubic). Honours prefers-reduced-motion by snapping to the value.
 *
 * `variant="card"` renders the hero coverage-card styling (default);
 * the count-up math is shared regardless of presentation.
 */
import { useRef, useEffect, useState } from 'react';

const compact = (n) =>
  new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 0 }).format(Math.round(n));

/**
 * @param {{ target: number, label: string, asCompact?: boolean, duration?: number, start?: boolean }} props
 */
export default function Stat({ target, label, asCompact = false, duration = 1500, start = true }) {
  const [v, setV] = useState(0);
  const raf = useRef(0);

  useEffect(() => {
    if (!start) return undefined;
    const reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduce) { setV(target); return undefined; }
    let startT = null;
    const step = (t) => {
      if (startT === null) startT = t;
      const p = Math.min((t - startT) / duration, 1);
      setV(target * (1 - Math.pow(1 - p, 3))); // easeOutCubic
      if (p < 1) raf.current = requestAnimationFrame(step);
    };
    raf.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf.current);
  }, [target, duration, start]);

  const display = asCompact ? compact(v) : Math.round(v).toString();
  return (
    <div className="ndl-stat">
      <span className="ndl-stat-num">{display}+</span>
      <span className="ndl-stat-lbl">{label}</span>
    </div>
  );
}
