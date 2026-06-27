/**
 * BrowserFrame — a light browser-chrome frame for the showcase (section 06).
 *
 * Pass `src` to drop in a real screenshot; without one it renders a tasteful
 * dark placeholder (tag + title + skeleton bars) so the layout reads as a
 * product shot even before real images exist.
 */
/**
 * @param {{ url: string, tag: string, title: string, src?: string }} props
 */
export default function BrowserFrame({ url, tag, title, src }) {
  return (
    <div className="ndl-frame">
      <div className="ndl-frame-bar" aria-hidden="true">
        <span className="ndl-frame-dot" /><span className="ndl-frame-dot" /><span className="ndl-frame-dot" />
        <span className="ndl-frame-url">{url}</span>
      </div>
      <div className="ndl-frame-body">
        {src ? (
          <img src={src} alt={title} loading="lazy" />
        ) : (
          <div className="ndl-frame-ph">
            <span className="ndl-frame-ph-tag">{tag}</span>
            <span className="ndl-frame-ph-title">{title}</span>
            <div className="ndl-frame-ph-bars">
              <i className="ndl-frame-ph-bar" /><i className="ndl-frame-ph-bar" /><i className="ndl-frame-ph-bar" />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
