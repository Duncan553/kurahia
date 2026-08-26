import { Navigate, Outlet } from 'react-router-dom'
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
  const user = useAuthStore((s) => s.user)
  if (!user || user.role_level < minLevel) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-6 text-center">
        <EmptyState icon={<Icon name="alert" size={40} />} title="Access restricted" description="You don't have permission to view this page." />
      </div>
    )
  }
  return <Outlet />
}

export function RequireRole({ minLevel, children }: { minLevel: number; children: ReactNode }) {
  const user = useAuthStore((s) => s.user)
  if (!user || user.role_level < minLevel) return null
  return <>{children}</>
}
