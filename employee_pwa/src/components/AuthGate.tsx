import { Navigate, Outlet, useLocation, useNavigate } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useAuthStore } from '../stores/authStore'
import { useQuery } from '@tanstack/react-query'
import api from '../lib/axios'
import { EmptyState, Icon } from '@shared'

export function AuthGate() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)
  const location = useLocation()

  if (!isAuthenticated) return <Navigate to="/login" replace />

  const isKiosk = location.pathname.startsWith('/kiosk')
  const isClockRoute = location.pathname === '/clock'

  const { data: clockStatus } = useQuery({
    queryKey: ['clock-status'],
    queryFn: () => api.get('/hr/clock-status').then(r => r.data),
    refetchInterval: 60_000,
    enabled: !isKiosk && !isClockRoute,
  })

  if (!isKiosk && !isClockRoute && clockStatus && clockStatus.status !== 'CLOCK_IN') {
    return <Navigate to="/clock" replace />
  }

  return <Outlet />
}

export function RoleGate({ minLevel }: { minLevel: number }) {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  if (!user || user.role_level < minLevel) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-6 text-center">
        {/* EmptyState's props are icon/title/description/actionLabel/onAction.
            This passed message= and action={{...}}, which React silently drops,
            so the user saw "Access restricted" with NO explanation and NO way
            back — a dead end. `icon` is required and was missing too. */}
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
  if (!user || user.role_level < minLevel) return null
  return <>{children}</>
}
