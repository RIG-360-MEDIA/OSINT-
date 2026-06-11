import { motion } from 'framer-motion';
import { Icons } from '../lib/ui';
import { supabase } from '../lib/supabase';
import { useMe } from '../lib/useMe';

// Login lives at the base path (App.jsx renders <Login /> when there is no
// principal). Redirect there after sign-out so useMe re-runs with no session.
const LOGIN_PATH = (import.meta.env.BASE_URL || '/');

async function logout() {
  try {
    await supabase.auth.signOut();
  } catch {
    /* sign-out should never block the redirect; fall through */
  }
  window.location.assign(LOGIN_PATH);
}

const NAV = [
  { k: 'Home', ic: 'home' },
  { k: 'War Room', ic: 'warroom' },
  { k: 'Analytics', ic: 'analytics' },
  { k: 'Dossier', ic: 'dossier' },
  { k: 'Map', ic: 'map' },
  { k: 'Dispatch', ic: 'dispatch' },
];

export default function Sidebar({ i, setI, onCollapse }) {
  const { me } = useMe();
  const email = me?.email || null;
  return (
    <nav className="rail">
      <div className="brand"><span className="r">RIG</span><span className="o">OSINT</span>
        {onCollapse && <button className="rail-collapse" title="Collapse menu" onClick={onCollapse}>«</button>}
      </div>
      {NAV.map((n, ix) => (
        <div key={n.k} className={'navitem' + (ix === i ? ' on' : '')} onClick={() => setI(ix)}>
          {ix === i && <motion.span layoutId="navpill" className="pill" transition={{ type: 'spring', stiffness: 380, damping: 32 }} />}
          {Icons[n.ic]}
          <span>{n.k}</span>
          <span className="ix">{String(ix + 1).padStart(2, '0')}</span>
        </div>
      ))}
      <div className="railfoot">ROBIN-OSINT<br />chrome is silence<br />— data is light</div>
      <div style={{ marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: 8, paddingTop: 14 }}>
        {email && (
          <div
            title={email}
            style={{
              fontSize: '0.62rem', letterSpacing: '0.12em', textTransform: 'uppercase',
              color: 'var(--faint, #8a8577)', opacity: 0.78, padding: '0 4px',
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}
          >
            {email}
          </div>
        )}
        <button
          type="button"
          onClick={logout}
          title="Sign out"
          style={{
            display: 'flex', alignItems: 'center', gap: 8, width: 'auto',
            padding: '5px 8px', cursor: 'pointer', textAlign: 'left',
            fontSize: '0.7rem', letterSpacing: '0.04em', lineHeight: 1,
            color: 'var(--gold)', background: 'transparent',
            border: '1px solid var(--gold)', borderRadius: 8,
            fontFamily: 'inherit',
          }}
        >
          <span className="bk" style={{ display: 'inline-flex', alignItems: 'center', color: 'var(--gold)' }}>
            {Icons.logout || Icons.dispatch}
          </span>
          <span>Log out</span>
        </button>
      </div>
    </nav>
  );
}
