'use client'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useState } from 'react'

import { ObservePersonaProvider } from './ObservePersonaContext'

export default function ObserveLayout({ children }: { children: React.ReactNode }) {
  // One QueryClient per browser session — keeps polled data in cache.
  const [qc] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { retry: 1, refetchOnWindowFocus: false },
        },
      })
  )
  return (
    <QueryClientProvider client={qc}>
      <ObservePersonaProvider>
        <div className="min-h-screen bg-[color:var(--bg)] text-[color:var(--fg)]">
          {children}
        </div>
      </ObservePersonaProvider>
    </QueryClientProvider>
  )
}
