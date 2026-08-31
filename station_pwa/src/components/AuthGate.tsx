import { Navigate, Outlet, useNavigate } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useAuthStore } from '../stores/authStore'
import { EmptyState, Icon } from '@shared'

// No clock-status redirect here (unlike employee_pwa's AuthGate) — station_pwa's
// login screen clocks the actor in as part of PIN login itself (see
// StationLoginScreen.tsx), so by the time anyone reaches a routed screen
// they're already clocked in. Auth-only gate.
export function AuthGate() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  if (!isAuthenticated) return <Navigate to="/login" replace />
  return <Outlet />
}

export function RoleGate({ minLevel }: { minLevel: number }) {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  if (!user || user.role_level < minLevel) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-6 text-center">
        {/* Same dead end employee_pwa already fixed: without actionLabel/onAction
            this screen offered no way out, which on a fixed tablet with no
            browser chrome means the only escape is signing out. */}
        <EmptyState
          icon={<Icon name="alert" size={40} />}
          title="Access restricted"
          description="You don't have permission to view this page."
          actionLabel="Go back"
          onAction={() => navigate(-1)}
        />
      </div>
    )
  }
  return <Outlet />
}

export function RequireRole({ minLevel, children }: { minLevel: number; children: ReactNode }) {
  const user = useAuthStore((s) => s.user)
  // Returning null here rendered a completely blank page — no header, no
  // explanation, nothing to tap. On a shared station tablet that reads as a
  // broken app, not as a permission boundary, and the person just stands
  // there. Every error in this system says what happened in plain English
  // (engineering invariant 5); a screen someone cannot open is no different.
  if (!user || user.role_level < minLevel) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 py-24 px-6 text-center">
        <p className="text-lg font-semibold text-ink-primary">This screen isn't yours to open</p>
        <p className="text-sm text-ink-tertiary max-w-sm">
          It needs a higher role than the account signed in at this station.
          Ask a manager to sign in here, or use a tool from the bar below.
        </p>
      </div>
    )
  }
  return <>{children}</>
}
