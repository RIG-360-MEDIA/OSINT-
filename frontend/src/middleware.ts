import { createServerClient } from '@supabase/ssr'
import { NextResponse, type NextRequest } from 'next/server'

/**
 * Route gating middleware.
 *
 * FRONTEND RESET (2026-05-19): only /, /landing, /login, /signup survive.
 * All previous gated routes (/admin, /onboarding, /brief, /coverage, /clips,
 * /cuttings, /threads, /signals, /documents, /analyst, /worldmonitor) were
 * removed. The middleware now:
 *
 *   1. Lets all surviving public routes through.
 *   2. Bounces any other path to /login (preserving ?next for the eventual
 *      rebuild), under the assumption it's a stale link.
 *
 * The /api/me/access page-allowlist check is gone — there are no gated pages
 * to allowlist. When new app pages ship they will be re-added explicitly.
 */

// Surviving public routes — anything else is considered an unknown path.
// '/_next/*' and '/api/*' are excluded by the `matcher` config below so they
// don't need to be in this list.
const PUBLIC_PREFIXES = ['/', '/landing', '/login', '/signup'] as const

function isPublic(pathname: string): boolean {
  return PUBLIC_PREFIXES.some(
    (p) => pathname === p || (p !== '/' && pathname.startsWith(`${p}/`)),
  )
}

export async function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl

  // Surviving routes pass through unconditionally — they're all public during
  // the rebuild. Auth is handled at the page level (login form, etc.).
  if (isPublic(pathname)) {
    // We still construct the Supabase response shape so cookies refresh if a
    // session is present, matching @supabase/ssr's expected wiring.
    const supabaseResponse = NextResponse.next({ request: req })
    createServerClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL!,
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
      {
        cookies: {
          getAll() {
            return req.cookies.getAll()
          },
          setAll(cookiesToSet) {
            cookiesToSet.forEach(({ name, value, options }) => {
              supabaseResponse.cookies.set(name, value, options)
            })
          },
        },
      },
    )
    return supabaseResponse
  }

  // Unknown path — most likely a stale bookmark or hard-coded link to a
  // removed route. Send the visitor to /login as the canonical re-entry
  // point. (The login form redirects to '/' on success.)
  const url = req.nextUrl.clone()
  url.pathname = '/login'
  url.searchParams.set('next', pathname)
  return NextResponse.redirect(url)
}

export const config = {
  // Run on every path *except* Next internals, static files, and the favicon.
  matcher: [
    '/((?!_next/static|_next/image|favicon.ico|api/|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)',
  ],
}
