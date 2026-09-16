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

// `allow` is for a screen whose real rule is a CAPABILITY, not a rank — stock
// counting being the one that bit: housekeeping (level 1) counts its own store
// and front desk (level 3) does not, so no minLevel can express it. Pass a
// predicate and the level check steps aside.
export function RequireRole({ minLevel, allow, children }: {
  minLevel: number
  allow?: (u: { role_level: number; can_count_stock?: boolean;
               department?: string | null }) => boolean
  children: ReactNode
}) {
  const user = useAuthStore((s) => s.user)
  const permitted = user ? (allow ? allow(user) : user.role_level >= minLevel) : false
  // Returning null here rendered a completely blank page — no header, no
  // explanation, nothing to tap. On a shared station tablet that reads as a
  // broken app, not as a permission boundary, and the person just stands
  // there. Every error in this system says what happened in plain English
  // (engineering invariant 5); a screen someone cannot open is no different.
  if (!permitted) {
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


// The same question asked about a CONTROL rather than a screen.
//
// RequireRole always answers with a full-page panel, because a screen someone
// cannot open must say so rather than go blank. Wrapped around a button that
// answer is wrong twice over: it drops a page-sized "This screen isn't yours
// to open" into a layout where a small button belongs, and it says something
// untrue — the Events screen IS theirs to open; only "+ Create Event" isn't.
// A gate lead opening Events saw the refusal panel where the header's action
// should sit and reasonably read the whole screen as forbidden.
//
// A control you cannot use simply should not be there. No explanation is owed
// for a button that was never offered.
export function IfRole({ minLevel, allow, children }: {
  minLevel: number
  allow?: (u: { role_level: number; can_count_stock?: boolean;
               department?: string | null }) => boolean
  children: ReactNode
}) {
  const user = useAuthStore((s) => s.user)
  const permitted = user ? (allow ? allow(user) : user.role_level >= minLevel) : false
  return permitted ? <>{children}</> : null
}
