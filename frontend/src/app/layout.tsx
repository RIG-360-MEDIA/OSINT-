import type { Metadata } from 'next'
import './globals.css'
import { ThemeProvider, themeBootstrapScript } from '@/components/theme/ThemeProvider'

export const metadata: Metadata = {
  title: 'Rig Surveillance',
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
        <script dangerouslySetInnerHTML={{ __html: themeBootstrapScript }} />
      </head>
      <body>
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  )
}
