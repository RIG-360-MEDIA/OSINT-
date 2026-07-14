/* Latest Coverage — real news + YouTube media wall for the home page. */
import { COVERAGE } from '../../data/windlass';
import { Card, Pill } from './coUi';

const TOPIC = { Defence: 'info', Trade: 'warn', Ceremonial: 'good', Competitor: 'risk', Collector: 'flat', Film: 'info', Expo: 'good' };

/* pull the 11-char YouTube video id from a watch / youtu.be / embed URL */
const ytId = (url = '') => {
  const m = url.match(/[?&]v=([\w-]{11})/) || url.match(/youtu\.be\/([\w-]{11})/) || url.match(/\/embed\/([\w-]{11})/);
  return m ? m[1] : null;
};

export default function Coverage() {
  const { articles = [], videos = [], note } = COVERAGE;
  if (!articles.length && !videos.length) return null;
  return (
    <div className="co-grid co-g2" style={{ marginBottom: 18 }}>
      <Card title="Industry & market news" icon="▤" x={`${articles.length} stories`}>
        {articles.map((a, i) => (
          <a key={i} className="co-art" href={a.url} target="_blank" rel="noreferrer">
            <div className="amt">
              <Pill tone={TOPIC[a.topic] || 'flat'}>{a.topic}</Pill>
              <span>{a.source}{a.date ? ` · ${a.date}` : ''}</span>
            </div>
            <div className="ah">{a.title}</div>
            {a.blurb && <div className="ab">{a.blurb}</div>}
          </a>
        ))}
        {note && <div style={{ fontSize: 11.5, color: 'var(--co-faint)', marginTop: 14, lineHeight: 1.5 }}>{note}</div>}
      </Card>

      <Card title="On TV" icon="📺" x={`${videos.length} clips`}>
        {videos.length ? (
          <div className="co-vgrid">
            {videos.map((v, i) => (
              <a key={i} className="co-vid" href={v.url} target="_blank" rel="noreferrer">
                <div className="co-vthumb">
                  {ytId(v.url) && (
                    <img src={`https://img.youtube.com/vi/${ytId(v.url)}/hqdefault.jpg`} alt=""
                      loading="lazy" onError={(e) => { e.currentTarget.style.display = 'none'; }} />
                  )}
                  <span className="play">▶</span>
                  {v.dur && <span className="dur">{v.dur}</span>}
                </div>
                <div className="vt">{v.title}</div>
                {(v.channel || v.year) && <div className="vc">{v.channel}{v.channel && v.year ? ' · ' : ''}{v.year || ''}</div>}
              </a>
            ))}
          </div>
        ) : (
          <div style={{ fontSize: 13, color: 'var(--co-muted)' }}>Video wall populating…</div>
        )}
      </Card>
    </div>
  );
}
