import { redirect } from 'next/navigation'
import { createClient } from '@/lib/supabase/server'
import LandingPage from './landing/page'

export default async function Home() {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()

  if (!user) {
    return <LandingPage />
  }

  const session = await supabase.auth.getSession()
  const token = session.data.session?.access_token

  try {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'
    // Use /api/me/access (role-aware) so super_admins land on /admin
    // instead of being trapped at /onboarding.
    const res = await fetch(`${apiUrl}/api/me/access`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: 'no-store',
    })
    if (res.ok) {
      const access = (await res.json()) as {
        role: 'user' | 'super_admin'
        has_profile: boolean
        has_entities: boolean
      }
      if (access.role === 'super_admin') {
        redirect('/admin')
      }
      redirect(access.has_profile && access.has_entities ? '/brief' : '/onboarding')
    }
  } catch {
    // Fall through to landing on any error
  }

  return <LandingPage />
}
