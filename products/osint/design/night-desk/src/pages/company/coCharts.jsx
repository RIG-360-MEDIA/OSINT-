/* ============================================================================
   Corporate-theme SVG visualization primitives for Company OSINT.
   Self-contained: colors resolve to --co-* CSS vars, so they render correctly
   under [data-product="company"] without touching the political chart set.
   ========================================================================== */
import { motion } from 'framer-motion';

const CV = {
  accent: 'var(--co-accent)', navy: 'var(--co-navy)', good: 'var(--co-good)',
  warn: 'var(--co-warn)', risk: 'var(--co-risk)', muted: 'var(--co-faint)', line: 'var(--co-line)',
};
const col = (k) => CV[k] || k || CV.accent;

/* sparkline — tiny trend line for KPI tiles */
export function Spark({ data = [], color = 'accent', w = 108, h = 34 }) {
  if (!data.length) return null;
  const mn = Math.min(...data), mx = Math.max(...data), sp = mx - mn || 1;
  const pts = data.map((v, i) => [(i / (data.length - 1)) * w, h - ((v - mn) / sp) * (h - 6) - 3]);
  const d = pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' ');
  const area = `${d} L${w} ${h} L0 ${h} Z`;
  const c = col(color), id = `sp${Math.round(data[0] * 97 + data.length)}`;
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
      <defs><linearGradient id={id} x1="0" x2="0" y1="0" y2="1">
        <stop offset="0" stopColor={c} stopOpacity=".22" /><stop offset="1" stopColor={c} stopOpacity="0" />
      </linearGradient></defs>
      <path d={area} fill={`url(#${id})`} />
      <motion.path d={d} fill="none" stroke={c} strokeWidth="2" strokeLinecap="round"
        initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: .9 }} />
    </svg>
  );
}

/* horizontal ranked bars — items: {label, value, tone?, sub?, you?} */
export function HBars({ items = [], max, unit = '', fmt }) {
  const m = max || Math.max(...items.map((i) => i.value)) || 1;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 11 }}>
      {items.map((it, i) => (
        <div key={i}>
          <div className="co-between" style={{ marginBottom: 5 }}>
            <span style={{ fontSize: 14, fontWeight: it.you ? 750 : 550, color: it.you ? 'var(--co-accent-d)' : 'var(--co-ink)' }}>
              {it.you && '★ '}{it.label}
            </span>
            <span className="co-mono co-tnum" style={{ fontSize: 13, color: 'var(--co-muted)' }}>
              {fmt ? fmt(it.value) : `${it.value.toLocaleString()}${unit}`}
            </span>
          </div>
          <div className="co-score">
            <motion.i style={{ background: it.you ? 'linear-gradient(90deg,var(--co-accent),#3fb9b3)' : undefined }}
              initial={{ width: 0 }} animate={{ width: `${Math.max(2, (it.value / m) * 100)}%` }}
              transition={{ duration: .8, delay: i * .05 }} />
          </div>
        </div>
      ))}
    </div>
  );
}

/* donut — segments: [{value, color, label}] */
export function Donut({ segments = [], size = 168, stroke = 26, center }) {
  const r = (size - stroke) / 2, c = 2 * Math.PI * r, cx = size / 2;
  let off = 0; const tot = segments.reduce((s, x) => s + x.value, 0) || 1;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <circle cx={cx} cy={cx} r={r} fill="none" stroke="var(--co-line)" strokeWidth={stroke} />
      {segments.map((s, i) => {
        const len = (s.value / tot) * c, el = <motion.circle key={i} cx={cx} cy={cx} r={r} fill="none"
          stroke={col(s.color)} strokeWidth={stroke} strokeDasharray={`${len} ${c - len}`}
          strokeDashoffset={-off} transform={`rotate(-90 ${cx} ${cx})`} strokeLinecap="butt"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * .08 }} />;
        off += len; return el;
      })}
      {center && (<text x={cx} y={cx} textAnchor="middle" dominantBaseline="central"
        style={{ fontWeight: 750, fontSize: 22, fill: 'var(--co-ink)' }}>{center}</text>)}
    </svg>
  );
}

/* opportunity scatter matrix — items: {label, x, y, r, tone, flag} 0..100 axes */
export function Scatter({ items = [], w = 520, h = 360, xLab = '', yLab = '' }) {
  const pad = 44, iw = w - pad * 2, ih = h - pad * 2;
  const px = (x) => pad + (x / 100) * iw, py = (y) => h - pad - (y / 100) * ih;
  const toneC = { good: 'var(--co-good)', warn: 'var(--co-warn)', risk: 'var(--co-risk)', you: 'var(--co-accent)' };
  return (
    <svg width="100%" viewBox={`0 0 ${w} ${h}`} style={{ maxWidth: w }}>
      {[0, 25, 50, 75, 100].map((g) => (
        <g key={g}>
          <line x1={px(g)} y1={pad} x2={px(g)} y2={h - pad} stroke="var(--co-line)" strokeWidth="1" />
          <line x1={pad} y1={py(g)} x2={w - pad} y2={py(g)} stroke="var(--co-line)" strokeWidth="1" />
        </g>
      ))}
      <rect x={px(66)} y={py(100)} width={px(100) - px(66)} height={py(66) - py(100)} fill="var(--co-accent)" opacity=".06" />
      <text x={px(83)} y={py(96)} textAnchor="middle" className="co-mono" style={{ fontSize: 10.5, fill: 'var(--co-accent-d)', letterSpacing: '.1em' }}>PRIORITY ZONE</text>
      {items.map((it, i) => (
        <motion.g key={i} initial={{ opacity: 0, scale: 0 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: i * .06, type: 'spring', stiffness: 180 }}>
          <circle cx={px(it.x)} cy={py(it.y)} r={8 + (it.r || 40) / 12} fill={toneC[it.tone] || 'var(--co-navy)'} opacity=".8" stroke="#fff" strokeWidth="1.5" />
          <text x={px(it.x)} y={py(it.y) - 12 - (it.r || 40) / 12} textAnchor="middle" style={{ fontSize: 12.5, fontWeight: 650, fill: 'var(--co-ink)' }}>{it.flag} {it.label}</text>
        </motion.g>
      ))}
      <text x={w / 2} y={h - 8} textAnchor="middle" className="co-mono" style={{ fontSize: 11, fill: 'var(--co-muted)', letterSpacing: '.1em' }}>{xLab} →</text>
      <text x={14} y={h / 2} textAnchor="middle" transform={`rotate(-90 14 ${h / 2})`} className="co-mono" style={{ fontSize: 11, fill: 'var(--co-muted)', letterSpacing: '.1em' }}>{yLab} →</text>
    </svg>
  );
}

/* trend line with labels — data: [{y, v}] */
export function TrendLine({ data = [], w = 520, h = 220, color = 'accent', unit = '' }) {
  if (!data.length) return null;
  const pad = 34, iw = w - pad * 2, ih = h - pad * 1.6;
  const vals = data.map((d) => d.v), mn = Math.min(...vals) * .9, mx = Math.max(...vals) * 1.05, sp = mx - mn || 1;
  const pts = data.map((d, i) => [pad + (i / (data.length - 1)) * iw, pad * .6 + ih - ((d.v - mn) / sp) * ih]);
  const line = pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' ');
  const c = col(color);
  return (
    <svg width="100%" viewBox={`0 0 ${w} ${h}`} style={{ maxWidth: w }}>
      <motion.path d={line} fill="none" stroke={c} strokeWidth="2.5" strokeLinecap="round"
        initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1 }} />
      {pts.map((p, i) => (
        <g key={i}>
          <circle cx={p[0]} cy={p[1]} r="4" fill="#fff" stroke={c} strokeWidth="2" />
          <text x={p[0]} y={p[1] - 12} textAnchor="middle" className="co-mono co-tnum" style={{ fontSize: 11, fontWeight: 600, fill: 'var(--co-ink)' }}>{data[i].v}{unit}</text>
          <text x={p[0]} y={h - 8} textAnchor="middle" className="co-mono" style={{ fontSize: 11, fill: 'var(--co-muted)' }}>{data[i].y}</text>
        </g>
      ))}
    </svg>
  );
}

/* flow bars — export-destination style; items: {country, flag, share, tone} */
export function FlowBars({ items = [] }) {
  const toneC = { good: 'var(--co-good)', warn: 'var(--co-warn)', risk: 'var(--co-risk)', flat: 'var(--co-navy)' };
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {items.map((it, i) => (
        <div key={i} className="co-flex" style={{ gap: 12 }}>
          <span style={{ width: 128, fontSize: 14, fontWeight: 550 }}><span className="co-flag">{it.flag}</span> {it.country}</span>
          <div className="co-score" style={{ flex: 1 }}>
            <motion.i style={{ background: toneC[it.tone] || toneC.flat }} initial={{ width: 0 }} animate={{ width: `${it.share}%` }} transition={{ duration: .8, delay: i * .05 }} />
          </div>
          <span className="co-mono co-tnum" style={{ width: 44, textAlign: 'right', fontSize: 13, color: 'var(--co-muted)' }}>{it.share}%</span>
        </div>
      ))}
    </div>
  );
}
