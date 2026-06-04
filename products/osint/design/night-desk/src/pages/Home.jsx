import { useEffect, useState } from 'react';
import { Reveal, StanceDot } from '../lib/ui';
import Panel from '../components/Panel';
import { authFetch } from '../lib/supabase';

const toneCls = (t) => (t === 'hostile' ? 'neg' : t === 'supportive' ? 'pos' : 'neu');
const TOVL = {
  hostile: 'linear-gradient(180deg, oklch(0.5 0.2 25 / .42), oklch(0.05 0.01 270 / .82))',
  supportive: 'linear-gradient(180deg, oklch(0.55 0.15 165 / .38), oklch(0.05 0.01 270 / .82))',
  neutral: 'linear-gradient(180deg, oklch(0.32 0.02 270 / .35), oklch(0.05 0.01 270 / .82))',
};

function Notice({ children }) {
  return (
    <div className="page" style={{ '--mt': '34px' }}>
      <div className="panel" style={{ padding: 28, color: 'var(--faint)' }}>{children}</div>
    </div>
  );
}

export default function Home() {
  const [home, setHome] = useState(null);
  const [stories, setStories] = useState([]);
  const [status, setStatus] = useState({ loading: true, error: null });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [h, s] = await Promise.all([
          authFetch('/api/brief/home'),
          authFetch('/api/brief/top-articles?limit=6').catch(() => null),
        ]);
        if (cancelled) return;
        setHome(h);
        setStories((s && s.articles) || []);
        setStatus({ loading: false, error: null });
      } catch (e) {
        if (!cancelled) setStatus({ loading: false, error: String(e?.message || e) });
      }
    })();
    return () => { cancelled = true; };
  }, []);

  if (status.loading) return <Notice>Assembling your situation brief…</Notice>;
  if (status.error) return <Notice>Couldn’t load your brief — {status.error}</Notice>;
  if (!home || !home.personalized) return <Notice>Finish onboarding to generate your situation brief.</Notice>;

  const M = home.masthead || {};
  const B = home.briefing || {};
  const players = home.players || [];
  const six = home.six || [];
  const caveat = (home.caveats || [])[0];

  return (
    <div className="page stack" style={{ '--mt': '34px' }}>
      {/* masthead */}
      <Reveal>
        <div className="eyebrow">SITUATION BRIEF · {M.state}</div>
        <div className="masthead" style={{ marginTop: 12 }}>
          <div>
            <h1 className="subject">{M.first} <em>{M.last}</em></h1>
            <div className="subline">
              {M.displayName && <><span>{M.displayName}</span><span className="sep" /></>}
              <span className="mono" style={{ color: 'var(--ink)' }}>{M.window}</span><span className="sep" />
              <span>confidence <span className="pill">{M.confidence}</span></span>
            </div>
          </div>
          <div className="asof">AS OF {M.asOf}</div>
        </div>
        <div className="rule-orn">◆</div>
      </Reveal>

      {/* ① THE BRIEFING */}
      <Reveal>
        <div className="panel hero briefing">
          <div className="label gold">The Briefing · {M.window}</div>

          <div className="bl-band">
            {(B.bottomLine || []).map((b, i) => (
              <div key={i} className={'bl-cell' + (b.action ? ' move' : '')}>
                <div className="k">{b.k}</div>
                <div className="v">{b.v}</div>
                {b.action && <div className="approve">approve →</div>}
              </div>
            ))}
          </div>

          <div className="brief-grid">
            <div className="col">
              <div className="sblk lead"><div className="kicker">What It Means</div><p>{B.whatItMeans}</p></div>
              <div className="sblk"><div className="kicker">Why It Matters</div><p>{B.whyItMatters}</p></div>
              <div className="sblk dissent"><div className="kicker">The Other Side</div><p>{B.otherSide}</p></div>
            </div>
            <div className="col">
              <div className="sblk"><div className="kicker">What Happened</div>
                <div className="record">
                  {(B.whatHappened || []).map((w, i) => (
                    <div className="r" key={i}><span className="d">{w.date}</span><span className="t">{w.text}<span className="src">{w.src}</span></span></div>
                  ))}
                </div>
              </div>
              <div className="sblk"><div className="kicker">What's Next</div>
                <p>{B.whatsNext?.text} <span className={'conf ' + (B.whatsNext?.confidence || '')} style={{ whiteSpace: 'nowrap' }}>confidence {B.whatsNext?.confidence}</span></p>
              </div>
              <div className="sblk"><div className="kicker">How to Play It</div><p>{B.howToPlay}</p></div>
            </div>
          </div>
        </div>
      </Reveal>

      {/* ② TOP STORIES FOR YOU */}
      {stories.length > 0 && (
        <Reveal>
          <div className="eyebrow">TOP STORIES FOR YOU</div>
          <div className="sub" style={{ marginBottom: 18 }}>The stories that matter to you — and why.</div>
          <div className="tstories">
            {stories.map((s, i) => (
              <Panel key={i} className="tstory flat">
                <div className="thumb">
                  <img src={s.thumbnail || `https://picsum.photos/seed/${i}-osint/720/440`} alt="" loading="lazy" />
                  <div className="tovl" style={{ background: TOVL[s.tone] || TOVL.neutral }} />
                  <span>{s.source}</span>
                </div>
                <div className="hd"><StanceDot t={s.tone} /><span>{s.headline}</span></div>
                <div className="meta">{s.source} · {s.age}</div>
                <div className="fy"><b>For you</b>{s.summary || (s.matched ? `Matched on ${s.matched}.` : 'In your coverage this window.')}</div>
              </Panel>
            ))}
          </div>
        </Reveal>
      )}

      {/* ③ PEOPLE TO WATCH */}
      <Reveal>
        <div className="eyebrow">PEOPLE TO WATCH</div>
        <div className="sub" style={{ marginBottom: 16 }}>
          {caveat || 'Pressure and presence — each read shows its work.'}
        </div>
        <div className="players">
          {players.map((p, i) => (
            <Panel key={i} className="player">
              <div className="ph">
                <div>
                  <div className="nm">{p.name}</div>
                  <div className="rl">{p.rel}{p.kind ? <span className="pill" style={{ marginLeft: 8 }}>{p.kind}</span> : null}</div>
                </div>
                <div className="vd">
                  <div className={'vv num ' + toneCls(p.stance)}>{p.verdict}</div>
                  <div className={'sc num ' + toneCls(p.stance)}>{p.score}</div>
                  {p.trend ? <div className="tr">{p.trend}</div> : null}
                </div>
              </div>
              <p className="sm">{p.summary}</p>
              <div className="wl"><span className="lab">Why</span>{p.why}</div>
              <div className="wl"><span className="lab">Watch</span>{p.watch}</div>
            </Panel>
          ))}
        </div>
      </Reveal>

      {/* THE SIX */}
      <Reveal>
        <div className="eyebrow">THE SIX</div>
        <div className="sub" style={{ marginBottom: 16 }}>The quieter tells — the truth, the noise filter, the drafts.</div>
        <div className="sixgrid">
          {six.map((s, i) => (
            <Panel key={i} className={'six' + (s.kicker === 'The Hard Truth' ? ' hardtruth' : '')}>
              <div className="kk">{s.kicker}</div>
              <div className="tt">{s.title}</div>
              {s.body && <p>{s.body}</p>}
              {s.items && s.items.map((it, j) => (
                <div className="it" key={j}><span className={'vchip ' + it.vtone}>{it.verdict}</span><span className="tx">{it.text}</span></div>
              ))}
              {s.print && <div className="pr">{s.print}</div>}
            </Panel>
          ))}
        </div>
      </Reveal>
    </div>
  );
}
