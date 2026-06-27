import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

/**
 * Turn inline `[S3]` citation markers into a link form react-markdown can
 * render, so we can intercept them as clickable pills. Anything already a
 * real markdown link is left untouched.
 * @param {string} text
 * @returns {string}
 */
function tagCitations(text) {
  return text.replace(/\[S(\d+)\]/g, (_, n) => `[S${n}](#cite-S${n})`);
}

/**
 * Streaming-aware markdown answer. Renders `[S#]` as accent citation pills;
 * clicking one calls onCite('S#'). A blinking cursor trails while streaming.
 *
 * @param {{ text: string, streaming?: boolean, onCite?: (marker: string) => void }} props
 */
export default function AskAnswer({ text, streaming, onCite }) {
  const components = {
    a({ href, children, ...rest }) {
      if (href && href.startsWith('#cite-')) {
        const marker = href.slice('#cite-'.length);
        return (
          <span
            className="ask-cite"
            role="button"
            tabIndex={0}
            onClick={() => onCite && onCite(marker)}
            onKeyDown={(e) => { if (e.key === 'Enter') onCite && onCite(marker); }}
          >
            {children}
          </span>
        );
      }
      return <a href={href} target="_blank" rel="noopener noreferrer" {...rest}>{children}</a>;
    },
  };

  return (
    <div className="ask-answer">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {tagCitations(text || '')}
      </ReactMarkdown>
      {streaming ? <span className="ask-cursor" /> : null}
    </div>
  );
}
