import { Suspense } from 'react'
import { Navigate, Outlet, useNavigate } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useAuthStore } from '../stores/authStore'
import { EmptyState } from '@shared'

const chunkFallback = (
  <div className="min-h-screen flex items-center justify-center bg-cream-card">
    <div className="w-8 h-8 rounded-full border-2 border-primary-dark border-t-transparent animate-spin" />
  </div>
)

export function AuthGate() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  if (!isAuthenticated) return <Navigate to="/pin" replace />
  // Lazy route chunks load behind this boundary
  return <Suspense fallback={chunkFallback}><Outlet /></Suspense>
}

// Role gate for nested routes — shows EmptyState (not redirect) so nav shell stays.
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
          description="Ask your manager if you think this is a mistake."
          actionLabel="Go back"
          onAction={() => navigate(-1)}
        />
      </div>
    )
  }
  return <Outlet />
}

// Used in AuthGate to check role before rendering a page inline (no nesting needed).
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
          description="Ask your manager if you think this is a mistake."
          actionLabel="Go back"
          onAction={() => navigate(-1)}
        />
      </div>
    )
  }
  return <>{children}</>
}

