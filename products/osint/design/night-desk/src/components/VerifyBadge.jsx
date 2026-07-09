import { useState, useEffect, useCallback, useRef } from 'react';
import './VerifyBadge.css';

// Isolated image-verification service (rigmedia) — see api.rig360media.com/media/.
const MEDIA_API = import.meta.env.VITE_MEDIA_API || 'https://api.rig360media.com/media';

const META = {
  red: { cls: 'vb-neg', icon: '⚑', text: 'Recycled' },        // ⚑
  circulated: { cls: 'vb-gold', icon: '↻', text: 'Circulated' }, // ↻
  clear: { cls: 'vb-pos', icon: '✓', text: 'Original' },       // ✓
  unknown: { cls: 'vb-mut', icon: '?', text: 'Unverified' },
};

async function fetchBadge(imageUrl, extra) {
  const url = `${MEDIA_API}/badge?image_url=${encodeURIComponent(imageUrl)}${extra || ''}`;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 42000);
  try {
    const res = await fetch(url, { signal: ctrl.signal });
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

const isHttp = (u) => typeof u === 'string' && /^https?:\/\//.test(u);

/**
 * Image-verification chip for a dossier feed row.
 * On mount it asks ONLY the cache (cheap, no reverse-search) — a badge auto-appears
 * for already-verified images. A never-verified image shows a "verify" affordance;
 * clicking it runs the real ~15 s search once, then the verdict is cached for everyone.
 *
 * @param {{ imageUrl?: string }} props
 */
export default function VerifyBadge({ imageUrl }) {
  const [badge, setBadge] = useState(null);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    setBadge(null);
    setOpen(false);
    if (isHttp(imageUrl)) {
      fetchBadge(imageUrl, '&cached_only=1')
        .then((d) => {
          if (alive.current && d && d.status && d.status !== 'none') setBadge(d);
        })
        .catch(() => {});
    }
    return () => {
      alive.current = false;
    };
  }, [imageUrl]);

  const run = useCallback(
    (e, fresh) => {
      e.preventDefault();
      e.stopPropagation();
      if (busy) return;
      setBusy(true);
      setOpen(false);
      fetchBadge(imageUrl, fresh ? '&fresh=1' : '')
        .then((d) => {
          if (alive.current) {
            setBadge(d);
            setOpen(true);
          }
        })
        .catch(() => {})
        .finally(() => {
          if (alive.current) setBusy(false);
        });
    },
    [imageUrl, busy],
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
          <button type="button" className="vb-recheck" onClick={(e) => run(e, true)}>
            re-check {'↻'}
          </button>
          <span className="vb-note">signal, not proof</span>
        </span>
      )}
    </span>
  );
}
