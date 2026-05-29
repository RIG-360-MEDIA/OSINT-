'use client';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { authFetch } from '../../lib/supabase';
import { useMe } from '../../lib/useMe';
import '../auth.css';

export default function AdminPage() {
  const router = useRouter();
  const { loading, me } = useMe();
  const [orgs, setOrgs] = useState([]);
  const [invites, setInvites] = useState([]);
  const [orgForm, setOrgForm] = useState({ name: '', role_template: 'govt', notes: '' });
  const [inviteForm, setInviteForm] = useState({ email: '', org_id: '', role_template: 'govt', expires_in_days: 14, notes: '' });
  const [lastLink, setLastLink] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (loading) return;
    if (!me) { router.push('/login?next=/admin'); return; }
    if (!me.is_super_admin) { router.push('/brief'); return; }
    reload();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, me]);

  async function reload() {
    try {
      const o = await authFetch('/api/admin/orgs');
      const i = await authFetch('/api/admin/invites?include_consumed=true');
      setOrgs(o.orgs); setInvites(i.invites);
    } catch (e) { setError(String(e.message || e)); }
  }

  async function createOrg(e) {
    e.preventDefault();
    setError(null);
    try {
      await authFetch('/api/admin/orgs', { method: 'POST', body: JSON.stringify(orgForm) });
      setOrgForm({ name: '', role_template: 'govt', notes: '' });
      await reload();
    } catch (e) { setError(String(e.message || e)); }
  }

  async function createInvite(e) {
    e.preventDefault();
    setError(null);
    try {
      const result = await authFetch('/api/admin/invites', { method: 'POST', body: JSON.stringify({
        ...inviteForm,
        expires_in_days: parseInt(inviteForm.expires_in_days, 10),
      }) });
      setLastLink(result.link);
      setInviteForm({ ...inviteForm, email: '', notes: '' });
      await reload();
    } catch (e) { setError(String(e.message || e)); }
  }

  if (loading || !me) {
    return <main className="auth-shell"><div className="auth-card">Checking access…</div></main>;
  }
  if (!me.is_super_admin) {
    return <main className="auth-shell"><div className="auth-card">Redirecting…</div></main>;
  }

  return (
    <main className="admin-shell">
      <h1>Admin — Invites & Orgs</h1>
      <p className="admin-hint">Signed in as <strong>{me.email}</strong> (super-admin)</p>

      <section className="admin-card">
        <h2>Create org</h2>
        <form onSubmit={createOrg}>
          <input placeholder="Org name" required value={orgForm.name} onChange={e => setOrgForm({ ...orgForm, name: e.target.value })} />
          <select value={orgForm.role_template} onChange={e => setOrgForm({ ...orgForm, role_template: e.target.value })}>
            <option value="govt">Government</option>
            <option value="pr">PR firm</option>
            <option value="journalist">Journalist</option>
            <option value="academic">Academic</option>
            <option value="corporate">Corporate</option>
          </select>
          <input placeholder="Notes (optional)" value={orgForm.notes} onChange={e => setOrgForm({ ...orgForm, notes: e.target.value })} />
          <button>Create org</button>
        </form>
      </section>

      <section className="admin-card">
        <h2>Issue invite</h2>
        <form onSubmit={createInvite}>
          <input type="email" placeholder="Email" required value={inviteForm.email} onChange={e => setInviteForm({ ...inviteForm, email: e.target.value })} />
          <select required value={inviteForm.org_id} onChange={e => setInviteForm({ ...inviteForm, org_id: e.target.value })}>
            <option value="">— pick an org —</option>
            {orgs.map(o => <option key={o.id} value={o.id}>{o.name} ({o.role_template})</option>)}
          </select>
          <select value={inviteForm.role_template} onChange={e => setInviteForm({ ...inviteForm, role_template: e.target.value })}>
            <option value="govt">govt</option>
            <option value="pr">pr</option>
            <option value="journalist">journalist</option>
            <option value="academic">academic</option>
            <option value="corporate">corporate</option>
          </select>
          <input type="number" min="1" max="90" placeholder="Days" value={inviteForm.expires_in_days} onChange={e => setInviteForm({ ...inviteForm, expires_in_days: e.target.value })} />
          <input placeholder="Notes (optional)" value={inviteForm.notes} onChange={e => setInviteForm({ ...inviteForm, notes: e.target.value })} />
          <button>Issue invite</button>
        </form>
        {lastLink && (
          <div className="invite-link">
            <strong>Invite link — copy and email to the client:</strong>
            <input readOnly value={lastLink} onClick={e => e.target.select()} />
            <button type="button" onClick={() => navigator.clipboard.writeText(lastLink)}>Copy</button>
          </div>
        )}
      </section>

      <section className="admin-card">
        <h2>Existing invites ({invites.length})</h2>
        <table className="admin-table">
          <thead><tr><th>Email</th><th>Org</th><th>Role</th><th>Expires</th><th>Status</th><th>Notes</th></tr></thead>
          <tbody>
            {invites.map(i => (
              <tr key={i.token_hash}>
                <td>{i.email}</td>
                <td>{i.org_name || '—'}</td>
                <td>{i.role_template}</td>
                <td>{i.expires_at ? new Date(i.expires_at).toLocaleString() : '—'}</td>
                <td>{i.consumed_at ? `✓ ${new Date(i.consumed_at).toLocaleDateString()}` : 'pending'}</td>
                <td>{i.notes || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {error && <p className="auth-error">{error}</p>}
    </main>
  );
}
