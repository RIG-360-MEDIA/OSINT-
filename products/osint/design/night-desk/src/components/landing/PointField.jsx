/**
 * PointField — the spine of the page: "clarity from chaos" made literal.
 *
 * A fixed full-viewport canvas behind every section. Each point drifts in
 * scattered noise at the top of the page and resolves into an ordered
 * phyllotaxis constellation (golden-angle spiral — the same packing logic
 * a sunflower uses) as the user scrolls down. Near-neighbour edges fade in
 * with the resolve, so the field reads as: many independent signals → one
 * coherent shape. That is the product thesis, drawn.
 *
 * Self-contained: one rAF loop, DPR-aware, pauses when the tab is hidden,
 * recomputes geometry on resize, and renders a calm static constellation
 * under prefers-reduced-motion (no animation, no scroll coupling).
 */
import { useRef, useEffect } from 'react';

const COUNT = 120;
const GOLDEN = Math.PI * (3 - Math.sqrt(5)); // ~2.39996 rad
const MAX_DPR = 2;
const EDGE_DIST = 132;     // px between resolved neighbours that earn an edge
const EDGE_MAX = 2;        // edges kept per point (keeps it sparse + elegant)

// hue mix: mostly cool white, a sprinkle of gold + mint beacons
const COLORS = [
  'rgba(232,236,245,', 'rgba(232,236,245,', 'rgba(232,236,245,',
  'rgba(228,190,120,', // gold
  'rgba(111,224,168,', // mint
];

const lerp = (a, b, t) => a + (b - a) * t;
const easeInOut = (t) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2);

export default function PointField() {
  const canvasRef = useRef(/** @type {HTMLCanvasElement|null} */ (null));

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const ctx = canvas.getContext('2d');
    if (!ctx) return undefined;

    const reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    let W = 0, H = 0, dpr = 1;
    let pts = [];
    let edges = [];
    let raf = 0;
    let running = true;

    // progress 0 (chaos, top) → 1 (resolved, ~2 screens down)
    const progress = () => {
      const vh = window.innerHeight || 1;
      const y = window.scrollY || window.pageYOffset || 0;
      return Math.max(0, Math.min(1, (y - vh * 0.28) / (vh * 1.7)));
    };

    const build = () => {
      W = window.innerWidth;
      H = window.innerHeight;
      dpr = Math.min(window.devicePixelRatio || 1, MAX_DPR);
      canvas.width = Math.round(W * dpr);
      canvas.height = Math.round(H * dpr);
      canvas.style.width = `${W}px`;
      canvas.style.height = `${H}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      // resolved constellation: golden-angle spiral, fit to an off-centre ellipse
      const cx = W * 0.62;
      const cy = H * 0.46;
      const rx = Math.min(W * 0.46, 720);
      const ry = Math.min(H * 0.46, 560);
      const scale = 1 / Math.sqrt(COUNT);

      pts = new Array(COUNT).fill(0).map((_, i) => {
        const r = Math.sqrt(i) * scale;             // 0..~1
        const a = i * GOLDEN;
        const tx = cx + Math.cos(a) * r * rx;
        const ty = cy + Math.sin(a) * r * ry;
        const ci = i % COLORS.length;
        const beacon = i % 17 === 0;                 // a few brighter anchors
        return {
          tx, ty,
          // scatter origin + slow independent drift
          bx: Math.random() * W,
          by: Math.random() * H,
          ax: 18 + Math.random() * 46, ay: 18 + Math.random() * 46,
          fx: 0.08 + Math.random() * 0.22, fy: 0.08 + Math.random() * 0.22,
          px: Math.random() * Math.PI * 2, py: Math.random() * Math.PI * 2,
          size: beacon ? 2.1 + Math.random() * 1.1 : 0.8 + Math.random() * 1.1,
          base: COLORS[ci],
          beacon,
        };
      });

      // precompute sparse near-neighbour edges from resolved positions
      edges = [];
      for (let i = 0; i < COUNT; i += 1) {
        const cand = [];
        for (let j = 0; j < COUNT; j += 1) {
          if (i === j) continue;
          const d = Math.hypot(pts[i].tx - pts[j].tx, pts[i].ty - pts[j].ty);
          if (d < EDGE_DIST) cand.push({ j, d });
        }
        cand.sort((m, n) => m.d - n.d);
        cand.slice(0, EDGE_MAX).forEach(({ j, d }) => {
          if (j > i) edges.push({ i, j, d });          // dedupe i<j
        });
      }
    };

    const draw = (timeSec) => {
      const p = reduce ? 1 : progress();
      const e = easeInOut(p);
      ctx.clearRect(0, 0, W, H);

      // positions for this frame
      const fx = new Float32Array(COUNT);
      const fy = new Float32Array(COUNT);
      for (let i = 0; i < COUNT; i += 1) {
        const pt = pts[i];
        const drift = reduce ? 0 : 1;
        const sx = pt.bx + Math.sin(timeSec * pt.fx + pt.px) * pt.ax * drift;
        const sy = pt.by + Math.cos(timeSec * pt.fy + pt.py) * pt.ay * drift;
        // resolved points keep a whisper of life so it never looks frozen
        const settle = pt.tx + Math.sin(timeSec * 0.15 + pt.px) * 3 * drift;
        const settleY = pt.ty + Math.cos(timeSec * 0.15 + pt.py) * 3 * drift;
        fx[i] = lerp(sx, settle, e);
        fy[i] = lerp(sy, settleY, e);
      }

      // edges (constellation) — only meaningful once mostly resolved
      if (e > 0.04) {
        for (let k = 0; k < edges.length; k += 1) {
          const { i, j, d } = edges[k];
          const a = (1 - d / EDGE_DIST) * 0.5 * e;
          if (a <= 0.01) continue;
          ctx.strokeStyle = `rgba(180,196,228,${a.toFixed(3)})`;
          ctx.lineWidth = 0.6;
          ctx.beginPath();
          ctx.moveTo(fx[i], fy[i]);
          ctx.lineTo(fx[j], fy[j]);
          ctx.stroke();
        }
      }

      // points
      for (let i = 0; i < COUNT; i += 1) {
        const pt = pts[i];
        // chaos = dim & even; resolved = brighter, beacons brightest
        const baseA = lerp(0.18, pt.beacon ? 0.95 : 0.5, e);
        ctx.fillStyle = `${pt.base}${baseA.toFixed(3)})`;
        ctx.beginPath();
        ctx.arc(fx[i], fy[i], pt.size, 0, Math.PI * 2);
        ctx.fill();
      }
    };

    const loop = (tMs) => {
      if (!running) return;
      draw(tMs / 1000);
      raf = requestAnimationFrame(loop);
    };

    const onVisibility = () => {
      if (document.hidden) {
        running = false;
        cancelAnimationFrame(raf);
      } else if (!running) {
        running = true;
        raf = requestAnimationFrame(loop);
      }
    };

    let resizeT = 0;
    const onResize = () => {
      window.clearTimeout(resizeT);
      resizeT = window.setTimeout(() => {
        build();
        if (reduce) draw(0); // static mode redraws once after layout settles
      }, 150);
    };

    build();
    if (reduce) {
      draw(0); // single static frame, no loop, no scroll coupling
    } else {
      raf = requestAnimationFrame(loop);
    }
    window.addEventListener('resize', onResize);
    document.addEventListener('visibilitychange', onVisibility);

    return () => {
      running = false;
      cancelAnimationFrame(raf);
      window.clearTimeout(resizeT);
      window.removeEventListener('resize', onResize);
      document.removeEventListener('visibilitychange', onVisibility);
    };
  }, []);

  return <canvas ref={canvasRef} className="ndl-field" aria-hidden="true" />;
}
