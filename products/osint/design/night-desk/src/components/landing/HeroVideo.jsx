/**
 * HeroVideo — two stacked <video> layers that crossfade at the loop seam,
 * so the clip's end-frame ≠ start-frame discontinuity dissolves away and the
 * background reads as continuous animation rather than a hard-cutting loop.
 */
import { useRef, useEffect } from 'react';

const BASE = import.meta.env.BASE_URL || '/';
const VIDEO_SRC = `${BASE}hero-space.mp4`;
const FADE = 1.1; // seconds of crossfade overlap at the loop seam

export default function HeroVideo() {
  const aRef = useRef(/** @type {HTMLVideoElement|null} */ (null));
  const bRef = useRef(/** @type {HTMLVideoElement|null} */ (null));

  useEffect(() => {
    const a = aRef.current;
    const b = bRef.current;
    if (!a || !b) return;

    let active = a;
    let idle = b;
    a.style.opacity = '1';
    b.style.opacity = '0';
    a.play().catch(() => {});

    const onTime = (e) => {
      const v = e.target;
      if (v !== active || !v.duration) return;
      if (v.currentTime >= v.duration - FADE) {
        const finished = active;
        idle.currentTime = 0;
        idle.play().catch(() => {});
        idle.style.opacity = '1';
        finished.style.opacity = '0';
        active = idle;
        idle = finished;
        window.setTimeout(() => { try { finished.pause(); } catch { /* noop */ } }, FADE * 1000 + 80);
      }
    };

    a.addEventListener('timeupdate', onTime);
    b.addEventListener('timeupdate', onTime);
    return () => {
      a.removeEventListener('timeupdate', onTime);
      b.removeEventListener('timeupdate', onTime);
    };
  }, []);

  return (
    <>
      <video ref={aRef} className="ndl-video" src={VIDEO_SRC} muted playsInline preload="auto" aria-hidden="true" />
      <video ref={bRef} className="ndl-video" src={VIDEO_SRC} muted playsInline preload="auto" aria-hidden="true" />
    </>
  );
}
