import { channelsFor } from '../data/channels';

// Live YouTube news channels, persona-scoped. GLOBAL = world wires; MINE = 3 national
// + 5 regional for the persona's primary state. Embeds the channel's current live stream.
export default function LiveChannels({ scope, stateCode }) {
  const { groups } = channelsFor(scope, stateCode);
  return (
    <section>
      <div className="eyebrow" style={{ color: 'var(--gold)' }}>LIVE CHANNELS</div>
      <h2 className="h-sec" style={{ margin: '4px 0' }}>On air<span className="h-sub"> — {scope === 'global' ? 'worldwide' : 'your region, live'}</span></h2>
      <div className="sub" style={{ marginBottom: 16 }}>
        {scope === 'global' ? 'Global news wires, streaming live.' : 'National + regional channels for your turf, streaming live.'}
      </div>
      {groups.map((g) => (
        <div key={g.label} style={{ marginBottom: 18 }}>
          <div style={{ fontFamily: 'var(--mono)', fontSize: '0.64rem', letterSpacing: '0.14em', color: 'var(--faint)', marginBottom: 8 }}>
            {g.label.toUpperCase()} · {g.items.length}
          </div>
          {g.items.length === 0
            ? <div className="sub">No channels configured for this region yet.</div>
            : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 12 }}>
                {g.items.map((c) => (
                  <div key={c.id + g.label} style={{ borderRadius: 10, overflow: 'hidden', border: '1px solid var(--line)', background: '#000' }}>
                    <div style={{ position: 'relative', paddingTop: '56.25%' }}>
                      <iframe
                        title={c.name}
                        src={`https://www.youtube.com/embed/live_stream?channel=${c.id}&mute=1`}
                        allow="encrypted-media; picture-in-picture; fullscreen"
                        loading="lazy"
                        style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', border: 0 }}
                      />
                    </div>
                    <div style={{ padding: '7px 11px', fontSize: '0.8rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span>{c.name}</span>
                      <span style={{ fontSize: '0.58rem', color: 'var(--neg, #fb7185)', letterSpacing: '0.12em' }}>● LIVE</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
        </div>
      ))}
    </section>
  );
}
