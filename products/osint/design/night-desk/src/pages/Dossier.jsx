import { useState, useEffect, useCallback } from 'react';
import { Reveal } from '../lib/ui';
import { Sparkline, RankBars } from '../lib/charts';
import { authFetch } from '../lib/supabase';
import Sources from '../components/Sources';

const TYPES = ['all', 'person', 'org', 'place'];
const ALIGN_DOT = { against: 'hostile', for: 'supportive', neutral: 'neutral' };
const initials = (n) => (n || '?').split(/\s+/).slice(0, 2).map((w) => w[0]).join('').toUpperCase();
const ageOf = (iso) => {
  if (!iso) return '';
  const d = (Date.now() - new Date(iso).getTime()) / 36e5;
  if (d < 1) return 'now'; if (d < 24) return `${Math.floor(d)}h`; return `${Math.floor(d / 24)}d`;
};

function Portrait({ ent, img }) {
  const src = img || ent.img;
  const [ok, setOk] = useState(!!src);
  useEffect(() => { setOk(!!src); }, [src]);
  return (
    <div className={'df-portrait a-' + ent.align}>
      {ok ? <img src={src} alt="" style={{ objectFit: 'cover' }} onError={() => setOk(false)} />
          : <div className="df-redacted"><span>{initials(ent.name)}</span><em>NO IMAGE</em></div>}
      <span className="df-stripe">{ent.align}</span>
    </div>
  );
}
function Tile({ k, v, tone, win }) {
  return (
    <div className="df-tile">
      <div className="df-tk">{k}</div>
      <div className={'df-tv' + (tone ? ' ' + tone : '')}>{v}</div>
      {win && <div className="df-twin" style={{ fontSize: '0.62rem', letterSpacing: '0.04em', textTransform: 'uppercase', opacity: 0.5, marginTop: 2 }}>{win}</div>}
    </div>
  );
}
function FPanel({ title, sub, source, children, span }) {
  return (
    <div className={'df-panel' + (span ? ' df-span' : '')}>
      <div className="df-ph"><span>{title}{sub && <em> · {sub}</em>}</span></div>
      <div className="df-pc">{children}</div>
      {source && <div className="df-src">{source}</div>}
    </div>
  );
}
function Stance({ sup, neu, crit }) {
  const t = sup + crit || 1;
  const supPct = Math.round((100 * sup) / t);
  const v = sup > crit * 1.25 ? { t: 'FRIENDLY', c: 'pos' } : crit > sup * 1.25 ? { t: 'HOSTILE', c: 'neg' } : { t: 'CONTESTED', c: 'gold' };
  return (
    <div className="df-stance">
      <div className="df-strow">
        <div className="df-stend pos"><b>{sup}</b><span>FOR</span></div>
        <div className="df-stbar"><i className="pos" style={{ width: supPct + '%' }} /><i className="neg" style={{ width: 100 - supPct + '%' }} /></div>
        <div className="df-stend neg"><b>{crit}</b><span>AGAINST</span></div>
      </div>
      <div className="df-stfoot"><span className={'df-verdict ' + v.c}>{v.t}</span>{neu ? <span className="df-stneu">{neu} neutral set aside</span> : null}</div>
    </div>
  );
}
function OutletLean({ items }) {
  return (
    <div className="df-outlets">
      {items.map((o) => {
        const net = Math.round((100 * (o.pos - o.neg)) / ((o.pos + o.neg) || 1));
        const neg = net < 0;
        return (
          <div className="df-outrow" key={o.name}>
            <span className="df-outname">{o.name}</span>
            <span className="df-outtrack"><i className={neg ? 'neg' : 'pos'} style={{ width: Math.min(Math.abs(net), 50) + '%', [neg ? 'right' : 'left']: '50%' }} /></span>
            <span className={'df-outv ' + (neg ? 'neg' : 'pos')}>{net > 0 ? '+' : ''}{net}% {neg ? 'hostile' : 'friendly'}</span>
          </div>
        );
      })}
    </div>
  );
}

function Notice({ children }) {
  return <div className="subjectfile"><div className="panel" style={{ padding: 28, color: 'var(--faint)' }}>{children}</div></div>;
}

export default function Dossier() {
  const [roster, setRoster] = useState([]);
  const [sel, setSel] = useState(null);
  const [q, setQ] = useState('');
  const [type, setType] = useState('all');
  const [file, setFile] = useState(null);
  const [feed, setFeed] = useState([]);
  const [cursor, setCursor] = useState(null);
  const [more, setMore] = useState(false);
  const [status, setStatus] = useState({ loading: true, error: null });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await authFetch('/api/brief/dossier/roster');
        if (cancelled) return;
        const list = r.roster || [];
        setRoster(list);
        const principal = list.find((e) => e.principal === true) || list[0];
        setSel((cur) => cur || (principal && principal.id) || null);
        setStatus({ loading: false, error: null });
      } catch (e) { if (!cancelled) setStatus({ loading: false, error: String(e?.message || e) }); }
    })();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!sel) return;
    let cancelled = false;
    setFile(null); setFeed([]); setCursor(null);
    (async () => {
      try {
        const [f, feedRes] = await Promise.all([
          authFetch(`/api/brief/dossier/entity/${sel}`),
          authFetch(`/api/brief/dossier/entity/${sel}/articles?limit=20`),
        ]);
        if (cancelled) return;
        setFile(f); setFeed(feedRes.articles || []); setCursor(feedRes.next_cursor || null);
      } catch (e) { if (!cancelled) setFile({ found: false, error: String(e?.message || e) }); }
    })();
    return () => { cancelled = true; };
  }, [sel]);

  const loadMore = useCallback(async () => {
    if (!cursor || more) return;
    setMore(true);
    try {
      const res = await authFetch(`/api/brief/dossier/entity/${sel}/articles?limit=20&cursor=${encodeURIComponent(cursor)}`);
      setFeed((cur) => [...cur, ...(res.articles || [])]);
      setCursor(res.next_cursor || null);
    } catch { /* keep what we have */ } finally { setMore(false); }
  }, [cursor, more, sel]);

  if (status.loading) return <Notice>Loading the registry…</Notice>;
  if (status.error) return <Notice>Couldn’t load the registry — {status.error}</Notice>;

  const list = roster.filter((e) => (type === 'all' || e.type === type) && e.name.toLowerCase().includes(q.toLowerCase()));
  const ent = roster.find((e) => e.id === sel) || roster[0] || { name: '', align: 'neutral' };

  return (
    <div className="subjectfile">
      <Reveal>
        <div className="eyebrow">THE REGISTRY · {roster.length} WATCHED</div>
        <h1 className="h-sec" style={{ marginTop: 6 }}>Dossier</h1>
        <div className="sub">Open a file on any watched entity — identity, a written read, and the full live coverage record.</div>
      </Reveal>

      <div className="df-shell">
        <aside className="df-roster">
          <div className="df-search"><input value={q} onChange={(e) => setQ(e.target.value)} placeholder={`Search ${roster.length} entities…`} /></div>
          <div className="df-filters">{TYPES.map((t) => <button key={t} className={'df-fbtn' + (type === t ? ' on' : '')} onClick={() => setType(t)}>{t}</button>)}</div>
          <div className="df-list">
            {list.map((e) => (
              <div key={e.id} className={'df-row' + (e.id === sel ? ' on' : '')} onClick={() => setSel(e.id)}>
                <span className="df-av">{e.img ? <img src={e.img} alt="" /> : initials(e.name)}</span>
                <div className="df-rn"><b>{e.name}</b><span>{e.role}</span></div>
                <span className={'df-dot ' + (ALIGN_DOT[e.align] || 'neutral')} />
                <span className="df-rc">{(e.mentions || 0).toLocaleString()}</span>
              </div>
            ))}
            {list.length === 0 && <div className="df-empty">No match.</div>}
          </div>
        </aside>

        <Reveal key={sel} className="df-open" y={10}>
          <div className="df-id">
            <Portrait ent={ent} img={file && file.found ? file.img : null} />
            <div className="df-idtext">
              <div className="df-class">WATCHLIST · {(ent.align || '').toUpperCase()}</div>
              <h2 className="df-name">{ent.name}</h2>
              <div className="df-meta">{ent.type} · {ent.role}</div>
              {file && file.found && file.aliases && file.aliases.length > 0 && (
                <div className="df-aka">{file.aliases.map((a) => <span key={a}>{a}</span>)}</div>)}
              {file && file.found && (
                <div className="df-tiles">
                  <Tile k="MENTIONS" v={(file.tiles.mentions || 0).toLocaleString()} win="all-time" />
                  <Tile k="QUOTES BY" v={file.tiles.quotes} win="all-time" />
                  <Tile k="CLAIMS" v={file.tiles.claims} win="all-time" />
                  <Tile k="NET STANCE" v={(file.tiles.net > 0 ? '+' : '') + file.tiles.net} tone={file.tiles.net < 0 ? 'neg' : file.tiles.net > 0 ? 'pos' : ''} win="90 days" />
                </div>)}
              {file && file.found && (
                <div className="df-winnote" style={{ fontSize: '0.66rem', color: 'var(--faint)', marginTop: 8, lineHeight: 1.4 }}>
                  MENTIONS · QUOTES BY · CLAIMS are all-time totals. NET STANCE, Standing &amp; Share of voice cover the last 90 days; Pulse covers the last 21 days. Lifetime totals are not comparable to the windowed stance.
                </div>)}
              {file && file.found && (
                <Sources kind="entity" value={file.id} label="all sources" />)}
            </div>
          </div>

          {file && file.found && (
            <div className="df-summary"><div className="df-stamp">RECENT ACTIVITY</div><p>{file.summary}</p></div>)}
          {file && !file.found && <div className="df-summary"><p>No file available for this entity.</p></div>}

          {file && file.found && (
            <div className="df-grid">
              <FPanel title="Pulse" sub="mentions / day · last 21 days" source="article_entity_mentions">
                <Sparkline data={file.pulse} color="cool" w={300} h={48} />
              </FPanel>
              <FPanel title="Standing" sub="for vs against · last 90 days" source="article_stances">
                <Stance sup={file.standing.sup} neu={file.standing.neu} crit={file.standing.crit} />
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 4 }}>
                  <Sources kind="entity" value={file.id} bucket="supportive" label="supportive" />
                  <Sources kind="entity" value={file.id} bucket="critical" label="critical" />
                  <Sources kind="entity" value={file.id} bucket="neutral" label="neutral" />
                </div>
              </FPanel>
              {file.sov.length > 0 && (
                <FPanel title="Share of voice" sub="vs peers · last 90 days" source="article_entity_mentions"><RankBars items={file.sov} /></FPanel>)}
              {file.issues.length > 0 && (
                <FPanel title="Issue footprint" sub="topics they ride" source="topic_category"><RankBars items={file.issues} /></FPanel>)}
              {file.quotes.length > 0 && (
                <FPanel title="In their words" sub="quotes by them" source="article_quotes">
                  <div className="df-quotes">{file.quotes.map((qq, i) => (
                    <div key={i} className="df-quote"><p>“{qq.q}”</p>{qq.q_en && <div className="en-gloss"><b>EN</b>{qq.q_en}</div>}<span>{qq.src} · {qq.date}</span></div>))}</div>
                  <Sources kind="entity" value={file.id} label="where they’re quoted" />
                </FPanel>)}
              {file.network.length > 0 && (
                <FPanel title="Network" sub="who they move with" source="entity co-mention">
                  <div className="df-rels">{file.network.map((nn) => (
                    <div className="df-relrow" key={nn.name}><span className="df-reldot ally" /><span className="df-relname">{nn.name}</span><span className="df-relmeta">{nn.rel} · {nn.n} shared</span></div>))}</div>
                </FPanel>)}
              {file.outlets.length > 0 && (
                <FPanel title="Who covers them" sub="friendly vs hostile" source="sources × article_stances"><OutletLean items={file.outlets} /></FPanel>)}
              <FPanel title="Reach" sub="language" source="articles.language_iso">
                <div className="df-reach">
                  <div className="df-langbar"><span className="en" style={{ flex: file.reach.en || 0.01 }} /><span className="te" style={{ flex: file.reach.te || 0.01 }} /></div>
                  <div className="df-langleg"><span><i className="en" />English {file.reach.en}</span><span><i className="te" />Telugu {file.reach.te}</span></div>
                </div>
              </FPanel>
              {file.timeline.length > 0 && (
                <FPanel title="Timeline" sub="events" source="article_events" span>
                  <div className="df-timeline">{file.timeline.map((t, i) => (
                    <div key={i} className="df-tl"><span className="df-tld">{t.date}</span><span className="df-tlw">
                      {t.url
                        ? <a href={t.url} target="_blank" rel="noreferrer noopener" style={{ color: 'inherit' }}>{t.what}</a>
                        : t.what}
                      {t.what_en && <span className="en-gloss"><b>EN</b>{t.what_en}</span>}
                      {t.src && <span className="df-tlsrc" style={{ display: 'block', fontSize: '0.78em', opacity: 0.6, marginTop: 2 }}>{t.src}</span>}
                    </span></div>))}</div>
                </FPanel>)}

              {/* LIVE WHOLE-CORPUS COVERAGE FEED — newest first, paginated */}
              <FPanel title="Full coverage" sub="every story, latest first" source="articles · live" span>
                <div className="df-feed">
                  {feed.map((a) => (
                    <a className="df-feedrow" key={a.id} href={a.url || '#'} target="_blank" rel="noreferrer">
                      <span className="df-feedthumb">{a.thumbnail ? <img src={a.thumbnail} alt="" loading="lazy" /> : <i className={'df-recdot ' + a.tone} />}</span>
                      <span className="df-feedmain"><span className="df-feedhead">{a.headline}</span>
                        {a.headline_en && <span className="en-gloss"><b>EN</b>{a.headline_en}</span>}
                        <span className="df-feedmeta"><span className={'df-recdot ' + a.tone} /> {a.source} · {ageOf(a.collected_at)}{a.topic ? ` · ${a.topic}` : ''}</span></span>
                    </a>
                  ))}
                  {feed.length === 0 && <div className="df-empty">No coverage in the corpus yet.</div>}
                  {cursor && <button className="df-loadmore" onClick={loadMore} disabled={more}>{more ? 'Loading…' : 'Load more'}</button>}
                </div>
              </FPanel>
            </div>)}
          {!file && <div className="df-summary"><p>Opening file…</p></div>}
        </Reveal>
      </div>
    </div>
  );
}
