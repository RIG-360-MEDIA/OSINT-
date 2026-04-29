'use client'

/**
 * /admin — super_admin-only console.
 *
 * Lists every user with their role and page-grant set, with controls to:
 *   - toggle individual page grants (live-saved on blur)
 *   - promote / demote between user and super_admin
 *   - "View as" — opens an impersonation session and reloads to /brief
 *
 * All API calls are super_admin-gated server-side. This page also self-gates:
 * non-admins are redirected to /brief by middleware before reaching here, but
 * we still render a friendly fallback if they slip through (e.g. localhost
 * dev with middleware short-circuited).
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAccess, type PageSlug } from '@/lib/access'
import { createClient } from '@/lib/supabase/client'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000'

interface AdminUser {
  id: string
  email: string
  role: 'user' | 'super_admin'
  created_at: string | null
  allowed_pages: string[]
  entity_count: number
  has_profile: boolean
}

interface UsersPayload {
  users: AdminUser[]
  known_pages: string[]
}

async function authedFetch(input: RequestInfo, init?: RequestInit): Promise<Response> {
  const supabase = createClient()
  const { data } = await supabase.auth.getSession()
  if (!data.session) throw new Error('not signed in')
  return fetch(input, {
    ...init,
    headers: {
      ...(init?.headers ?? {}),
      Authorization: `Bearer ${data.session.access_token}`,
      'Content-Type': 'application/json',
    },
    credentials: 'include',
  })
}

export default function AdminPage() {
  const router = useRouter()
  const { access, loading: accessLoading } = useAccess()
  const [data, setData] = useState<UsersPayload | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busyUserId, setBusyUserId] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const r = await authedFetch(`${API_BASE}/api/admin/users`)
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      setData(await r.json())
    } catch (e) {
      setError(e instanceof Error ? e.message : 'failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!accessLoading && access?.role === 'super_admin') refresh()
  }, [access, accessLoading, refresh])

  const togglePage = async (user: AdminUser, slug: string, on: boolean) => {
    const next = on
      ? Array.from(new Set([...user.allowed_pages, slug]))
      : user.allowed_pages.filter((p) => p !== slug)
    setBusyUserId(user.id)
    try {
      const r = await authedFetch(`${API_BASE}/api/admin/users/${user.id}/pages`, {
        method: 'PUT',
        body: JSON.stringify({ pages: next }),
      })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'page update failed')
    } finally {
      setBusyUserId(null)
    }
  }

  const setRole = async (user: AdminUser, role: AdminUser['role']) => {
    if (role === user.role) return
    if (!confirm(`Set ${user.email}'s role to "${role}"?`)) return
    setBusyUserId(user.id)
    try {
      const r = await authedFetch(`${API_BASE}/api/admin/users/${user.id}/role`, {
        method: 'PUT',
        body: JSON.stringify({ role }),
      })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'role update failed')
    } finally {
      setBusyUserId(null)
    }
  }

  const impersonate = async (user: AdminUser) => {
    if (user.role === 'super_admin') {
      alert('Cannot impersonate another super_admin.')
      return
    }
    if (!confirm(`View the app as ${user.email}? You can exit anytime.`)) return
    setBusyUserId(user.id)
    try {
      const r = await authedFetch(`${API_BASE}/api/admin/impersonate/${user.id}`, {
        method: 'POST',
        body: JSON.stringify({ reason: null }),
      })
      if (!r.ok) {
        const detail = await r.json().catch(() => ({}))
        throw new Error(detail.detail ?? `HTTP ${r.status}`)
      }
      router.push('/brief')
      router.refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'impersonation failed')
      setBusyUserId(null)
    }
  }

  if (accessLoading) return <FullPageStatus message="Loading…" />
  if (!access) return <FullPageStatus message="Sign in required." />
  if (access.role !== 'super_admin') {
    return <FullPageStatus message="Super admin access required." />
  }

  return (
    <div style={{ padding: 32, maxWidth: 1200, margin: '0 auto' }}>
      <h1 style={{ fontSize: 24, fontWeight: 600, marginBottom: 8 }}>User Administration</h1>
      <p style={{ color: '#666', marginBottom: 24, fontSize: 14 }}>
        Toggle page access, change roles, or view the app as another user.
      </p>

      {error && (
        <div
          role="alert"
          style={{
            background: '#fee2e2',
            color: '#991b1b',
            padding: 12,
            borderRadius: 4,
            marginBottom: 16,
          }}
        >
          {error}
        </div>
      )}

      {loading || !data ? (
        <FullPageStatus message="Loading users…" inline />
      ) : (
        <UserTable
          data={data}
          busyUserId={busyUserId}
          onTogglePage={togglePage}
          onSetRole={setRole}
          onImpersonate={impersonate}
        />
      )}
    </div>
  )
}

interface UserTableProps {
  data: UsersPayload
  busyUserId: string | null
  onTogglePage: (u: AdminUser, slug: string, on: boolean) => void
  onSetRole: (u: AdminUser, role: AdminUser['role']) => void
  onImpersonate: (u: AdminUser) => void
}

function UserTable({
  data,
  busyUserId,
  onTogglePage,
  onSetRole,
  onImpersonate,
}: UserTableProps) {
  const { users, known_pages } = data
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
        <thead>
          <tr style={{ borderBottom: '2px solid #ddd', textAlign: 'left' }}>
            <th style={th}>Email</th>
            <th style={th}>Role</th>
            <th style={th}>Profile</th>
            <th style={th}>Entities</th>
            <th style={th}>Pages</th>
            <th style={th}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id} style={{ borderBottom: '1px solid #eee', verticalAlign: 'top' }}>
              <td style={td}>
                <div style={{ fontWeight: 500 }}>{u.email}</div>
                <div style={{ fontSize: 11, color: '#999' }}>{u.id}</div>
              </td>
              <td style={td}>
                <select
                  value={u.role}
                  onChange={(e) => onSetRole(u, e.target.value as AdminUser['role'])}
                  disabled={busyUserId === u.id}
                  style={{ padding: '4px 8px', fontSize: 12 }}
                >
                  <option value="user">user</option>
                  <option value="super_admin">super_admin</option>
                </select>
              </td>
              <td style={td}>{u.has_profile ? '✓' : '—'}</td>
              <td style={td}>{u.entity_count}</td>
              <td style={td}>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {known_pages.map((slug) => {
                    const on = u.allowed_pages.includes(slug)
                    return (
                      <label
                        key={slug}
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: 4,
                          padding: '2px 8px',
                          borderRadius: 3,
                          background: on ? '#d1fae5' : '#f3f4f6',
                          fontSize: 11,
                          cursor: busyUserId === u.id ? 'wait' : 'pointer',
                        }}
                      >
                        <input
                          type="checkbox"
                          checked={on}
                          disabled={busyUserId === u.id}
                          onChange={(e) => onTogglePage(u, slug, e.target.checked)}
                          style={{ margin: 0 }}
                        />
                        {slug}
                      </label>
                    )
                  })}
                </div>
              </td>
              <td style={td}>
                <button
                  type="button"
                  onClick={() => onImpersonate(u)}
                  disabled={busyUserId === u.id || u.role === 'super_admin'}
                  style={{
                    padding: '4px 12px',
                    fontSize: 12,
                    background: '#1f2937',
                    color: 'white',
                    border: 'none',
                    borderRadius: 3,
                    cursor: u.role === 'super_admin' ? 'not-allowed' : 'pointer',
                    opacity: u.role === 'super_admin' ? 0.4 : 1,
                  }}
                >
                  View as
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const th: React.CSSProperties = { padding: '10px 8px', fontSize: 12, fontWeight: 600 }
const td: React.CSSProperties = { padding: '10px 8px' }

function FullPageStatus({ message, inline }: { message: string; inline?: boolean }) {
  return (
    <div
      style={{
        minHeight: inline ? 200 : '60vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: '#666',
        fontSize: 14,
      }}
    >
      {message}
    </div>
  )
}
