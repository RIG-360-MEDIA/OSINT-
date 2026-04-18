import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'RIG SURVEILLANCE',
  description: 'Personal Intelligence Platform',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{
        backgroundColor: '#F7F4EF',
        fontFamily: "'DM Sans', system-ui, sans-serif",
        color: '#1A1614',
      }}>
        {children}
      </body>
    </html>
  )
}
