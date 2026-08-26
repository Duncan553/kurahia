import { Suspense } from 'react'
import type { ReactElement } from 'react'
import { useNavigate, NavLink, Outlet, Navigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useAuthStore } from '../stores/authStore'
import api from '../lib/axios'

// ── Icons (inline SVG, no library) ──────────────────────────────────────────
function WaiterIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <rect x="3.5" y="2" width="13" height="16" rx="2" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M7 6h6M7 9h6M7 12h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
}
function KitchenIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M3.5 9h13v6.5a2 2 0 01-2 2h-9a2 2 0 01-2-2V9z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M3 9h14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
}
function BarIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M4.5 3.5l5.5 7.5 5.5-7.5H4.5z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M10 11v5.5M6.5 16.5h7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
}
function SpaIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M10 17C10 17 3.5 13 3.5 8a6.5 6.5 0 0113 0C16.5 13 10 17 10 17z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
}
function WaterIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M2 11c1.3-2.5 2.6-2.5 4 0s2.6 2.5 4 0 2.6-2.5 4 0 2.6 2.5 4 0" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
}
function SafetyIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M10 2.5L3.5 5.5v4.5c0 4 2.5 7.5 6.5 8.5 4-1 6.5-4.5 6.5-8.5V5.5L10 2.5z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M7.5 10l2 2.5L13.5 8.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
}
function VillaIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M3 9.5L10 3l7 6.5v8a1 1 0 01-1 1H4a1 1 0 01-1-1v-8z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
}
function HousekeepingIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M10 2l1.2 2.4L14 5l-2 2 .5 3L10 8.5 7.5 10l.5-3-2-2 2.8-.6L10 2z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
}
function GateIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <rect x="2.5" y="4.5" width="15" height="11" rx="2" stroke="currentColor" strokeWidth="1.5"/>
    <circle cx="10" cy="10" r="2.5" stroke="currentColor" strokeWidth="1.5"/>
  </svg>
}
function CheckInIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <rect x="3" y="3.5" width="14" height="14" rx="2" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M7 13l2.5 2.5L14 11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
}
function BandIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <circle cx="8.5" cy="8.5" r="5.5" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M13 13l4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
}
function IncidentIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M10 3L2 17h16L10 3z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M10 9v4M10 14.5v.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
}

function deptIs(dept: string | null, ...keywords: string[]): boolean {
  if (!dept) return false
  const d = dept.toLowerCase()
  return keywords.some((k) => d.includes(k))
}

interface NavItem {
  id: string; path: string; label: string; Icon: () => ReactElement
  visible: (level: number, dept: string | null) => boolean
}

// Every item here (except Incident) is department-gated — a station tablet
// only shows the tool(s) for whichever department the logged-in person is
// on (fixed home department, or today's roster override — see the query
// below). Incident is the one tool every station always carries, regardless
// of department, since safety reporting needs to work wherever it happens.
const NAV_ITEMS: NavItem[] = [
  { id: 'waiter', path: '/pos/tabs', label: 'Tables', Icon: WaiterIcon,
    visible: (_l, d) => deptIs(d, 'waiter', 'restaurant', 'food', 'beverage', 'f&b', 'front-of-house') },
  { id: 'kitchen', path: '/pos/kitchen', label: 'Kitchen', Icon: KitchenIcon,
    visible: (_l, d) => deptIs(d, 'kitchen') },
  { id: 'bar', path: '/pos/bar', label: 'Bar', Icon: BarIcon,
    visible: (_l, d) => deptIs(d, 'bar') },
  { id: 'spa', path: '/pos/spa', label: 'Services', Icon: SpaIcon,
    visible: (_l, d) => deptIs(d, 'spa', 'gym', 'wellness', 'massage', 'beauty', 'fitness') },
  { id: 'waiver', path: '/gate/waiver', label: 'Waiver', Icon: WaterIcon,
    visible: (_l, d) => deptIs(d, 'water', 'activit', 'aqua') },
  { id: 'safety', path: '/equipment/safety-check', label: 'Safety', Icon: SafetyIcon,
    visible: (_l, d) => deptIs(d, 'water', 'activit', 'aqua') },
  { id: 'water-pay', path: '/pos/water-pay', label: 'Payment', Icon: WaterIcon,
    visible: (_l, d) => deptIs(d, 'water', 'activit', 'aqua') },
  // level >= 3: VillaScreen's booking-availability call (GET /bookings/availability)
  // requires FRONT_DESK_LEVEL (3) on the backend — a level-1 housekeeping staffer
  // hit a real 403 here. They still get Cleaning below regardless of level.
  { id: 'villa', path: '/villa', label: 'Villa', Icon: VillaIcon,
    visible: (l, d) => deptIs(d, 'villa', 'housekeep') && l >= 3 },
  { id: 'housekeeping', path: '/housekeeping', label: 'Cleaning', Icon: HousekeepingIcon,
    visible: (_l, d) => deptIs(d, 'villa', 'housekeep') },
  { id: 'gate-hub', path: '/gate/hub', label: 'Gate', Icon: GateIcon,
    visible: (_l, d) => deptIs(d, 'gate', 'entry', 'secur') },
  { id: 'checkin', path: '/front-desk/checkin', label: 'Check-In', Icon: CheckInIcon,
    visible: (_l, d) => deptIs(d, 'front desk', 'front-desk') },
  { id: 'band-lookup', path: '/gate/band-lookup', label: 'Band', Icon: BandIcon,
    visible: (_l, d) => deptIs(d, 'gate', 'front desk', 'front-desk') },
  { id: 'incident', path: '/incidents', label: 'Incident', Icon: IncidentIcon,
    visible: () => true },
]

// ── Landing redirect: send whoever just logged in to their department's
// first tool. Falls back to Incident (always visible) if nothing matches —
// e.g. a manager/owner PINs in here with no station department of their own. ──
export function StationHome() {
  const user = useAuthStore((s) => s.user)
  const { data: rosterToday } = useQuery<{ department: string | null }>({
    queryKey: ['roster', 'me'],
    queryFn: () => api.get('/hr/roster/me').then(r => r.data),
    staleTime: 5 * 60_000,
    enabled: !!user,
  })
  if (!user) return <Navigate to="/login" replace />
  const dept = rosterToday?.department ?? user.department ?? null
  const first = NAV_ITEMS.find(i => i.id !== 'incident' && i.visible(user.role_level, dept))
  return <Navigate to={first?.path ?? '/incidents'} replace />
}

export default function AppLayout() {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const clearAuth = useAuthStore((s) => s.clearAuth)
  const roleLevel = user?.role_level ?? 0

  const { data: rosterToday } = useQuery<{ department: string | null }>({
    queryKey: ['roster', 'me'],
    queryFn: () => api.get('/hr/roster/me').then(r => r.data),
    staleTime: 5 * 60_000,
  })
  const department = rosterToday?.department ?? user?.department ?? null

  const visibleItems = NAV_ITEMS.filter(i => i.visible(roleLevel, department))

  function signOut() { clearAuth(); navigate('/login') }

  return (
    <div className="h-screen flex flex-col">
      {/* Top bar */}
      <header className="h-14 shrink-0 flex items-center justify-between px-4 border-b border-white/5"
        style={{ background: 'rgba(30, 16, 12, 0.95)' }}>
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-lg font-bold font-serif text-ink-primary shrink-0">Kurahia</span>
          {department && (
            <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full
              bg-primary-main/20 text-primary-main truncate">
              {department}
            </span>
          )}
        </div>
        {/* Sign out. 44x44 tappable box, 32px orange circle inside — the header
            looks unchanged, only the hit area grew. -mr-1.5 eats back into the
            header's px-4 so the circle stays on the same pixel. */}
        <button onClick={signOut}
          className="w-11 h-11 -mr-1.5 flex items-center justify-center rounded-full
            shrink-0" aria-label="Sign out">
          <span className="w-8 h-8 rounded-full bg-primary-main/20 flex items-center justify-center
            text-primary-main text-sm font-bold" aria-hidden="true">
            {user?.username?.[0]?.toUpperCase() ?? '?'}
          </span>
        </button>
      </header>

      {/* Page content */}
      <main className="flex-1 overflow-y-auto">
        <Suspense fallback={
          <div className="flex items-center justify-center py-24">
            <div className="w-7 h-7 rounded-full border-2 border-primary-main border-t-transparent animate-spin" />
          </div>
        }>
          <Outlet />
        </Suspense>
      </main>

      {/* Bottom nav — this station's tool(s) + Incident, always */}
      <nav className="shrink-0 flex border-t border-white/5" style={{ background: 'rgba(30, 16, 12, 0.95)' }}
        aria-label="Main navigation">
        {visibleItems.map(({ id, path, label, Icon }) => (
          <NavLink key={id} to={path} end
            className={({ isActive }) => [
              'flex-1 flex flex-col items-center justify-center gap-0.5 py-2 min-h-[56px]',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-main focus-visible:ring-inset',
              isActive ? 'text-primary-main' : 'text-ink-tertiary hover:text-ink-primary',
            ].join(' ')}
          >
            <Icon />
            <span className="text-[10px] font-medium leading-none">{label}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
