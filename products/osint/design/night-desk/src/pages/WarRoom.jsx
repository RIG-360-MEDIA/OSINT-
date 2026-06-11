import { useState, useEffect } from 'react';
import { Reveal, Magnetic } from '../lib/ui';
import { authFetch } from '../lib/supabase';
import LiveStamp from '../components/LiveStamp';
import Sources from '../components/Sources';

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
  const [w, setW] = useState(null);
  const [status, setStatus] = useState({ loading: true, error: null });
  const [loadedAt, setLoadedAt] = useState(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const d = await authFetch('/api/brief/warroom');
        if (!cancelled) { setW(d); setStatus({ loading: false, error: null }); setLoadedAt(Date.now()); }
      } catch (e) { if (!cancelled) setStatus({ loading: false, error: String(e?.message || e) }); }
    }
    load();
    const id = setInterval(load, 30 * 60 * 1000);
    const onFocus = () => load();
    window.addEventListener('focus', onFocus);
    return () => { cancelled = true; clearInterval(id); window.removeEventListener('focus', onFocus); };
  }, []);

  if (status.loading) return <Notice>Opening the war room…</Notice>;
  if (status.error || !w || !w.personalized) return <Notice>{status.error ? `Couldn’t load the war room — ${status.error}` : 'Finish onboarding to open the war room.'}</Notice>;

  const STATION = w.station, LEAD = w.lead, CABLES = w.cables || [], ARSENAL = w.arsenal || {};

  return (
    <div className="cabledesk">
      <div className="cd-station">
        <div className="cd-deskname"><span className="cd-live" />WAR ROOM <i>∕∕</i> {STATION.desk}<span style={{ marginLeft: 12 }}><LiveStamp at={loadedAt} /></span></div>
        <div className="cd-stats">
          {STATION.mood && (
            <Stat k="MOOD" v={STATION.mood.label} tone={STATION.mood.tone} note={STATION.mood.window_label} />
          )}
          <Stat k="ACTIVE ATTACKS" v={STATION.activeAttacks} note="separate stories against you · last 21 days" />
          <Stat k="SERIOUS" v={STATION.serious} tone="neg" note="rated critical · last 21 days" />
          <Stat k="NEGATIVE STORIES" v={STATION.negStories} tone="neg" note="last 21 days" />
          <Stat k="TREND" v={STATION.trendLabel} tone={STATION.trendTone} note="vs earlier in 21-day window" />
        </div>
        <div className="cd-asof">{STATION.asOf}<span>{STATION.window}</span></div>
      </div>

      <Reveal y={10}>
        <div className="cd-lead">
          <div className="cd-leadhead">
            <span className="cd-leadtag">{LEAD.tag}</span>
            <span className="cd-leadslug">{LEAD.slug}</span>
            <span className="cd-leadwin">{LEAD.windowEst}<em>*</em></span>
          </div>
          <p className="cd-leadread">{LEAD.read}</p>
          {LEAD.summary && (
            <div className="cd-leadsummary">
              <div className="cd-leadsummary-h">SITUATION SUMMARY</div>
              <p>{LEAD.summary}</p>
            </div>
          )}
          <div className="cd-leadmeta"><span>{LEAD.trigger}</span><span>{LEAD.basis}</span></div>
          <div className="cd-leadcav">* {LEAD.caveat}</div>
        </div>
      </Reveal>

      <div className="cd-grid">
        <div className="cd-stack">
          <div className="cd-stackhead">ATTACKS ON YOU <em>· worst first</em></div>
          {CABLES.map((c, i) => (
            <Reveal key={c.id || i} y={10} delay={0.04 + i * 0.05}>
              <div className="cd-cable" data-sev={c.sev}>
                <div className="cd-slug">
                  <span className="cd-sevchip">{c.sev}</span>
                  <span className="cd-verdict">{c.verdict}</span>
                </div>
                <div className="cd-hostline">{c.src} adverse piece{c.src === 1 ? '' : 's'} · {c.facets.outlets} outlet{c.facets.outlets === 1 ? '' : 's'}</div>
                <p className="cd-claim">{c.claim}</p>
                {c.claim_en && <div className="en-gloss"><b>EN</b>{c.claim_en}</div>}
                <div className="cd-meta"><span>● Originated with {c.origin}</span><span>Latest {c.date}</span></div>
                <dl className="cd-facets">
                  <div><dt>ISSUE</dt><dd>{c.facets.what}</dd></div>
                  <div><dt>SCALE</dt><dd>{c.facets.hurts}</dd></div>
                  <div><dt>ORIGIN</dt><dd>{c.origin} · first seen {c.date}</dd></div>
                  <div><dt>ACTION</dt><dd>{c.facets.acts}</dd></div>
                  <div className="cd-hits"><dt>OUTLETS</dt><dd>{(c.facets.hits || []).map((h) => <span className="cd-chip" key={h}>{h}</span>)}</dd></div>
                </dl>
                <Sources kind="topic" value={c.id} label="sources" />
              </div>
            </Reveal>
          ))}
          {CABLES.length === 0 && <div className="cd-cable"><p className="cd-claim">No concentrated adverse storyline in the window — the board is quiet.</p></div>}
        </div>

        <aside className="cd-arsenal">
          <div className="cd-block">
            <div className="cd-bh">YOUR BEST LINES <em>· on {ARSENAL.forCable}</em></div>
            {(ARSENAL.ammunition || []).map((a, i) => (
              <div className="cd-ammo" key={i}>▸ {a.url
                ? <a href={a.url} target="_blank" rel="noreferrer" style={{ color: 'inherit', textDecoration: 'none' }}>{a.text || a}</a>
                : (a.text || a)}{a.text_en && <div className="en-gloss"><b>EN</b>{a.text_en}</div>}</div>
            ))}
          </div>
          {ARSENAL.predraft && (
            <div className="cd-block">
              <div className="cd-bh">SUGGESTED REPLY <span className="cd-langs"><b>{ARSENAL.predraft.lang}</b> · {ARSENAL.predraft.words}w</span></div>
              <p className="cd-draft">{ARSENAL.predraft.en}</p>
              <div className="cd-flag">⚑ {ARSENAL.predraft.flag}</div>
              <div className="cd-actrow"><Magnetic className="btn primary">approve</Magnetic><button className="btn">edit</button><button className="btn cd-ghost">kill</button></div>
            </div>)}
          <div className="cd-block">
            <div className="cd-bh">WHAT OPPONENTS ARE SAYING <em>· in stories that hit you</em></div>
            {(ARSENAL.intercepts || []).map((qq, i) => {
              const body = (
                <>
                  <div className="cd-iq">“{qq.quote}”</div>
                  {qq.quote_en && <div className="en-gloss"><b>EN</b>{qq.quote_en}</div>}
                  <div className="cd-im"><b>{qq.who}</b> · {qq.role}<span className="cd-tier">{qq.tier}</span><span className="cd-isrc">{qq.src}</span></div>
                </>
              );
              return qq.url
                ? <a className="cd-intercept" key={i} href={qq.url} target="_blank" rel="noreferrer" style={{ color: 'inherit', textDecoration: 'none', display: 'block' }}>{body}</a>
                : <div className="cd-intercept" key={i}>{body}</div>;
            })}
            {(ARSENAL.intercepts || []).length === 0 && <div className="cd-ammo">No opposition quotes in stories that hit you this window.</div>}
          </div>
        </aside>
      </div>
    </div>
  );
}
