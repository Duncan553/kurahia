import { Navigate, Outlet, useNavigate } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useAuthStore } from '../stores/authStore'
import { EmptyState } from '@shared'

export function AuthGate() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  if (!isAuthenticated) return <Navigate to="/pin" replace />
  return <Outlet />
}

// Role gate for nested routes — shows EmptyState (not redirect) so sidebar stays.
export function RoleGate({ minLevel }: { minLevel: number }) {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  if (!user || user.role_level < minLevel) {
    return (
      <div className="p-6">
        <EmptyState
          icon={
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none" aria-hidden="true">
              <rect x="12" y="22" width="24" height="18" rx="3" stroke="currentColor" strokeWidth="2" />
              <path d="M16 22v-6a8 8 0 0116 0v6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              <circle cx="24" cy="31" r="2" fill="currentColor" />
            </svg>
          }
          title="You don't have access to this area."
          description="Contact the property owner if you think this is a mistake."
          actionLabel="Go back"
          onAction={() => navigate(-1)}
        />
      </div>
    )
  }
  return <Outlet />
}

// Inline role check for non-route-nesting use (e.g., hiding a button or section).
export function RequireRole({ minLevel, children }: { minLevel: number; children: ReactNode }) {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  if (!user || user.role_level < minLevel) {
    return (
      <div className="p-6">
        <EmptyState
          icon={
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none" aria-hidden="true">
              <rect x="12" y="22" width="24" height="18" rx="3" stroke="currentColor" strokeWidth="2" />
              <path d="M16 22v-6a8 8 0 0116 0v6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              <circle cx="24" cy="31" r="2" fill="currentColor" />
            </svg>
          }
          title="You don't have access to this area."
          description="Contact the property owner if you think this is a mistake."
          actionLabel="Go back"
          onAction={() => navigate(-1)}
        />
      </div>
    )
  }
  return <>{children}</>
}
