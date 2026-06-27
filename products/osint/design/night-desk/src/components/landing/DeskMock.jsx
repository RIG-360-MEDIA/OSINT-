/**
 * DeskMock — a stylised "your brief" card that anchors section 01 visually,
 * the way Rayvn anchors each section with a product/device mockup. Pure
 * CSS/markup (no screenshot dependency); the items are illustrative, not
 * live data. Swap for a real product screenshot later if desired.
 */
const ITEMS = [
  { tag: 'Geopolitics', c: 'ember', h: 'Iran signals openness to fresh nuclear talks', meta: '14 sources · 5 languages' },
  { tag: 'Your region', c: 'teal', h: 'Telangana cabinet expansion delayed again', meta: '9 sources · Telugu, English' },
  { tag: 'Markets', c: 'gold', h: 'Oil steadies as supply fears ease', meta: '22 sources · 6 languages' },
];

export default function DeskMock() {
  return (
    <div className="ndl-mock" aria-hidden="true">
      <div className="ndl-mock-glow" />
      <div className="ndl-mock-head">
        <span className="ndl-mock-title">Your brief</span>
        <span className="ndl-mock-date"><i className="ndl-mock-dot" />Tue · 24 Jun</span>
      </div>
      <ul className="ndl-mock-list">
        {ITEMS.map((it) => (
          <li key={it.h} className="ndl-mock-item">
            <span className="ndl-mock-tag" data-c={it.c}>{it.tag}</span>
            <span className="ndl-mock-h">{it.h}</span>
            <span className="ndl-mock-meta">{it.meta}</span>
          </li>
        ))}
      </ul>
      <div className="ndl-mock-more">+ 9 more matched your world today</div>
    </div>
  );
}
