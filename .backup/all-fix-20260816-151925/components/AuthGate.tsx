import { Navigate, Outlet, useNavigate } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useAuthStore } from '../stores/authStore'
import { EmptyState } from '@shared'

export function AuthGate() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const user = useAuthStore((s) => s.user)

  if (!isAuthenticated) return <Navigate to="/login" replace />
  // Owner PWA is strictly for owners (level 10+)
  if (!user || user.role_level < 10) {
    return <Navigate to="/login" replace />
  }
  return <Outlet />
}

export function RoleGate({ minLevel }: { minLevel: number }) {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  if (!user || user.role_level < minLevel) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-6 text-center">
        <EmptyState
          title="Access restricted"
          message="You don't have permission to view this page."
          action={{ label: 'Go back', onClick: () => navigate(-1) }}
        />
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
