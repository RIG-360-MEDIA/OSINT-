/**
 * SignalFunnel — the unique element for section 03.
 *
 * A wide scatter of faint signals at the top falls and converges toward a
 * single point near the bottom. Most dim out partway down (the billion,
 * filtered); a rare few brighten to ember and reach the node, flaring it —
 * "the few, for you". Canvas + rAF, DPR-aware, pauses when hidden, and renders
 * one static converged frame under prefers-reduced-motion.
 */
import { useRef, useEffect } from 'react';

const N = 200;
const MAX_DPR = 2;
const FX = 0.5;   // focal point (normalised)
const FY = 0.82;

const spawn = (p) => {
  p.x = 0.08 + Math.random() * 0.84;
  p.y = Math.random() * 0.10;
  p.px = p.x; p.py = p.y;
  p.chosen = Math.random() < 0.07;          // ~7% reach the node
  p.sp = 0.010 + Math.random() * 0.010;     // closing fraction per frame
  p.jit = (Math.random() - 0.5) * 0.0016;
  return p;
};

export default function SignalFunnel() {
  const ref = useRef(/** @type {HTMLCanvasElement|null} */ (null));

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return undefined;
    const ctx = canvas.getContext('2d');
    if (!ctx) return undefined;
    const reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    let W = 0, H = 0, dpr = 1, raf = 0, running = true, nodeGlow = 0;
    let parts = new Array(N).fill(0).map(() => spawn({}));

    const build = () => {
      W = canvas.clientWidth; H = canvas.clientHeight;
      dpr = Math.min(window.devicePixelRatio || 1, MAX_DPR);
      canvas.width = Math.round(W * dpr);
      canvas.height = Math.round(H * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const drawNode = () => {
      const nx = FX * W, ny = FY * H;
      const r = 34 + nodeGlow * 64;
      const g = ctx.createRadialGradient(nx, ny, 0, nx, ny, r);
      g.addColorStop(0, `rgba(224,135,90,${(0.45 + nodeGlow * 0.4).toFixed(3)})`);
      g.addColorStop(1, 'rgba(224,135,90,0)');
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.arc(nx, ny, r, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = 'rgba(255,226,201,0.95)';
      ctx.beginPath(); ctx.arc(nx, ny, 3.2, 0, Math.PI * 2); ctx.fill();
    };

    const step = (p, moving) => {
      p.px = p.x; p.py = p.y;
      if (moving) {
        const dx = FX - p.x, dy = FY - p.y;
        p.x += dx * p.sp + p.jit;
        p.y += dy * p.sp;
        if (Math.hypot(FX - p.x, FY - p.y) < 0.012) {
          if (p.chosen) nodeGlow = 1;
          spawn(p);
        }
      }
      const prog = Math.min(1, p.y / FY);
      const a = p.chosen ? 0.85 : Math.max(0, 0.42 * (1 - prog * 1.18));
      if (!p.chosen && a <= 0.02 && moving) { spawn(p); return; }
      const col = p.chosen ? '224,135,90' : '198,204,220';
      const x = p.x * W, y = p.y * H, px = p.px * W, py = p.py * H;
      ctx.strokeStyle = `rgba(${col},${(a * 0.45).toFixed(3)})`;
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(px, py); ctx.lineTo(x, y); ctx.stroke();
      ctx.fillStyle = `rgba(${col},${a.toFixed(3)})`;
      ctx.beginPath(); ctx.arc(x, y, p.chosen ? 1.9 : 1.1, 0, Math.PI * 2); ctx.fill();
    };

    const frame = () => {
      ctx.clearRect(0, 0, W, H);
      drawNode();
      parts.forEach((p) => step(p, true));
      nodeGlow *= 0.92;
    };

    const loop = () => { if (!running) return; frame(); raf = requestAnimationFrame(loop); };

    const onVis = () => {
      if (document.hidden) { running = false; cancelAnimationFrame(raf); }
      else if (!running) { running = true; raf = requestAnimationFrame(loop); }
    };
    let rt = 0;
    const onResize = () => { window.clearTimeout(rt); rt = window.setTimeout(() => { build(); staticFrame(); }, 150); };

    const staticFrame = () => {
      ctx.clearRect(0, 0, W, H);
      drawNode();
      parts.forEach((p) => { p.y = Math.random() * FY; p.x = FX + (p.x - 0.5) * (1 - p.y / FY); step(p, false); });
    };

    build();
    staticFrame(); // paint a full first frame immediately (no dependence on rAF timing)
    if (!reduce) raf = requestAnimationFrame(loop);
    window.addEventListener('resize', onResize);
    document.addEventListener('visibilitychange', onVis);
    return () => {
      running = false; cancelAnimationFrame(raf); window.clearTimeout(rt);
      window.removeEventListener('resize', onResize);
      document.removeEventListener('visibilitychange', onVis);
    };
  }, []);

  return <canvas ref={ref} aria-hidden="true" />;
}
