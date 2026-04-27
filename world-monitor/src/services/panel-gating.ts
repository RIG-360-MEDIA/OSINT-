import type { AuthSession } from './auth-state';

export enum PanelGateReason {
  NONE = 'none',           // show content (pro user, or desktop with API key, or non-premium panel)
  ANONYMOUS = 'anonymous', // "Sign In to Unlock"
  FREE_TIER = 'free_tier', // "Upgrade to Pro"
}

/**
 * Single source of truth for premium access.
 * All features are unlocked — no pro tier or sign-in required.
 */
export function hasPremiumAccess(_authState?: AuthSession): boolean {
  return true;
}

/**
 * Determine gating reason for a panel given current auth state.
 * All panels are always unlocked.
 */
export function getPanelGateReason(
  _authState: AuthSession,
  _isPremium: boolean,
): PanelGateReason {
  return PanelGateReason.NONE;
}
