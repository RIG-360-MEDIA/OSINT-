/**
 * useViewportProgress — a reliable scroll-progress MotionValue for an element.
 *
 * Returns { ref, progress } where progress is a framer-motion MotionValue that
 * runs 0 → 1 as the element passes through the viewport (0 when its top sits at
 * the viewport bottom, 1 when its bottom sits at the viewport top). Driven by a
 * passive scroll listener + rAF on getBoundingClientRect — not framer's
 * target-based useScroll, which doesn't track reliably in this setup.
 */
import { useEffect, useRef } from 'react';
import { useMotionValue } from 'framer-motion';

export default function useViewportProgress() {
  const ref = useRef(/** @type {HTMLElement|null} */ (null));
  const progress = useMotionValue(0);

  useEffect(() => {
    let raf = 0;
    const measure = () => {
      raf = 0;
      const el = ref.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      const vh = window.innerHeight || 1;
      const p = (vh - r.top) / (vh + r.height);
      progress.set(Math.max(0, Math.min(1, p)));
    };
    const onScroll = () => { if (!raf) raf = requestAnimationFrame(measure); };
    measure();
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);
    return () => {
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onScroll);
      if (raf) cancelAnimationFrame(raf);
    };
  }, [progress]);

  return { ref, progress };
}
