/**
 * 02 · Who it serves — elevated dark band, teal accent.
 *
 * Separated from the void sections by a crisp top seam + teal glow, not by a
 * jarring light flash (the light beat is saved for the imagery showcase).
 * Heading leads, a short line frames it, then six substantial cards: a large
 * ghosted index numeral, a single-word title, and the one-line promise.
 */
import { Reveal, RevealGroup, RevealItem } from '../Reveal';
import Parallax from '../Parallax';

const AUDIENCES = [
  { n: '01', who: 'Companies', line: 'See what is said about your markets, rivals and reputation — in every country you operate in, the moment it is said.' },
  { n: '02', who: 'Governments', line: 'Track the narrative, the opposition, and how the world is covering you — at home and abroad, as it shifts.' },
  { n: '03', who: 'Newsrooms', line: 'Catch the story while it is breaking — anywhere, in any language — before it reaches the wire.' },
  { n: '04', who: 'Analysts', line: 'Follow one actor, one region or one fault line closely, without reading a thousand feeds to do it.' },
  { n: '05', who: 'Investors', line: 'Know what moved a market — or is about to — before the rest of the market notices.' },
  { n: '06', who: 'Watchdogs', line: 'Surface conflict, rights and policy signals from the places almost no one else is watching.' },
];

export default function WhoFor() {
  return (
    <section id="s02" className="ndl-section ndl-s02" aria-labelledby="s02-h">
      <Reveal>
        <h2 id="s02-h" className="ndl-display">
          Built for the ones who <em>can&apos;t miss.</em>
        </h2>
      </Reveal>
      <Reveal delay={0.1}>
        <p className="ndl-lede ndl-sub">
          Six kinds of people who cannot afford to look away — and what ROBIN does for each.
        </p>
      </Reveal>

      <Parallax offset={32}>
        <RevealGroup className="ndl-aud" stagger={0.09}>
          {AUDIENCES.map((a) => (
            <RevealItem key={a.n}>
              <div className="ndl-aud-card">
                <span className="ndl-aud-ghost" aria-hidden="true">{a.n}</span>
                <span className="ndl-aud-n">{a.n}</span>
                <h3 className="ndl-aud-who">{a.who}</h3>
                <p className="ndl-aud-line">{a.line}</p>
              </div>
            </RevealItem>
          ))}
        </RevealGroup>
      </Parallax>
    </section>
  );
}
