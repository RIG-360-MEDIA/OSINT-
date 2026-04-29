import { createServerClient } from '@supabase/ssr'
import { NextResponse, type NextRequest } from 'next/server'

/**
 * Route gating middleware.
 *
 * Responsibilities:
 *   1. Auth — unauthenticated visitors to a protected path are redirected to /login.
 *   2. Onboarding — authenticated users without a profile or tracked entities
 *      are redirected to /onboarding (matches the "no entities = no content" rule).
 *   3. Page access — users who hit a path they don't have in their allowlist
 *      are bounced to /brief with ?denied=<slug>.
 *
 * Public routes (no auth required): /, /landing, /login, /signup, /onboarding,
 *   plus all Next internals and static assets.
 *
 * The page access check calls `${NEXT_PUBLIC_API_URL}/api/me/access` once per
 * navigation. The Supabase access token is read from the Supabase auth cookie
 * via @supabase/ssr — same source the rest of the app uses.
 */

// D-17 fix — middleware runs server-side inside the rig-frontend container,
// where `127.0.0.1:8000` is unreachable (the backend is in a sibling container).
// Use INTERNAL_API_URL when set so SSR/middleware can reach
// `http://rig-backend:8000`; the browser-side bundles still use
// NEXT_PUBLIC_API_URL because the host port-maps 8000 → backend container.
// Without this split the page-allowlist check silently bypasses on every
// request because the fetch throws and the catch falls through.
const API_BASE =
  process.env.INTERNAL_API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  'http://127.0.0.1:8000'

// Map URL path → page slug recognised by the backend.
// Order matters: longest-prefix first so '/brief/cm' resolves to 'brief'.
const ROUTE_TO_SLUG: ReadonlyArray<readonly [string, string]> = [
  ['/coverage',     'coverage'],
  ['/clips',        'clips'],
  ['/cuttings',     'cuttings'],
  ['/threads',      'threads'],
  ['/signals',      'signals'],
  ['/documents',    'documents'],
  ['/brief',        'brief'],       // covers /brief and /brief/cm
  ['/analyst',      'analyst'],
  ['/worldmonitor', 'worldmonitor'],
] as const

const PUBLIC_PREFIXES = ['/', '/landing', '/login', '/signup', '/onboarding']
// '/admin' is intentionally excluded from PUBLIC_PREFIXES — its access check
// happens server-side at the router level. We still let the page render so it
// can show a friendly "not authorized" state if needed.

interface AccessShape {
  role: 'user' | 'super_admin'
  allowed_pages: string[]
  has_profile: boolean
  has_entities: boolean
}

function pathToSlug(pathname: string): string | null {
  for (const [prefix, slug] of ROUTE_TO_SLUG) {
    if (pathname === prefix || pathname.startsWith(`${prefix}/`)) return slug
  }
  return null
}

function isPublic(pathname: string): boolean {
  return PUBLIC_PREFIXES.some(
    (p) => pathname === p || (p !== '/' && pathname.startsWith(`${p}/`)),
  )
}

export async function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl

  if (isPublic(pathname)) return NextResponse.next()

  // Build a Supabase server client backed by request cookies so we can read
  // the user's session without making the user re-auth.
  let supabaseResponse = NextResponse.next({ request: req })
  const supabase = createServerClient(
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

  const {
    data: { session },
  } = await supabase.auth.getSession()

  if (!session) {
    const url = req.nextUrl.clone()
    url.pathname = '/login'
    url.searchParams.set('next', pathname)
    return NextResponse.redirect(url)
  }

  const slug = pathToSlug(pathname)

  // Path is authenticated-only but not in our slug map (e.g. /admin).
  // Allow through — server enforces. Skip the /api/me/access round-trip.
  if (!slug) return supabaseResponse

  // Page-level gating: ask the backend for the user's effective access set.
  // We forward the impersonation cookie alongside the bearer token.
  let access: AccessShape | null = null
  try {
    const impersonate = req.cookies.get('rig_impersonate')?.value
    const cookieHeader = impersonate ? `rig_impersonate=${impersonate}` : ''
    const res = await fetch(`${API_BASE}/api/me/access`, {
      headers: {
        Authorization: `Bearer ${session.access_token}`,
        ...(cookieHeader ? { Cookie: cookieHeader } : {}),
      },
      cache: 'no-store',
    })
    if (res.ok) access = (await res.json()) as AccessShape
  } catch {
    // Backend down — fall through and allow render. Better to risk a brief
    // visual broken state than to lock the user out of the app entirely.
    return supabaseResponse
  }

  if (!access) return supabaseResponse

  // Onboarding gate — applies to non-admins only. Super_admins skip so they
  // can land on /admin or impersonate without being trapped on /onboarding.
  if (access.role !== 'super_admin' && (!access.has_profile || !access.has_entities)) {
    const url = req.nextUrl.clone()
    url.pathname = '/onboarding'
    return NextResponse.redirect(url)
  }

  // Page allowlist gate
  if (access.role !== 'super_admin' && !access.allowed_pages.includes(slug)) {
    const url = req.nextUrl.clone()
    url.pathname = '/brief'
    url.searchParams.set('denied', slug)
    return NextResponse.redirect(url)
  }

  return supabaseResponse
}

export const config = {
  // Run on every path *except* Next internals, static files, and the favicon.
  matcher: [
    '/((?!_next/static|_next/image|favicon.ico|api/|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)',
  ],
}
