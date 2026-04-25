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
    const res = await fetch(`${apiUrl}/api/onboarding/status`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: 'no-store',
    })
    if (res.ok) {
      const status = await res.json()
      redirect(status.has_profile ? '/brief' : '/onboarding')
    }
  } catch {
    // Fall through to landing on any error
  }

  return <LandingPage />
}
