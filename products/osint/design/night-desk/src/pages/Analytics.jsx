import { useState, useEffect } from 'react';
import { Reveal } from '../lib/ui';
import { AreaTrend, Donut, Sparkline, RankBars, LeanBars, StackBar, GroupBars } from '../lib/charts';
import Verify from '../components/Verify';
import { authFetch } from '../lib/supabase';

const TONE = { gold: 'var(--gold)', cool: 'var(--cool)', supportive: 'var(--supportive)', hostile: 'var(--hostile)', muted: 'var(--muted)' };
const BANDS = ['THE BIG PICTURE', 'WHO & WHERE', 'THE DETAIL'];

/* ── per-viz blocks ──────────────────────────────────────────────────────── */
const SmallMult = ({ rows }) => (
  <div className="smallmult">
    {rows.map((r) => (
      <div className="dsm" key={r.label}>
        <span className="dsm-l">{r.label}</span>
        <Sparkline data={r.series} color="cool" w={92} h={22} />
        <span className={'dsm-t ' + r.dir}>{r.dir === 'up' ? '▲' : '▼'} {r.trend}</span>
      </div>
    ))}
  </div>
);
const RankList = ({ items, unit }) => (
  <div className="ranklist">
    {items.map((it, i) => (
      <div className="drl" key={it.label}>
        <span className="drl-n">{i + 1}</span><span className="drl-name">{it.label}</span>
        <span className="drl-v">{it.value}<small> {unit}</small></span>
      </div>
    ))}
  </div>
);
const DonutBlock = ({ d }) => (
  <div className="donutblock">
    <Donut segments={d.segments} center={{ value: d.centerValue, label: d.centerLabel }} size={138} stroke={16} />
    <div className="donut-legend">
      {d.segments.map((s) => (<div key={s.label}><i style={{ background: TONE[s.color] || 'var(--muted)' }} /><span>{s.label}</span><b>{s.value}%</b></div>))}
    </div>
  </div>
);
const EventCal = ({ items }) => (
  <div className="eventcal">{items.map((e, i) => (
    <div className="dec" key={i}><span className="dec-d">{e.date}</span><span className="dec-l">{e.label}</span><span className="dec-t">{e.type}</span></div>
  ))}</div>
);
const QuotesBlock = ({ items }) => (
  <div className="qblock">{items.map((q, i) => (
    <div className="dqb" key={i}><p className="dqb-q">“{q.q}”</p><div className="dqb-m"><b>{q.who}</b> · {q.role}<span>{q.src}</span></div></div>
  ))}</div>
);
const ClaimsBlock = ({ items }) => (
  <div className="cblock">{items.map((c, i) => (
    <div className="dcb" key={i}><span className="dcb-p">{c.pred}</span><p className="dcb-t">{c.text}</p><span className="dcb-s">{c.src}</span></div>
  ))}</div>
);
const FiguresBlock = ({ items }) => (
  <div className="figblock">{items.map((f, i) => (<div className="dfig" key={i}><div className="dfig-v">{f.value}</div><div className="dfig-c">{f.ctx}</div></div>))}</div>
);
const IMG_TINT = { hostile: 'oklch(0.5 0.2 25 / .5)', supportive: 'oklch(0.55 0.15 165 / .45)', neutral: 'oklch(0.42 0.02 270 / .4)', gold: 'oklch(0.72 0.14 85 / .45)' };
const ImagesBlock = ({ items }) => (
  <div className="imgwall">{items.map((im, i) => (
    <div className="diw" key={i} style={{ background: `radial-gradient(120% 90% at 30% 18%, ${IMG_TINT[im.tone] || IMG_TINT.neutral}, transparent 64%), repeating-linear-gradient(125deg, oklch(0.17 0.014 270) 0 8px, oklch(0.12 0.012 270) 8px 16px)` }}>
      <span className={'diw-dot ' + im.tone} />
    </div>
  ))}</div>
);

function Viz({ m }) {
  const d = m.data;
  switch (m.viz) {
    case 'area': return <><AreaTrend data={d.series} color="cool" h={118} /><div className="dash-note">{d.note}</div></>;
    case 'rank': return <RankBars items={d.items} color={m.id === 'tone' ? 'gold' : 'cool'} />;
    case 'smallmult': return <SmallMult rows={d.rows} />;
    case 'stack': return <StackBar segments={d.segments} />;
    case 'lean': return <LeanBars items={d.items} />;
    case 'donut': return <DonutBlock d={d} />;
    case 'groupbars': return <GroupBars items={d.items} />;
    case 'list': return <RankList items={d.items} unit={d.unit} />;
    case 'eventcal': return <EventCal items={d.items} />;
    case 'quotes': return <QuotesBlock items={d.items} />;
    case 'claims': return <ClaimsBlock items={d.items} />;
    case 'figures': return <FiguresBlock items={d.items} />;
    case 'images': return <ImagesBlock items={d.items} />;
    default: return null;
  }
}

function DashCard({ m, onExplain }) {
  return (
    <div className="panel dash-card">
      <div className="dash-head">
        <div className="dash-id">
          <div className="dash-name">{m.name}</div>
          <div className="dash-sub">{m.sub}</div>
        </div>
        <button className="dash-explain" onClick={() => onExplain(m.metric)} title="Definition, formula, source rows">ⓘ explain</button>
      </div>
      <div className="dash-viz"><Viz m={m} /></div>
      <div className="dash-src">{m.source} · n={m.metric.n.toLocaleString()}</div>
      {m.data.foot && <div className="dash-foot">{m.data.foot}</div>}
    </div>
  );
}

export default function Analytics() {
  const [vm, setVm] = useState(null);
  const [data, setData] = useState(null);
  const [status, setStatus] = useState({ loading: true, error: null });

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const d = await authFetch('/api/brief/analytics');
        if (!cancelled) { setData(d); setStatus({ loading: false, error: null }); }
      } catch (e) {
        if (!cancelled) setStatus({ loading: false, error: String(e?.message || e) });
      }
    }
    load();
    const id = setInterval(load, 30 * 60 * 1000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  if (status.loading) return <div className="dashboard"><div className="panel" style={{ padding: 28, color: 'var(--faint)' }}>Loading your instrument panel…</div></div>;
  if (status.error || !data || !data.personalized) return <div className="dashboard"><div className="panel" style={{ padding: 28, color: 'var(--faint)' }}>{status.error ? `Couldn’t load analytics — ${status.error}` : 'Finish onboarding to see your analytics.'}</div></div>;

  const MODULES = data.modules || [];
  const DASH = { base: data.base, window: data.window, asOf: data.asOf };
  return (
    <div className="dashboard">
      <Reveal>
        <div className="eyebrow">THE INSTRUMENT PANEL</div>
        <h1 className="h-sec" style={{ marginTop: 6 }}>Analytics</h1>
        <div className="sub" style={{ maxWidth: 620 }}>Twenty reads on your coverage — pure data, no AI. Every card carries its source, and an <b style={{ color: 'var(--cool)' }}>ⓘ explain</b> that opens the definition, formula, source tables and the rows behind the number.</div>
        <div className="dash-kpis">
          <span><b>{DASH.base}</b> articles</span><span className="sep" />
          <span>{DASH.window}</span><span className="sep" />
          <span className="mono">{DASH.asOf}</span>
        </div>
      </Reveal>

      {BANDS.map((band) => (
        <section className="dash-band-wrap" key={band}>
          <div className="dash-band">{band}<span>{MODULES.filter((m) => m.band === band).length} cards</span></div>
          <div className="dash-grid">
            {MODULES.filter((m) => m.band === band).map((m, i) => (
              <Reveal key={m.id} className={m.span === 2 ? 'span2' : ''} y={12} delay={0.02 + i * 0.03}>
                <DashCard m={m} onExplain={setVm} />
              </Reveal>
            ))}
          </div>
        </section>
      ))}

      <Verify metric={vm} onClose={() => setVm(null)} />
    </div>
  );
}
