/**
 * 06 · See it work — elevated dark band, mint accent. Interactive demo.
 *
 * A search box that returns an intelligence card — sources, sentiment, reach,
 * and sample headlines — for any query. Results are HARDCODED for now (clearly
 * labelled a sample); the lookup is isolated in `resolve()` so swapping in a
 * real read-only endpoint later is a one-function change. Paired with the desk
 * mockup (drop the MacBook image at public/desk-macbook.png).
 */
import { useState, useRef, useEffect } from 'react';
import { Reveal } from '../Reveal';
import DeviceShot from '../DeviceShot';

const BASE = import.meta.env.BASE_URL || '/';
const compact = (n) => new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 }).format(n);
const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
const hash = (s) => { let h = 0; for (let i = 0; i < s.length; i += 1) h = (h * 31 + s.charCodeAt(i)) >>> 0; return h; };

const CHIPS = ['Iran', 'Narendra Modi', 'Tesla', 'Ukraine'];

const CANNED = {
  iran: { srcs: 41200, sent: -0.34, places: ['Iran', 'US', 'Israel', 'UK'], langs: ['fa', 'en', 'ar', 'he'], items: [
    { tag: 'BROADCAST', h: 'Nuclear talks stall as new sanctions are floated in Washington', s: 98 },
    { tag: 'NEWSPAPER', h: 'Tehran dailies and Western press split sharply on the same statement', s: 95 },
    { tag: 'SOCIAL', h: 'Protest footage spreading across Persian and Arabic channels', s: 92 },
  ] },
  'narendra modi': { srcs: 88600, sent: 0.12, places: ['India', 'US', 'UK', 'UAE'], langs: ['hi', 'en', 'te', 'ta'], items: [
    { tag: 'BROADCAST', h: 'Policy address leads Hindi and English bulletins nationwide', s: 97 },
    { tag: 'NEWSPAPER', h: 'Regional fronts diverge from national coverage on the same speech', s: 94 },
    { tag: 'GOV', h: 'Two ministries publish follow-up notifications within the hour', s: 90 },
  ] },
  tesla: { srcs: 53100, sent: 0.05, places: ['US', 'China', 'Germany', 'India'], langs: ['en', 'zh', 'de'], items: [
    { tag: 'BROADCAST', h: 'Delivery numbers move the pre-market; analysts split on guidance', s: 96 },
    { tag: 'SOCIAL', h: 'Owner sentiment cooling in two markets after price change', s: 91 },
    { tag: 'NEWSPAPER', h: 'Factory-expansion reports surface in regional German press', s: 88 },
  ] },
  ukraine: { srcs: 76400, sent: -0.41, places: ['Ukraine', 'Russia', 'US', 'Poland'], langs: ['uk', 'ru', 'en', 'pl'], items: [
    { tag: 'BROADCAST', h: 'Front-line shift reported across Ukrainian and Polish networks', s: 98 },
    { tag: 'GOV', h: 'Aid package detail published; figures vary by source', s: 93 },
    { tag: 'SOCIAL', h: 'Russian and Ukrainian channels carry opposing framings', s: 90 },
  ] },
};

function resolve(raw) {
  const q = raw.trim().toLowerCase();
  if (CANNED[q]) return CANNED[q];
  const seed = hash(q || 'x');
  const Q = cap(raw.trim() || 'your topic');
  return {
    srcs: 1800 + (seed % 9000),
    sent: ((seed % 100) / 100) * 0.6 - 0.3,
    places: ['Global', 'US', 'India', 'EU'],
    langs: ['en', 'hi', 'es'],
    items: [
      { tag: 'BROADCAST', h: `${Q} leads several evening bulletins as coverage rises`, s: 95 },
      { tag: 'NEWSPAPER', h: `Front pages split on ${Q} — mentions up sharply this week`, s: 92 },
      { tag: 'SOCIAL', h: `${Q} trending in two languages; sentiment turning`, s: 89 },
    ],
  };
}

const sentLabel = (v) => (v < -0.15 ? 'Negative' : v > 0.15 ? 'Positive' : 'Mixed');

export default function LiveDemo() {
  const [q, setQ] = useState('');
  const [status, setStatus] = useState('idle'); // idle | loading | done
  const [res, setRes] = useState(null);
  const timer = useRef(0);

  const run = (term) => {
    const value = term ?? q;
    if (!value.trim()) return;
    if (term !== undefined) setQ(term);
    setStatus('loading');
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => { setRes({ q: value.trim(), ...resolve(value) }); setStatus('done'); }, 720);
  };
  useEffect(() => () => window.clearTimeout(timer.current), []);

  return (
    <section id="s06" className="ndl-section ndl-s06" aria-labelledby="s06-h">
      <Reveal>
        <h2 id="s06-h" className="ndl-display">See it work — <em>right now.</em></h2>
      </Reveal>
      <Reveal delay={0.1}>
        <p className="ndl-lede ndl-s06-lede">
          Type a name, a company, a country — anything you would want watched. Here is a taste of what ROBIN surfaces.
        </p>
      </Reveal>

      <div className="ndl-demo-grid">
        <Reveal>
          <div>
            <form className="ndl-search" onSubmit={(e) => { e.preventDefault(); run(); }}>
              <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Try a person, brand, or place…" aria-label="Search" />
              <button type="submit">Surface it</button>
            </form>
            <div className="ndl-chips">
              {CHIPS.map((c) => <button key={c} type="button" className="ndl-chip" onClick={() => run(c)}>{c}</button>)}
            </div>

            <div className="ndl-result" aria-live="polite">
              {status === 'idle' && (
                <div className="ndl-result-skel"><i style={{ width: '40%' }} /><i style={{ width: '90%' }} /><i style={{ width: '75%' }} /><i style={{ width: '85%' }} /></div>
              )}
              {status === 'loading' && (
                <div className="ndl-result-skel"><i style={{ width: '52%' }} /><i style={{ width: '88%' }} /><i style={{ width: '70%' }} /><i style={{ width: '80%' }} /></div>
              )}
              {status === 'done' && res && (
                <>
                  <div className="ndl-result-top">
                    <span className="ndl-result-q">{res.q}</span>
                    <span className="ndl-result-srcs"><b>{compact(res.srcs)}</b> sources · 48h</span>
                  </div>
                  <div className="ndl-sent">
                    <div className="ndl-sent-row"><span>Media sentiment</span><span>{sentLabel(res.sent)}</span></div>
                    <div className="ndl-sent-bar"><i style={{ left: `${((res.sent + 1) / 2) * 100}%` }} /></div>
                  </div>
                  <div className="ndl-meta">
                    {res.places.map((p) => <span key={p}>{p}</span>)}
                    {res.langs.map((l) => <span key={l}>{l}</span>)}
                  </div>
                  {res.items.map((it) => (
                    <div className="ndl-result-item" key={it.h}>
                      <span className="t">{it.tag}</span><span className="h">{it.h}</span><span className="s">{it.s}</span>
                    </div>
                  ))}
                  <p className="ndl-result-foot">Demo sample — the live desk searches the full corpus and updates in real time.</p>
                </>
              )}
            </div>
          </div>
        </Reveal>

        <Reveal delay={0.15}>
          <div className="ndl-demo-shot">
            <DeviceShot src={`${BASE}desk-macbook.png`} tag="The desk" title="Your intelligence desk" />
          </div>
        </Reveal>
      </div>
    </section>
  );
}
