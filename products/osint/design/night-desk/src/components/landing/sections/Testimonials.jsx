/**
 * 04 · Why trust it — the light "paper" beat, testimonial carousel.
 *
 * Rayvn's trust anatomy: an editorial heading, a giant outline quote-mark, and
 * an avatar + quote that cross-fade through several voices with ‹ › controls
 * (auto-advancing). Placeholder people for now — real quotes before launch;
 * avatars fall back to monograms until photos are dropped in.
 */
import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Reveal } from '../Reveal';

const TESTIMONIALS = [
  { initials: 'JH', name: 'Placeholder Name', role: 'Comms Director, National party office', quote: 'ROBIN catches things my whole team used to miss — and it is on my phone before the first meeting of the day.' },
  { initials: 'AR', name: 'Placeholder Name', role: 'Founder, Fintech', quote: 'We replaced three monitoring tools and a frantic morning scramble with a single brief written around us.' },
  { initials: 'SM', name: 'Placeholder Name', role: 'Head of Strategy, Corporate', quote: 'The bias and sentiment read alone changed how we respond to coverage. We see the narrative forming, not after.' },
  { initials: 'KV', name: 'Placeholder Name', role: 'Analyst, Risk advisory', quote: 'It reads the local-language press we never could. That is the edge — the story before it crosses into English.' },
  { initials: 'DN', name: 'Placeholder Name', role: 'Regional political office', quote: 'I know what is happening across my region before anyone calls me about it. That has never been true before.' },
];

const FADE = { initial: { opacity: 0, y: 8 }, animate: { opacity: 1, y: 0 }, exit: { opacity: 0, y: -8 }, transition: { duration: 0.4, ease: [0.16, 0.84, 0.28, 1] } };

export default function Testimonials() {
  const [i, setI] = useState(0);
  const n = TESTIMONIALS.length;
  const go = (d) => setI((p) => (p + d + n) % n);

  useEffect(() => {
    const reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduce) return undefined;
    const t = window.setInterval(() => setI((p) => (p + 1) % n), 7000);
    return () => window.clearInterval(t);
  }, [n]);

  const t = TESTIMONIALS[i];

  return (
    <section id="s04" className="ndl-section ndl-s04 ndl-paper" aria-labelledby="s04-h">
      <div className="ndl-quote-top">
        <Reveal>
          <h2 id="s04-h" className="ndl-display">People rely on it to <em>not miss a thing.</em></h2>
        </Reveal>
        <span className="ndl-quote-glyph" aria-hidden="true">&ldquo;</span>
      </div>

      <div className="ndl-tm-wrap">
        <AnimatePresence mode="wait">
          <motion.div key={i} className="ndl-tm" {...FADE}>
            <div className="ndl-tm-side">
              <div className="ndl-tm-avatar">{t.src ? <img src={t.src} alt={t.name} /> : t.initials}</div>
              <div className="ndl-tm-name">{t.name}</div>
              <div className="ndl-tm-role">{t.role}</div>
            </div>
            <blockquote className="ndl-tm-quote">&ldquo;{t.quote}&rdquo;</blockquote>
          </motion.div>
        </AnimatePresence>
      </div>

      <div className="ndl-tm-arrows">
        <button type="button" className="ndl-tm-arrow" onClick={() => go(-1)} aria-label="Previous">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M15 6l-6 6 6 6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
        </button>
        <button type="button" className="ndl-tm-arrow" onClick={() => go(1)} aria-label="Next">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M9 6l6 6-6 6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
        </button>
      </div>
    </section>
  );
}
