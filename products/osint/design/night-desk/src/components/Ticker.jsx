import { useEffect, useState } from 'react';
import { authFetch } from '../lib/supabase';

const REFRESH_MS = 3 * 60 * 1000; // re-pull the newest headlines every ~3 min

export default function Ticker() {
  const [items, setItems] = useState([]);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const data = await authFetch('/api/brief/ticker');
        if (alive) setItems(Array.isArray(data?.items) ? data.items : []);
      } catch {
        // Not signed in / backend unreachable — leave the marquee empty rather
        // than crash the page; the loading fallback covers the gap.
        if (alive) setItems([]);
      }
    };
    load();
    const t = setInterval(load, REFRESH_MS);
    return () => { alive = false; clearInterval(t); };
  }, []);

  const line = items.map((it, i) => {
    const text = it.title_en || it.title || '';
    const label = it.source ? <>{text} <b>· {it.source}</b></> : text;
    const headline = it.url ? (
      <a href={it.url} target="_blank" rel="noreferrer"
         style={{ color: 'inherit', textDecoration: 'none' }}>{label}</a>
    ) : (
      <span>{label}</span>
    );
    return (
      <span className="item" key={it.id || i}>
        {headline}
        <span className="sep" aria-hidden="true">◆</span>
      </span>
    );
  });

  // Keep the scroll readable: drive the marquee duration off the amount of
  // content so longer headline lists don't whip past faster. ~6s of travel
  // per headline, with a calm floor so short lists still read slowly.
  const duration = Math.max(60, items.length * 6);

  return (
    <div className="ticker">
      <span className="tag"><span className="dot" />Breaking</span>
      <div className="track-wrap">
        {items.length ? (
          <div className="track" style={{ '--ticker-duration': `${duration}s` }}>
            <span className="run">{line}</span>
            <span className="run" aria-hidden="true">{line}</span>
          </div>
        ) : (
          <div className="track"><span className="run">Loading the latest headlines…</span></div>
        )}
      </div>
      <span className="rep">LIVE · 48H</span>
    </div>
  );
}
