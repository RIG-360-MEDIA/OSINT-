// Situation-Room scroll sections, built entirely from the live map payload
// (bubbles + feed + situation). No fabricated values — every number traces to data.

const SUP = 'var(--supportive, #3cd6a0)';
const CRIT = 'var(--hostile, #f05c5c)';
const NEU = 'var(--faint, #8a8577)';

function timeAgo(ts) {
  if (!ts) return '';
  const then = new Date(ts.replace(' ', 'T'));
  const mins = Math.max(0, Math.round((Date.now() - then.getTime()) / 60000));
  if (mins < 60) return `${mins}m ago`;
  const h = Math.round(mins / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.round(h / 24)}d ago`;
}

function Section({ eyebrow, title, sub, children }) {
  return (
    <section className="wm-sec" style={{ marginTop: 30 }}>
      <div className="eyebrow" style={{ color: 'var(--gold)' }}>{eyebrow}</div>
      <h2 className="h-sec" style={{ margin: '4px 0' }}>{title}</h2>
      {sub && <div className="sub" style={{ marginBottom: 16 }}>{sub}</div>}
      {children}
    </section>
  );
}

function netChip(net) {
  const c = net > 0 ? SUP : net < 0 ? CRIT : NEU;
  return <span style={{ color: c, fontWeight: 600 }}>{net > 0 ? '+' : ''}{net}</span>;
}

export default function MapSections({ data, scope, onOpen }) {
  const bubbles = data.bubbles || [];
  const feed = data.feed || [];
  const total = bubbles.reduce((s, b) => s + (b.articles || 0), 0);
  const sup = bubbles.reduce((s, b) => s + (b.sup || 0), 0);
  const crit = bubbles.reduce((s, b) => s + (b.crit || 0), 0);
  const neu = Math.max(0, total - sup - crit);
  const supPct = total ? Math.round((100 * sup) / (sup + crit || 1)) : 0;
  const byVol = [...bubbles].sort((a, b) => (b.articles || 0) - (a.articles || 0));
  const pressure = [...bubbles].filter((b) => (b.articles || 0) >= 3).sort((a, b) => (a.net || 0) - (b.net || 0)).slice(0, 8);
  const maxAbsNet = Math.max(1, ...pressure.map((b) => Math.abs(b.net || 0)));
  const isDistrict = data.level === 'district';
  const noun = isDistrict ? 'district' : 'region';

  return (
    <div>
      {/* Situation & Posture */}
      <Section eyebrow="SITUATION" title="Where things stand" sub={`${data.region} · last ${data.window_days} days`}>
        {data.situation && <p style={{ margin: '0 0 14px', maxWidth: 760, lineHeight: 1.55 }}>{data.situation}</p>}
        <div style={{ display: 'flex', height: 10, borderRadius: 6, overflow: 'hidden', maxWidth: 760 }}>
          <i style={{ width: `${total ? (100 * sup) / total : 0}%`, background: SUP }} />
          <i style={{ width: `${total ? (100 * neu) / total : 0}%`, background: '#3a4256' }} />
          <i style={{ width: `${total ? (100 * crit) / total : 0}%`, background: CRIT }} />
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', maxWidth: 760, fontSize: '0.74rem', color: 'var(--faint)', marginTop: 5 }}>
          <span>{sup.toLocaleString()} supportive</span><span>{neu.toLocaleString()} neutral</span><span>{crit.toLocaleString()} critical</span>
        </div>
      </Section>

      {/* Focal Points */}
      <Section eyebrow="FOCAL POINTS" title="Hottest datelines" sub={`Busiest ${noun}s by coverage volume.`}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 12 }}>
          {byVol.slice(0, 6).map((b) => (
            <div key={b.id || b.name}
              onClick={() => isDistrict && b.id && onOpen && onOpen(b)}
              style={{ background: 'var(--surface, #14110d)', border: '1px solid var(--line)', borderRadius: 10, padding: '12px 14px', cursor: isDistrict && b.id ? 'pointer' : 'default' }}>
              <div style={{ fontSize: '0.95rem', fontWeight: 600, marginBottom: 2 }}>{b.name}</div>
              <div style={{ fontSize: '0.72rem', color: 'var(--faint)' }}>{(b.articles || 0).toLocaleString()} stories · net {netChip(b.net || 0)}</div>
              {b.topic && <div style={{ fontSize: '0.66rem', color: 'var(--faint)', marginTop: 4, textTransform: 'capitalize' }}>{b.topic}</div>}
            </div>
          ))}
        </div>
      </Section>

      {/* Regional Pressure */}
      {pressure.length > 0 && (
        <Section eyebrow="REGIONAL PRESSURE" title="Stance gradient" sub={`Where coverage leans hostile vs supportive (${noun}s with ≥3 stories).`}>
          <div style={{ maxWidth: 760 }}>
            {pressure.map((b) => {
              const w = (Math.abs(b.net || 0) / maxAbsNet) * 50;
              const pos = (b.net || 0) >= 0;
              return (
                <div key={b.id || b.name} style={{ display: 'grid', gridTemplateColumns: '150px 1fr 52px', alignItems: 'center', gap: 10, padding: '4px 0' }}>
                  <span style={{ fontSize: '0.8rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{b.name}</span>
                  <div style={{ position: 'relative', height: 8, background: 'var(--surface-2, #1a1712)', borderRadius: 4 }}>
                    <div style={{ position: 'absolute', left: '50%', top: 0, bottom: 0, width: 1, background: 'var(--line)' }} />
                    <div style={{ position: 'absolute', top: 0, bottom: 0, borderRadius: 4,
                      left: pos ? '50%' : `${50 - w}%`, width: `${w}%`, background: pos ? SUP : CRIT }} />
                  </div>
                  <span style={{ fontSize: '0.78rem', textAlign: 'right' }}>{netChip(b.net || 0)}</span>
                </div>
              );
            })}
          </div>
        </Section>
      )}

      {/* Live Intel Feed */}
      {feed.length > 0 && (
        <Section eyebrow="LIVE INTEL" title="Newest on the wire" sub={`Freshest geo-tagged stories${isDistrict ? ` across ${data.region}` : ''}, latest first.`}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: 12 }}>
            {feed.map((a) => (
              <a key={a.id} href={a.url || '#'} target="_blank" rel="noreferrer"
                style={{ display: 'flex', gap: 11, textDecoration: 'none', color: 'inherit', background: 'var(--surface, #14110d)', border: '1px solid var(--line)', borderRadius: 10, padding: 11 }}>
                <span style={{ flex: '0 0 64px', height: 44, borderRadius: 6, overflow: 'hidden', background: 'var(--surface-2, #1a1712)', display: 'grid', placeItems: 'center' }}>
                  {a.thumbnail ? <img src={a.thumbnail} alt="" loading="lazy" style={{ width: '100%', height: '100%', objectFit: 'cover' }} /> : <i className={'df-recdot ' + a.tone} />}
                </span>
                <span style={{ minWidth: 0 }}>
                  <span style={{ fontSize: '0.84rem', display: 'block' }}>{a.headline}</span>
                  {a.headline_en && <span className="en-gloss"><b>EN</b>{a.headline_en}</span>}
                  <span style={{ display: 'block', fontFamily: 'var(--mono)', fontSize: '0.62rem', color: 'var(--faint)', marginTop: 2 }}>{a.source} · {timeAgo(a.collected_at)}</span>
                </span>
              </a>
            ))}
          </div>
        </Section>
      )}

      {/* By the Numbers */}
      <Section eyebrow="BY THE NUMBERS" title="At a glance">
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 12 }}>
          {[
            ['STORIES', total.toLocaleString()],
            [isDistrict ? 'DISTRICTS' : 'REGIONS', bubbles.length],
            ['SUPPORTIVE', `${supPct}%`],
            ['CRITICAL', `${100 - supPct}%`],
            ['BUSIEST', byVol[0] ? byVol[0].name : '—'],
            ['WINDOW', `${data.window_days}d`],
          ].map(([k, v]) => (
            <div key={k} style={{ background: 'var(--surface, #14110d)', border: '1px solid var(--line)', borderRadius: 10, padding: '13px 14px' }}>
              <div style={{ fontSize: '0.58rem', color: 'var(--faint)', letterSpacing: '0.1em' }}>{k}</div>
              <div style={{ fontSize: '1.15rem', fontWeight: 600, marginTop: 3 }}>{v}</div>
            </div>
          ))}
        </div>
      </Section>
    </div>
  );
}
