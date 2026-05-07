// Production deployment override - render every page on demand.
// Required because pages like /brief call backend with auth context that
// is not available at build time. Set in root layout so it propagates to
// every child route. See infrastructure/DEPLOYMENT_NOTES.md.
export const dynamic = "force-dynamic"

import type { Metadata } from 'next'
import './globals.css'
import { ThemeProvider, themeBootstrapScript } from '@/components/theme/ThemeProvider'
import { ImpersonationBanner } from '@/components/ImpersonationBanner'

export const metadata: Metadata = {
  title: 'Robin OSINT',
  description: 'A reading room of one — filed by morning.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="parchment">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,500;0,600;0,700;1,400;1,500;1,600;1,700&family=DM+Mono:wght@400;500&family=DM+Sans:wght@400;500;600&display=swap"
          rel="stylesheet"
        />
        {/* Onyx theme fonts — used by /coverage and future migrated pages */}
        <link
          href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=JetBrains+Mono:wght@300;400;500;600&family=Instrument+Serif:ital@0;1&display=swap"
          rel="stylesheet"
        />
        <script dangerouslySetInnerHTML={{ __html: themeBootstrapScript }} />
      </head>
      <body>
        <ThemeProvider>
          <ImpersonationBanner />
          {children}
        </ThemeProvider>
      </body>
    </html>
  )
}
