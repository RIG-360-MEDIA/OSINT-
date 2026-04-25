'use client'

import { createContext, useCallback, useContext, useEffect, useState } from 'react'

export type Theme = 'parchment' | 'night'

interface ThemeContextValue {
  theme: Theme
  setTheme: (theme: Theme) => void
  toggleTheme: () => void
}

const ThemeContext = createContext<ThemeContextValue | null>(null)

const STORAGE_KEY = 'rig-theme'
const DEFAULT_THEME: Theme = 'parchment'

function readInitialTheme(): Theme {
  if (typeof window === 'undefined') return DEFAULT_THEME
  const fromAttr = document.documentElement.dataset.theme
  if (fromAttr === 'parchment' || fromAttr === 'night') return fromAttr
  return DEFAULT_THEME
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(readInitialTheme)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try {
      window.localStorage.setItem(STORAGE_KEY, theme)
    } catch {
      /* storage may be blocked — non-critical */
    }
  }, [theme])

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next)
  }, [])

  const toggleTheme = useCallback(() => {
    setThemeState((prev) => (prev === 'parchment' ? 'night' : 'parchment'))
  }, [])

  return (
    <ThemeContext.Provider value={{ theme, setTheme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider')
  return ctx
}

/**
 * Inline script injected into <head> to set the theme attribute before
 * first paint. Prevents flash of wrong theme on hydration.
 */
export const themeBootstrapScript = `
(function(){try{
  var s=localStorage.getItem('${STORAGE_KEY}');
  var t=(s==='night'||s==='parchment')?s:'${DEFAULT_THEME}';
  document.documentElement.dataset.theme=t;
}catch(e){
  document.documentElement.dataset.theme='${DEFAULT_THEME}';
}})();`
