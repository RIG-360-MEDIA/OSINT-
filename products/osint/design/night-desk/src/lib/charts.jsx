import { motion } from 'framer-motion';

const EASE = [0.16, 0.84, 0.28, 1];
const VAR = { gold: 'var(--gold)', hostile: 'var(--hostile)', supportive: 'var(--supportive)', rival: 'var(--rival)', cool: 'var(--cool)', muted: 'var(--muted)' };
const c = (k) => VAR[k] || k;

/* tiny sparkline */
export function Sparkline({ data, color = 'gold', w = 92, h = 26 }) {
  const max = Math.max(...data), min = Math.min(...data), rng = max - min || 1;
  const pts = data.map((v, i) => `${(i / (data.length - 1)) * w},${h - ((v - min) / rng) * (h - 4) - 2}`).join(' ');
  return (
    <svg width={w} height={h} style={{ overflow: 'visible' }}>
      <motion.polyline
        points={pts} fill="none" stroke={c(color)} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"
        initial={{ pathLength: 0, opacity: 0 }} animate={{ pathLength: 1, opacity: 1 }} transition={{ duration: 1, ease: EASE }}
        style={{ filter: `drop-shadow(0 0 5px ${c(color)})` }}
      />
    </svg>
  );
}

/* area trend with gradient fill */
export function AreaTrend({ data, labels, color = 'cool', w = 300, h = 90 }) {
  const max = Math.max(...data), min = Math.min(...data), rng = max - min || 1;
  const x = (i) => (i / (data.length - 1)) * w;
  const y = (v) => h - ((v - min) / rng) * (h - 8) - 4;
  const line = data.map((v, i) => `${x(i)},${y(v)}`).join(' ');
  const area = `0,${h} ${line} ${w},${h}`;
  const id = 'g' + color;
  // sample ~6 evenly-spaced day labels, positioned at their true x-fraction
  const n = data.length;
  const ticks = labels && labels.length === n
    ? labels.map((l, i) => ({ l, i })).filter(({ i }) => i % Math.max(1, Math.ceil(n / 6)) === 0 || i === n - 1)
    : null;
  return (
    <div style={{ width: '100%' }}>
      <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
        <defs>
          <linearGradient id={id} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0" stopColor={c(color)} stopOpacity="0.32" />
            <stop offset="1" stopColor={c(color)} stopOpacity="0" />
          </linearGradient>
        </defs>
        <motion.polygon points={area} fill={`url(#${id})`} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 1.1 }} />
        <motion.polyline points={line} fill="none" stroke={c(color)} strokeWidth="2" strokeLinecap="round"
          initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1.2, ease: EASE }}
          style={{ filter: `drop-shadow(0 0 6px ${c(color)})` }} />
      </svg>
      {ticks && (
        <div style={{ position: 'relative', height: 14, marginTop: 5 }}>
          {ticks.map(({ l, i }) => (
            <span key={i} style={{
              position: 'absolute', left: `${(i / (n - 1)) * 100}%`,
              transform: i === 0 ? 'none' : i === n - 1 ? 'translateX(-100%)' : 'translateX(-50%)',
              fontFamily: 'var(--mono)', fontSize: '0.6rem', color: 'var(--faint)', whiteSpace: 'nowrap',
            }}>{l}</span>
          ))}
        </div>
      )}
    </div>
  );
}

/* donut with segments (share of voice) */
export function Donut({ segments, size = 168, stroke = 18, center }) {
  const r = (size - stroke) / 2, circ = 2 * Math.PI * r;
  let offset = 0;
  const total = segments.reduce((s, x) => s + x.value, 0) || 1;
  return (
    <div style={{ position: 'relative', width: size, height: size }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="oklch(0.25 0.02 270 / .5)" strokeWidth={stroke} />
        {segments.map((s, i) => {
          const len = (s.value / total) * circ;
          const el = (
            <motion.circle
              key={i} cx={size / 2} cy={size / 2} r={r} fill="none" stroke={c(s.color)} strokeWidth={stroke}
              strokeDasharray={`${len} ${circ}`} strokeLinecap="butt"
              initial={{ strokeDashoffset: circ }} animate={{ strokeDashoffset: -offset }}
              transition={{ duration: 1, ease: EASE, delay: 0.1 + i * 0.08 }}
              style={{ filter: `drop-shadow(0 0 5px ${c(s.color)})` }}
            />
          );
          offset += len;
          return el;
        })}
      </svg>
      {center && (
        <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', textAlign: 'center' }}>
          <div>
            <div className="mono" style={{ fontSize: '1.6rem', fontWeight: 500 }}>{center.value}</div>
            <div className="mono" style={{ fontSize: '0.58rem', color: 'var(--muted)', letterSpacing: '0.12em', textTransform: 'uppercase' }}>{center.label}</div>
          </div>
        </div>
      )}
    </div>
  );
}

/* diverging favourability bars (−100 … +100) */
export function DivergingBars({ items }) {
  const norm = (v) => Math.min(Math.abs(v), 100) / 2; // half-width %
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontFamily: 'var(--mono)', fontSize: '0.58rem', letterSpacing: '0.18em', textTransform: 'uppercase', color: 'var(--faint)', marginBottom: 12 }}>
        <span>◄ Hostile</span><span>Ally ►</span>
      </div>
      {items.map((it, i) => (
        <div className="dvg" key={i}>
          <div className="nm">{it.name}</div>
          <div className="track">
            <motion.div className={'b ' + (it.value < 0 ? 'neg' : 'pos')}
              initial={{ width: 0 }} animate={{ width: norm(it.value) + '%' }}
              transition={{ duration: 0.9, ease: EASE, delay: 0.1 + i * 0.05 }} />
          </div>
          <div className={'sc ' + (it.value < 0 ? 'neg' : 'pos')}>{it.value > 0 ? '+' : ''}{it.value.toFixed(1)}</div>
        </div>
      ))}
    </div>
  );
}

/* horizontal heat bars (0…100), amber→coral */
export function HeatBars({ items }) {
  const max = Math.max(...items.map((i) => i.value)) || 1;
  return (
    <div style={{ display: 'grid', gap: 11 }}>
      {items.map((it, i) => (
        <div key={i}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.86rem', marginBottom: 5 }}>
            <span>{it.name}</span><span className="num">{it.value}</span>
          </div>
          <div style={{ height: 7, background: 'oklch(0.25 0.02 270 / .6)', borderRadius: 4, overflow: 'hidden' }}>
            <motion.div initial={{ width: 0 }} animate={{ width: (it.value / max) * 100 + '%' }}
              transition={{ duration: 0.9, ease: EASE, delay: 0.15 + i * 0.07 }}
              style={{ height: '100%', borderRadius: 4, background: 'linear-gradient(90deg, var(--gold), var(--hostile))', boxShadow: '0 0 12px oklch(0.645 0.215 25 / .45)' }} />
          </div>
        </div>
      ))}
    </div>
  );
}

/* mood waveform — line crossing a zero baseline, area above jade / below coral */
export function Wave({ data, w = 300, h = 96 }) {
  const mid = h / 2;
  const x = (i) => (i / (data.length - 1)) * w;
  const y = (v) => mid - v * (mid - 6);
  const line = data.map((v, i) => `${x(i)},${y(v)}`).join(' ');
  return (
    <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
      <defs>
        <linearGradient id="wv" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="var(--supportive)" stopOpacity="0.3" />
          <stop offset="0.5" stopColor="var(--supportive)" stopOpacity="0" />
          <stop offset="0.5" stopColor="var(--hostile)" stopOpacity="0" />
          <stop offset="1" stopColor="var(--hostile)" stopOpacity="0.3" />
        </linearGradient>
      </defs>
      <line x1="0" y1={mid} x2={w} y2={mid} stroke="var(--line)" strokeWidth="1" strokeDasharray="3 4" />
      <motion.polygon points={`0,${mid} ${line} ${w},${mid}`} fill="url(#wv)" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 1 }} />
      <motion.polyline points={line} fill="none" stroke="var(--ink-2)" strokeWidth="1.8" strokeLinecap="round"
        initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1.3, ease: EASE }} />
    </svg>
  );
}

/* ranked horizontal bars (label · bar · value) */
export function RankBars({ items, color = 'cool' }) {
  const max = Math.max(...items.map((i) => i.value)) || 1;
  return (
    <div className="rankbars">
      {items.map((it, i) => (
        <div className={'drb' + (it.you ? ' you' : '')} key={i}>
          <span className="drb-l">{it.label}</span>
          <span className="drb-t">
            <motion.i initial={{ width: 0 }} animate={{ width: (it.value / max) * 100 + '%' }}
              transition={{ duration: 0.8, ease: EASE, delay: 0.05 + i * 0.04 }}
              style={{ background: it.you ? 'var(--gold)' : c(color) }} />
          </span>
          <span className="drb-v">{it.value.toLocaleString()}</span>
        </div>
      ))}
    </div>
  );
}

/* diverging "net lean" bars from {label,pos,neg} → net% supportive(+)/critical(−) */
export function LeanBars({ items }) {
  const leans = items.map((it) => ({ ...it, net: Math.round((100 * (it.pos - it.neg)) / ((it.pos + it.neg) || 1)) }));
  const max = Math.max(...leans.map((l) => Math.abs(l.net)), 1);
  return (
    <div className="leanbars">
      <div className="dlb-axis"><span>◄ critical</span><span>supportive ►</span></div>
      {leans.map((l, i) => (
        <div className="dlb" key={i}>
          <span className="dlb-l">{l.label}</span>
          <span className="dlb-track">
            <motion.i className={l.net < 0 ? 'neg' : 'pos'} initial={{ width: 0 }}
              animate={{ width: (Math.abs(l.net) / max) * 50 + '%' }}
              transition={{ duration: 0.8, ease: EASE, delay: 0.05 + i * 0.05 }}
              style={l.net < 0 ? { right: '50%' } : { left: '50%' }} />
          </span>
          <span className={'dlb-v ' + (l.net < 0 ? 'neg' : 'pos')}>{l.net > 0 ? '+' : ''}{l.net}%</span>
        </div>
      ))}
    </div>
  );
}

/* single horizontal stacked bar (share) */
export function StackBar({ segments }) {
  const total = segments.reduce((s, x) => s + x.value, 0) || 1;
  return (
    <div>
      <div className="stackbar">
        {segments.map((s, i) => (
          <motion.div key={i} initial={{ width: 0 }} animate={{ width: (s.value / total) * 100 + '%' }}
            transition={{ duration: 0.9, ease: EASE, delay: 0.1 + i * 0.1 }}
            style={{ background: c(s.color) }} title={s.label} />
        ))}
      </div>
      <div className="stack-legend">
        {segments.map((s) => (<span key={s.label}><i style={{ background: c(s.color) }} />{s.label} <b>{s.value}%</b></span>))}
      </div>
    </div>
  );
}

/* grouped english/telugu bars per issue */
export function GroupBars({ items }) {
  const max = Math.max(...items.flatMap((i) => [i.en, i.te])) || 1;
  return (
    <div className="groupbars">
      {items.map((it, i) => (
        <div className="dgb" key={i}>
          <span className="dgb-l">{it.label}</span>
          <span className="dgb-bars">
            <motion.i className="dgb-en" initial={{ width: 0 }} animate={{ width: (it.en / max) * 100 + '%' }} transition={{ duration: 0.7, ease: EASE, delay: 0.05 + i * 0.04 }} />
            <motion.i className="dgb-te" initial={{ width: 0 }} animate={{ width: (it.te / max) * 100 + '%' }} transition={{ duration: 0.7, ease: EASE, delay: 0.08 + i * 0.04 }} />
          </span>
        </div>
      ))}
      <div className="dgb-legend"><span><i className="dgb-en" />English</span><span><i className="dgb-te" />Telugu</span></div>
    </div>
  );
}
