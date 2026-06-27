/**
 * Landing — public, scrollable marketing page for ROBIN OSINT.
 *
 * Screen 1 is the hero (full-bleed space video, wordmark + nav, oversized
 * thin headline, interactive glass coverage card) — unchanged in spirit, now
 * the first 100vh panel of a scrolling page instead of a fixed overlay.
 *
 * Below it, sections 01..N answer the questions a homepage must answer, over
 * a fixed point-field that resolves from chaos to a constellation as you
 * scroll ("clarity from chaos", drawn). Styling lives in styles/landing.css,
 * scoped under .ndl-root so it never touches the app's design system.
 *
 * `onEnter` advances into the authenticated app.
 */
import { useRef, useEffect, useState } from 'react';
import { MotionConfig, motion, useMotionValue, useTransform, useReducedMotion } from 'framer-motion';
import '../styles/landing.css';

import HeroVideo from '../components/landing/HeroVideo';
import Stat from '../components/landing/Stat';
import WhatWeDo from '../components/landing/sections/WhatWeDo';
import WhoFor from '../components/landing/sections/WhoFor';
import WhyMatters from '../components/landing/sections/WhyMatters';
import Testimonials from '../components/landing/sections/Testimonials';
import Services from '../components/landing/sections/Services';
import LiveDemo from '../components/landing/sections/LiveDemo';
import CallToAction from '../components/landing/sections/CallToAction';

const NAV = ['Home', 'About', 'Coverage', 'News', 'Contact'];
const FOOTER_NAV = ['Coverage', 'Clips', 'Signals', 'Brief', 'Chronicle', 'Analyst'];
const BASE = import.meta.env.BASE_URL || '/';

// built sections, in order — drives the right-edge progress index
const SECTIONS = ['s01', 's02', 's03', 's04', 's05', 's06', 's07'];
const TOTAL = SECTIONS.length;

const scrollToId = (id) => {
  const el = document.getElementById(id);
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
};
const scrollTop = () => window.scrollTo({ top: 0, behavior: 'smooth' });

/**
 * @param {{ onEnter?: () => void }} props
 */
export default function Landing({ onEnter }) {
  const cardRef = useRef(/** @type {HTMLDivElement|null} */ (null));
  const [scrolled, setScrolled] = useState(false);
  const [active, setActive] = useState(-1); // -1 = hero

  // cinematic hero hand-off: text drifts up + fades, video scales in, as you
  // scroll out of the first screen. heroP (0→1 over the first viewport) is set
  // by the scroll listener below.
  const reduce = useReducedMotion();
  const heroP = useMotionValue(0);
  const heroTextY = useTransform(heroP, [0, 1], [0, -100]);
  const heroTextFade = useTransform(heroP, [0, 0.85], [1, 0]);
  const heroVidScale = useTransform(heroP, [0, 1], [1, 1.14]);

  const enter = (e) => {
    if (e) e.preventDefault();
    if (onEnter) onEnter();
  };

  // nav condenses + progress index + sticky CTA appear once we leave the hero;
  // same listener drives the hero hand-off progress (0→1 over one viewport).
  useEffect(() => {
    const onScroll = () => {
      const y = window.scrollY || 0;
      setScrolled(y > 40);
      heroP.set(Math.max(0, Math.min(1, y / (window.innerHeight || 1))));
    };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, [heroP]);

  // active-section tracking for the progress index
  useEffect(() => {
    const els = SECTIONS.map((id) => document.getElementById(id)).filter(Boolean);
    if (!els.length) return undefined;
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((en) => {
          if (en.isIntersecting) setActive(SECTIONS.indexOf(en.target.id));
        });
      },
      { rootMargin: '-45% 0px -45% 0px' },
    );
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, []);

  // cursor-driven 3D tilt + glare position on the coverage card
  const onCardMove = (e) => {
    const el = cardRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const px = (e.clientX - r.left) / r.width;
    const py = (e.clientY - r.top) / r.height;
    el.style.setProperty('--rx', `${(0.5 - py) * 7}deg`);
    el.style.setProperty('--ry', `${(px - 0.5) * 9}deg`);
    el.style.setProperty('--mx', `${px * 100}%`);
    el.style.setProperty('--my', `${py * 100}%`);
  };
  const onCardLeave = () => {
    const el = cardRef.current;
    if (!el) return;
    el.style.setProperty('--rx', '0deg');
    el.style.setProperty('--ry', '0deg');
  };

  const activeCount = active < 0 ? 0 : active + 1;

  return (
    <MotionConfig reducedMotion="user">
      <div className="ndl-root">
        {/* fixed top bar — condenses to a glass strip on scroll */}
        <header className={`ndl-top${scrolled ? ' is-scrolled' : ''}`}>
          <a className="ndl-wordmark" href={BASE} onClick={(e) => { e.preventDefault(); scrollTop(); }}>
            ROBIN OSINT
          </a>
          <nav className="ndl-nav">
            {NAV.map((item) => (
              <button key={item} type="button" onClick={enter} className="ndl-navlink">{item}</button>
            ))}
            <button
              type="button"
              onClick={enter}
              className="ndl-login-btn"
            >
              Log in
            </button>
          </nav>
        </header>

        {/* right-edge section index */}
        <div className={`ndl-progress${scrolled ? ' is-on' : ''}`} aria-hidden="true">
          {SECTIONS.map((id, i) => (
            <button
              key={id}
              type="button"
              className={`ndl-progress-tick${i === active ? ' is-active' : ''}`}
              onClick={() => scrollToId(id)}
              style={{ pointerEvents: 'auto', background: 'none', border: 0, cursor: 'pointer', padding: 0 }}
              aria-label={`Go to section ${i + 1}`}
            />
          ))}
          <span className="ndl-progress-count">
            {String(activeCount).padStart(2, '0')} / {String(TOTAL).padStart(2, '0')}
          </span>
        </div>

        {/* ── SCREEN 1: hero ─────────────────────────────────────────────── */}
        <section className="ndl-hero-screen">
          <motion.div className="ndl-video-wrap" style={{ scale: reduce ? 1 : heroVidScale }}>
            <HeroVideo />
          </motion.div>
          <div className="ndl-scrim" aria-hidden="true" />

          <motion.div className="ndl-hero" style={{ y: reduce ? 0 : heroTextY, opacity: reduce ? 1 : heroTextFade }}>
            <h1 className="ndl-headline">
              Clarity from chaos.<br />On demand.
            </h1>
            <button type="button" className="ndl-learn" onClick={() => scrollToId('s01')}>
              Learn more
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path d="M6 9l6 6 6-6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          </motion.div>

          <div className="ndl-card" ref={cardRef} onMouseMove={onCardMove} onMouseLeave={onCardLeave}>
            <div className="ndl-card-glare" aria-hidden="true" />
            <span className="ndl-card-live"><i className="ndl-card-dot" />Live global coverage</span>
            <div className="ndl-card-grid">
              <Stat target={1000000} label="sources" asCompact />
              <Stat target={180} label="countries" />
              <Stat target={40} label="languages" />
            </div>
            <p className="ndl-card-foot">
              Newspapers, broadcast, social &amp; government — surfaced, scored &amp; cross-checked in real time.
            </p>
          </div>
        </section>

        {/* ── scrolling sections ─────────────────────────────────────────── */}
        <main>
          <WhatWeDo />
          <WhoFor />
          <WhyMatters />
          <Testimonials />
          <Services />
          <LiveDemo />
          <CallToAction onEnter={onEnter} />
        </main>

        <footer className="ndl-footer">
          <div className="ndl-footer-in">
            <span className="ndl-footer-mark">ROBIN OSINT</span>
            <nav className="ndl-footer-nav">
              {FOOTER_NAV.map((item) => (
                <button key={item} type="button" className="ndl-footer-link" onClick={enter}>{item}</button>
              ))}
            </nav>
          </div>
          <div className="ndl-footer-fine">Clarity from chaos, on demand — intelligence from a million sources, scored to your world.</div>
        </footer>

        {/* persistent CTA — appears once past the hero */}
        <button type="button" className={`ndl-cta${scrolled ? ' is-on' : ''}`} onClick={enter}>
          Enter the desk
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M5 12h14M13 6l6 6-6 6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>
    </MotionConfig>
  );
}
