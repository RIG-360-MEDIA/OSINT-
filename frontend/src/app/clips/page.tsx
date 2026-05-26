'use client'

/**
 * /clips — THE NEWSROOM (Phase 7).
 *
 * Replaces the previous transcript browser with a five-mode cinematic
 * intelligence interface. The five modes (WALL, STREAM, ECHO, DOSSIER,
 * BRIEF) live under backend/src/components/newsroom/ and are mounted
 * by NewsroomLayout. The URL stays /clips per the implementation
 * brief — page-access is gated by `require_page("clips")` server-side.
 *
 * Visual system: Onyx three-color palette (black, --onyx-red, bone)
 * defined in app/globals.css. Mode differentiation is via typography
 * weight, rule weight, and chip language — never hue.
 */

import { NewsroomLayout } from '@/components/newsroom/NewsroomLayout'
import { OnyxTopBar } from '@/components/coverage/OnyxTopBar'

export default function ClipsPage() {
  return (
    <>
      <OnyxTopBar />
      <div data-theme="onyx" style={{ paddingTop: 'var(--topbar-h)' }}>
        <NewsroomLayout />
      </div>
    </>
  )
}
