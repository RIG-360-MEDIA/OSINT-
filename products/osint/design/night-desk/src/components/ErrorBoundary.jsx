import { Component } from 'react';

// Catches render-time errors in the page subtree so one page's throw shows a
// graceful fallback instead of white-screening the whole app. Reset is keyed by
// the parent (e.g. <ErrorBoundary key={i}>) so switching pages clears the error.
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { failed: false };
  }

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div style={{ minHeight: '60vh', display: 'grid', placeItems: 'center',
        color: 'var(--faint, #8a8577)', fontFamily: 'var(--mono, monospace)' }}>
        <div style={{ textAlign: 'center', maxWidth: 420, padding: 28 }}>
          <div style={{ color: 'var(--gold, #c9a227)', letterSpacing: '0.14em', fontSize: '0.62rem', marginBottom: 10 }}>SOMETHING WENT WRONG</div>
          <p style={{ color: 'var(--ink)', fontSize: '0.92rem', lineHeight: 1.5, margin: '0 0 18px' }}>
            Something went wrong on this page. Try reloading.
          </p>
          <button type="button" onClick={() => window.location.reload()}
            style={{ padding: '8px 18px', borderRadius: 7, cursor: 'pointer', fontWeight: 600,
              fontSize: '0.78rem', letterSpacing: '0.08em',
              border: '1px solid var(--gold, #c9a227)', background: 'var(--gold, #c9a227)', color: '#0b0b0e' }}>
            Reload
          </button>
        </div>
      </div>
    );
  }
}
