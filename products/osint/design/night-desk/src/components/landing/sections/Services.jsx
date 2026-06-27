/**
 * 05 · What ROBIN does for you — void band, gold accent.
 *
 * Benefit-framed (not internal pillar names): six capability cards with real
 * detail so a visitor grasps the breadth, plus a closing line that signals
 * "and whatever else you need".
 */
import { Reveal, RevealGroup, RevealItem } from '../Reveal';

const CAPS = [
  {
    n: '01', h: 'Watch anyone, anything',
    p: 'Name the people, companies, agencies or topics that matter to you. ROBIN tracks every mention, move and statement across the web — automatically, every day — and builds a running picture of what they are doing and how they are being talked about.',
  },
  {
    n: '02', h: 'Your morning brief, your way',
    p: 'Before you wake, a brief written around your world: the few developments worth your attention, ranked and summarised. Delivered at the hour you choose, to the channel you live in — WhatsApp, email, Telegram, or all three.',
  },
  {
    n: '03', h: 'Alerts the moment it breaks',
    p: 'When something abrupt happens around the things you watch — a statement, a leak, a market move, a protest — you are notified within minutes, not after the news cycle has already moved on.',
  },
  {
    n: '04', h: 'ROBIN AI, your analyst',
    p: 'Not just data. Ask ROBIN anything about your space and it reads the whole corpus, explains what is happening and why, and tells you what it means for your business or decision — sourced, every time.',
  },
  {
    n: '05', h: 'Bias, sentiment & exposure',
    p: 'See which outlets lean for or against you, how sentiment is shifting week to week, which narratives are gaining ground, and exactly where your weak points and risks sit — across the whole landscape, not a sample.',
  },
  {
    n: '06', h: 'Local to global, every channel',
    p: 'From a small-town newspaper to YouTube, international wires, government filings and X — hundreds of source types in 40 languages, read natively. One desk covers it all.',
  },
];

export default function Services() {
  return (
    <section id="s05" className="ndl-section ndl-s05" aria-labelledby="s05-h">
      <Reveal>
        <h2 id="s05-h" className="ndl-display">Everything you would watch, <em>if you had the time.</em></h2>
      </Reveal>
      <Reveal delay={0.1}>
        <p className="ndl-lede ndl-s05-lede">
          ROBIN is built around you. A few of the things it does — and the list keeps growing:
        </p>
      </Reveal>

      <RevealGroup className="ndl-cap-grid" stagger={0.08}>
        {CAPS.map((c) => (
          <RevealItem key={c.n}>
            <div className="ndl-cap">
              <span className="ndl-cap-n">{c.n}</span>
              <h3 className="ndl-cap-h">{c.h}</h3>
              <p className="ndl-cap-p">{c.p}</p>
            </div>
          </RevealItem>
        ))}
      </RevealGroup>

      <Reveal delay={0.1}>
        <p className="ndl-cap-foot">
          And if there is something specific you need watched, measured or summarised — just ask.
          If it is anywhere in the world&apos;s information, ROBIN can bring it to you.
        </p>
      </Reveal>
    </section>
  );
}
