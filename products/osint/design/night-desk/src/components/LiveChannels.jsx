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
function ChannelTile({ c }) {
  const ref = useRef(null);
  const [show, setShow] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || show) return undefined;
    const io = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) { setShow(true); io.disconnect(); }
    }, { rootMargin: '300px' });
    io.observe(el);
    return () => io.disconnect();
  }, [show]);
  return (
    <div ref={ref} style={{ borderRadius: 12, overflow: 'hidden', border: '1px solid var(--line)', background: '#000', boxShadow: '0 2px 18px rgba(0,0,0,0.45)' }}>
      <div style={{ position: 'relative', paddingTop: '56.25%' }}>
        {show
          ? (
            <iframe
              title={c.name}
              src={embedSrc(c)}
              allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
              allowFullScreen
              style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', border: 0 }}
            />
          )
          : <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', color: 'var(--faint)', fontSize: '0.72rem', letterSpacing: '0.12em' }}>● LOADING STREAM…</div>}
      </div>
      <div style={{ padding: '9px 13px', fontSize: '0.86rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span>{c.name}</span>
        <span style={{ fontSize: '0.6rem', color: 'var(--neg, #fb7185)', letterSpacing: '0.12em' }}>● LIVE</span>
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
    <section>
      <div className="eyebrow" style={{ color: 'var(--gold)' }}>LIVE CHANNELS</div>
      <h2 className="h-sec" style={{ margin: '4px 0' }}>On air<span className="h-sub"> — {scope === 'global' ? 'worldwide' : 'your region, live'}</span></h2>
      <div className="sub" style={{ marginBottom: 18 }}>
        {scope === 'global' ? 'Global news wires, streaming live.' : 'National + regional channels for your turf, streaming live.'}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(440px, 1fr))', gap: 16 }}>
        {items.map((c) => <ChannelTile key={c.id} c={c} />)}
      </div>
    </section>
  );
}
