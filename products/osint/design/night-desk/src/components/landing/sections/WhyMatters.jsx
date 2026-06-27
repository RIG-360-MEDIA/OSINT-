/**
 * 03 · Why it matters — void band, ember accent.
 *
 * Asymmetric (Rayvn-style): the VIP statement + copy on the left, a "Your
 * brief" product mockup on the right that shows the billion-to-few reduction
 * concretely — a handful surfaced from everything ROBIN read today.
 */
import { Reveal } from '../Reveal';
import Parallax from '../Parallax';
import SignalFunnel from '../SignalFunnel';

export default function WhyMatters() {
  return (
    <section id="s03" className="ndl-section ndl-s03" aria-labelledby="s03-h">
      <div className="ndl-s03-grid">
        <div>
          <Reveal>
            <h2 id="s03-h" className="ndl-display">
              Your attention is <em>the asset.</em>
            </h2>
          </Reveal>
          <Reveal delay={0.12}>
            <p className="ndl-lede ndl-s03-lede">
              A billion things are said every day. You are the person whose decisions move
              markets, mandates and headlines — you cannot afford to miss the one signal
              that matters, or lose an hour to the ninety-nine that don&apos;t. ROBIN reads
              all of it and brings only what is worthy of you. The noise never reaches your
              desk.
            </p>
          </Reveal>
        </div>

        <Parallax offset={48}>
          <Reveal delay={0.2}>
            <div className="ndl-funnel">
              <span className="ndl-funnel-cap ndl-funnel-top">1,000,000,000+ signals today</span>
              <SignalFunnel />
              <span className="ndl-funnel-cap ndl-funnel-foot"><b>The few</b> — for you</span>
            </div>
          </Reveal>
        </Parallax>
      </div>
    </section>
  );
}
