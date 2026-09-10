import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

// Only what the JWT gives us + the username the user typed on the login form.
// No full_name on the backend User model — username is the display identity.
export interface AuthUser {
  id: string               // JWT `sub`
  username: string         // from login form
  role_level: number       // JWT `role_level` claim (owner=10, manager=5, staff=1)
  department: string | null // JWT `department` claim — drives tablet-aware nav
  // Whether this role may submit stock counts. It is a per-ROLE flag, not a
  // level: housekeeping (level 1) counts its own store and front desk (level 3)
  // does not, so no `level >= n` test can stand in for it. The stock-count
  // screen was gated `minLevel={5}`, which locked out every role whose job it
  // is — chef, bar lead, spa, housekeeping, grounds — while the backend was
  // happily allowing them. Optional so an old cached token stays readable.
  can_count_stock?: boolean
}

interface AuthState {
  user: AuthUser | null
  accessToken: string | null
  refreshToken: string | null  // long-lived token sent to /auth/refresh
  isAuthenticated: boolean
  setupToken: string | null  // short-lived token from requires_pin_setup flow
  setAuth: (user: AuthUser, accessToken: string, refreshToken: string) => void
  setSetupToken: (token: string) => void
  clearAuth: () => void
}

// Signing out must also drop every cached ANSWER, not just the token.
// The station tablet is shared: front desk signs out, a waiter signs in on the
// same device seconds later. React Query keys like ['roster','me'] carry no
// user identity, so the waiter was being served the front desk's cached roster
// — landing him on /front-desk/checkin and showing him a FRONT DESK badge.
// Each app registers its queryClient.clear() here at start-up, so every
// clearAuth() (sign-out button AND the 401 interceptor) wipes the cache too.
let cacheReset: (() => void) | null = null
export function setAuthCacheReset(fn: () => void) { cacheReset = fn }

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      setupToken: null,

      setAuth: (user, accessToken, refreshToken) =>
        set({ user, accessToken, refreshToken, isAuthenticated: true, setupToken: null }),

      setSetupToken: (setupToken) =>
        set({ setupToken }),

      clearAuth: () => {
        cacheReset?.()                       // drop the previous person's data
        set({ user: null, accessToken: null, refreshToken: null, isAuthenticated: false, setupToken: null })
      },
    }),
    { name: 'kurahia-auth', storage: createJSONStorage(() => sessionStorage) },
  ),
)
