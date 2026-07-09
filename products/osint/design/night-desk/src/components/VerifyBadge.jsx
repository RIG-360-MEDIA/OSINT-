import { useState, useEffect, useCallback, useRef } from 'react';
import './VerifyBadge.css';

// Isolated services — see api.rig360media.com/media/ (verify) and /geo/ (satellite).
const MEDIA_API = import.meta.env.VITE_MEDIA_API || 'https://api.rig360media.com/media';
const GEO_API = import.meta.env.VITE_GEO_API || 'https://api.rig360media.com/geo';

const META = {
  red: { cls: 'vb-neg', icon: '⚑', text: 'Recycled' },
  circulated: { cls: 'vb-gold', icon: '↻', text: 'Circulated' },
  clear: { cls: 'vb-pos', icon: '✓', text: 'Original' },
  unknown: { cls: 'vb-mut', icon: '?', text: 'Unverified' },
};

const isHttp = (u) => typeof u === 'string' && /^https?:\/\//.test(u);
const pad = (n) => String(n).padStart(2, '0');
const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

// Default corroboration windows: a recent ~100-day window vs the same season a year back.
function changeWindows() {
  const now = new Date();
  const day = 864e5;
  return {
    before: `${iso(new Date(now - 465 * day))}/${iso(new Date(now - 365 * day))}`,
    after: `${iso(new Date(now - 100 * day))}/${iso(now)}`,
  };
}

async function getJson(url, ms) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), ms || 42000);
  try {
    const res = await fetch(url, { signal: ctrl.signal });
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Image-verification chip for a dossier feed row, with two fusions in the popover:
 *  - satellite: an EXIF-GPS image pulls the /geo/ view of that spot + one-click change-detection.
 *  - corpus: where the same image already appears in our article corpus (perceptual-hash match).
 *
 * @param {{ imageUrl?: string }} props
 */
export default function VerifyBadge({ imageUrl }) {
  const [badge, setBadge] = useState(null);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const [corpus, setCorpus] = useState(null);
  const [chg, setChg] = useState(null);
  const [chgBusy, setChgBusy] = useState(false);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    setBadge(null);
    setOpen(false);
    setCorpus(null);
    setChg(null);
    if (isHttp(imageUrl)) {
      getJson(`${MEDIA_API}/badge?image_url=${encodeURIComponent(imageUrl)}&cached_only=1`, 12000)
        .then((d) => {
          if (alive.current && d && d.status && d.status !== 'none') setBadge(d);
        })
        .catch(() => {});
    }
    return () => {
      alive.current = false;
    };
  }, [imageUrl]);

  // Cross-check the corpus the first time the popover opens on a verified image.
  useEffect(() => {
    if (!open || !badge || corpus !== null) return;
    getJson(`${MEDIA_API}/corpus?image_url=${encodeURIComponent(imageUrl)}`, 30000)
      .then((d) => {
        if (alive.current) setCorpus(d || { match_count: 0, matches: [] });
      })
      .catch(() => alive.current && setCorpus({ match_count: 0, matches: [] }));
  }, [open, badge, corpus, imageUrl]);

  const run = useCallback(
    (e, fresh) => {
      e.preventDefault();
      e.stopPropagation();
      if (busy) return;
      setBusy(true);
      setOpen(false);
      setCorpus(null);
      setChg(null);
      getJson(`${MEDIA_API}/badge?image_url=${encodeURIComponent(imageUrl)}${fresh ? '&fresh=1' : ''}`)
        .then((d) => {
          if (alive.current) {
            setBadge(d);
            setOpen(true);
          }
        })
        .catch(() => {})
        .finally(() => alive.current && setBusy(false));
    },
    [imageUrl, busy],
  );

  const runChange = useCallback(
    (e, sat) => {
      e.preventDefault();
      e.stopPropagation();
      if (chgBusy) return;
      setChgBusy(true);
      setChg(null);
      const w = changeWindows();
      getJson(
        `${GEO_API}/change?lat=${sat.lat}&lon=${sat.lon}&before=${w.before}&after=${w.after}&km=6&mode=optical`,
        200000,
      )
        .then((d) => alive.current && setChg(d))
        .catch(() => alive.current && setChg({ error: 'change-detection failed' }))
        .finally(() => alive.current && setChgBusy(false));
    },
    [chgBusy],
  );

  const toggle = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setOpen((o) => !o);
  }, []);
  const swallow = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
  }, []);

  if (!isHttp(imageUrl)) return null;
  if (busy) return <span className="vb-pill vb-busy">checking…</span>;
  if (!badge) {
    return (
      <button type="button" className="vb-pill vb-idle" title="Verify where this image came from" onClick={(e) => run(e, false)}>
        {'⌕'} verify
      </button>
    );
  }

  const m = META[badge.status] || META.unknown;
  const sat = badge.satellite;
  return (
    <span className="vb-wrap">
      <button type="button" className={`vb-pill ${m.cls}`} onClick={toggle} title={badge.label}>
        <span className="vb-ic">{m.icon}</span>
        {m.text}
      </button>
      {open && (
        <span className="vb-pop" onClick={swallow}>
          <b className={m.cls}>{badge.label}</b>
          {Array.isArray(badge.factcheck_hits) && badge.factcheck_hits.length > 0 && (
            <span className="vb-row vb-neg">fact-check: {badge.factcheck_hits.join(', ')}</span>
          )}
          {typeof badge.sites === 'number' && <span className="vb-row">seen on {badge.sites} sites</span>}
          <span className="vb-row">
            {badge.has_exif ? 'EXIF present' : 'no EXIF (stripped)'}
            {badge.gps ? ` · ${badge.gps}` : ''}
          </span>
          {(badge.signals || []).map((s, i) => (
            <span className="vb-sig" key={i}>
              {s}
            </span>
          ))}

          {/* Fusion 1 — satellite corroboration of the EXIF-GPS spot */}
          {sat && (
            <span className="vb-sect">
              <span className="vb-h">🛰 satellite · {sat.place || `${sat.lat}, ${sat.lon}`}</span>
              <img className="vb-satimg" src={sat.imagery} alt="satellite" onError={(ev) => (ev.target.style.display = 'none')} />
              <span className="vb-satrow">
                <a href={sat.viewer} target="_blank" rel="noreferrer" className="vb-link">open geo desk ↗</a>
                <button type="button" className="vb-recheck" onClick={(e) => runChange(e, sat)} disabled={chgBusy}>
                  {chgBusy ? 'detecting change… (1–3 min)' : 'corroborate change ↻'}
                </button>
              </span>
              {chg && !chg.error && chg.summary && (
                <span className="vb-chg">
                  <span className="vb-row">
                    {chg.summary.before_date} → {chg.summary.after_date} · {chg.summary.changed_fraction_pct}% changed · Δbuilt-up {chg.summary.mean_dNDBI}
                  </span>
                  <span className="vb-chgimgs">
                    {['before_rgb', 'after_rgb', 'dNDBI'].map((k) =>
                      chg.images && chg.images[k] ? <img key={k} src={chg.images[k]} alt={k} title={k} /> : null,
                    )}
                  </span>
                </span>
              )}
              {chg && chg.error && <span className="vb-row vb-mut">{chg.error}</span>}
            </span>
          )}

          {/* Fusion 2 — same image already in our corpus */}
          {open && (
            <span className="vb-sect">
              <span className="vb-h">🔎 in corpus</span>
              {corpus === null && <span className="vb-row vb-mut">checking corpus…</span>}
              {corpus && corpus.match_count > 0 && (
                <>
                  <span className="vb-row">this image appears in {corpus.match_count} corpus {corpus.match_count === 1 ? 'story' : 'stories'}:</span>
                  {corpus.matches.slice(0, 6).map((mm) => (
                    <a key={mm.article_id} href={mm.url || '#'} target="_blank" rel="noreferrer" className="vb-cstory">
                      <span className="vb-cdist">{mm.distance === 0 ? 'exact' : `~${mm.distance}`}</span>
                      {(mm.title || mm.url || 'story').slice(0, 70)}
                    </a>
                  ))}
                </>
              )}
              {corpus && corpus.match_count === 0 && (
                <span className="vb-row vb-mut">not found in indexed corpus (index of {corpus.indexed_total ?? '…'} grows from use)</span>
              )}
            </span>
          )}

          <button type="button" className="vb-recheck" onClick={(e) => run(e, true)}>
            re-check {'↻'}
          </button>
          <span className="vb-note">signal, not proof</span>
        </span>
      )}
    </span>
  );
}
