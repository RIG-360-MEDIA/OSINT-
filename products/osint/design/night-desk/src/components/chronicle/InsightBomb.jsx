import { useEffect, useRef } from 'react';

const CONFIDENCE_ICONS = { high: '●', medium: '◑', low: '○' };

export default function InsightBomb({ insight, index = 0 }) {
  const ref = useRef(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          el.classList.add('visible');
          observer.unobserve(el);
        }
      },
      { threshold: 0.1, rootMargin: '0px 0px -30px 0px' }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const confidence = (insight.confidence || 'medium').toLowerCase();

  return (
    <div className="insight-bomb" ref={ref} style={{ transitionDelay: `${index * 80}ms` }}>
      <div className="ib-header">
        <span className="ib-icon">&#9889;</span>
        <span className="ib-type-label">Intelligence Finding</span>
      </div>

      <h3 className="ib-question">{insight.question}</h3>

      {insight.evidence && <p className="ib-evidence">{insight.evidence}</p>}
      {insight.inference && <p className="ib-inference">{insight.inference}</p>}

      <div className="ib-footer">
        <div className="ib-confidence">
          <span className={`ib-confidence-badge ${confidence}`}>
            {CONFIDENCE_ICONS[confidence] || '◑'} {confidence} confidence
          </span>
          {insight.confidence_reason && (
            <span className="ib-confidence-reason">{insight.confidence_reason}</span>
          )}
        </div>
        {insight.implication && <p className="ib-implication">{insight.implication}</p>}
      </div>
    </div>
  );
}
