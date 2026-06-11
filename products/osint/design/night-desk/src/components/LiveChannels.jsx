import { useRef, useState, useEffect } from 'react';
import { channelsFor } from '../data/channels';
import { authFetch } from '../lib/supabase';

// Build the embed URL. Prefer a resolved live videoId (deterministic, reliable for
// channels that run multiple parallel live streams); otherwise the channel
// live_stream redirect (self-heals when a single-live channel goes on air).
function embedSrc(c) {
  const q = 'autoplay=1&mute=1&playsinline=1&modestbranding=1&rel=0';
  return c.live
    ? `https://www.youtube.com/embed/${c.live}?${q}`
    : `https://www.youtube.com/embed/live_stream?channel=${c.id}&${q}`;
}

// Mounts the heavy YouTube iframe only once the tile scrolls near the viewport —
// keeps the map snappy and avoids 6 live HLS streams loading at once on page open.
function ChannelTile({ c, n }) {
  const ref = useRef(null);
  const [play, setPlay] = useState(false);
  const poster = c.live ? `https://i.ytimg.com/vi/${c.live}/hqdefault.jpg` : null;
  // Show the poster instantly; mount the autoplaying stream only once the tile is
  // visible, STAGGERED by index so 6 live HLS streams don't all load at once.
  useEffect(() => {
    const el = ref.current;
    if (!el || play) return undefined;
    let timer;
    const io = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) {
        io.disconnect();
        timer = setTimeout(() => setPlay(true), (n - 1) * 600);
      }
    }, { rootMargin: '150px' });
    io.observe(el);
    return () => { io.disconnect(); if (timer) clearTimeout(timer); };
  }, [play, n]);
  return (
    <div ref={ref} className="wm-tile" style={{ borderRadius: 7, overflow: 'hidden', border: '1px solid var(--line)', background: '#06070a' }}>
      <div style={{ position: 'relative', paddingTop: '56.25%' }}>
        {poster
          ? <img src={poster} alt="" loading="lazy" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover' }} />
          : <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', color: 'var(--faint)', fontFamily: 'var(--mono)', fontSize: '0.64rem', letterSpacing: '0.14em' }}>{c.name.toUpperCase()}</div>}
        {play && (
          <iframe
            title={c.name}
            src={embedSrc(c)}
            allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
            allowFullScreen
            style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', border: 0 }}
          />
        )}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '7px 11px', background: '#0a0b10', borderTop: '1px solid var(--line)' }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 9, minWidth: 0 }}>
          <span style={{ fontFamily: 'var(--mono)', fontSize: '0.6rem', color: 'var(--faint)' }}>{String(n).padStart(2, '0')}</span>
          <span style={{ fontSize: '0.8rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{c.name}</span>
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 5, fontFamily: 'var(--mono)', fontSize: '0.56rem', letterSpacing: '0.16em', color: '#fb6a6a', flex: 'none' }}>
          <i className="wm-livedot" />LIVE
        </span>
      </div>
    </div>
  );
}

// Live YouTube news channel wall, persona-scoped. GLOBAL = world wires; MINE =
// national + regional for the persona's primary state. Up to 6 tiles, World-Monitor style.
export default function LiveChannels({ scope, stateCode }) {
  // The backend resolver returns only channels that are LIVE right now (live ids
  // rotate hourly). Fall back to the static curated list if it's unavailable.
  const [items, setItems] = useState(() => channelsFor(scope, stateCode));
  useEffect(() => {
    let cancelled = false;
    setItems(channelsFor(scope, stateCode));
    (async () => {
      try {
        const r = await authFetch(`/api/brief/channels?scope=${scope}`);
        if (!cancelled && r && Array.isArray(r.channels) && r.channels.length) setItems(r.channels);
      } catch { /* keep static fallback */ }
    })();
    return () => { cancelled = true; };
  }, [scope, stateCode]);
  return (
    <section className="wm-sec">
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
        <div>
          <div className="eyebrow" style={{ color: 'var(--gold)' }}>LIVE CHANNELS</div>
          <h2 className="h-sec" style={{ margin: '4px 0' }}>On air<span className="h-sub"> — {scope === 'global' ? 'worldwide' : 'your region, live'}</span></h2>
        </div>
        <span style={{ display: 'flex', alignItems: 'center', gap: 7, fontFamily: 'var(--mono)', fontSize: '0.62rem', letterSpacing: '0.16em', color: '#fb6a6a' }}>
          <i className="wm-livedot" />{items.length} STREAMING
        </span>
      </div>
      <div className="sub" style={{ marginBottom: 16 }}>
        {scope === 'global' ? 'Global news wires, streaming live.' : 'National + regional channels for your turf, streaming live.'}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(404px, 1fr))', gap: 12 }}>
        {items.map((c, ix) => <ChannelTile key={c.id} c={c} n={ix + 1} />)}
      </div>
    </section>
  );
}
