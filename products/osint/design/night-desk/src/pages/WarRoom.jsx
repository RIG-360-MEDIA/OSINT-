import { useState, useEffect, Fragment } from 'react';
import { Reveal, Magnetic } from '../lib/ui';
import Verify from '../components/Verify';
import { authFetch } from '../lib/supabase';

function Spark({ label, v, tone }) {
  return (
    <span className="cd-spark">
      <span className="cd-spark-l">{label}</span>
      <span className="cd-spark-t"><i className={'cd-spark-f' + (tone ? ' ' + tone : '')} style={{ width: Math.round((v || 0) * 100) + '%' }} /></span>
    </span>
  );
}
function Cite({ metric, onClick }) {
  if (!metric) return null;
  return <button className="cd-cite" onClick={onClick} title="Trace this figure">⌖ verify · {metric.n}</button>;
}
function Stat({ k, v, tone, note }) {
  return (
    <div className="cd-stat">
      <div className="cd-stk">{k}</div>
      <div className={'cd-stv' + (tone ? ' ' + tone : '')}>{v}</div>
      {note && <div className="cd-stn">{note}</div>}
    </div>
  );
}
function Notice({ children }) {
  return <div className="cabledesk"><div className="panel" style={{ padding: 28, color: 'var(--faint)' }}>{children}</div></div>;
}

export default function WarRoom() {
  const [metric, setMetric] = useState(null);
  const [w, setW] = useState(null);
  const [status, setStatus] = useState({ loading: true, error: null });
  const open = (m) => setMetric(m);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const d = await authFetch('/api/brief/warroom');
        if (!cancelled) { setW(d); setStatus({ loading: false, error: null }); }
      } catch (e) { if (!cancelled) setStatus({ loading: false, error: String(e?.message || e) }); }
    }
    load();
    const id = setInterval(load, 30 * 60 * 1000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  if (status.loading) return <Notice>Opening the war room…</Notice>;
  if (status.error || !w || !w.personalized) return <Notice>{status.error ? `Couldn’t load the war room — ${status.error}` : 'Finish onboarding to open the war room.'}</Notice>;

  const STATION = w.station, LEAD = w.lead, CABLES = w.cables || [], ARSENAL = w.arsenal || {};
  const MOMENTUM = w.momentum || { items: [] }, ATTACKMAP = w.attackmap || { issues: [], rivals: [], grid: {} };
  const BLOC = w.bloc || { edges: [], solo: [] }, ROSTER = w.roster || { against: [], neutral: [], forNote: '' };
  const COUNTERATTACK = w.counterattack || { items: [] };
  const maxVol = Math.max(1, ...MOMENTUM.items.map((m) => m.vol || 0));

  return (
    <div className="cabledesk">
      <div className="cd-station">
        <div className="cd-deskname"><span className="cd-live" />WAR ROOM <i>∕∕</i> {STATION.desk}</div>
        <div className="cd-stats">
          <Stat k="OPEN" v={STATION.open} />
          <Stat k="CRITICAL" v={STATION.critical} tone="neg" />
          <Stat k="PRESSURE" v={STATION.pressure} tone="neg" note={STATION.pressureNote} />
          <Stat k="COUNTER-SPEED" v={STATION.counterSpeed} />
        </div>
        <div className="cd-asof">{STATION.asOf}<span>{STATION.window}</span></div>
      </div>

      <Reveal y={10}>
        <div className="cd-lead">
          <div className="cd-leadhead">
            <span className="cd-leadtag">{LEAD.tag}</span>
            <span className="cd-leadslug">{LEAD.slug}</span>
            <span className="cd-leadwin">{LEAD.windowEst}<em>*</em></span>
            <Cite metric={LEAD.metric} onClick={() => open(LEAD.metric)} />
          </div>
          <p className="cd-leadread">{LEAD.read}</p>
          <div className="cd-leadmeta"><span>{LEAD.trigger}</span><span>{LEAD.basis}</span></div>
          <div className="cd-leadcav">* {LEAD.caveat}</div>
        </div>
      </Reveal>

      <div className="cd-grid">
        <div className="cd-stack">
          <div className="cd-stackhead">THREAT STACK <em>· ranked by volume · negativity · reach · tier</em></div>
          {CABLES.map((c, i) => (
            <Reveal key={c.id || i} y={10} delay={0.04 + i * 0.05}>
              <div className="cd-cable" data-sev={c.sev}>
                <div className="cd-slug">
                  <span className="cd-sev">{c.sev}</span>
                  <span className="cd-verdict">{c.verdict}</span>
                  <span className="cd-score">{c.score}<sup>{c.src}</sup></span>
                </div>
                <div className="cd-receipt">
                  <Spark label="reach" v={c.receipt.reach} />
                  <Spark label="neg" v={c.receipt.neg} tone="neg" />
                  <Spark label="vel" v={c.receipt.vel} />
                  <Spark label="tier" v={c.receipt.tier} />
                </div>
                <p className="cd-claim">{c.claim}</p>
                <div className="cd-meta"><span>● {c.who}</span><span>{c.date} · {c.origin}</span></div>
                <dl className="cd-facets">
                  <div><dt>WHAT</dt><dd>{c.facets.what}</dd></div>
                  <div><dt>HURTS</dt><dd>{c.facets.hurts}</dd></div>
                  <div><dt>ACTS</dt><dd>{c.facets.acts}</dd></div>
                  <div className="cd-hits"><dt>HITS</dt><dd>{(c.facets.hits || []).map((h) => <span className="cd-chip" key={h}>{h}</span>)}</dd></div>
                </dl>
              </div>
            </Reveal>
          ))}
          {CABLES.length === 0 && <div className="cd-cable"><p className="cd-claim">No concentrated adverse storyline in the window — the board is quiet.</p></div>}
        </div>

        <aside className="cd-arsenal">
          <div className="cd-block">
            <div className="cd-bh">AMMUNITION <em>· for {ARSENAL.forCable}</em></div>
            {(ARSENAL.ammunition || []).map((a, i) => <div className="cd-ammo" key={i}>▸ {a}</div>)}
          </div>
          {ARSENAL.predraft && (
            <div className="cd-block">
              <div className="cd-bh">PRE-DRAFT <span className="cd-langs"><b>{ARSENAL.predraft.lang}</b> · {ARSENAL.predraft.words}w</span></div>
              <p className="cd-draft">{ARSENAL.predraft.en}</p>
              <div className="cd-flag">⚑ {ARSENAL.predraft.flag}</div>
              <div className="cd-actrow"><Magnetic className="btn primary">approve</Magnetic><button className="btn">edit</button><button className="btn cd-ghost">kill</button></div>
            </div>)}
          <div className="cd-block">
            <div className="cd-bh">INTERCEPTS <em>· watched voices in adverse coverage</em></div>
            {(ARSENAL.intercepts || []).map((qq, i) => (
              <div className="cd-intercept" key={i}>
                <div className="cd-iq">“{qq.quote}”</div>
                <div className="cd-im"><b>{qq.who}</b> · {qq.role}<span className="cd-tier">{qq.tier}</span><span className="cd-isrc">{qq.src}</span></div>
              </div>
            ))}
            {(ARSENAL.intercepts || []).length === 0 && <div className="cd-ammo">No opposition quotes intercepted in adverse coverage.</div>}
          </div>
        </aside>
      </div>

      <div className="cd-fhead">THE FIELD <em>· entity intelligence</em></div>
      <div className="cd-mods">
        <div className="cd-mod">
          <div className="cd-mh">MOMENTUM</div>
          <div className="cd-rows">
            {MOMENTUM.items.map((m) => (
              <div className="cd-mrow" key={m.name}>
                <span className="cd-mn">{m.name}</span>
                <span className="cd-mbar"><i style={{ width: Math.round(m.vol / maxVol * 100) + '%' }} /><i className="neg" style={{ width: Math.round(m.neg / maxVol * 100) + '%' }} /></span>
                <span className={'cd-mt ' + m.dir}>{m.trend}</span>
              </div>
            ))}
          </div>
          <div className="cd-mnote">{MOMENTUM.note}</div>
        </div>

        <div className="cd-mod">
          <div className="cd-mh">ATTACK MAP</div>
          {ATTACKMAP.rivals.length > 0 ? (
            <div className="cd-matrix" style={{ gridTemplateColumns: `auto repeat(${ATTACKMAP.issues.length}, 1fr)` }}>
              <span />
              {ATTACKMAP.issues.map((is) => <span className="cd-mxh" key={is}>{is}</span>)}
              {ATTACKMAP.rivals.map((rv) => (
                <Fragment key={rv}>
                  <span className="cd-mxr">{rv}</span>
                  {ATTACKMAP.issues.map((is) => {
                    const n = (ATTACKMAP.grid[rv] || {})[is] || 0;
                    return <span className="cd-mxc" key={is}><i style={{ opacity: n ? 0.2 + n * 0.6 : 0.05 }} /></span>;
                  })}
                </Fragment>
              ))}
            </div>
          ) : <div className="cd-mnote">No co-occurring adverse coverage to map.</div>}
          <div className="cd-mnote">{ATTACKMAP.foot}</div>
        </div>

        <div className="cd-mod">
          <div className="cd-mh">BLOC</div>
          <div className="cd-bloc">
            {BLOC.edges.map((e, i) => (
              <div className="cd-edge" key={i}><span className="cd-node">{e.a}</span><span className="cd-link"><i />{e.n}<i /></span><span className="cd-node">{e.b}</span></div>
            ))}
            {BLOC.edges.length === 0 && <div className="cd-mnote">No repeated co-coverage clusters.</div>}
          </div>
          <div className="cd-mnote">{BLOC.foot}</div>
        </div>

        <div className="cd-mod cd-mod-wide">
          <div className="cd-mh">ALLEGIANCE ROSTER <em>· outlets</em></div>
          <div className="cd-roster">
            <div>
              <div className="cd-rcolh neg">HOSTILE · {ROSTER.against.length}</div>
              <div className="cd-rwrap">{ROSTER.against.map((a) => <span className="cd-rchip neg" key={a}>{a}</span>)}{ROSTER.against.length === 0 && <span className="cd-fornote">none</span>}</div>
            </div>
            <div>
              <div className="cd-rcolh">FENCE · {ROSTER.neutral.length}</div>
              <div className="cd-rwrap">{ROSTER.neutral.map((a) => <span className="cd-rchip" key={a}>{a}</span>)}{ROSTER.neutral.length === 0 && <span className="cd-fornote">none</span>}</div>
            </div>
            <div>
              <div className="cd-rcolh hollow">FRIENDLY</div>
              <div className="cd-fornote">{ROSTER.forNote}</div>
            </div>
          </div>
        </div>
      </div>

      <div className="cd-mods2">
        <div className="cd-mod">
          <div className="cd-mh">COUNTER-ATTACK <em>· entities under heat</em><Cite metric={COUNTERATTACK.metric} onClick={() => open(COUNTERATTACK.metric)} /></div>
          {COUNTERATTACK.items.map((t, i) => (
            <div className="cd-ca" key={i}>
              <div className="cd-cahead"><span className="cd-caname">{t.name} <em>· {t.issue}</em></span><span className="cd-caheat">{t.heat}</span></div>
              <p className="cd-caline">{t.line}</p>
            </div>
          ))}
          {COUNTERATTACK.items.length === 0 && <div className="cd-caline">No watched entity is under notable heat.</div>}
        </div>
      </div>

      <Verify metric={metric} onClose={() => setMetric(null)} />
    </div>
  );
}
