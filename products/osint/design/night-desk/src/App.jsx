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

function AppShell() {
  const [i, setI] = useState(0);
  // Sidebar is collapsed by default (and remembers the user's choice). It stays
  // whatever it is across page switches since this state lives above the pages.
  const [railOpen, setRailOpen] = useState(() => { try { return localStorage.getItem('nd-rail') === 'open'; } catch { return false; } });
  const [theme, setTheme] = useState(() => { try { return localStorage.getItem('nd-theme') || 'dark'; } catch { return 'dark'; } });
  useEffect(() => { window.scrollTo({ top: 0, behavior: 'instant' }); }, [i]);
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
