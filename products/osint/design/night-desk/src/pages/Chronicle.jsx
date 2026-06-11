import { useEffect, useState, useCallback } from 'react';
import { Reveal } from '../lib/ui';
import { authFetch } from '../lib/supabase';
import EventChain from '../components/chronicle/EventChain';
import InsightBomb from '../components/chronicle/InsightBomb';
import ActorCard from '../components/chronicle/ActorCard';
import ChronicleLoader from '../components/chronicle/ChronicleLoader';
import CoverageMap from '../components/chronicle/CoverageMap';
import '../styles/chronicle.css';

const BASE = (import.meta.env.BASE_URL || '/').replace(/\/$/, '');

// Pull the {storyId} out of /chronicle/{id} (base-path aware). null → list view.
function storyIdFromPath() {
  let p = window.location.pathname || '/';
  if (BASE && p.startsWith(BASE)) p = p.slice(BASE.length);
  const parts = p.replace(/^\/+/, '').split('/'); // ['chronicle', '{id}'?]
  return parts[0] === 'chronicle' && parts[1] ? decodeURIComponent(parts[1]) : null;
}

/* ════════════════════════════════════════════════════════════════════════
   ARTICLES DRAWER — lazy-loaded source list on each list card
   ════════════════════════════════════════════════════════════════════════ */
function ArticlesDrawer({ storyId, articleCount }) {
  const [open, setOpen] = useState(false);
  const [articles, setArticles] = useState(null);
  const [loading, setLoading] = useState(false);

  const toggle = (e) => {
    e.stopPropagation();
    if (!open && articles === null) {
      setLoading(true);
      authFetch(`/api/chronicle/${storyId}/articles`)
        .then((d) => { setArticles(d.articles || []); setLoading(false); })
        .catch(() => { setArticles([]); setLoading(false); });
    }
    setOpen((o) => !o);
  };

  return (
    <div className="chron-drawer" onClick={(e) => e.stopPropagation()}>
      <button className="chron-drawer-toggle" onClick={toggle}>
        <span className={`chron-drawer-chevron ${open ? 'open' : ''}`}>›</span>
        <span>{articleCount} source articles</span>
      </button>

      {open && (
        <div className="chron-drawer-body">
          {loading && <div className="chron-drawer-status">Loading articles…</div>}
          {!loading && articles && articles.length === 0 && (
            <div className="chron-drawer-status">No articles found.</div>
          )}
          {!loading && articles && articles.map((a, i) => (
            <a
              key={i}
              className="chron-drawer-item"
              href={a.url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
            >
              <span className="chron-drawer-item-title">{a.title}</span>
              <span className="chron-drawer-item-meta">
                {a.source}{a.pub_date ? ` · ${a.pub_date}` : ''}
              </span>
            </a>
          ))}
        </div>
      )}
    </div>
  );
}

/* ════════════════════════════════════════════════════════════════════════
   LIST — the Chronicles an admin pushed to this user
   ════════════════════════════════════════════════════════════════════════ */
function ChronicleList({ onOpen }) {
  const [items, setItems] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    authFetch('/api/chronicle/mine')
      .then((d) => setItems(d.items || []))
      .catch((e) => setError(e.message || 'Could not load your Chronicles'));
  }, []);

  return (
    <div className="chron-list">
      <Reveal>
        <div className="chron-list-head">
          <div className="chron-eyebrow">CHRONICLE</div>
          <div className="chron-sub">
            Deep, reasoned reconstructions of the stories assigned to you — the causal chain,
            the findings beneath the headlines, and who is really playing what game.
          </div>
        </div>
      </Reveal>

      {error && (
        <div className="chron-error">
          <span>Could not load your Chronicles.</span>
          <code>{error}</code>
        </div>
      )}

      {!error && items === null && (
        <div className="chron-grid">
          {[0, 1, 2].map((i) => (
            <div key={i} className="chron-skel-card" style={{ height: 200 }}>
              <div className="chron-skel-line w40" />
              <div className="chron-skel-line tall w90" />
              <div className="chron-skel-line w60" />
            </div>
          ))}
        </div>
      )}

      {!error && items !== null && items.length === 0 && (
        <div className="chron-empty">
          <div className="big">No Chronicles yet</div>
          <div>When an analyst pushes a story to you, its full Chronicle will appear here.</div>
        </div>
      )}

      {!error && items && items.length > 0 && (
        <div className="chron-grid">
          {items.map((s, i) => (
            <Reveal key={s.story_id} delay={i * 0.05}>
              <div className="chron-card" onClick={() => onOpen(s.story_id)}>
                {s.label && <span className="chron-card-label">{s.label}</span>}
                <div className="chron-card-title">{s.title}</div>
                <div className="chron-card-meta">
                  {s.first_seen && <span>{s.first_seen}</span>}
                  {s.span_days != null && <><span className="sep">·</span><span>{s.span_days} days</span></>}
                  {s.article_count != null && <><span className="sep">·</span><span>{s.article_count} articles</span></>}
                  {s.source_count != null && <><span className="sep">·</span><span>{s.source_count} sources</span></>}
                </div>
                <div className="chron-card-foot">
                  <span className="chron-open">Open Chronicle &rarr;</span>
                  <span className={`chron-ready ${s.ready ? 'on' : 'off'}`}>
                    <span className="dot" />{s.ready ? 'Ready' : 'On open'}
                  </span>
                </div>
                {s.article_count > 0 && (
                  <ArticlesDrawer storyId={s.story_id} articleCount={s.article_count} />
                )}
              </div>
            </Reveal>
          ))}
        </div>
      )}
    </div>
  );
}

/* ════════════════════════════════════════════════════════════════════════
   DETAIL — the three-layer Chronicle for one story
   ════════════════════════════════════════════════════════════════════════ */
function ChronicleDetail({ storyId, onBack }) {
  const [meta, setMeta]       = useState(null);
  const [chronicle, setChron] = useState(null);
  const [error, setError]     = useState(null);
  const [tab, setTab]         = useState('story');

  useEffect(() => {
    setMeta(null); setChron(null); setError(null); setTab('story');
    authFetch(`/api/chronicle/${storyId}/meta`).then(setMeta).catch(() => {});
    authFetch(`/api/chronicle/${storyId}`)
      .then(setChron)
      .catch((e) => setError(e.message || 'Analysis unavailable'));
  }, [storyId]);

  const spanDays = meta?.span_days;

  // Fetch article pool once — passed to EventChain for per-event source matching
  const [articlePool, setArticlePool] = useState([]);
  useEffect(() => {
    authFetch(`/api/chronicle/${storyId}/articles`)
      .then((d) => setArticlePool(d.articles || []))
      .catch(() => setArticlePool([]));
  }, [storyId]);

  return (
    <div className="chron">
      {/* ── Hero — scrolls away; contains full title + meta ── */}
      <div className="chron-hero">
        <button className="chron-back" onClick={onBack}>&larr; All Chronicles</button>
        <h1 className="chron-title">{meta?.title || '…'}</h1>
        {meta && (
          <div className="chron-metarow">
            {meta.first_seen && <span>{meta.first_seen}</span>}
            {meta.last_seen  && <><span className="sep">—</span><span>{meta.last_seen}</span></>}
            {spanDays   != null && <><span className="sep">·</span><span>{spanDays} days</span></>}
            {meta.article_count != null && <><span className="sep">·</span><span>{meta.article_count} articles</span></>}
            {meta.source_count  != null && <><span className="sep">·</span><span>{meta.source_count} sources</span></>}
            {chronicle?.windows?.length > 0 && (
              <span className="chron-v2-badge">
                V2 · {chronicle.windows.length} windows
              </span>
            )}
          </div>
        )}
      </div>

      {/* ── Tab bar — slim, sticks at top as hero scrolls away ── */}
      <div className="chron-tabbar">
        {[
          { id: 'story',    label: 'The Story'    },
          { id: 'insights', label: 'What It Means' },
          { id: 'players',  label: 'The Players'  },
        ].map(({ id, label }) => (
          <button
            key={id}
            className={`chron-tab ${tab === id ? 'active' : ''}`}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </div>

      {/* ── Single active panel — only the chosen layer is rendered ── */}
      <div className="chron-panel">

        {tab === 'story' && (
          <>
            <div className="chron-section-head">
              <span className="chron-section-label">THE STORY</span>
              <p className="chron-section-sub">
                A causal reconstruction — not what was reported, but what actually happened
                and why each thing set the next in motion.
              </p>
            </div>
            {error ? (
              <div className="chron-error">
                <span>Chronicle analysis could not be generated.</span>
                <code>{error}</code>
              </div>
            ) : !chronicle ? (
              <ChronicleLoader />
            ) : (
              <>
                <CoverageMap windows={chronicle.windows} />
                <EventChain events={chronicle.event_chain} articles={articlePool} />
              </>
            )}
          </>
        )}

        {tab === 'insights' && (
          <>
            <div className="chron-section-head">
              <span className="chron-section-label">WHAT IT MEANS</span>
              <p className="chron-section-sub">
                Analytical findings invisible to the headline reader — the deductions that
                reframe everything.
              </p>
            </div>
            {!chronicle ? (
              <ChronicleLoader />
            ) : chronicle.insights?.length > 0 ? (
              chronicle.insights.map((ins, i) => <InsightBomb key={i} insight={ins} index={i} />)
            ) : (
              <p className="chron-muted">No insights available for this story.</p>
            )}
          </>
        )}

        {tab === 'players' && (
          <>
            <div className="chron-section-head">
              <span className="chron-section-label">THE PLAYERS</span>
              <p className="chron-section-sub">
                Who is actually playing what game — stated positions, real agendas, and what
                to watch for next.
              </p>
            </div>
            {!chronicle ? (
              <ChronicleLoader />
            ) : chronicle.actors?.length > 0 ? (
              <div className="chron-actors-grid">
                {chronicle.actors.map((a, i) => (
                  <ActorCard key={i} actor={a} storySpanDays={spanDays} index={i} />
                ))}
              </div>
            ) : (
              <p className="chron-muted">No actor analysis available for this story.</p>
            )}
          </>
        )}

      </div>
    </div>
  );
}

/* ════════════════════════════════════════════════════════════════════════
   ORCHESTRATOR — list ⇄ detail, kept in sync with the address bar
   ════════════════════════════════════════════════════════════════════════ */
export default function Chronicle() {
  const [storyId, setStoryId] = useState(() => storyIdFromPath());

  useEffect(() => {
    const onPop = () => setStoryId(storyIdFromPath());
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  const open = useCallback((id) => {
    setStoryId(id);
    window.history.pushState({}, '', `${BASE}/chronicle/${id}`);
    window.scrollTo({ top: 0, behavior: 'instant' });
  }, []);

  const back = useCallback(() => {
    setStoryId(null);
    window.history.pushState({}, '', `${BASE}/chronicle`);
    window.scrollTo({ top: 0, behavior: 'instant' });
  }, []);

  return storyId
    ? <ChronicleDetail storyId={storyId} onBack={back} />
    : <ChronicleList onOpen={open} />;
}
