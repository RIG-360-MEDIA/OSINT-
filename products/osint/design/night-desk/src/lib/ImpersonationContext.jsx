/**
 * Impersonation context for super_user "view as" mode.
 *
 * When a super_user selects another user from the dashboard:
 *   - viewingAs = { id, email, full_name, role, org_name }
 *   - All authFetch calls automatically include X-Impersonate: <id>
 *   - The sidebar shows a banner + exit button
 *
 * When viewingAs is null the super_user sees their own view.
 */
import { createContext, useContext, useState, useCallback } from 'react';
import { setImpersonationTarget } from './supabase';

const Ctx = createContext({ viewingAs: null, enterAs: () => {}, exitImpersonation: () => {} });

export function ImpersonationProvider({ children }) {
  const [viewingAs, setViewingAs] = useState(null);

  const enterAs = useCallback((user) => {
    setViewingAs(user);
    setImpersonationTarget(user?.id ?? null);
  }, []);

  const exitImpersonation = useCallback(() => {
    setViewingAs(null);
    setImpersonationTarget(null);
  }, []);

  return (
    <Ctx.Provider value={{ viewingAs, enterAs, exitImpersonation }}>
      {children}
    </Ctx.Provider>
  );
}

export function useImpersonation() {
  return useContext(Ctx);
}
