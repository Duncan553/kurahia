import { Navigate, Outlet } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'
import { EmptyState } from '@shared'

// Redirects unauthenticated users to /pin (daily auth method)
export function AuthGate() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  if (!isAuthenticated) return <Navigate to="/pin" replace />
  return <Outlet />
}

// Wraps a route that requires a minimum role level.
// Shows EmptyState (not a redirect) so the nav shell stays visible.
export function requireRole(minLevel: number) {
  return function RoleGate() {
    const user = useAuthStore((s) => s.user)
    if (!user || user.role_level < minLevel) {
      return (
        <EmptyState
          icon={
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none" aria-hidden="true">
              <rect x="12" y="22" width="24" height="18" rx="3" stroke="currentColor" strokeWidth="2" />
              <path d="M16 22v-6a8 8 0 0116 0v6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              <circle cx="24" cy="31" r="2" fill="currentColor" />
            </svg>
          }
          title="You don't have access to this area."
          description="Ask your manager if you think this is a mistake."
        />
      )
    }
    return <Outlet />
  }
}
