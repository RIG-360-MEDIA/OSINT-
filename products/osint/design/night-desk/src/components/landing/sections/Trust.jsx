/**
 * 04 · Why trust it — elevated dark band, mint accent.
 *
 * Trust isn't claimed, it's shown in the method: a short statement, then a
 * four-part "how it stays honest" strip (a spec-sheet row, distinct from the
 * cards and mockups elsewhere).
 */
import { Reveal, RevealGroup, RevealItem } from '../Reveal';
import Parallax from '../Parallax';

const METHOD = [
  { k: 'Corroborated', h: 'Cross-checked first', p: 'A story surfaces only once independent sources confirm it — never on a single post.' },
  { k: 'Native', h: '40 languages, read whole', p: 'Each source is read in its own language, not through a thin machine gloss.' },
  { k: 'Tagged', h: 'Stance, sentiment, entities', p: 'Every item is labelled — who, where, and which way it leans — so nothing hides.' },
  { k: 'Full spectrum', h: 'Sources that disagree', p: 'We pull from across the divide, so you see the argument, not an echo.' },
];

export default function Trust() {
  return (
    <section id="s04" className="ndl-section ndl-s04" aria-labelledby="s04-h">
      <Reveal>
        <h2 id="s04-h" className="ndl-display">Trust is in <em>the method.</em></h2>
      </Reveal>
      <Reveal delay={0.1}>
        <p className="ndl-lede ndl-s04-lede">
          ROBIN never asks you to take its word. Everything it surfaces is corroborated,
          labelled, and traceable straight back to the source.
        </p>
      </Reveal>

      <Parallax offset={30}>
        <RevealGroup className="ndl-method" stagger={0.1}>
          {METHOD.map((m) => (
            <RevealItem key={m.k}>
              <div className="ndl-method-item">
                <span className="ndl-method-k">{m.k}</span>
                <h3 className="ndl-method-h">{m.h}</h3>
                <p className="ndl-method-p">{m.p}</p>
              </div>
            </RevealItem>
          ))}
        </RevealGroup>
      </Parallax>
    </section>
  );
}
