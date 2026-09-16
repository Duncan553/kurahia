import { Navigate, Outlet, useNavigate } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useAuthStore } from '../stores/authStore'
import { EmptyState, Icon } from '@shared'

export function AuthGate() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated)

  // Signed in is the whole gate. Being CLOCKED IN is not a condition of
  // reaching anything in this app any more.
  //
  // It used to be: any route except /clock and /kiosk bounced you to /clock,
  // silently, if clock-status came back anything but CLOCK_IN. That rule was
  // written when this app still carried the tills — you should not ring up a
  // sale off the clock, fair enough. Those screens are station_pwa's now, and
  // what is left here is a person's own HR: leave, absence, conduct, profile,
  // calendar, disputes.
  //
  // Which turned the rule inside out. The absence notice — the screen whose
  // entire purpose is "I am not coming in today" — could only be opened by
  // someone already at work. So could a leave request, so could a grievance
  // about the manager, so could reading your own profile. A waiter off duty
  // typed /disputes, watched the URL flip to /clock, and was told nothing.
  //
  // It is the third rule to survive the app split by pointing at screens that
  // left: HomeRedirect's station landing and AppLayout's department landing
  // were the other two. The clock is still where everyone lands (HomeRedirect),
  // it is just no longer a wall.
  if (!isAuthenticated) return <Navigate to="/login" replace />

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
