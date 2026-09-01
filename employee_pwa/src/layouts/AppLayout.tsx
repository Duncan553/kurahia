import { Suspense, useEffect } from 'react'
import type { ReactElement } from 'react'
import { useLocation, useNavigate, NavLink, Outlet } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { useQuery } from '@tanstack/react-query'
import { OfflineBanner, InstallPrompt } from '@shared'
import { useAuthStore } from '../stores/authStore'
import api from '../lib/axios'
import { kvGet, kvSet } from '../lib/idb'
import { loadFontSizePref } from '../lib/fontSizePref'
import PushPrompt from '../components/PushPrompt'
import IdleBrand from '../components/IdleBrand'
import type { Notification } from '../screens/NotificationsScreen'

// ── Icons (inline SVG — no library dependency) ─────────────────────────────

function ClockIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <circle cx="10" cy="10" r="7.5" stroke="currentColor" strokeWidth="1.5" />
    <path d="M10 6v4.5l3 2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
}
function BellIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M10 2.5a6.5 6.5 0 00-6.5 6.5v3.5L2 14.5h16L16.5 12.5V9A6.5 6.5 0 0010 2.5z"
      stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M8.5 16a1.5 1.5 0 003 0" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
}
function ProfileIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <circle cx="10" cy="7" r="3.5" stroke="currentColor" strokeWidth="1.5" />
    <path d="M3 18c0-3.3 3.1-5.5 7-5.5s7 2.2 7 5.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
}
// Band search: magnifier
// Gate: wristband icon
// Check-in: calendar + check
// Waiver: document + pen
// Inventory: grid
// Restock: clipboard + arrow up
// Meals: utensils
// Safety check: shield + checkmark
// Maintenance: wrench
// Manager: person + check badge

// Waiter pad: notepad + pen stroke
// Kitchen: pot/flame
// Bar: cocktail glass
// Spa/Gym: leaf
// Water: wave
// Events: calendar + star
// Villa: house

// Calendar: monthly calendar
function CalendarIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <rect x="3" y="4" width="14" height="14" rx="2" stroke="currentColor" strokeWidth="1.5" />
    <path d="M7 2v4M13 2v4M3 9h14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    <circle cx="7.5" cy="12.5" r="1" fill="currentColor" />
    <circle cx="10" cy="12.5" r="1" fill="currentColor" />
    <circle cx="12.5" cy="12.5" r="1" fill="currentColor" />
    <circle cx="7.5" cy="15.5" r="1" fill="currentColor" />
  </svg>
}
// Disputes: shield + exclamation
function DisputesIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M10 2.5L3.5 5.5v4.5c0 4 2.5 7.5 6.5 8.5 4-1 6.5-4.5 6.5-8.5V5.5L10 2.5z"
      stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M10 8v3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <circle cx="10" cy="13.5" r="0.75" fill="currentColor" />
  </svg>
}
// Performance: bar chart
// Housekeeping: sparkle

function IncidentIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M10 3L2 17h16L10 3z" stroke="currentColor" strokeWidth="1.5"
      strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M10 9v4M10 14.5v.5" stroke="currentColor" strokeWidth="1.5"
      strokeLinecap="round"/>
  </svg>
}

// ── Department helper ──────────────────────────────────────────────────────────


// ── Nav item definition ─────────────────────────────────────────────────────

interface NavItem {
  id: string
  path: string
  label: string
  Icon: () => ReactElement
  badge?: boolean
  // mode: 'personal' = phone HR app, 'station' = shared work tablet, 'both' = always
  mode: 'personal' | 'station' | 'both'
  visible: (level: number, dept: string | null) => boolean
}

const NAV_ITEMS: NavItem[] = [
  // Personal only. The station entries that used to sit here — POS, kitchen and
  // bar queues, gate hub, front-desk check-in, villa, housekeeping, the manager
  // group — pointed at routes this app no longer serves, because those are the
  // POST'S tools and live in station_pwa. A nav item whose route is gone is a
  // dead link, so the two are kept in step: everything below resolves.
  // ── Personal phone: HR + clock-in ───────────────────────────────────────────
  {
    id: 'clock',
    path: '/clock',
    label: 'Clock',
    Icon: ClockIcon,
    mode: 'personal',
    visible: () => true,
  },
  {
    id: 'alerts',
    path: '/notifications',
    label: 'Alerts',
    Icon: BellIcon,
    badge: true,
    mode: 'personal',
    visible: () => true,
  },
  {
    id: 'profile',
    path: '/profile',
    label: 'Profile',
    Icon: ProfileIcon,
    mode: 'personal',
    visible: (level) => level < 5,
  },
  {
    id: 'calendar',
    path: '/calendar',
    label: 'Calendar',
    Icon: CalendarIcon,
    mode: 'personal',
    visible: () => true,
  },
  {
    id: 'incidents',
    path: '/incidents',
    label: 'Incident',
    Icon: IncidentIcon,
    // 'both' — was personal-only, meaning a station tablet (kitchen/bar/gate/
    // etc.) had no way to report an incident at all, only someone's own phone.
    // Safety reporting needs to work right where the incident happens. Placed
    // after the station work-tools (not with clock/alerts/profile above) so
    // it doesn't bump the actual work screen out of the mobile nav's first
    // 5 slots on a station tablet.
    mode: 'both',
    visible: () => true,
  },
  {
    id: 'disputes',
    path: '/disputes',
    label: 'Disputes',
    Icon: DisputesIcon,
    mode: 'both',
    visible: (level) => level >= 5,
  },
]

// ── Page transition ─────────────────────────────────────────────────────────

const pageVariants = {
  initial: { opacity: 0, x: 20 },
  animate: { opacity: 1,  x: 0  },
  exit:    { opacity: 0,        },
}

// ── AppLayout ───────────────────────────────────────────────────────────────

export default function AppLayout() {
  const location = useLocation()
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const clearAuth = useAuthStore((s) => s.clearAuth)
  const roleLevel = user?.role_level ?? 0

  // Today's station roster overrides the employee's fixed home department —
  // a manager can put someone on a different station for a shift (e.g. a
  // waiter covering Front Desk today) without touching their account. Falls
  // back to the account's own department when nobody explicitly rostered
  // them today (the ordinary case). Same cache key everywhere it's read.
  const { data: rosterToday } = useQuery<{ department: string | null }>({
    queryKey: ['roster', 'me'],
    queryFn: () => api.get('/hr/roster/me').then(r => r.data),
    staleTime: 5 * 60_000,
  })
  const department = rosterToday?.department ?? user?.department ?? null

  // No station branch any more — this app has one mode. Every remaining item
  // is personal, and station_pwa owns the post's tools.
  const visibleItems = NAV_ITEMS.filter((item) => item.visible(roleLevel, department))

  // Shares the same TanStack cache key as NotificationsScreen → no extra network request
  const { data: inbox } = useQuery<Notification[]>({
    queryKey: ['notifications', 'inbox'],
    queryFn: () => api.get<Notification[]>('/notifications/inbox').then((r) => r.data),
    staleTime: 30_000,
  })
  const badgeCount = inbox?.length ?? 0

  // The clock-status read that sat here existed only to break a redirect loop
  // with AuthGate: this layout used to redirect a clocked-in station user AWAY
  // from /clock, while AuthGate pushed anyone not clocked in TOWARDS it, and
  // the two fought until the check was added. With the station redirects gone
  // there is nothing left to fight — AuthGate is the only rule about /clock —
  // so the query goes too rather than sitting there costing a cache read to
  // guard a loop that can no longer happen.

  function signOut() { clearAuth(); navigate('/pin') }

  // Apply saved font-size preference from IDB at session start
  useEffect(() => { void loadFontSizePref() }, [])

  // The department-landing block that used to sit here is gone.
  //
  // It sent people straight to their post after clocking in: kitchen to
  // /pos/kitchen, a waiter to /pos/tabs, gate to /gate/hub, and so on. Every
  // one of those routes now lives in station_pwa, so keeping the redirect
  // would have dropped every non-manager on a dead route the moment they
  // clocked in — the single biggest risk in removing the station screens.
  //
  // There is nowhere else to send them, and that is the point: on their own
  // phone a person clocks in, checks their HR, reads their profile. The tools
  // of the post are on the tablet at the post.

  return (
    <div className="h-screen flex">
      <IdleBrand />
      <OfflineBanner />

      {/* ── Left Nav Rail (sm+) ─────────────────────────────────── */}
      <aside className="hidden sm:flex flex-col w-16 lg:w-52 shrink-0 border-r border-white/5"
        style={{ background: 'var(--color-chrome-95)', backdropFilter: 'blur(20px)' }}>

        {/* Logo */}
        <div className="h-14 flex items-center justify-center lg:justify-start lg:px-4 border-b border-white/5">
          <span className="text-ink-primary font-bold font-serif text-lg">
            <span className="hidden lg:block">Kurahia</span>
            <span className="lg:hidden">K</span>
          </span>
        </div>

        {/* Nav items */}
        <nav className="flex-1 py-2 space-y-0.5 overflow-y-auto" aria-label="Main navigation">
          {visibleItems.map(({ id, path, label, Icon, badge }) => (
            <NavLink key={id} to={path} end={path === '/clock'}
              className={({ isActive }) => [
                // min-h-[44px]: on the COLLAPSED tablet rail (sm..lg, w-16) this row
                // was only 40px tall — a 20px icon plus py-2.5. The rail is the only
                // navigation on a tablet, so it has to clear the 44px touch minimum.
                // Nothing moves on desktop: the expanded row was already >44px.
                'flex items-center gap-3 px-3 lg:px-4 py-2.5 mx-1 rounded-lg transition-colors min-h-[44px]',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-main',
                isActive
                  ? 'bg-primary-main/10 text-[#ffb59f]'
                  : 'text-ink-tertiary hover:text-ink-primary hover:bg-white/5',
              ].join(' ')}
            >
              <span className="relative shrink-0">
                <Icon />
                {badge && badgeCount > 0 && (
                  <span className="absolute -top-1 -right-1 min-w-[14px] h-3.5 rounded-full
                    bg-status-failed text-white text-[8px] font-bold flex items-center justify-center px-0.5">
                    {badgeCount > 9 ? '9+' : badgeCount}
                  </span>
                )}
              </span>
              <span className="hidden lg:block text-sm font-medium truncate">{label}</span>
            </NavLink>
          ))}
        </nav>

        {/* User */}
        <div className="p-2 border-t border-white/5 space-y-1">
          {/* The "Station mode" toggle stood here. It was the original idea —
              one app that a manager could flip into a work tablet — and
              station_pwa was built to replace it. The app shipped; the toggle
              never got removed, so this app kept a second personality nobody
              wanted. Gone now: a device is a phone or it is a station, and
              which one is decided by which app is installed on it. */}
          <div className="flex items-center gap-2 px-2">
            <div className="w-8 h-8 rounded-full bg-primary-main/20 border border-primary-main/20
              flex items-center justify-center text-primary-main text-xs font-bold shrink-0">
              {user?.username?.[0]?.toUpperCase() ?? '?'}
            </div>
            <div className="hidden lg:block flex-1 min-w-0">
              <p className="text-xs font-medium text-ink-primary truncate">{user?.username}</p>
              <button onClick={signOut} className="text-[10px] text-status-failed/50 hover:text-status-failed">
                Sign out
              </button>
            </div>
          </div>
        </div>
      </aside>

      {/* ── Main content area ──────────────────────────────────── */}
      <div className="flex flex-col flex-1 min-w-0">

        {/* Mobile top bar (sm: hidden since sidebar has logo) */}
        <header className="sm:hidden h-14 shrink-0 flex items-center justify-between px-4 border-b border-white/5"
          style={{ background: 'var(--color-chrome-90)' }}>
          <span className="text-lg font-bold font-serif text-ink-primary">Kurahia</span>
          {/* Sign out. The button box is 44x44 (the touch minimum) but the orange
              circle inside stays 32px, so the header looks identical — only the
              tappable area grew. -mr-1.5 pulls the wider box back over the header's
              px-4 padding so the circle sits on the same pixel it always did. */}
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
          {location.pathname === '/clock' && (
            <>
              <InstallPrompt kvGet={kvGet} kvSet={kvSet} />
              <PushPrompt />
            </>
          )}
          <AnimatePresence mode="wait">
            <motion.div
              key={location.pathname}
              variants={pageVariants}
              initial="initial"
              animate="animate"
              exit="exit"
              transition={{ duration: 0.25, ease: 'easeOut' }}
              className="min-h-full"
            >
              <Suspense fallback={
                <div className="flex items-center justify-center py-24">
                  <div className="w-7 h-7 rounded-full border-2 border-primary-main border-t-transparent animate-spin" />
                </div>
              }>
                <Outlet />
              </Suspense>
            </motion.div>
          </AnimatePresence>
        </main>

        {/* Mobile bottom nav (sm: hidden since sidebar replaces it) */}
        <nav className="sm:hidden shrink-0 flex border-t border-white/5"
          style={{ background: 'var(--color-chrome-95)' }}
          aria-label="Main navigation">
          {visibleItems.slice(0, 5).map(({ id, path, label, Icon, badge }) => (
            <NavLink key={id} to={path} end={path === '/clock'}
              className={({ isActive }) => [
                'flex-1 flex flex-col items-center justify-center gap-0.5 py-2',
                'min-h-[56px] relative transition-colors',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-main focus-visible:ring-inset',
                isActive ? 'text-primary-main' : 'text-ink-tertiary hover:text-ink-primary',
              ].join(' ')}
            >
              <span className="relative">
                <Icon />
                {badge && badgeCount > 0 && (
                  <span className="absolute -top-1 -right-1 min-w-[16px] h-4 rounded-full
                    bg-status-failed text-white text-[10px] font-bold flex items-center justify-center px-1">
                    {badgeCount > 9 ? '9+' : badgeCount}
                  </span>
                )}
              </span>
              <span className="text-[10px] font-medium leading-none">{label}</span>
            </NavLink>
          ))}
        </nav>

      </div>
    </div>
  )
}
