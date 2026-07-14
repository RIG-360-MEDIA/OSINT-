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

// Keyword Intelligence nav entry intentionally removed (2026-07-07) — see
// App.jsx for why. Re-add only once it does real on-demand collection with
// verifiable evidence, not just reads of pre-stored data.
const ALL_NAV = [
  { k: 'Home', ic: 'home' },
  { k: 'War Room', ic: 'warroom' },
  { k: 'Analytics', ic: 'analytics' },
  { k: 'Dossier', ic: 'dossier' },
  { k: 'Map', ic: 'map' },
  { k: 'Dispatch', ic: 'dispatch' },
  { k: 'Ask', ic: 'ask' },
];

export default function Sidebar({ i, setI, onCollapse, effectiveRole, viewingAs, onExitImpersonation }) {
  const { me } = useMe();
  const email = me?.email || null;

  // Client users don't see the Ask nav item (now last).
  const NAV = effectiveRole === 'client' ? ALL_NAV.slice(0, 6) : ALL_NAV;

  return (
    <nav className="rail">
      <div className="brand"><span className="r">RIG</span><span className="o">OSINT</span>
        {onCollapse && <button className="rail-collapse" title="Collapse menu" onClick={onCollapse}>«</button>}
      </div>

      {/* Impersonation banner */}
      {viewingAs && (
        <div style={{
          margin: '0 0 8px', padding: '8px 10px', borderRadius: 8,
          background: 'var(--gold, #e9c46a)18',
          border: '1px solid var(--gold, #e9c46a)40',
          fontSize: '0.62rem', letterSpacing: '0.08em',
        }}>
          <div style={{ color: 'var(--gold, #e9c46a)', marginBottom: 4, fontFamily: 'var(--mono, monospace)' }}>
            VIEWING AS
          </div>
          <div style={{ color: 'var(--ink, #f8f5ef)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginBottom: 6 }}>
            {viewingAs.full_name || viewingAs.email}
          </div>
          <button
            onClick={onExitImpersonation}
            style={{
              width: '100%', padding: '4px 0', borderRadius: 5, border: '1px solid var(--gold, #e9c46a)60',
              background: 'transparent', color: 'var(--gold, #e9c46a)', cursor: 'pointer',
              fontSize: '0.6rem', letterSpacing: '0.12em', fontFamily: 'inherit',
            }}
          >
            ← EXIT
          </button>
        </div>
      )}

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
