/**
 * 07 · How it works + contact — void band, gold accent. The close.
 *
 * Rayvn's numbered-step layout (alternating text / laptop mockup), but our
 * process: discovery → build → live → tune. Laptop images drop into public/
 * as step-1..4.png (DeviceShot shows placeholders until then). Ends on a
 * contact block.
 */
import { Reveal } from '../Reveal';
import Parallax from '../Parallax';
import DeviceShot from '../DeviceShot';

const BASE = import.meta.env.BASE_URL || '/';

const STEPS = [
  { n: 'Step 1', h: 'Book a discovery call', img: 'step-1.png',
    p: 'We learn your world — the people, places and topics you need watched, how fast you need to know, and the form that fits how you work.' },
  { n: 'Step 2', h: 'We build your desk', img: 'step-2.png',
    p: 'Our team stands up an intelligence desk made for you: your entities, sources, languages, alert rules and brief schedule — configured, tuned and tested before you ever log in.' },
  { n: 'Step 3', h: 'Your brief goes live', img: 'step-3.png',
    p: 'Each morning, and the instant anything breaks, ROBIN delivers — to WhatsApp, email or Telegram, wherever you already are.' },
  { n: 'Step 4', h: 'We tune it with you', img: 'step-4.png',
    p: 'As your priorities shift, we sharpen the targets, sources and filters. The desk only gets better the longer you run it.' },
];

/**
 * @param {{ onEnter?: () => void }} props
 */
export default function CallToAction({ onEnter }) {
  const enter = () => onEnter && onEnter();
  return (
    <section id="s07" className="ndl-section ndl-s07" aria-labelledby="s07-h">
      <Reveal>
        <h2 id="s07-h" className="ndl-display">How we get <em>your desk live.</em></h2>
      </Reveal>
      <Reveal delay={0.1}>
        <p className="ndl-lede ndl-s07-lede">Tell us your world. We build it. You get the signal — and we keep it sharp.</p>
      </Reveal>

      <div className="ndl-psteps">
        {STEPS.map((s) => (
          <Reveal key={s.n}>
            <div className="ndl-pstep">
              <div className="ndl-pstep-text">
                <span className="ndl-pstep-n">{s.n}</span>
                <h3 className="ndl-pstep-h">{s.h}</h3>
                <p className="ndl-pstep-p">{s.p}</p>
              </div>
              <Parallax offset={26} className="ndl-pstep-shot">
                <DeviceShot src={`${BASE}${s.img}`} tag={s.n} title={s.h} />
              </Parallax>
            </div>
          </Reveal>
        ))}
      </div>

      <div className="ndl-contact">
        <h3 className="ndl-contact-h">Ready to see your world clearly?</h3>
        <div className="ndl-cta-row">
          <button type="button" className="ndl-cta-big" onClick={enter}>
            Book a call
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>
          </button>
          <button type="button" className="ndl-cta-ghost" onClick={enter}>Request a brief</button>
        </div>
      </div>
    </section>
  );
}
