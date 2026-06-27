/**
 * 06 · See it on the desk — the single LIGHT ("paper") band, teal accent.
 *
 * The page's one light beat, where the dark product shots pop against cream —
 * exactly why the light treatment was saved for here. Browser-framed mockups
 * (real screenshots drop straight into BrowserFrame via `src`).
 */
import { Reveal, RevealGroup, RevealItem } from '../Reveal';
import Parallax from '../Parallax';
import BrowserFrame from '../BrowserFrame';

const SHOTS = [
  { url: 'robin.osint / home', tag: 'Home', title: 'Today, across your world' },
  { url: 'robin.osint / war-room', tag: 'War Room', title: 'One event, every angle' },
  { url: 'robin.osint / chronicle', tag: 'Chronicle', title: 'A storyline, end to end', wide: true },
];

export default function Showcase() {
  return (
    <section id="s06" className="ndl-section ndl-s06 ndl-paper" aria-labelledby="s06-h">
      <Reveal>
        <h2 id="s06-h" className="ndl-display">See it on <em>the desk.</em></h2>
      </Reveal>
      <Reveal delay={0.1}>
        <p className="ndl-lede ndl-s06-lede">
          One calm surface for a loud world — coverage, conflicts and full storylines,
          scored to you and refreshed all day.
        </p>
      </Reveal>

      <Parallax offset={28}>
        <RevealGroup className="ndl-shots" stagger={0.12}>
          {SHOTS.map((s) => (
            <RevealItem key={s.tag} className={s.wide ? 'ndl-shots-wide' : undefined}>
              <BrowserFrame url={s.url} tag={s.tag} title={s.title} src={s.src} />
            </RevealItem>
          ))}
        </RevealGroup>
      </Parallax>
    </section>
  );
}
