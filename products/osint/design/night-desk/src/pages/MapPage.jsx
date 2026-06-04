import { useState, useMemo, useEffect, useRef } from 'react';
import DeckGL from '@deck.gl/react';
import { ScatterplotLayer, TextLayer } from '@deck.gl/layers';
import { FlyToInterpolator, WebMercatorViewport } from '@deck.gl/core';
import { Map } from 'react-map-gl/maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';
import { authFetch } from '../lib/supabase';

const DARK_STYLE = import.meta.env.VITE_BASEMAP_URL || 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json';
const WORLD = { longitude: 35, latitude: 22, zoom: 1.35, pitch: 0, bearing: 0 };
const TONE = { supportive: [60, 214, 160], hostile: [240, 92, 92], neutral: [120, 140, 175] };

function viewForBbox(bbox, scope) {
  if (!bbox) return WORLD;
  try {
    const vp = new WebMercatorViewport({ width: 1280, height: 720 }).fitBounds(
      [[bbox.minLon, bbox.minLat], [bbox.maxLon, bbox.maxLat]],
      { padding: scope === 'mine' ? 90 : 140 });
    return { longitude: vp.longitude, latitude: vp.latitude, zoom: Math.min(Math.max(vp.zoom, 3), 7.6), pitch: 42, bearing: -12 };
  } catch {
    return { longitude: bbox.centerLon, latitude: bbox.centerLat, zoom: scope === 'mine' ? 6.4 : 4.4, pitch: 42, bearing: -12 };
  }
}

export default function MapPage() {
  const [scope, setScope] = useState('mine');
  const [data, setData] = useState(null);
  const [status, setStatus] = useState({ loading: true, error: null });
  const [view, setView] = useState(WORLD);
  const [hover, setHover] = useState(null);
  const cache = useRef({});

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        let d = cache.current[scope];
        if (!d) { d = await authFetch(`/api/brief/map?scope=${scope}`); cache.current[scope] = d; }
        if (cancelled) return;
        setData(d);
        setStatus({ loading: false, error: null });
        // signature animation: fly from the current (world) view into the scope's extent
        setView({ ...viewForBbox(d.bbox, scope), transitionDuration: 2400, transitionInterpolator: new FlyToInterpolator({ speed: 1.3 }) });
      } catch (e) {
        if (!cancelled) setStatus({ loading: false, error: String(e?.message || e) });
      }
    }
    load();
    return () => { cancelled = true; };
  }, [scope]);

  const bubbles = (data && data.bubbles) || [];
  const maxArt = useMemo(() => Math.max(1, ...bubbles.map((b) => b.articles || 0)), [bubbles]);

  const layers = useMemo(() => {
    const radius = (b) => 14000 + Math.sqrt((b.articles || 0) / maxArt) * 130000 * (scope === 'mine' ? 0.42 : 1);
    return [
      new ScatterplotLayer({
        id: 'bubbles', data: bubbles, pickable: true, stroked: true, filled: true,
        radiusUnits: 'meters', getPosition: (b) => [b.lon, b.lat],
        getRadius: radius, radiusMinPixels: 5, radiusMaxPixels: 64,
        getFillColor: (b) => [...(TONE[b.tone] || TONE.neutral), 165],
        getLineColor: (b) => [...(TONE[b.tone] || TONE.neutral), 255], lineWidthMinPixels: 1.2,
        onHover: (info) => setHover(info.object ? { x: info.x, y: info.y, b: info.object } : null),
        updateTriggers: { getRadius: [scope, maxArt] },
        transitions: { getRadius: 500, getFillColor: 400 },
      }),
      new TextLayer({
        id: 'labels', data: scope === 'mine' ? bubbles : bubbles.filter((b) => b.articles > maxArt * 0.15),
        getPosition: (b) => [b.lon, b.lat], getText: (b) => b.name,
        getSize: 11, getColor: [233, 238, 248, 220], getPixelOffset: [0, -14],
        fontFamily: 'ui-monospace, monospace', getTextAnchor: 'middle', getAlignmentBaseline: 'bottom',
        outlineWidth: 2, outlineColor: [10, 12, 18, 255], fontSettings: { sdf: true },
      }),
    ];
  }, [bubbles, maxArt, scope]);

  const total = bubbles.reduce((s, b) => s + (b.articles || 0), 0);

  return (
    <div style={{ position: 'relative', height: 'calc(100vh - 132px)', minHeight: 520, borderRadius: 14, overflow: 'hidden', border: '1px solid var(--line)' }}>
      <DeckGL viewState={view} onViewStateChange={(e) => setView(e.viewState)} controller={true} layers={layers} style={{ position: 'absolute', inset: 0 }}>
        <Map reuseMaps mapStyle={DARK_STYLE} attributionControl={false} />
      </DeckGL>

      {/* header / scope toggle */}
      <div style={{ position: 'absolute', top: 16, left: 16, right: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', pointerEvents: 'none' }}>
        <div style={{ pointerEvents: 'auto' }}>
          <div className="eyebrow" style={{ color: 'var(--gold)' }}>THE THEATRE</div>
          <h1 className="h-sec" style={{ margin: '4px 0' }}>Situation Map</h1>
          <div className="sub" style={{ maxWidth: 460 }}>
            {data ? (scope === 'mine'
              ? `${data.region} — ${bubbles.length} districts · ${total.toLocaleString()} stories · ${data.window_days}d`
              : `Global rollup — ${bubbles.length} regions · ${total.toLocaleString()} stories`) : 'Loading the theatre…'}
          </div>
        </div>
        <div style={{ pointerEvents: 'auto', display: 'flex', gap: 6, background: 'var(--void-2,#0b0a10)', border: '1px solid var(--line)', borderRadius: 10, padding: 5 }}>
          {['mine', 'global'].map((s) => (
            <button key={s} onClick={() => setScope(s)}
              style={{ padding: '8px 16px', borderRadius: 7, border: 'none', cursor: 'pointer', fontWeight: 600, fontSize: '0.78rem', letterSpacing: '0.08em',
                background: scope === s ? 'var(--gold)' : 'transparent', color: scope === s ? '#1a1407' : 'var(--faint)' }}>
              {s === 'mine' ? 'MINE' : 'GLOBAL'}
            </button>
          ))}
        </div>
      </div>

      {/* legend */}
      <div style={{ position: 'absolute', bottom: 16, left: 16, background: 'var(--void-2,#0b0a10cc)', border: '1px solid var(--line)', borderRadius: 10, padding: '10px 14px', fontSize: '0.72rem', color: 'var(--faint)' }}>
        <div style={{ marginBottom: 6, letterSpacing: '0.1em' }}>BUBBLE = COVERAGE · COLOUR = STANCE</div>
        <div style={{ display: 'flex', gap: 14 }}>
          {[['supportive', 'supportive'], ['neutral', 'neutral'], ['hostile', 'critical']].map(([k, lbl]) => (
            <span key={k} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <i style={{ width: 9, height: 9, borderRadius: 9, background: `rgb(${TONE[k].join(',')})` }} />{lbl}
            </span>
          ))}
        </div>
      </div>

      {status.loading && <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', color: 'var(--faint)', background: 'var(--void,#07060a)' }}>Flying in…</div>}
      {status.error && <div style={{ position: 'absolute', bottom: 16, right: 16, color: 'var(--neg,#fb7185)', fontSize: '0.8rem' }}>Map error — {status.error}</div>}

      {hover && hover.b && (
        <div className="tmap-card" style={{ position: 'absolute', left: Math.min(hover.x + 16, 900), top: hover.y + 16, pointerEvents: 'none' }}>
          <h4>{hover.b.name}</h4>
          <div className="cv">{(hover.b.articles || 0).toLocaleString()} stories{hover.b.topic ? ` · ${hover.b.topic}` : ''}</div>
          <div className="cr">+{hover.b.sup} / −{hover.b.crit} (net {hover.b.net > 0 ? '+' : ''}{hover.b.net})</div>
        </div>
      )}
    </div>
  );
}
