import { useState, useEffect, useMemo } from 'react';
import { motion } from 'framer-motion';
import { Atmos, Spotlight } from './lib/ui';
import Sidebar from './components/Sidebar';
import CommandBar from './components/CommandBar';
import Ticker from './components/Ticker';
import ErrorBoundary from './components/ErrorBoundary';
import Home from './pages/Home';
import WarRoom from './pages/WarRoom';
import Analytics from './pages/Analytics';
import Dossier from './pages/Dossier';
import MapPage from './pages/MapPage';
import Dispatch from './pages/Dispatch';
import Ask from './pages/Ask';
import Login from './pages/Login';
import Landing from './pages/Landing';
import SuperUserDashboard from './pages/SuperUserDashboard';
import { useMe } from './lib/useMe';
import { ImpersonationProvider, useImpersonation } from './lib/ImpersonationContext';

const ALL_PAGES = [Home, WarRoom, Analytics, Dossier, MapPage, Dispatch, Ask];
const ALL_SLUGS = ['home', 'war-room', 'analytics', 'dossier', 'map', 'dispatch', 'ask'];
const BASE = (import.meta.env.BASE_URL || '/').replace(/\/$/, ''); // '' at root, '/desk' on subpath

// Client users cannot access the Ask/RAG page (index 6).
function pagesForRole(role) {
  if (role === 'client') {
    return { pages: ALL_PAGES.slice(0, 6), slugs: ALL_SLUGS.slice(0, 6) };
  }
  return { pages: ALL_PAGES, slugs: ALL_SLUGS };
}

function pathToIndex(pathname, slugs) {
  let p = pathname || '/';
  if (BASE && p.startsWith(BASE)) p = p.slice(BASE.length);
  const slug = p.replace(/^\/+/, '').split('/')[0] || 'home';
  const ix = slugs.indexOf(slug);
  return ix >= 0 ? ix : 0;
}
function indexToPath(ix, slugs) {
  return ix === 0 ? `${BASE}/` : `${BASE}/${slugs[ix]}`;
}

function AppShell() {
  const { me } = useMe();
  const { viewingAs, exitImpersonation } = useImpersonation();

  // Page access follows the VIEWER's own privilege, not the impersonated
  // target. While impersonating, `me` itself resolves to the target (the
  // X-Impersonate header is on /api/me too), so me.role would read 'client'.
  // `viewingAs` is the reliable signal that the real viewer is a super_user,
  // who "acts as admin" for any user → full page access (including Ask/RAG).
  // Data stays scoped to the target via the backend header.
  const effectiveRole = viewingAs ? 'admin' : (me?.role || 'client');
  const { pages: PAGES, slugs: SLUGS } = useMemo(() => pagesForRole(effectiveRole), [effectiveRole]);

  const [i, setIState] = useState(() => pathToIndex(window.location.pathname, SLUGS));
  // Switch page AND update the URL so each page has its own address + back/forward works.
  const setI = (ix) => {
    setIState(Math.min(ix, PAGES.length - 1));
    const target = indexToPath(Math.min(ix, PAGES.length - 1), SLUGS);
    if (window.location.pathname !== target) {
      window.history.pushState({ i: ix }, '', target);
    }
  };
  // Sidebar is collapsed by default (and remembers the user's choice). It stays
  // whatever it is across page switches since this state lives above the pages.
  const [railOpen, setRailOpen] = useState(() => { try { return localStorage.getItem('nd-rail') === 'open'; } catch { return false; } });
  const [theme, setTheme] = useState(() => { try { return localStorage.getItem('nd-theme') || 'light'; } catch { return 'light'; } });
  useEffect(() => { window.scrollTo({ top: 0, behavior: 'instant' }); }, [i]);
  useEffect(() => {
    const onPop = () => setIState(pathToIndex(window.location.pathname, SLUGS));
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, [SLUGS]);
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
        <Sidebar i={i} setI={setI} onCollapse={() => setRailOpen(false)}
                 effectiveRole={effectiveRole} slugs={SLUGS}
                 viewingAs={viewingAs} onExitImpersonation={exitImpersonation} />
        <main className="main">
          <CommandBar theme={theme} onToggle={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))} />
          <Ticker />
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: [0.16, 0.84, 0.28, 1] }}
          >
            <ErrorBoundary key={i}>
              <Page />
            </ErrorBoundary>
          </motion.div>
        </main>
      </div>
    </>
  );
}

// ── auth gate ──────────────────────────────────────────────────────────────
function AuthGate() {
  const { loading, me } = useMe();
  const { viewingAs } = useImpersonation();

  const [path, setPath] = useState(() => window.location.pathname);
  useEffect(() => {
    const onPop = () => setPath(window.location.pathname);
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);
  const stripped = BASE && path.startsWith(BASE) ? path.slice(BASE.length) : path;
  const onRoot = stripped === '' || stripped === '/';
  const enterApp = () => {
    const target = `${BASE}/home`;
    window.history.pushState({}, '', target);
    setPath(target);
  };

  if (loading) {
    return (
      <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center',
        background: 'var(--void, #07060a)', color: 'var(--faint, #8a8577)',
        fontFamily: 'var(--mono, monospace)', letterSpacing: '0.2em', fontSize: '0.8rem' }}>
        LOADING…
      </div>
    );
  }
  if (onRoot && !me) return <Landing onEnter={enterApp} />;
  if (!me) return <Login />;
  // Super-user with no active impersonation → user-picker dashboard
  if (me.role === 'super_user' && !viewingAs) return <SuperUserDashboard />;
  return <AppShell />;
}

export default function App() {
  return (
    <ImpersonationProvider>
      <AuthGate />
    </ImpersonationProvider>
  );
}
