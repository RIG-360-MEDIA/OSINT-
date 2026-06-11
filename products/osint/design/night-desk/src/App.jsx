import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Atmos, Spotlight } from './lib/ui';
import Sidebar from './components/Sidebar';
import CommandBar from './components/CommandBar';
import Ticker from './components/Ticker';
import Home from './pages/Home';
import WarRoom from './pages/WarRoom';
import Analytics from './pages/Analytics';
import Dossier from './pages/Dossier';
import MapPage from './pages/MapPage';
import Dispatch from './pages/Dispatch';
import Login from './pages/Login';
import { useMe } from './lib/useMe';

const PAGES = [Home, WarRoom, Analytics, Dossier, MapPage, Dispatch];
// URL slug per page (Home lives at the base). Keeps the address bar + back/forward
// in sync, and is base-path aware so it works at '/' (dev) or '/desk/' (subpath deploy).
const SLUGS = ['home', 'war-room', 'analytics', 'dossier', 'map', 'dispatch'];
const BASE = (import.meta.env.BASE_URL || '/').replace(/\/$/, ''); // '' at root, '/desk' on subpath

function pathToIndex(pathname) {
  let p = pathname || '/';
  if (BASE && p.startsWith(BASE)) p = p.slice(BASE.length);
  const slug = p.replace(/^\/+/, '').split('/')[0] || 'home';
  const ix = SLUGS.indexOf(slug);
  return ix >= 0 ? ix : 0;
}
function indexToPath(ix) {
  return ix === 0 ? `${BASE}/` : `${BASE}/${SLUGS[ix]}`;
}

function AppShell() {
  const [i, setIState] = useState(() => pathToIndex(window.location.pathname));
  // Switch page AND update the URL so each page has its own address + back/forward works.
  const setI = (ix) => {
    setIState(ix);
    if (window.location.pathname !== indexToPath(ix)) {
      window.history.pushState({ i: ix }, '', indexToPath(ix));
    }
  };
  // Sidebar is collapsed by default (and remembers the user's choice). It stays
  // whatever it is across page switches since this state lives above the pages.
  const [railOpen, setRailOpen] = useState(() => { try { return localStorage.getItem('nd-rail') === 'open'; } catch { return false; } });
  const [theme, setTheme] = useState(() => { try { return localStorage.getItem('nd-theme') || 'dark'; } catch { return 'dark'; } });
  useEffect(() => { window.scrollTo({ top: 0, behavior: 'instant' }); }, [i]);
  useEffect(() => {
    const onPop = () => setIState(pathToIndex(window.location.pathname));
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);
  useEffect(() => { try { localStorage.setItem('nd-rail', railOpen ? 'open' : 'closed'); } catch { /* ignore */ } }, [railOpen]);
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    try { localStorage.setItem('nd-theme', theme); } catch { /* ignore */ }
  }, [theme]);
  const Page = PAGES[i];
  return (
    <>
      <Atmos />
      <Spotlight />
      {!railOpen && (
        <button className="rail-toggle" title="Show menu" onClick={() => setRailOpen(true)}>☰</button>
      )}
      <div className={'shell' + (railOpen ? '' : ' rail-collapsed')}>
        <Sidebar i={i} setI={setI} onCollapse={() => setRailOpen(false)} />
        <main className="main">
          <CommandBar theme={theme} onToggle={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))} />
          <Ticker />
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: [0.16, 0.84, 0.28, 1] }}
          >
            <Page />
          </motion.div>
        </main>
      </div>
    </>
  );
}

// ── auth gate ──────────────────────────────────────────────────────────────
// Show the sign-in until a Supabase session resolves a principal via /api/me;
// then render the app shell. (Per-persona data wiring is layered on next.)
export default function App() {
  const { loading, me } = useMe();
  if (loading) {
    return (
      <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center',
        background: 'var(--void, #07060a)', color: 'var(--faint, #8a8577)',
        fontFamily: 'var(--mono, monospace)', letterSpacing: '0.2em', fontSize: '0.8rem' }}>
        LOADING…
      </div>
    );
  }
  if (!me) return <Login />;
  return <AppShell />;
}
