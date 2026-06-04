import { useState, useMemo, useEffect, useRef } from 'react';
import DeckGL from '@deck.gl/react';
import { GeoJsonLayer, ColumnLayer, TextLayer } from '@deck.gl/layers';
import { FlyToInterpolator, WebMercatorViewport } from '@deck.gl/core';
import { Map } from 'react-map-gl/maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';
import { authFetch } from '../lib/supabase';
import LiveChannels from '../components/LiveChannels';
import MapSections from '../components/MapSections';
import AP_GEO from '../data/andhra-pradesh-districts.json';
import TG_GEO from '../data/telangana-districts.json';
import WORLD_GEO from '../data/world-countries.json';

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
// World choropleth join: ISO_A2_EH fixes Natural Earth's -99 codes (France, Norway, …).
const isoOf = (f) => { const p = f.properties || {}; const eh = p.ISO_A2_EH; return (eh && eh !== '-99') ? eh : p.ISO_A2; };

function stanceFill(d) {
  if (!d || (d.sup + d.crit) === 0) return [60, 68, 92, 200];
  const p = (d.sup - d.crit) / (d.sup + d.crit);
  const t = clamp01(Math.abs(p) / 0.35);
  return [...(p >= 0 ? lerp(C_NEU, C_SUP, t) : lerp(C_NEU, C_CRIT, t)), 218];
}

// Volume heatmap (cool -> hot) — colours every country by how much coverage it has.
const HEAT = [[20, 28, 44], [30, 86, 112], [52, 150, 142], [206, 168, 74], [224, 96, 64], [206, 44, 52]];
function heatColor(t) {
  const x = clamp01(t) * (HEAT.length - 1);
  const i = Math.floor(x);
  return i >= HEAT.length - 1 ? HEAT[HEAT.length - 1] : lerp(HEAT[i], HEAT[i + 1], x - i);
}
function heatFill(d, maxArt) {
  if (!d || !d.articles) return [26, 30, 42, 120];
  const t = Math.log(1 + d.articles) / Math.log(1 + (maxArt || 1));
  return [...heatColor(t), 225];
}

function viewForBbox(bbox, scope, flat) {
  const pitch = flat ? 0 : 46, bearing = flat ? 0 : -16;
  if (!bbox) return WORLD;
  try {
    const vp = new WebMercatorViewport({ width: 1280, height: 720 }).fitBounds(
      [[bbox.minLon, bbox.minLat], [bbox.maxLon, bbox.maxLat]], { padding: scope === 'mine' ? 70 : 140 });
    return { longitude: vp.longitude, latitude: vp.latitude, zoom: Math.min(Math.max(vp.zoom, 3), 7.4), pitch, bearing };
  } catch {
    return { longitude: bbox.centerLon, latitude: bbox.centerLat, zoom: scope === 'mine' ? 6.3 : 4.4, pitch, bearing };
  }
}

const dRow = { display: 'flex', gap: 10, alignItems: 'flex-start', padding: '7px 0', textDecoration: 'none', color: 'inherit', borderBottom: '1px solid var(--line)' };
const dBar = { display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem', padding: '4px 0', color: 'var(--faint)' };
function DCard({ title, children }) {
  return <div style={{ marginTop: 14 }}><div style={{ fontFamily: 'var(--mono)', fontSize: '0.62rem', letterSpacing: '0.14em', color: 'var(--gold)', marginBottom: 6 }}>{title.toUpperCase()}</div>{children}</div>;
}
function DStance({ s }) {
  const tot = (s.sup + s.crit) || 1, supPct = Math.round(100 * s.sup / tot);
  return (
    <div>
      <div style={{ display: 'flex', height: 8, borderRadius: 5, overflow: 'hidden' }}>
        <i style={{ width: supPct + '%', background: 'var(--supportive,#3cd6a0)' }} /><i style={{ width: (100 - supPct) + '%', background: 'var(--hostile,#f05c5c)' }} />
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.7rem', color: 'var(--faint)', marginTop: 4 }}>
        <span>{s.sup} for</span><span>{s.neu} neutral</span><span>{s.crit} against</span>
      </div>
    </div>
  );
}

export default function MapPage() {
  const [scope, setScope] = useState('mine');
  const [data, setData] = useState(null);
  const [status, setStatus] = useState({ loading: true, error: null });
  const [view, setView] = useState(WORLD);
  const [flat, setFlat] = useState(true); // 2D (flat) is the default for both scopes
  const [hover, setHover] = useState(null);
  const [dist, setDist] = useState(null); // district drawer { id, loading, file, feed, cursor, more }
  const [country, setCountry] = useState(null); // country drawer { iso, loading, file, feed, cursor, more }
  const cache = useRef({});

  function toggleFlat() {
    setFlat((f) => {
      const nf = !f;
      setView((v) => ({ ...v, pitch: nf ? 0 : 46, bearing: nf ? 0 : -16, transitionDuration: 600 }));
      return nf;
    });
  }

  async function openDistrict(b) {
    if (!b || !b.id) return;
    setDist({ id: b.id, loading: true, file: null, feed: [], cursor: null });
    try {
      const [f, fd] = await Promise.all([
        authFetch(`/api/brief/district/${b.id}`),
        authFetch(`/api/brief/district/${b.id}/articles?limit=15`),
      ]);
      setDist({ id: b.id, loading: false, file: f, feed: fd.articles || [], cursor: fd.next_cursor || null, more: false });
    } catch (e) {
      setDist({ id: b.id, loading: false, file: { found: false, error: String(e?.message || e) }, feed: [], cursor: null });
    }
  }
  async function loadMoreD() {
    if (!dist || !dist.cursor || dist.more) return;
    setDist((d) => ({ ...d, more: true }));
    try {
      const fd = await authFetch(`/api/brief/district/${dist.id}/articles?limit=15&cursor=${encodeURIComponent(dist.cursor)}`);
      setDist((d) => ({ ...d, feed: [...d.feed, ...(fd.articles || [])], cursor: fd.next_cursor || null, more: false }));
    } catch { setDist((d) => ({ ...d, more: false })); }
  }

  async function openCountry(iso, name) {
    if (!iso) return;
    setCountry({ iso, name, loading: true, file: null, feed: [], cursor: null });
    try {
      const [f, fd] = await Promise.all([
        authFetch(`/api/brief/country/${iso}`),
        authFetch(`/api/brief/country/${iso}/articles?limit=15`),
      ]);
      setCountry({ iso, name, loading: false, file: f, feed: fd.articles || [], cursor: fd.next_cursor || null, more: false });
    } catch (e) {
      setCountry({ iso, name, loading: false, file: { found: false, error: String(e?.message || e) }, feed: [], cursor: null });
    }
  }
  async function loadMoreC() {
    if (!country || !country.cursor || country.more) return;
    setCountry((c) => ({ ...c, more: true }));
    try {
      const fd = await authFetch(`/api/brief/country/${country.iso}/articles?limit=15&cursor=${encodeURIComponent(country.cursor)}`);
      setCountry((c) => ({ ...c, feed: [...c.feed, ...(fd.articles || [])], cursor: fd.next_cursor || null, more: false }));
    } catch { setCountry((c) => ({ ...c, more: false })); }
  }

  useEffect(() => {
    let cancelled = false; let timer;
    (async () => {
      try {
        let d = cache.current[scope];
        if (!d) { d = await authFetch(`/api/brief/map?scope=${scope}`); cache.current[scope] = d; }
        if (cancelled) return;
        setData(d); setStatus({ loading: false, error: null });
        const flyTo = (vs, dur) => ({ ...vs, transitionDuration: dur, transitionInterpolator: new FlyToInterpolator({ speed: 1.2 }) });
        if (scope === 'mine') {
          // Hold on the whole world for 2s, then animate down into the user's region.
          setView({ ...WORLD, pitch: flat ? 0 : 28 });
          timer = setTimeout(() => { if (!cancelled) setView(flyTo(viewForBbox(d.bbox, scope, flat), 2600)); }, 2000);
        } else {
          // Global: pull back out to the whole-world view.
          setView(flyTo(viewForBbox(d.bbox, scope, flat), 2200));
        }
      } catch (e) { if (!cancelled) setStatus({ loading: false, error: String(e?.message || e) }); }
    })();
    return () => { cancelled = true; if (timer) clearTimeout(timer); };
  }, [scope]);

  const bubbles = (data && data.bubbles) || [];
  const maxArt = useMemo(() => Math.max(1, ...bubbles.map((b) => b.articles || 0)), [bubbles]);
  const lookup = useMemo(() => { const m = {}; bubbles.forEach((b) => { m[norm(b.name)] = b; }); return m; }, [bubbles]);
  const countryLookup = useMemo(() => { const m = {}; bubbles.forEach((b) => { if (b.id) m[b.id] = b; }); return m; }, [bubbles]);
  const geo = data && data.state_code ? GEOJSON[data.state_code] : null;
  const useChoropleth = scope === 'mine' && !!geo;

  const layers = useMemo(() => {
    const labelData = [...bubbles].sort((a, b) => (b.articles || 0) - (a.articles || 0)).slice(0, scope === 'mine' ? 12 : 18);
    const labelLayer = new TextLayer({
      id: 'labels', data: labelData, getPosition: (b) => [b.lon, b.lat], getText: (b) => b.name,
      getSize: 11, getColor: [236, 241, 250, 240], getPixelOffset: [0, -4],
      fontFamily: 'ui-monospace, monospace', getTextAnchor: 'middle', getAlignmentBaseline: 'center',
      outlineWidth: 3, outlineColor: [5, 7, 12, 255], fontSettings: { sdf: true },
    });
    if (scope === 'global') {
      return [new GeoJsonLayer({
        id: 'world', data: WORLD_GEO, extruded: !flat, filled: true, stroked: true, wireframe: false,
        getElevation: (f) => { if (flat) return 0; const d = countryLookup[isoOf(f)]; return d ? (Math.sqrt(d.articles) / Math.sqrt(maxArt)) * 480000 : 0; },
        getFillColor: (f) => heatFill(countryLookup[isoOf(f)], maxArt),
        getLineColor: [222, 228, 244, flat ? 95 : 60], lineWidthMinPixels: 0.6, pickable: true,
        autoHighlight: true, highlightColor: [245, 200, 90, 140],
        material: { ambient: 0.5, diffuse: 0.65, shininess: 40, specularColor: [50, 50, 60] },
        transitions: { getElevation: 550, getFillColor: 400 },
        updateTriggers: { getFillColor: [countryLookup, maxArt], getElevation: [countryLookup, maxArt, flat], getLineColor: [flat] },
        onHover: (info) => setHover(info.object ? { x: info.x, y: info.y, b: countryLookup[isoOf(info.object)] || { name: (info.object.properties.NAME || info.object.properties.ADMIN), articles: 0, sup: 0, crit: 0, net: 0 } } : null),
        onClick: (info) => { if (info.object) { const d = countryLookup[isoOf(info.object)]; if (d && d.articles) openCountry(d.id, d.name); } },
      }), labelLayer];
    }
    if (useChoropleth) {
      return [new GeoJsonLayer({
        id: 'choropleth', data: geo, extruded: !flat, filled: true, stroked: true, wireframe: false,
        getElevation: (f) => { if (flat) return 0; const d = lookup[norm(f.properties.district)]; return d ? (Math.sqrt(d.articles) / Math.sqrt(maxArt)) * 115000 : 0; },
        getFillColor: (f) => stanceFill(lookup[norm(f.properties.district)]),
        getLineColor: [222, 228, 244, flat ? 130 : 75], lineWidthMinPixels: flat ? 1.2 : 1, pickable: true,
        autoHighlight: true, highlightColor: [245, 200, 90, 120],
        material: { ambient: 0.5, diffuse: 0.65, shininess: 40, specularColor: [50, 50, 60] },
        transitions: { getElevation: 550, getFillColor: 400 },
        updateTriggers: { getFillColor: [lookup], getElevation: [lookup, maxArt, flat], getLineColor: [flat] },
        onHover: (info) => setHover(info.object ? { x: info.x, y: info.y, b: lookup[norm(info.object.properties.district)] || { name: info.object.properties.district, articles: 0, sup: 0, crit: 0, net: 0 } } : null),
        onClick: (info) => info.object && openDistrict(lookup[norm(info.object.properties.district)]),
      }), labelLayer];
    }
    return [new ColumnLayer({
      id: 'cols', data: bubbles, diskResolution: 18, extruded: !flat, pickable: true,
      radius: scope === 'mine' ? 6500 : 135000, getPosition: (b) => [b.lon, b.lat],
      getFillColor: (b) => [...(TONE[b.tone] || TONE.neutral), 235], getLineColor: [255, 255, 255, 28],
      getElevation: (b) => (flat ? 0 : (Math.sqrt(b.articles || 0) / Math.sqrt(maxArt || 1)) * 95000),
      material: { ambient: 0.55, diffuse: 0.7, shininess: 60, specularColor: [60, 60, 70] },
      autoHighlight: true, highlightColor: [245, 200, 90, 200],
      transitions: { getElevation: 550, getFillColor: 400 }, updateTriggers: { getElevation: [maxArt, scope, flat] },
      onHover: (info) => setHover(info.object ? { x: info.x, y: info.y, b: info.object } : null),
      onClick: (info) => info.object && openDistrict(info.object),
    }), labelLayer];
  }, [bubbles, maxArt, scope, geo, useChoropleth, lookup, countryLookup, flat]);

  const total = bubbles.reduce((s, b) => s + (b.articles || 0), 0);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 22, padding: '4px clamp(18px, 2.5vw, 42px) 60px', boxSizing: 'border-box', maxWidth: '100%', overflowX: 'hidden' }}>
      <div style={{ position: 'relative', height: '66vh', minHeight: 480, borderRadius: 8, overflow: 'hidden', border: '1px solid var(--line)' }}>
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
              : `${data.region} — ${bubbles.length} countries · ${total.toLocaleString()} stories`) : 'Loading the theatre…'}
          </div>
        </div>
        <div style={{ pointerEvents: 'auto', display: 'flex', gap: 8 }}>
          <div className="wm-hud" style={{ display: 'flex', gap: 6, padding: 5 }}>
            {['mine', 'global'].map((s) => (
              <button key={s} onClick={() => setScope(s)}
                style={{ padding: '8px 16px', borderRadius: 7, border: 'none', cursor: 'pointer', fontWeight: 600, fontSize: '0.78rem', letterSpacing: '0.08em',
                  background: scope === s ? 'var(--gold)' : 'transparent', color: scope === s ? '#1a1407' : 'var(--faint)' }}>
                {s === 'mine' ? 'MINE' : 'GLOBAL'}
              </button>
            ))}
          </div>
          <div className="wm-hud" style={{ display: 'flex', gap: 6, padding: 5 }}>
            {[['3D', false], ['2D', true]].map(([lbl, val]) => (
              <button key={lbl} onClick={() => { if (flat !== val) toggleFlat(); }}
                style={{ padding: '8px 13px', borderRadius: 7, border: 'none', cursor: 'pointer', fontWeight: 600, fontSize: '0.78rem', letterSpacing: '0.08em',
                  background: flat === val ? 'var(--gold)' : 'transparent', color: flat === val ? '#1a1407' : 'var(--faint)' }}>
                {lbl}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="wm-hud" style={{ position: 'absolute', bottom: 16, left: 16, padding: '10px 14px', fontSize: '0.72rem', color: 'var(--faint)' }}>
        {scope === 'global' ? (
          <>
            <div className="wm-label" style={{ marginBottom: 6 }}>COUNTRY COLOUR = COVERAGE{flat ? '' : ' · HEIGHT = COVERAGE'}</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span>less</span>
              <i style={{ width: 130, height: 9, borderRadius: 5, background: 'linear-gradient(90deg, rgb(30,86,112), rgb(52,150,142), rgb(206,168,74), rgb(224,96,64), rgb(206,44,52))' }} />
              <span>more</span>
            </div>
          </>
        ) : (
          <>
            <div className="wm-label" style={{ marginBottom: 6 }}>{useChoropleth ? (flat ? 'DISTRICT COLOUR = NET STANCE' : 'DISTRICT COLOUR = NET STANCE · HEIGHT = COVERAGE') : 'COLOUR = STANCE'}</div>
            <div style={{ display: 'flex', gap: 14 }}>
              {[['supportive', 'supportive'], ['neutral', 'neutral'], ['hostile', 'critical']].map(([k, lbl]) => (
                <span key={k} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                  <i style={{ width: 9, height: 9, borderRadius: 9, background: `rgb(${TONE[k].join(',')})` }} />{lbl}
                </span>
              ))}
            </div>
          </>
        )}
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

      {dist && (
        <div style={{ position: 'absolute', top: 0, right: 0, bottom: 0, width: 'min(440px, 92vw)', background: 'var(--void-2,#0b0a10)', borderLeft: '1px solid var(--line)', overflowY: 'auto', boxShadow: '-20px 0 60px rgba(0,0,0,.5)', padding: '18px 18px 48px' }}>
          <button onClick={() => setDist(null)} style={{ position: 'absolute', top: 12, right: 14, background: 'transparent', border: 'none', color: 'var(--faint)', fontSize: '1.4rem', cursor: 'pointer', lineHeight: 1 }}>×</button>
          {dist.loading && <div style={{ color: 'var(--faint)', padding: '30px 0' }}>Opening district…</div>}
          {dist.file && !dist.file.found && (
            <div style={{ color: 'var(--faint)', padding: '20px 0' }}>
              {dist.file.error
                ? <>Couldn’t load this district — {dist.file.error}. <button onClick={() => openDistrict({ id: dist.id })} style={{ background: 'none', border: '1px solid var(--line)', color: 'var(--gold)', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', marginLeft: 6 }}>retry</button></>
                : 'No coverage on file for this district.'}
            </div>)}
          {dist.file && dist.file.found && (
            <>
              <div className="eyebrow" style={{ color: 'var(--gold)' }}>DISTRICT · {dist.file.state}</div>
              <h2 style={{ margin: '4px 0 2px', fontSize: '1.5rem' }}>{dist.file.name.toUpperCase()}</h2>
              <div className="sub" style={{ marginBottom: 12 }}>{dist.file.hq ? `HQ ${dist.file.hq} · ` : ''}{dist.file.window_days}d window</div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 8, marginBottom: 14 }}>
                {[['ARTICLES', dist.file.tiles.articles.toLocaleString()], ['ENTITIES', dist.file.tiles.entities], ['QUOTES', dist.file.tiles.quotes.toLocaleString()], ['NET', (dist.file.tiles.net > 0 ? '+' : '') + dist.file.tiles.net]].map(([k, v]) => (
                  <div key={k} style={{ background: 'var(--surface,#14110d)', borderRadius: 8, padding: '8px 4px', textAlign: 'center' }}>
                    <div style={{ fontSize: '0.55rem', color: 'var(--faint)', letterSpacing: '0.08em' }}>{k}</div><div style={{ fontSize: '1.02rem', fontWeight: 600 }}>{v}</div>
                  </div>))}
              </div>
              <div className="df-summary"><div className="df-stamp">RECENT ACTIVITY</div><p style={{ margin: '6px 0 0' }}>{dist.file.summary}</p></div>
              <DCard title="Standing"><DStance s={dist.file.standing} /></DCard>
              {dist.file.top_stories.length > 0 && <DCard title="Top stories">{dist.file.top_stories.map((s, i) => (
                <a key={i} href={s.url || '#'} target="_blank" rel="noreferrer" style={dRow}>
                  <span className={'df-recdot ' + s.tone} style={{ marginTop: 5 }} />
                  <span><span style={{ color: 'var(--ink)' }}>{s.headline}</span>{s.headline_en && <span className="en-gloss"><b>EN</b>{s.headline_en}</span>}<span style={{ display: 'block', fontFamily: 'var(--mono)', fontSize: '0.64rem', color: 'var(--faint)' }}>{s.source}</span></span>
                </a>))}</DCard>}
              {dist.file.entities.length > 0 && <DCard title="Who's in the news here">{dist.file.entities.map((e, i) => <span key={i} className="pill" style={{ marginRight: 6, marginBottom: 6, display: 'inline-block' }}>{e.name} · {e.n}</span>)}</DCard>}
              {dist.file.topics.length > 0 && <DCard title="Topics">{dist.file.topics.map((t, i) => <div key={i} style={dBar}><span>{t.label}</span><b>{t.value}</b></div>)}</DCard>}
              {dist.file.quotes.length > 0 && <DCard title="In the words">{dist.file.quotes.map((q, i) => (
                <div key={i} style={{ marginBottom: 8 }}><p style={{ margin: 0, fontSize: '0.85rem' }}>“{q.q}”</p>{q.q_en && <div className="en-gloss"><b>EN</b>{q.q_en}</div>}<span style={{ fontSize: '0.66rem', color: 'var(--faint)' }}>{q.who} · {q.src}</span></div>))}</DCard>}
              {dist.file.outlets.length > 0 && <DCard title="Who covers it">{dist.file.outlets.map((o, i) => { const net = Math.round(100 * (o.pos - o.neg) / ((o.pos + o.neg) || 1)); return <div key={i} style={dBar}><span>{o.name}</span><b style={{ color: net < 0 ? 'var(--hostile)' : 'var(--supportive)' }}>{net > 0 ? '+' : ''}{net}%</b></div>; })}</DCard>}
              <DCard title="Reach"><div style={{ fontSize: '0.8rem', color: 'var(--faint)' }}>English {dist.file.reach.en} · Telugu {dist.file.reach.te}</div></DCard>
              <DCard title="Full coverage">
                {dist.feed.map((a, i) => (
                  <a key={i} href={a.url || '#'} target="_blank" rel="noreferrer" style={dRow}>
                    <span style={{ flex: '0 0 52px', height: 34, borderRadius: 5, overflow: 'hidden', background: 'var(--surface-2,#1a1712)', display: 'grid', placeItems: 'center' }}>{a.thumbnail ? <img src={a.thumbnail} alt="" loading="lazy" style={{ width: '100%', height: '100%', objectFit: 'cover' }} /> : <i className={'df-recdot ' + a.tone} />}</span>
                    <span><span style={{ color: 'var(--ink)', fontSize: '0.82rem' }}>{a.headline}</span>{a.headline_en && <span className="en-gloss"><b>EN</b>{a.headline_en}</span>}<span style={{ display: 'block', fontFamily: 'var(--mono)', fontSize: '0.62rem', color: 'var(--faint)' }}>{a.source}</span></span>
                  </a>))}
                {dist.cursor && <button onClick={loadMoreD} disabled={dist.more} className="df-loadmore">{dist.more ? 'Loading…' : 'Load more'}</button>}
              </DCard>
            </>
          )}
        </div>
      )}

      {country && (
        <div style={{ position: 'absolute', top: 0, right: 0, bottom: 0, width: 'min(440px, 92vw)', background: 'var(--void-2,#0b0a10)', borderLeft: '1px solid var(--line)', overflowY: 'auto', boxShadow: '-20px 0 60px rgba(0,0,0,.5)', padding: '18px 18px 48px' }}>
          <button onClick={() => setCountry(null)} style={{ position: 'absolute', top: 12, right: 14, background: 'transparent', border: 'none', color: 'var(--faint)', fontSize: '1.4rem', cursor: 'pointer', lineHeight: 1 }}>×</button>
          {country.loading && <div style={{ color: 'var(--faint)', padding: '30px 0' }}>Opening {country.name}…</div>}
          {country.file && !country.file.found && (
            <div style={{ color: 'var(--faint)', padding: '20px 0' }}>
              {country.file.error
                ? <>Couldn’t load {country.name} — {country.file.error}. <button onClick={() => openCountry(country.iso, country.name)} style={{ background: 'none', border: '1px solid var(--line)', color: 'var(--gold)', borderRadius: 6, padding: '4px 10px', cursor: 'pointer', marginLeft: 6 }}>retry</button></>
                : 'No coverage on file for this country.'}
            </div>)}
          {country.file && country.file.found && (
            <>
              <div className="eyebrow" style={{ color: 'var(--gold)' }}>COUNTRY · {country.file.iso}</div>
              <h2 style={{ margin: '4px 0 2px', fontSize: '1.5rem' }}>{country.file.name}</h2>
              <div className="sub" style={{ marginBottom: 12 }}>{country.file.window_days}d window</div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 8, marginBottom: 14 }}>
                {[['STORIES', country.file.tiles.articles.toLocaleString()], ['OUTLETS', country.file.tiles.sources], ['QUOTES', country.file.tiles.quotes.toLocaleString()], ['NET', (country.file.tiles.net > 0 ? '+' : '') + country.file.tiles.net]].map(([k, v]) => (
                  <div key={k} style={{ background: 'var(--surface,#14110d)', borderRadius: 8, padding: '8px 4px', textAlign: 'center' }}>
                    <div style={{ fontSize: '0.55rem', color: 'var(--faint)', letterSpacing: '0.08em' }}>{k}</div><div style={{ fontSize: '1.02rem', fontWeight: 600 }}>{v}</div>
                  </div>))}
              </div>
              <div className="df-summary"><div className="df-stamp">RECENT ACTIVITY</div><p style={{ margin: '6px 0 0' }}>{country.file.summary}</p></div>
              <DCard title="Standing"><DStance s={country.file.standing} /></DCard>
              {country.file.top_stories.length > 0 && <DCard title="Top stories">{country.file.top_stories.map((s, i) => (
                <a key={i} href={s.url || '#'} target="_blank" rel="noreferrer" style={dRow}>
                  <span className={'df-recdot ' + s.tone} style={{ marginTop: 5 }} />
                  <span><span style={{ color: 'var(--ink)' }}>{s.headline}</span>{s.headline_en && <span className="en-gloss"><b>EN</b>{s.headline_en}</span>}<span style={{ display: 'block', fontFamily: 'var(--mono)', fontSize: '0.64rem', color: 'var(--faint)' }}>{s.source}</span></span>
                </a>))}</DCard>}
              {country.file.topics.length > 0 && <DCard title="Topics">{country.file.topics.map((t, i) => <div key={i} style={dBar}><span>{t.label}</span><b>{t.value}</b></div>)}</DCard>}
              {country.file.outlets.length > 0 && <DCard title="Who covers it">{country.file.outlets.map((o, i) => { const net = Math.round(100 * (o.pos - o.neg) / ((o.pos + o.neg) || 1)); return <div key={i} style={dBar}><span>{o.name}</span><b style={{ color: net < 0 ? 'var(--hostile)' : 'var(--supportive)' }}>{net > 0 ? '+' : ''}{net}%</b></div>; })}</DCard>}
              <DCard title="Full coverage">
                {country.feed.map((a, i) => (
                  <a key={i} href={a.url || '#'} target="_blank" rel="noreferrer" style={dRow}>
                    <span style={{ flex: '0 0 52px', height: 34, borderRadius: 5, overflow: 'hidden', background: 'var(--surface-2,#1a1712)', display: 'grid', placeItems: 'center' }}>{a.thumbnail ? <img src={a.thumbnail} alt="" loading="lazy" style={{ width: '100%', height: '100%', objectFit: 'cover' }} /> : <i className={'df-recdot ' + a.tone} />}</span>
                    <span><span style={{ color: 'var(--ink)', fontSize: '0.82rem' }}>{a.headline}</span>{a.headline_en && <span className="en-gloss"><b>EN</b>{a.headline_en}</span>}<span style={{ display: 'block', fontFamily: 'var(--mono)', fontSize: '0.62rem', color: 'var(--faint)' }}>{a.source}</span></span>
                  </a>))}
                {country.cursor && <button onClick={loadMoreC} disabled={country.more} className="df-loadmore">{country.more ? 'Loading…' : 'Load more'}</button>}
              </DCard>
            </>
          )}
        </div>
      )}
      </div>
      <LiveChannels scope={scope} stateCode={data && data.state_code} />
      {data && <MapSections data={data} scope={scope} onOpen={openDistrict} />}
    </div>
  );
}
