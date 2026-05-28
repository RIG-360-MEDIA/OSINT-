import LandingPage from './landing/page'

// Frontend reset (2026-05-19): root '/' renders the landing page directly.
// All previously-redirected destinations (/admin, /onboarding, /brief, /coverage)
// have been removed. Surviving routes are /, /landing, /login, /signup.
export default function Home() {
  return <LandingPage />
}
