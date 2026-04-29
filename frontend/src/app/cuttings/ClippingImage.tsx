'use client'

import { useEffect, useState } from 'react'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export function newspaperInitials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 3)
    .map(w => w[0]!.toUpperCase())
    .join('')
}

interface ClippingImageProps {
  clippingId: string
  token: string | null
  hasImage: boolean
  newspaperName: string
}

export function ClippingImage({
  clippingId, token, hasImage, newspaperName,
}: ClippingImageProps) {
  const [imgB64, setImgB64] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    if (!hasImage || !token) {
      setFailed(true)
      return
    }
    // FE-1: AbortController so closing the modal mid-fetch cancels the
    // in-flight request instead of silently downloading and discarding it.
    // Each card fires its own controller; closing the modal unmounts the
    // card which calls cleanup which aborts.
    const controller = new AbortController()
    ;(async () => {
      try {
        const r = await fetch(`${API_BASE}/api/clippings/${clippingId}/image`, {
          headers: { Authorization: `Bearer ${token}` },
          signal: controller.signal,
        })
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        const data = await r.json()
        if (data.image_b64) setImgB64(data.image_b64)
        else setFailed(true)
      } catch (error: unknown) {
        // Don't flip to "failed" on intentional aborts — the card is
        // unmounting; setting state would be a no-op anyway, but it's
        // also semantically wrong to call this a failure.
        if (error instanceof DOMException && error.name === 'AbortError') {
          return
        }
        setFailed(true)
      }
    })()
    return () => { controller.abort() }
  }, [clippingId, token, hasImage])

  if (imgB64) {
    return (
      <img
        src={`data:image/jpeg;base64,${imgB64}`}
        alt={`${newspaperName} clipping`}
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'cover',
          display: 'block',
          filter: 'sepia(0.06) contrast(1.02)',
        }}
      />
    )
  }

  return (
    <div
      style={{
        width: '100%',
        height: '100%',
        background: 'var(--rig-paper-2)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        color: 'var(--rig-ink-soft)',
        textAlign: 'center',
        padding: '12px',
      }}
    >
      <span
        style={{
          fontFamily: 'var(--font-serif)',
          fontStyle: 'italic',
          fontSize: '38px',
          color: 'var(--rig-gold)',
          letterSpacing: '0.04em',
        }}
      >
        {newspaperInitials(newspaperName)}
      </span>
      {failed ? (
        <span style={{ fontSize: '11px', marginTop: '6px', opacity: 0.6 }}>
          image unavailable
        </span>
      ) : null}
    </div>
  )
}
