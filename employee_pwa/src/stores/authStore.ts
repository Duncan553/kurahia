import { create } from 'zustand'

// Only what the JWT gives us + the username the user typed on the login form.
// No full_name on the backend User model — username is the display identity.
export interface AuthUser {
  id: string               // JWT `sub`
  username: string         // from login form
  role_level: number       // JWT `role_level` claim (owner=10, manager=5, staff=1)
  department: string | null // JWT `department` claim — drives tablet-aware nav
}

interface AuthState {
  user: AuthUser | null
  accessToken: string | null
  isAuthenticated: boolean
  setupToken: string | null  // short-lived token from requires_pin_setup flow
  setAuth: (user: AuthUser, accessToken: string) => void
  setSetupToken: (token: string) => void
  clearAuth: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  accessToken: null,
  isAuthenticated: false,
  setupToken: null,

  setAuth: (user, accessToken) =>
    set({ user, accessToken, isAuthenticated: true, setupToken: null }),

  setSetupToken: (setupToken) =>
    set({ setupToken }),

  clearAuth: () =>
    set({ user: null, accessToken: null, isAuthenticated: false, setupToken: null }),
}))
