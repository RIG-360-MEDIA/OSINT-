'use client'

import { createContext, useContext, useState, type ReactNode } from 'react'

export type Persona = 'developer' | 'auditor' | 'journalist'

interface Ctx {
  persona: Persona
  setPersona: (p: Persona) => void
}

const PersonaCtx = createContext<Ctx>({ persona: 'developer', setPersona: () => {} })

export function ObservePersonaProvider({ children }: { children: ReactNode }) {
  const [persona, setPersona] = useState<Persona>('developer')
  return <PersonaCtx.Provider value={{ persona, setPersona }}>{children}</PersonaCtx.Provider>
}

export function usePersona() {
  return useContext(PersonaCtx)
}
