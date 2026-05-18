'use client'

/**
 * FRONTEND RESET (2026-05-19) — neutralized.
 *
 * The /admin route and its impersonation flow have been removed. This banner
 * is kept as a no-op export so layout.tsx can keep importing it without a
 * conditional, and so the new app rebuild can wire impersonation back in
 * (with refreshed UX) when /admin returns.
 */
export function ImpersonationBanner() {
  return null
}
