// Sources — the reusable "show me the articles" receipts control.
//
// Drop <Sources kind value label count /> under any qualitative read (a threat
// cable, a sentiment split, an outlet-lean bar, an entity standing) and the user
// gets a one-click trail to the real coverage the read was built from.
//
// On first click it lazy-fetches GET /api/brief/sources?kind=<kind>&value=<value>
// via authFetch, then toggles an inline panel listing each article: a tone dot,
// the headline as a new-tab link, and "outlet · relative-time". Loading / error /
// empty states are all handled. Dark theme, inline styles only (no index.css).
import { useState, useCallback } from 'react';
import { authFetch } from '../lib/supabase';

const TONE_COLOR = {
  supportive: '#3fb98a', // friendly / with-you
  hostile: '#e0564f',    // adverse / against-you
  neutral: '#8a8f9c',    // mixed / set-aside
};

/** Relative "time ago" from an ISO timestamp; '' when missing/unparseable. */
function timeAgo(iso) {
  if (!iso) return '';
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return '';
  const h = (Date.now() - t) / 36e5;
  if (h < 1) return `${Math.max(1, Math.round(h * 60))}m ago`;
  if (h < 24) return `${Math.floor(h)}h ago`;
  const d = Math.floor(h / 24);
  return d < 7 ? `${d}d ago` : `${Math.floor(d / 7)}w ago`;
}

function Dot({ tone }) {
  return (
    <span
      aria-hidden="true"
      style={{
        flex: '0 0 auto', width: 7, height: 7, marginTop: 6, borderRadius: '50%',
        background: TONE_COLOR[tone] || TONE_COLOR.neutral,
      }}
    />
  );
}

function Row({ a }) {
  return (
    <li style={{ display: 'flex', gap: 9, padding: '8px 2px', borderTop: '1px solid rgba(255,255,255,0.06)' }}>
      <Dot tone={a.tone} />
      <span style={{ minWidth: 0, flex: 1 }}>
        <a
          href={a.url || '#'}
          target="_blank"
          rel="noreferrer"
          style={{ color: '#dfe3ea', textDecoration: 'none', fontSize: 12.5, lineHeight: 1.35, display: 'block' }}
          onMouseEnter={(e) => { e.currentTarget.style.textDecoration = 'underline'; }}
          onMouseLeave={(e) => { e.currentTarget.style.textDecoration = 'none'; }}
        >
          {a.title || '(untitled)'}
        </a>
        {a.title_en && a.title_en !== a.title && (
          <span style={{ display: 'block', color: '#9aa0ac', fontSize: 11, marginTop: 1 }}>
            <b style={{ fontSize: 9, opacity: 0.7, marginRight: 4 }}>EN</b>{a.title_en}
          </span>
        )}
        <span style={{ display: 'block', color: '#7b8090', fontSize: 10.5, marginTop: 2 }}>
          {[a.outlet, timeAgo(a.when)].filter(Boolean).join(' · ')}
        </span>
      </span>
    </li>
  );
}

/**
 * @param {{ kind: string, value?: string|number, bucket?: string, label?: string, count?: number }} props
 */
export default function Sources({ kind, value, bucket, label, count }) {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState({ loading: false, error: null, loaded: false });
  const [articles, setArticles] = useState([]);

  const load = useCallback(async () => {
    setState({ loading: true, error: null, loaded: false });
    try {
      const qs = new URLSearchParams({ kind });
      if (value !== undefined && value !== null && value !== '') qs.set('value', String(value));
      if (bucket) qs.set('bucket', String(bucket));
      const d = await authFetch(`/api/brief/sources?${qs.toString()}`);
      setArticles(Array.isArray(d?.articles) ? d.articles : []);
      setState({ loading: false, error: null, loaded: true });
    } catch (e) {
      setState({ loading: false, error: String(e?.message || e), loaded: false });
    }
  }, [kind, value, bucket]);

  const onToggle = useCallback(() => {
    const next = !open;
    setOpen(next);
    // Lazy-fetch the first time it's opened (or to retry after an error).
    if (next && !state.loaded && !state.loading) load();
  }, [open, state.loaded, state.loading, load]);

  const btnLabel = label || (typeof count === 'number' ? `see the ${count} stories` : 'sources');

  return (
    <div style={{ marginTop: 8 }}>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 5,
          background: 'transparent', border: '1px solid rgba(255,255,255,0.14)',
          borderRadius: 5, color: '#aeb4c0', cursor: 'pointer',
          font: 'inherit', fontSize: 11, letterSpacing: 0.2, padding: '3px 8px',
        }}
        onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'rgba(255,255,255,0.3)'; e.currentTarget.style.color = '#e6e9ef'; }}
        onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'rgba(255,255,255,0.14)'; e.currentTarget.style.color = '#aeb4c0'; }}
      >
        <span aria-hidden="true">◰</span>
        {btnLabel}
        {typeof count === 'number' && !label ? null : (typeof count === 'number' ? <span style={{ opacity: 0.6 }}>· {count}</span> : null)}
        <span aria-hidden="true" style={{ opacity: 0.6, fontSize: 9 }}>{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div
          style={{
            marginTop: 6, maxHeight: 320, overflowY: 'auto',
            background: 'rgba(8,10,16,0.55)', border: '1px solid rgba(255,255,255,0.08)',
            borderRadius: 6, padding: '4px 10px',
          }}
        >
          {state.loading && (
            <div style={{ color: '#8a8f9c', fontSize: 12, padding: '10px 2px' }}>Loading the stories…</div>
          )}
          {!state.loading && state.error && (
            <div style={{ color: '#e0564f', fontSize: 12, padding: '10px 2px' }}>
              Couldn’t load sources — {state.error}{' '}
              <button
                type="button"
                onClick={load}
                style={{ background: 'none', border: 'none', color: '#aeb4c0', cursor: 'pointer', font: 'inherit', fontSize: 12, textDecoration: 'underline', padding: 0 }}
              >
                retry
              </button>
            </div>
          )}
          {!state.loading && !state.error && state.loaded && articles.length === 0 && (
            <div style={{ color: '#8a8f9c', fontSize: 12, padding: '10px 2px' }}>No stories to show here.</div>
          )}
          {!state.loading && !state.error && articles.length > 0 && (
            <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
              {articles.map((a) => <Row key={a.id} a={a} />)}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
