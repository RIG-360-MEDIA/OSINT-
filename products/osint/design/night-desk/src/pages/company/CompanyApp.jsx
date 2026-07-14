/* Corporate shell for the Windlass Company OSINT product.
   Owns its own left rail + top bar, applies the [data-product="company"]
   theme while mounted, and renders the active company page from internal
   state. Deliberately independent of the political AppShell so neither
   product can affect the other. */
import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import ErrorBoundary from '../../components/ErrorBoundary';
import { COMPANY_NAV, META } from '../../data/windlass';
import Overview from './Overview';
import Tenders from './Tenders';
import Markets from './Markets';
import Competitors from './Competitors';
import Social from './Social';
import Brand from './Brand';
import Trade from './Trade';
import Geo from './Geo';
import Grow from './Grow';
import Signals from './Signals';

const PAGES = { overview: Overview, tenders: Tenders, markets: Markets, competitors: Competitors,
  social: Social, brand: Brand, trade: Trade, geo: Geo, grow: Grow, signals: Signals };

const GROUP_ORDER = ['Intelligence', 'Presence', 'Context'];

export default function CompanyApp({ me, onSwitchProduct }) {
  const [slug, setSlug] = useState('overview');
  const [theme, setTheme] = useState(() => { try { return localStorage.getItem('co-theme') || 'dark'; } catch { return 'dark'; } });
  const toggleTheme = () => setTheme((t) => (t === 'dark' ? 'light' : 'dark'));

  // Apply the corporate product + theme only while this product is mounted.
  useEffect(() => {
    const html = document.documentElement;
    const prev = html.getAttribute('data-product');
    html.setAttribute('data-product', 'company');
    window.scrollTo({ top: 0 });
    return () => {
      if (prev) html.setAttribute('data-product', prev); else html.removeAttribute('data-product');
      html.removeAttribute('data-co-theme');
    };
  }, []);
  useEffect(() => {
    document.documentElement.setAttribute('data-co-theme', theme);
    try { localStorage.setItem('co-theme', theme); } catch { /* ignore */ }
  }, [theme]);
  useEffect(() => { window.scrollTo({ top: 0 }); }, [slug]);

  const Page = PAGES[slug] || Overview;
  const groups = GROUP_ORDER.map((g) => ({ g, items: COMPANY_NAV.filter((n) => n.group === g) }));

  return (
    <div className="co-app">
      <aside className="co-rail">
        <div className="co-brand">
          <div className="mk">W</div>
          <div>
            <div className="nm">Windlass</div>
            <div className="sub">Company OSINT</div>
          </div>
        </div>
        <nav className="co-nav">
          {groups.map(({ g, items }) => (
            <div key={g}>
              <div className="co-nav-lab">{g}</div>
              {items.map((n) => (
                <button key={n.slug} className={'co-navi' + (slug === n.slug ? ' on' : '')} onClick={() => setSlug(n.slug)}>
                  <span className="ic">{n.icon}</span>{n.label}
                </button>
              ))}
            </div>
          ))}
        </nav>
        <div className="co-rail-foot">
          <button className="co-navi" onClick={onSwitchProduct} style={{ padding: '8px 11px' }}>
            <span className="ic">⇄</span>Switch product
          </button>
          <div style={{ padding: '8px 11px 0', fontSize: 11 }}>Intelligence · {META.asOf}</div>
        </div>
      </aside>

      <div className="co-main">
        <header className="co-top">
          <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.15 }}>
            <span style={{ fontFamily: 'var(--co-grotesk)', fontSize: 14.5, fontWeight: 700, letterSpacing: '-.01em', color: 'var(--co-ink)' }}>Windlass Steelcrafts</span>
            <span className="co-mono" style={{ fontSize: 10.5, letterSpacing: '.2em', textTransform: 'uppercase', color: 'var(--co-muted)', marginTop: 2 }}>Company Intelligence</span>
          </div>
          <div className="co-live"><span className="dot" />Updated · {META.asOf}</div>
          <button className="co-theme-btn" onClick={toggleTheme} title={theme === 'dark' ? 'Switch to light' : 'Switch to dark'} aria-label="Toggle theme">
            {theme === 'dark' ? '☀' : '☾'}
          </button>
          <div className="co-chip-btn" title={me?.email}>{(me?.email || 'account')[0].toUpperCase()} · {me?.email?.split('@')[0]}</div>
        </header>
        <motion.div key={slug} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
          transition={{ duration: .35, ease: [0.16, 0.84, 0.28, 1] }}>
          <ErrorBoundary key={slug}>
            <Page go={setSlug} />
          </ErrorBoundary>
        </motion.div>
      </div>
    </div>
  );
}
