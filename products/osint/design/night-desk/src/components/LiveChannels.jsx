import { channelsFor } from '../data/channels';

// Build the embed URL. Prefer a resolved live videoId (deterministic, reliable);
// fall back to the channel live_stream redirect. Autoplay muted so tiles start on
// their own — World-Monitor style, no clicking needed.
function embedSrc(c) {
  const common = 'autoplay=1&mute=1&playsinline=1&modestbranding=1&rel=0';
  return c.live
    ? `https://www.youtube.com/embed/${c.live}?${common}`
    : `https://www.youtube.com/embed/live_stream?channel=${c.id}&${common}`;
}

// Live YouTube news channel wall, persona-scoped. GLOBAL = world wires; MINE =
// national + regional for the persona's primary state. Up to 6 tiles, all auto-playing.
export default function LiveChannels({ scope, stateCode }) {
  const items = channelsFor(scope, stateCode);
  return (
    <section>
      <div className="eyebrow" style={{ color: 'var(--gold)' }}>LIVE CHANNELS</div>
      <h2 className="h-sec" style={{ margin: '4px 0' }}>On air<span className="h-sub"> — {scope === 'global' ? 'worldwide' : 'your region, live'}</span></h2>
      <div className="sub" style={{ marginBottom: 18 }}>
        {scope === 'global' ? 'Global news wires, streaming live.' : 'National + regional channels for your turf, streaming live.'}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(440px, 1fr))', gap: 16 }}>
        {items.map((c) => (
          <div key={c.id} style={{ borderRadius: 12, overflow: 'hidden', border: '1px solid var(--line)', background: '#000', boxShadow: '0 2px 18px rgba(0,0,0,0.45)' }}>
            <div style={{ position: 'relative', paddingTop: '56.25%' }}>
              <iframe
                title={c.name}
                src={embedSrc(c)}
                allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
                allowFullScreen
                style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', border: 0 }}
              />
            </div>
            <div style={{ padding: '9px 13px', fontSize: '0.86rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>{c.name}</span>
              <span style={{ fontSize: '0.6rem', color: 'var(--neg, #fb7185)', letterSpacing: '0.12em' }}>● LIVE</span>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
