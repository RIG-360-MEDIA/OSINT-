/**
 * 01 · What ROBIN does — void band, gold accent.
 *
 * Asymmetric two-column head (Rayvn-style): a short title-heading on the left,
 * the explaining in small copy on the right. No overline. Below, three
 * plain-spoken pillars give the section structure: read everything, weigh it
 * against you, verify before it surfaces.
 */
import { Reveal, RevealGroup, RevealItem } from '../Reveal';
import Parallax from '../Parallax';

const PILLARS = [
  { n: 'Read', h: 'Everything, everywhere', p: 'Newspapers, broadcast, social and government — across 180 countries and 40 languages, around the clock.' },
  { n: 'Weigh', h: 'Against your world', p: 'Every item is scored for how much it actually matters to the people, places and topics you watch.' },
  { n: 'Verify', h: 'Before it reaches you', p: 'Stories are cross-checked across independent sources, so what surfaces is signal — not rumour.' },
];

export default function WhatWeDo() {
  return (
    <section id="s01" className="ndl-section ndl-s01" aria-labelledby="s01-h">
      <div className="ndl-s01-head">
        <Reveal>
          <h2 id="s01-h" className="ndl-display">We read <em>the world.</em></h2>
        </Reveal>
        <Reveal delay={0.14}>
          <p className="ndl-lede">
            A million signals cross the desk every day. We read all of them, weigh each
            one against the things you care about, and hand you the few worth your time.
          </p>
        </Reveal>
      </div>

      <Parallax offset={36}>
        <RevealGroup className="ndl-pillars" stagger={0.14}>
          {PILLARS.map((p) => (
            <RevealItem key={p.n}>
              <div className="ndl-pillar">
                <span className="ndl-pillar-n">{p.n}</span>
                <h3 className="ndl-pillar-h">{p.h}</h3>
                <p className="ndl-pillar-p">{p.p}</p>
              </div>
            </RevealItem>
          ))}
        </RevealGroup>
      </Parallax>
    </section>
  );
}
