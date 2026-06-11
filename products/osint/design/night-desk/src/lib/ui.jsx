import { useRef, useEffect, useState } from 'react';
import { motion, useMotionValue, useSpring, useTransform, animate } from 'framer-motion';

const EASE = [0.16, 0.84, 0.28, 1];

/* ── background atmosphere ──────────────────────────────────────────────── */
export const Atmos = () => (
  <>
    <div className="atmos" />
    <div className="vign" />
    <div className="grain" />
  </>
);

/* ── hover-mask spotlight: one delegated listener paints a cursor-tracked
   amber radial on whichever .panel the pointer is over ──────────────────── */
export function Spotlight() {
  const last = useRef(null);
  useEffect(() => {
    const clear = (el) => { if (el) { el.style.removeProperty('--mx'); el.style.removeProperty('--my'); } };
    const onMove = (e) => {
      const panel = e.target.closest && e.target.closest('.panel');
      if (panel !== last.current) { clear(last.current); last.current = panel; }
      if (panel) {
        const r = panel.getBoundingClientRect();
        panel.style.setProperty('--mx', e.clientX - r.left + 'px');
        panel.style.setProperty('--my', e.clientY - r.top + 'px');
      }
    };
    window.addEventListener('pointermove', onMove, { passive: true });
    return () => { window.removeEventListener('pointermove', onMove); clear(last.current); };
  }, []);
  return null;
}

/* ── cursor-parallax 3D tilt (hero panels only) ─────────────────────────── */
export function HeroTilt({ children, className = '', max = 5 }) {
  const ref = useRef(null);
  const rx = useSpring(useMotionValue(0), { stiffness: 150, damping: 18 });
  const ry = useSpring(useMotionValue(0), { stiffness: 150, damping: 18 });
  const onMove = (e) => {
    const r = ref.current.getBoundingClientRect();
    const px = (e.clientX - r.left) / r.width - 0.5;
    const py = (e.clientY - r.top) / r.height - 0.5;
    ry.set(px * max * 2);
    rx.set(-py * max * 2);
  };
  const reset = () => { rx.set(0); ry.set(0); };
  return (
    <motion.div
      ref={ref} className={className}
      onMouseMove={onMove} onMouseLeave={reset}
      style={{ rotateX: rx, rotateY: ry, transformPerspective: 1200 }}
    >
      {children}
    </motion.div>
  );
}

/* ── mount/scroll reveal ────────────────────────────────────────────────── */
export const Reveal = ({ children, delay = 0, y = 16, className = '', style }) => (
  <motion.div
    className={className} style={style}
    initial={{ opacity: 0, y }} animate={{ opacity: 1, y: 0 }}
    transition={{ duration: 0.6, ease: EASE, delay }}
  >
    {children}
  </motion.div>
);

/* ── magnetic button ────────────────────────────────────────────────────── */
export function Magnetic({ children, className, onClick }) {
  const mx = useMotionValue(0), my = useMotionValue(0);
  const x = useSpring(mx, { stiffness: 220, damping: 15 });
  const y = useSpring(my, { stiffness: 220, damping: 15 });
  const ref = useRef(null);
  return (
    <motion.button
      ref={ref} className={className} onClick={onClick} style={{ x, y }}
      onMouseMove={(e) => { const r = ref.current.getBoundingClientRect(); mx.set((e.clientX - r.left - r.width / 2) * 0.3); my.set((e.clientY - r.top - r.height / 2) * 0.3); }}
      onMouseLeave={() => { mx.set(0); my.set(0); }}
    >
      {children}
    </motion.button>
  );
}

/* ── count-up number ────────────────────────────────────────────────────── */
export function CountUp({ to, decimals = 0, prefix = '', suffix = '', dur = 1.1 }) {
  const [v, setV] = useState(0);
  useEffect(() => {
    const controls = animate(0, to, { duration: dur, ease: EASE, onUpdate: (x) => setV(x) });
    return () => controls.stop();
  }, [to, dur]);
  return <>{prefix}{v.toFixed(decimals)}{suffix}</>;
}

/* ── liquid-glass mask over an anonymous duotone block (no real faces) ──── */
export function LiquidImage({ label = 'REDACTED', tint = 'gold', className = '', height = 200 }) {
  const ref = useRef(null);
  const [lens, setLens] = useState({ on: false, x: 0, y: 0 });
  const tintc = { gold: 'oklch(0.82 0.14 85 / .28)', cool: 'oklch(0.74 0.13 235 / .28)', hostile: 'oklch(0.645 0.215 25 / .26)' }[tint] || 'oklch(0.82 0.14 85 / .28)';
  return (
    <div
      ref={ref} className={'liquid ' + className}
      onMouseMove={(e) => { const r = ref.current.getBoundingClientRect(); setLens({ on: true, x: e.clientX - r.left, y: e.clientY - r.top }); }}
      onMouseLeave={() => setLens((l) => ({ ...l, on: false }))}
      style={{
        position: 'relative', height, borderRadius: 12, overflow: 'hidden', cursor: 'crosshair',
        border: '1px solid var(--line)',
        background: `
          repeating-linear-gradient(115deg, oklch(0.14 0.012 270) 0 9px, oklch(0.11 0.012 270) 9px 18px),
          radial-gradient(120% 90% at 70% 20%, ${tintc}, transparent 60%),
          linear-gradient(180deg, var(--surface), var(--void-2))`,
      }}
    >
      <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', pointerEvents: 'none' }}>
        <span className="mono" style={{ fontSize: '0.66rem', letterSpacing: '0.34em', color: 'var(--faint)', border: '1px solid var(--line)', padding: '6px 14px', borderRadius: 6, background: 'oklch(0 0 0 / .35)' }}>{label}</span>
      </div>
      <motion.div
        animate={{ opacity: lens.on ? 1 : 0, left: lens.x - 60, top: lens.y - 60, scale: lens.on ? 1 : 0.6 }}
        transition={{ type: 'spring', stiffness: 260, damping: 22, opacity: { duration: 0.25 } }}
        style={{
          position: 'absolute', width: 120, height: 120, borderRadius: '46% 54% 58% 42% / 52% 44% 56% 48%',
          backdropFilter: 'blur(2px) saturate(1.5) brightness(1.2)',
          WebkitBackdropFilter: 'blur(2px) saturate(1.5) brightness(1.2)',
          boxShadow: 'inset 0 0 30px oklch(1 0 0 / .12), 0 0 24px oklch(0.82 0.14 85 / .25)',
          border: '1px solid oklch(1 0 0 / .14)', pointerEvents: 'none',
        }}
      />
    </div>
  );
}

/* ── stance dot ─────────────────────────────────────────────────────────── */
export const StanceDot = ({ t }) => <span className={'dot-sq ' + (t || 'neutral')} />;

/* ── thin-line icon set ─────────────────────────────────────────────────── */
const P = (d) => (
  <svg className="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">{d}</svg>
);
export const Icons = {
  home: P(<><path d="M3 11l9-8 9 8" /><path d="M5 10v10h14V10" /></>),
  warroom: P(<><circle cx="12" cy="12" r="8" /><path d="M12 2v4M12 18v4M2 12h4M18 12h4" /><circle cx="12" cy="12" r="2" /></>),
  analytics: P(<><path d="M4 20V10M10 20V4M16 20v-7M22 20H2" /></>),
  dossier: P(<><rect x="4" y="3" width="16" height="18" rx="2" /><path d="M8 8h8M8 12h8M8 16h5" /></>),
  map: P(<><path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2Z" /><path d="M9 4v14M15 6v14" /></>),
  dispatch: P(<><path d="M22 2 11 13M22 2l-7 20-4-9-9-4 20-7Z" /></>),
  spark: P(<path d="M12 2l1.6 6.4L20 10l-6.4 1.6L12 18l-1.6-6.4L4 10l6.4-1.6L12 2Z" />),
  search: P(<><circle cx="11" cy="11" r="7" /><path d="m20 20-3-3" /></>),
  shield: P(<path d="M12 3l7 3v5c0 4.2-3 7.4-7 8.4-4-1-7-4.2-7-8.4V6l7-3Z" />),
  calendar: P(<><rect x="3" y="4" width="18" height="17" rx="2" /><path d="M3 9h18M8 3v4M16 3v4" /></>),
  target: P(<><circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="3.5" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3" /></>),
  compare: P(<><path d="M4 8h12M4 8l3-3M4 8l3 3" /><path d="M20 16H8M20 16l-3-3M20 16l-3 3" /></>),
  clock: P(<><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3.5 2" /></>),
  globe: P(<><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c3 3.2 3 14.8 0 18M12 3c-3 3.2-3 14.8 0 18" /></>),
  route: P(<><circle cx="6" cy="18" r="2.2" /><circle cx="18" cy="6" r="2.2" /><path d="M8.2 18H15a3 3 0 0 0 0-6H9a3 3 0 0 1 0-6h6.8" /></>),
  pulse: P(<path d="M2 12h5l2.5-7 4 14 2.5-7H22" />),
};
