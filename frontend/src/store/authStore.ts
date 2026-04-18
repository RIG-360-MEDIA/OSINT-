import { create } from 'zustand'

interface User {
  id: string
  email: string
}

interface AuthState {
  user: User | null
  hasProfile: boolean
  isLoading: boolean
  setUser: (user: User | null) => void
  setHasProfile: (v: boolean) => void
  setLoading: (v: boolean) => void
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  hasProfile: false,
  isLoading: true,
  setUser: (user) => set({ user }),
  setHasProfile: (hasProfile) => set({ hasProfile }),
  setLoading: (isLoading) => set({ isLoading }),
}))
