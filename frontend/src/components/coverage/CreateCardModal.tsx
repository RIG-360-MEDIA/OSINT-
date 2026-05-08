/**
 * CreateCardModal — single-input modal for creating a tracker card.
 *
 * User types a free-text description of what to track. Backend's
 * card-create endpoint accepts label + user_intent + entity_refs/topics.
 * For v1, we send label + user_intent and an empty entity_refs list —
 * the daily LLM summary still reasons against user_intent + recent
 * articles matching the label as a search term.
 *
 * On success: triggers `onCreated()` so the parent can bump the
 * refresh tick and refetch the cards list.
 */

'use client'

import { useState } from 'react'
import { createClient } from '@/lib/supabase/client'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface Props {
  open: boolean
  onClose: () => void
  onCreated: () => void
}

export function CreateCardModal({ open, onClose, onCreated }: Props) {
  const [label, setLabel] = useState('')
  const [intent, setIntent] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!open) return null

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!label.trim() || submitting) return
    setError(null)
    setSubmitting(true)

    try {
      const supabase = createClient()
      const { data: { session } } = await supabase.auth.getSession()
      const token = session?.access_token
      if (!token) throw new Error('Sign in required')

      const res = await fetch(`${API_BASE}/api/coverage/cards`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          label: label.trim(),
          user_intent: intent.trim() || null,
          entity_refs: [],
          topic_filters: [],
          geo_filter: [],
        }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({})) as { detail?: string }
        throw new Error(body.detail || `Failed (${res.status})`)
      }
      setLabel('')
      setIntent('')
      onCreated()
      onClose()
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Unexpected error')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0, 0, 0, 0.7)',
        backdropFilter: 'blur(8px)',
        zIndex: 1000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '24px',
        animation: 'onyx-fade-up 0.3s ease both',
      }}
    >
      <form
        onSubmit={submit}
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'var(--onyx-bg)',
          border: '1px solid var(--onyx-red-hair)',
          padding: '40px',
          width: '100%',
          maxWidth: '560px',
          display: 'flex',
          flexDirection: 'column',
          gap: '24px',
        }}
      >
        <header>
          <div
            className="onyx-mono"
            style={{
              fontSize: '10px',
              letterSpacing: '0.42em',
              textTransform: 'uppercase',
              color: 'var(--onyx-dim)',
              marginBottom: '8px',
            }}
          >
            Track something new
          </div>
          <h2
            style={{
              fontFamily: 'var(--onyx-display)',
              fontWeight: 500,
              fontSize: '24px',
              color: 'var(--onyx-bone)',
              margin: 0,
            }}
          >
            Create a tracker card
          </h2>
        </header>

        <div>
          <Label>Label</Label>
          <input
            type="text"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="e.g. Bandi Sanjay activity"
            maxLength={120}
            autoFocus
            style={inputStyle()}
          />
        </div>

        <div>
          <Label>What do you want to track? (optional)</Label>
          <textarea
            value={intent}
            onChange={(e) => setIntent(e.target.value)}
            placeholder="e.g. His public statements, party-internal positioning, and any escalation around EWS reservation."
            rows={4}
            maxLength={500}
            style={{ ...inputStyle(), resize: 'vertical', fontFamily: 'var(--onyx-italic)', fontStyle: 'italic' }}
          />
        </div>

        {error && (
          <div
            className="onyx-mono"
            style={{
              fontSize: '10px',
              letterSpacing: '0.24em',
              color: 'var(--onyx-red)',
            }}
          >
            {error}
          </div>
        )}

        <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="onyx-mono"
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--onyx-dim)',
              fontSize: '10px',
              letterSpacing: '0.32em',
              textTransform: 'uppercase',
              padding: '12px 0',
              cursor: 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={submitting || !label.trim()}
            className="onyx-mono"
            style={{
              background: 'transparent',
              border: '1px solid var(--onyx-cyan)',
              color: submitting ? 'var(--onyx-dim)' : 'var(--onyx-cyan)',
              fontSize: '10px',
              letterSpacing: '0.32em',
              textTransform: 'uppercase',
              padding: '12px 24px',
              cursor: submitting || !label.trim() ? 'not-allowed' : 'pointer',
              transition: 'background 0.2s',
            }}
          >
            {submitting ? '…' : 'Create card →'}
          </button>
        </div>
      </form>
    </div>
  )
}

function inputStyle(): React.CSSProperties {
  return {
    width: '100%',
    background: 'transparent',
    border: '1px solid var(--onyx-rule-dim)',
    color: 'var(--onyx-bone)',
    fontFamily: 'var(--onyx-display)',
    fontSize: '15px',
    padding: '12px 14px',
    outline: 'none',
    transition: 'border-color 0.3s',
  }
}

const Label = ({ children }: { children: React.ReactNode }) => (
  <div
    className="onyx-mono"
    style={{
      fontSize: '9px',
      letterSpacing: '0.32em',
      textTransform: 'uppercase',
      color: 'var(--onyx-dim)',
      marginBottom: '8px',
    }}
  >
    {children}
  </div>
)
