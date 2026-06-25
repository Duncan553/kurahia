import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

// Only what the JWT gives us + the username the user typed on the login form.
// No full_name on the backend User model — username is the display identity.
export interface AuthUser {
  id: string         // JWT `sub`
  username: string   // from login form
  role_level: number // JWT `role_level` claim (owner=10, manager=5, staff=1)
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

      clearAuth: () =>
        set({ user: null, accessToken: null, refreshToken: null, isAuthenticated: false, setupToken: null }),
    }),
    { name: 'kurahia-owner-auth', storage: createJSONStorage(() => sessionStorage) },
  ),
)
