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
  const districtFeeds = data.districtFeeds || [];
  const total = bubbles.reduce((s, b) => s + (b.articles || 0), 0);
  const sup = bubbles.reduce((s, b) => s + (b.sup || 0), 0);
  const crit = bubbles.reduce((s, b) => s + (b.crit || 0), 0);
  const neu = Math.max(0, total - sup - crit);
  const supPct = total ? Math.round((100 * sup) / (sup + crit || 1)) : 0;
  const byVol = [...bubbles].sort((a, b) => (b.articles || 0) - (a.articles || 0));
  const isDistrict = data.level === 'district';
  const noun = isDistrict ? 'district' : 'region';

  return (
    <div>
      {/* Situation & Posture — OVERALL coverage tone (not directed at the principal) */}
      <Section eyebrow="SITUATION" title="Where things stand" sub={`${data.region} · overall coverage tone · last ${data.window_days} days`}>
        {data.situation && <p style={{ margin: '0 0 14px', maxWidth: 760, lineHeight: 1.55 }}>{data.situation}</p>}
        <div style={{ display: 'flex', height: 10, borderRadius: 6, overflow: 'hidden', maxWidth: 760 }}>
          <i style={{ width: `${total ? (100 * sup) / total : 0}%`, background: SUP }} />
          <i style={{ width: `${total ? (100 * neu) / total : 0}%`, background: '#3a4256' }} />
          <i style={{ width: `${total ? (100 * crit) / total : 0}%`, background: CRIT }} />
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', maxWidth: 760, fontSize: '0.74rem', color: 'var(--faint)', marginTop: 5 }}>
          <span>{sup.toLocaleString()} positive</span><span>{neu.toLocaleString()} neutral</span><span>{crit.toLocaleString()} negative</span>
        </div>
        <div style={{ maxWidth: 760, fontSize: '0.66rem', color: 'var(--faint)', marginTop: 8, fontStyle: 'italic' }}>
          Overall tone of all coverage across {data.region} (last {data.window_days} days) — not sentiment directed at you.
        </div>
      </Section>

      {/* Focal Points — net is OVERALL coverage tone, not directed at the principal */}
      <Section eyebrow="FOCAL POINTS" title="Hottest datelines" sub={`Busiest ${noun}s by coverage volume · last ${data.window_days} days · net = overall coverage tone.`}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 12 }}>
          {byVol.slice(0, 6).map((b) => (
            <div key={b.id || b.name}
              onClick={() => isDistrict && b.id && onOpen && onOpen(b)}
              style={{ background: 'var(--surface, #14110d)', border: '1px solid var(--line)', borderRadius: 10, padding: '12px 14px', cursor: isDistrict && b.id ? 'pointer' : 'default' }}>
              <div style={{ fontSize: '0.95rem', fontWeight: 600, marginBottom: 2 }}>{b.name}</div>
              <div style={{ fontSize: '0.72rem', color: 'var(--faint)' }}>{(b.articles || 0).toLocaleString()} stories · tone {netChip(b.net || 0)}</div>
              {b.topic && <div style={{ fontSize: '0.66rem', color: 'var(--faint)', marginTop: 4, textTransform: 'capitalize' }}>{b.topic}</div>}
            </div>
          ))}
        </div>
      </Section>

      {/* District Cards — every district in the state, newest stories per district */}
      {districtFeeds.length > 0 && (
        <Section eyebrow="DISTRICT WIRE" title="Every district, latest first" sub={`Newest stories in each ${noun}${isDistrict ? ` across ${data.region}` : ''} · last 7 days.`}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 12 }}>
            {districtFeeds.map((d) => (
              <div key={d.id || d.name}
                style={{ background: 'var(--surface, #14110d)', border: '1px solid var(--line)', borderRadius: 10, padding: '13px 15px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8, marginBottom: 10 }}>
                  <span style={{ fontSize: '0.95rem', fontWeight: 600 }}>{d.name}</span>
                  <span style={{ fontFamily: 'var(--mono)', fontSize: '0.66rem', color: 'var(--faint)' }}>{(d.count || 0).toLocaleString()} {((d.count || 0) === 1) ? 'story' : 'stories'}</span>
                </div>
                {(d.items && d.items.length > 0) ? (
                  <div>
                    {d.items.map((a) => (
                      <a key={a.id} href={a.url || '#'} target="_blank" rel="noreferrer"
                        style={{ display: 'flex', gap: 9, alignItems: 'flex-start', padding: '6px 0', textDecoration: 'none', color: 'inherit', borderTop: '1px solid var(--line)' }}>
                        <i className={'df-recdot ' + a.tone} style={{ flex: '0 0 auto', marginTop: 6 }} />
                        <span style={{ minWidth: 0 }}>
                          <span style={{ fontSize: '0.82rem', display: 'block' }}>{a.headline}</span>
                          {a.headline_en && <span className="en-gloss"><b>EN</b>{a.headline_en}</span>}
                          <span style={{ display: 'block', fontFamily: 'var(--mono)', fontSize: '0.62rem', color: 'var(--faint)', marginTop: 2 }}>{a.source}{a.collected_at ? ` · ${timeAgo(a.collected_at)}` : ''}</span>
                        </span>
                      </a>
                    ))}
                  </div>
                ) : (
                  <div style={{ fontSize: '0.76rem', color: 'var(--faint)', fontStyle: 'italic', padding: '4px 0' }}>No coverage this week</div>
                )}
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* By the Numbers — POSITIVE/NEGATIVE are overall coverage tone, not directed at the principal */}
      <Section eyebrow="BY THE NUMBERS" title="At a glance" sub={`Overall coverage tone · last ${data.window_days} days.`}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 12 }}>
          {[
            ['STORIES', total.toLocaleString()],
            [isDistrict ? 'DISTRICTS' : 'REGIONS', bubbles.length],
            ['POSITIVE TONE', `${supPct}%`],
            ['NEGATIVE TONE', `${100 - supPct}%`],
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
