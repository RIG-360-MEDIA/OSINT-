import { useState, useMemo, useEffect, useRef } from 'react';
import DeckGL from '@deck.gl/react';
import { GeoJsonLayer, ColumnLayer, TextLayer } from '@deck.gl/layers';
import { FlyToInterpolator, WebMercatorViewport } from '@deck.gl/core';
import { Map } from 'react-map-gl/maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';
import { authFetch } from '../lib/supabase';
import AP_GEO from '../data/andhra-pradesh-districts.json';
import TG_GEO from '../data/telangana-districts.json';

const DARK_STYLE = import.meta.env.VITE_BASEMAP_URL || 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json';
const WORLD = { longitude: 35, latitude: 22, zoom: 1.35, pitch: 0, bearing: 0 };
const GEOJSON = { AP: AP_GEO, TG: TG_GEO };

const C_SUP = [60, 214, 160], C_CRIT = [240, 92, 92], C_NEU = [96, 110, 140];
const TONE = { supportive: C_SUP, hostile: C_CRIT, neutral: [120, 140, 175] };
const lerp = (a, b, t) => a.map((v, i) => Math.round(v + (b[i] - v) * t));
const clamp01 = (t) => Math.max(0, Math.min(1, t));

// geojson district name -> our backend district key (handles the 2022-rename diffs)
const ALIAS = { ANANTAPURAMU: 'ANANTAPUR', YSR: 'YSR KADAPA', 'ALLURI SITHARAMA RAJU': 'ALLURI SITARAMA RAJU' };
const norm = (s) => { const u = (s || '').toUpperCase().replace(/\s+/g, ' ').trim(); return ALIAS[u] || u; };

function stanceFill(d) {
  if (!d || (d.sup + d.crit) === 0) return [60, 68, 92, 200];
  const p = (d.sup - d.crit) / (d.sup + d.crit);
  const t = clamp01(Math.abs(p) / 0.35);
  return [...(p >= 0 ? lerp(C_NEU, C_SUP, t) : lerp(C_NEU, C_CRIT, t)), 218];
}

function viewForBbox(bbox, scope) {
  if (!bbox) return WORLD;
  try {
    const vp = new WebMercatorViewport({ width: 1280, height: 720 }).fitBounds(
      [[bbox.minLon, bbox.minLat], [bbox.maxLon, bbox.maxLat]], { padding: scope === 'mine' ? 70 : 140 });
    return { longitude: vp.longitude, latitude: vp.latitude, zoom: Math.min(Math.max(vp.zoom, 3), 7.4), pitch: 46, bearing: -16 };
  } catch {
    return { longitude: bbox.centerLon, latitude: bbox.centerLat, zoom: scope === 'mine' ? 6.3 : 4.4, pitch: 46, bearing: -16 };
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
    (async () => {
      try {
        let d = cache.current[scope];
        if (!d) { d = await authFetch(`/api/brief/map?scope=${scope}`); cache.current[scope] = d; }
        if (cancelled) return;
        setData(d); setStatus({ loading: false, error: null });
        setView({ ...viewForBbox(d.bbox, scope), transitionDuration: 2400, transitionInterpolator: new FlyToInterpolator({ speed: 1.3 }) });
      } catch (e) { if (!cancelled) setStatus({ loading: false, error: String(e?.message || e) }); }
    })();
    return () => { cancelled = true; };
  }, [scope]);

  const bubbles = (data && data.bubbles) || [];
  const maxArt = useMemo(() => Math.max(1, ...bubbles.map((b) => b.articles || 0)), [bubbles]);
  const lookup = useMemo(() => { const m = {}; bubbles.forEach((b) => { m[norm(b.name)] = b; }); return m; }, [bubbles]);
  const geo = data && data.state_code ? GEOJSON[data.state_code] : null;
  const useChoropleth = scope === 'mine' && !!geo;

  const layers = useMemo(() => {
    const labelData = [...bubbles].sort((a, b) => (b.articles || 0) - (a.articles || 0)).slice(0, scope === 'mine' ? 12 : 6);
    const labelLayer = new TextLayer({
      id: 'labels', data: labelData, getPosition: (b) => [b.lon, b.lat], getText: (b) => b.name,
      getSize: 11, getColor: [236, 241, 250, 240], getPixelOffset: [0, -4],
      fontFamily: 'ui-monospace, monospace', getTextAnchor: 'middle', getAlignmentBaseline: 'center',
      outlineWidth: 3, outlineColor: [5, 7, 12, 255], fontSettings: { sdf: true },
    });
    if (useChoropleth) {
      return [new GeoJsonLayer({
        id: 'choropleth', data: geo, extruded: true, filled: true, stroked: true, wireframe: false,
        getElevation: (f) => { const d = lookup[norm(f.properties.district)]; return d ? (Math.sqrt(d.articles) / Math.sqrt(maxArt)) * 115000 : 0; },
        getFillColor: (f) => stanceFill(lookup[norm(f.properties.district)]),
        getLineColor: [222, 228, 244, 75], lineWidthMinPixels: 1, pickable: true,
        autoHighlight: true, highlightColor: [245, 200, 90, 120],
        material: { ambient: 0.5, diffuse: 0.65, shininess: 40, specularColor: [50, 50, 60] },
        transitions: { getElevation: 550, getFillColor: 400 },
        updateTriggers: { getFillColor: [lookup], getElevation: [lookup, maxArt] },
        onHover: (info) => setHover(info.object ? { x: info.x, y: info.y, b: lookup[norm(info.object.properties.district)] || { name: info.object.properties.district, articles: 0, sup: 0, crit: 0, net: 0 } } : null),
      }), labelLayer];
    }
    return [new ColumnLayer({
      id: 'cols', data: bubbles, diskResolution: 18, extruded: true, pickable: true,
      radius: scope === 'mine' ? 6500 : 55000, getPosition: (b) => [b.lon, b.lat],
      getFillColor: (b) => [...(TONE[b.tone] || TONE.neutral), 235], getLineColor: [255, 255, 255, 28],
      getElevation: (b) => (Math.sqrt(b.articles || 0) / Math.sqrt(maxArt || 1)) * 95000,
      material: { ambient: 0.55, diffuse: 0.7, shininess: 60, specularColor: [60, 60, 70] },
      autoHighlight: true, highlightColor: [245, 200, 90, 200],
      transitions: { getElevation: 550, getFillColor: 400 }, updateTriggers: { getElevation: [maxArt, scope] },
      onHover: (info) => setHover(info.object ? { x: info.x, y: info.y, b: info.object } : null),
    }), labelLayer];
  }, [bubbles, maxArt, scope, geo, useChoropleth, lookup]);

  const total = bubbles.reduce((s, b) => s + (b.articles || 0), 0);

  return (
    <div style={{ position: 'relative', height: 'calc(100vh - 132px)', minHeight: 520, borderRadius: 14, overflow: 'hidden', border: '1px solid var(--line)' }}>
      <DeckGL viewState={view} onViewStateChange={(e) => setView(e.viewState)} controller={true} layers={layers} style={{ position: 'absolute', inset: 0 }}>
        <Map reuseMaps mapStyle={DARK_STYLE} attributionControl={false} />
      </DeckGL>

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

      <div style={{ position: 'absolute', bottom: 16, left: 16, background: 'var(--void-2,#0b0a10cc)', border: '1px solid var(--line)', borderRadius: 10, padding: '10px 14px', fontSize: '0.72rem', color: 'var(--faint)' }}>
        <div style={{ marginBottom: 6, letterSpacing: '0.1em' }}>{useChoropleth ? 'DISTRICT COLOUR = NET STANCE · HEIGHT = COVERAGE' : 'COLUMN HEIGHT = COVERAGE · COLOUR = STANCE'}</div>
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
