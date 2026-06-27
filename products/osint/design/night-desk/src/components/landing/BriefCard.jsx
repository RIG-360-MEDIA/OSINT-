/**
 * BriefCard — a small "your brief" product mockup used in section 03.
 *
 * The visible end of "a billion signals in, a handful out": a few items, each
 * with its pillar tag and a relevance score, under a live header and a footer
 * that states the reduction. Content is illustrative, not real reporting.
 */
const ITEMS = [
  { tag: 'BROADCAST', head: 'Rate decision lands — one more cut signalled before year-end', score: 98 },
  { tag: 'NEWSPAPER', head: 'Border talks resume after a six-week freeze', score: 96 },
  { tag: 'GOV', head: 'New export controls name three exposed suppliers', score: 94 },
];

export default function BriefCard() {
  return (
    <div className="ndl-brief" role="img" aria-label="Example daily brief: three items surfaced from a billion signals">
      <div className="ndl-brief-top">
        <span className="ndl-brief-title"><i className="ndl-brief-dot" aria-hidden="true" />Your brief</span>
        <span className="ndl-brief-day">Today</span>
      </div>
      {ITEMS.map((it) => (
        <div className="ndl-brief-item" key={it.head}>
          <span className="ndl-brief-tag">{it.tag}</span>
          <span className="ndl-brief-head">{it.head}</span>
          <span className="ndl-brief-score">{it.score}</span>
        </div>
      ))}
      <p className="ndl-brief-foot"><b>1,000,000,000+</b> scanned today · 3 surfaced for you</p>
    </div>
  );
}
