/**
 * Super-user user-picker dashboard.
 *
 * Shown instead of AppShell when the logged-in user has role=super_user
 * and has not selected a user to view as. Lists all accounts; clicking
 * any card enters impersonation mode and renders the full desk for that user.
 */
import { useState, useEffect } from 'react';
import { authFetch } from '../lib/supabase';
import { useImpersonation } from '../lib/ImpersonationContext';
import { useMe } from '../lib/useMe';
import { supabase } from '../lib/supabase';

const LOGIN_PATH = (import.meta.env.BASE_URL || '/');

async function logout() {
  try { await supabase.auth.signOut(); } catch { /* fall through */ }
  window.location.assign(LOGIN_PATH);
}

const ROLE_COLOR = {
  super_user: '#e9c46a',
  admin: '#06d6a0',
  client: '#8a8577',
};

const ROLE_LABEL = {
  super_user: 'SUPER',
  admin: 'ADMIN',
  client: 'CLIENT',
};

function RoleBadge({ role }) {
  return (
    <span style={{
      fontSize: '0.58rem', letterSpacing: '0.18em', fontFamily: 'var(--mono, monospace)',
      padding: '2px 7px', borderRadius: 4,
      background: ROLE_COLOR[role] + '22',
      color: ROLE_COLOR[role] || '#8a8577',
      border: `1px solid ${ROLE_COLOR[role] || '#8a8577'}44`,
    }}>
      {ROLE_LABEL[role] || role?.toUpperCase()}
    </span>
  );
}

function UserCard({ user, onSelect, patchingId, onRoleChange }) {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <div
      style={{
        padding: '18px 20px', borderRadius: 12, cursor: 'pointer',
        background: 'var(--void-2, #0b0a10)',
        border: '1px solid var(--line, rgba(255,255,255,.1))',
        transition: 'border-color 0.15s, box-shadow 0.15s',
        position: 'relative',
      }}
      onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--gold, #e9c46a)44'; e.currentTarget.style.boxShadow = '0 4px 20px rgba(0,0,0,.4)'; }}
      onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--line, rgba(255,255,255,.1))'; e.currentTarget.style.boxShadow = 'none'; }}
    >
      {/* Main click area — enter impersonation */}
      <div onClick={() => onSelect(user)} style={{ marginBottom: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
          <div style={{
            width: 36, height: 36, borderRadius: '50%', flexShrink: 0,
            background: 'var(--gold, #e9c46a)22',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: '1rem', color: 'var(--gold, #e9c46a)', fontWeight: 700,
          }}>
            {(user.full_name || user.email || '?')[0].toUpperCase()}
          </div>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontWeight: 600, fontSize: '0.92rem', color: 'var(--ink, #f8f5ef)', marginBottom: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {user.full_name || '—'}
            </div>
            <div style={{ fontSize: '0.75rem', color: 'var(--faint, #8a8577)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {user.email}
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 4 }}>
          <RoleBadge role={user.role} />
          {user.org_name && (
            <span style={{ fontSize: '0.62rem', color: 'var(--faint, #8a8577)', letterSpacing: '0.08em', padding: '2px 7px' }}>
              {user.org_name}
            </span>
          )}
          {!user.onboarded && (
            <span style={{ fontSize: '0.58rem', color: '#fb7185', letterSpacing: '0.1em', padding: '2px 7px', border: '1px solid #fb718540', borderRadius: 4 }}>
              NOT ONBOARDED
            </span>
          )}
        </div>
      </div>

      {/* Role changer (small gear button) */}
      <div style={{ position: 'absolute', top: 14, right: 14 }} onClick={e => e.stopPropagation()}>
        <button
          onClick={() => setMenuOpen(v => !v)}
          title="Change role"
          style={{
            background: 'transparent', border: '1px solid var(--line, rgba(255,255,255,.12))',
            borderRadius: 6, padding: '3px 7px', cursor: 'pointer',
            fontSize: '0.65rem', color: 'var(--faint, #8a8577)', fontFamily: 'inherit',
          }}
        >
          ⚙
        </button>
        {menuOpen && (
          <div style={{
            position: 'absolute', right: 0, top: '100%', marginTop: 4, zIndex: 10,
            background: 'var(--void-2, #0b0a10)', border: '1px solid var(--line, rgba(255,255,255,.15))',
            borderRadius: 8, overflow: 'hidden', minWidth: 110,
            boxShadow: '0 8px 30px rgba(0,0,0,.6)',
          }}>
            {['super_user', 'admin', 'client'].map(r => (
              <button
                key={r}
                disabled={patchingId === user.id || user.role === r}
                onClick={() => { onRoleChange(user.id, r); setMenuOpen(false); }}
                style={{
                  display: 'block', width: '100%', padding: '8px 14px',
                  background: user.role === r ? 'var(--gold, #e9c46a)15' : 'transparent',
                  border: 'none', cursor: user.role === r ? 'default' : 'pointer',
                  textAlign: 'left', color: user.role === r ? 'var(--gold, #e9c46a)' : 'var(--ink, #f8f5ef)',
                  fontSize: '0.75rem', fontFamily: 'inherit', letterSpacing: '0.06em',
                }}
              >
                {ROLE_LABEL[r]}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default function SuperUserDashboard() {
  const { me } = useMe();
  const { enterAs } = useImpersonation();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [patchingId, setPatchingId] = useState(null);
  const [search, setSearch] = useState('');

  useEffect(() => {
    authFetch('/api/admin/users')
      .then(d => { setUsers(d.users || []); setLoading(false); })
      .catch(e => { setError(e.message); setLoading(false); });
  }, []);

  async function handleRoleChange(uid, role) {
    setPatchingId(uid);
    try {
      const updated = await authFetch(`/api/admin/users/${uid}/role`, {
        method: 'PATCH',
        body: JSON.stringify({ role }),
      });
      setUsers(prev => prev.map(u => u.id === uid ? { ...u, role: updated.role } : u));
    } catch (e) {
      alert('Failed to update role: ' + e.message);
    } finally {
      setPatchingId(null);
    }
  }

  const filtered = users.filter(u =>
    !search || u.email?.toLowerCase().includes(search.toLowerCase()) ||
    u.full_name?.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div style={{
      minHeight: '100vh', background: 'var(--void, #07060a)',
      color: 'var(--ink, #f8f5ef)', padding: '40px 32px',
      fontFamily: 'var(--body, sans-serif)',
    }}>
      {/* Header */}
      <div style={{ maxWidth: 900, margin: '0 auto' }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 32 }}>
          <div>
            <div className="mono" style={{ fontSize: '0.62rem', letterSpacing: '0.3em', color: 'var(--faint, #8a8577)', marginBottom: 8 }}>
              RIG · OSINT · SUPER ADMIN
            </div>
            <h1 style={{ fontSize: '1.9rem', fontWeight: 700, margin: 0, letterSpacing: '-0.02em' }}>
              User Dashboard
            </h1>
            <p style={{ color: 'var(--faint, #8a8577)', fontSize: '0.85rem', marginTop: 6 }}>
              Signed in as <strong style={{ color: 'var(--gold, #e9c46a)' }}>{me?.email}</strong>
              {' · '}Click any user to view the desk as them.
            </p>
          </div>
          <button
            onClick={logout}
            style={{
              padding: '8px 16px', borderRadius: 8, border: '1px solid var(--gold, #e9c46a)',
              background: 'transparent', color: 'var(--gold, #e9c46a)',
              cursor: 'pointer', fontSize: '0.78rem', fontFamily: 'inherit', letterSpacing: '0.04em',
            }}
          >
            Log out
          </button>
        </div>

        {/* Search */}
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search by email or name…"
          style={{
            width: '100%', padding: '11px 16px', borderRadius: 8, marginBottom: 24,
            background: 'var(--void-2, #0b0a10)', color: 'var(--ink, #f8f5ef)',
            border: '1px solid var(--line, rgba(255,255,255,.12))',
            fontSize: '0.9rem', outline: 'none', boxSizing: 'border-box',
          }}
        />

        {/* Stats row */}
        <div style={{ display: 'flex', gap: 16, marginBottom: 28, flexWrap: 'wrap' }}>
          {[
            { label: 'Total users', val: users.length },
            { label: 'Super', val: users.filter(u => u.role === 'super_user').length, color: '#e9c46a' },
            { label: 'Admin', val: users.filter(u => u.role === 'admin').length, color: '#06d6a0' },
            { label: 'Client', val: users.filter(u => u.role === 'client').length, color: '#8a8577' },
          ].map(s => (
            <div key={s.label} style={{
              padding: '10px 18px', borderRadius: 8, background: 'var(--void-2, #0b0a10)',
              border: '1px solid var(--line, rgba(255,255,255,.08))',
            }}>
              <div style={{ fontSize: '1.4rem', fontWeight: 700, color: s.color || 'var(--ink)' }}>{s.val}</div>
              <div style={{ fontSize: '0.7rem', color: 'var(--faint, #8a8577)', letterSpacing: '0.08em' }}>{s.label}</div>
            </div>
          ))}
        </div>

        {/* User grid */}
        {loading && (
          <div style={{ color: 'var(--faint, #8a8577)', fontFamily: 'var(--mono, monospace)', letterSpacing: '0.2em', fontSize: '0.8rem', padding: 40, textAlign: 'center' }}>
            LOADING USERS…
          </div>
        )}
        {error && (
          <div style={{ color: '#fb7185', fontSize: '0.85rem', padding: 20, background: '#fb718510', borderRadius: 8, border: '1px solid #fb718530' }}>
            Failed to load users: {error}
          </div>
        )}
        {!loading && !error && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 14 }}>
            {filtered.map(user => (
              <UserCard
                key={user.id}
                user={user}
                onSelect={enterAs}
                patchingId={patchingId}
                onRoleChange={handleRoleChange}
              />
            ))}
            {filtered.length === 0 && (
              <div style={{ gridColumn: '1/-1', color: 'var(--faint, #8a8577)', textAlign: 'center', padding: 40 }}>
                No users match your search.
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
