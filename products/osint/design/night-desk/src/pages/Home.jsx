import { useCallback, useEffect, useState } from 'react';
import { Reveal, StanceDot } from '../lib/ui';
import { Wave } from '../lib/charts';
import Panel from '../components/Panel';
import LiveStamp from '../components/LiveStamp';
import { authFetch } from '../lib/supabase';

const toneCls = (t) => (t === 'hostile' ? 'neg' : t === 'supportive' ? 'pos' : 'neu');
const sentiCls = (v) => (typeof v !== 'number' ? 'neu' : v >= 10 ? 'pos' : v <= -10 ? 'neg' : 'neu');
// Colour-classify the briefing callout cells by their meaning, not position
// (the cell order varies — "The Attack" only appears when there's an adverse line).
const blTone = (k = '') => {
  const s = String(k).toLowerCase();
  if (s.includes('stand')) return 'stand';
  if (s.includes('attack')) return 'attack';
  if (s.includes('move')) return 'move';
  return 'know';
};
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

// Show the translation line only when it's ACTUALLY English (the backend's
// lead_text_translated is unreliable — sometimes still in the source language).
// Heuristic: >60% ASCII letters = English. Truncate at a word boundary, no mid-word cuts.
function enText(t) {
  if (!t) return '';
  const s = String(t).trim();
  const ascii = (s.match(/[\x00-\x7F]/g) || []).length;
  if (!s.length || ascii / s.length < 0.6) return '';
  return s.length > 150 ? s.slice(0, 150).replace(/\s+\S*$/, '') + '…' : s;
}

export default function Home() {
  const [home, setHome] = useState(null);
  const [stories, setStories] = useState([]);
  const [status, setStatus] = useState({ loading: true, error: null });
  const [loadedAt, setLoadedAt] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  // Sentiment drill-down: top +/- stories driving the number, fetched on first open.
  const [explain, setExplain] = useState(null);
  const [explainOpen, setExplainOpen] = useState(false);

  // Silent swap: on a refetch we keep the current screen up (no loading flash) and
  // only surface an error on the very first load — a failed refresh keeps stale data.
  const load = useCallback(async ({ silent = false } = {}) => {
    if (silent) setRefreshing(true);
    try {
      const [h, s] = await Promise.all([
        authFetch('/api/brief/home'),
        authFetch('/api/brief/top-articles?limit=6').catch(() => null),
      ]);
      setHome(h);
      setStories((s && s.articles) || []);
      setStatus({ loading: false, error: null });
      setLoadedAt(Date.now());
    } catch (e) {
      setStatus((st) => (st.loading ? { loading: false, error: String(e?.message || e) } : st));
    } finally {
      if (silent) setRefreshing(false);
    }
  }, []);

  // Click the sentiment number → reveal the stories driving it (lazy-fetched once).
  const toggleExplain = useCallback(async () => {
    if (explainOpen) { setExplainOpen(false); return; }
    setExplainOpen(true);
    if (!explain) {
      try {
        const d = await authFetch('/api/brief/home/sentiment-explain');
        setExplain(d || { top_positive: [], top_negative: [] });
      } catch {
        setExplain({ top_positive: [], top_negative: [] });
      }
    }
  }, [explainOpen, explain]);

  useEffect(() => {
    load();
    // Auto-refresh every 30 min (matches the matview refresh cadence).
    const id = setInterval(() => load({ silent: true }), 30 * 60 * 1000);
    const onFocus = () => load({ silent: true });
    window.addEventListener('focus', onFocus);
    return () => { clearInterval(id); window.removeEventListener('focus', onFocus); };
  }, [load]);

  if (status.loading) return <Notice>Assembling your situation brief…</Notice>;
  if (status.error) return <Notice>Couldn’t load your brief — {status.error}</Notice>;
  if (!home || !home.personalized) return <Notice>Finish onboarding to generate your situation brief.</Notice>;

  const M = home.masthead || {};
  const B = home.briefing || {};
  const S = home.sentiment || {};
  const sPoints = S.points || [];
  const players = home.players || [];
  const six = home.six || [];
  const caveat = (home.caveats || [])[0];

  return (
    <div className="page stack" style={{ '--mt': '34px' }}>
      {/* masthead */}
      <Reveal>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <div className="eyebrow">SITUATION BRIEF</div>
          <LiveStamp at={loadedAt} />
        </div>
        <div className="masthead" style={{ marginTop: 12 }}>
          <div>
            {/* Headline is the theatre (state/entity), not the individual; the
                principal drops to the subline. Falls back to the principal if
                the persona has no state. */}
            <h1 className="subject">{M.state || M.principal}</h1>
            <div className="subline">
              {M.state && M.principal && <><span>{M.principal}</span><span className="sep" /></>}
              {M.displayName && <><span>{M.displayName}</span><span className="sep" /></>}
              <span className="mono" style={{ color: 'var(--ink)' }}>{M.window}</span><span className="sep" />
              <span>confidence <span className="pill">{M.confidence}</span></span>
            </div>
          </div>
          <div className="asof">AS OF {M.asOf}</div>
        </div>
        <div className="rule-orn">◆</div>
      </Reveal>

      {/* ⓪ COVERAGE SENTIMENT — persona-scoped waveform (jade above / coral below) */}
      {sPoints.length >= 2 && (
        <Reveal>
          <div className="panel senti">
            <div className="senti-head">
              <div className="label gold">Coverage Sentiment · {M.window}</div>
              <div className={'senti-now ' + sentiCls(S.now)} onClick={toggleExplain}
                   role="button" tabIndex={0} style={{ cursor: 'pointer' }}
                   title="Why this number? See the stories driving it"
                   onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') toggleExplain(); }}>
                <span className="snum">{typeof S.now === 'number' ? (S.now > 0 ? '+' : '') + S.now : '—'}</span>
                <span className="slab">{S.label || '—'}</span>
                <button type="button" className="senti-why" onClick={(e) => { e.stopPropagation(); toggleExplain(); }}>
                  {explainOpen ? 'Hide why ▾' : 'Why? ▸'}
                </button>
              </div>
            </div>
            <Wave data={sPoints.map((p) => Math.max(-1, Math.min(1, (p.v || 0) / 100)))} />
            <div className="senti-foot">
              <span className="pos">▲ Favourable</span>
              <span className="muted">{S.n || 0} stance signals · {M.principal}'s coverage</span>
              <span className="neg">Adverse ▼</span>
            </div>
            {explainOpen && (
              <div className="senti-explain">
                <div className="se-col">
                  <div className="se-head pos">▲ Lifting it up</div>
                  {!explain && <div className="se-row muted">Loading…</div>}
                  {explain && (explain.top_positive || []).map((x) => (
                    <a className="se-row" key={'p' + x.article_id} href={x.url || undefined}
                       target="_blank" rel="noopener noreferrer">
                      {x.why}
                      {enText(x.headline_en) && <div className="se-en">{enText(x.headline_en)}</div>}
                    </a>
                  ))}
                  {explain && !(explain.top_positive || []).length && (
                    <div className="se-row muted">No clear positive drivers.</div>
                  )}
                </div>
                <div className="se-col">
                  <div className="se-head neg">▼ Pulling it down</div>
                  {!explain && <div className="se-row muted">Loading…</div>}
                  {explain && (explain.top_negative || []).map((x) => (
                    <a className="se-row" key={'n' + x.article_id} href={x.url || undefined}
                       target="_blank" rel="noopener noreferrer">
                      {x.why}
                      {enText(x.headline_en) && <div className="se-en">{enText(x.headline_en)}</div>}
                    </a>
                  ))}
                  {explain && !(explain.top_negative || []).length && (
                    <div className="se-row muted">No clear negative drivers.</div>
                  )}
                </div>
              </div>
            )}
          </div>
        </Reveal>
      )}

      {/* ① THE BRIEFING */}
      <Reveal>
        <div className="panel hero briefing">
          <div className="label gold">The Briefing · {M.window}</div>

          <div className="bl-band">
            {(B.bottomLine || []).map((b, i) => (
              <div key={i} className={'bl-cell bl-' + blTone(b.k) + (b.action ? ' move' : '')}>
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
              <div className="sblk"><div className="kicker kicker-row"><span>What Happened</span>
                  <button type="button" className="refresh-btn" onClick={() => load({ silent: true })}
                          disabled={refreshing} title="Refresh the timeline">
                    <span className={'rfx' + (refreshing ? ' spin' : '')}>↻</span>{refreshing ? 'Refreshing' : 'Refresh'}
                  </button>
                </div>
                <div className="record">
                  {(B.whatHappened || []).map((w, i) => (
                    <div className="r" key={i}><span className="d">{w.date}</span><span className="t">{w.text}<span className="src">{w.src}</span>{w.text_en && <span className="en-gloss"><b>EN</b>{w.text_en}</span>}</span></div>
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
                {s.headline_en && <div className="en-gloss"><b>EN</b>{s.headline_en}</div>}
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
              {p.latest_headline_en && <div className="en-gloss"><b>EN</b>{p.latest_headline_en}</div>}
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
