import { Suspense, useEffect } from 'react'
import type { ReactElement } from 'react'
import { useLocation, useNavigate, NavLink, Outlet, Navigate } from 'react-router-dom'
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
  return <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
    <circle cx="11" cy="11" r="8" stroke="currentColor" strokeWidth="1.5" />
    <path d="M11 7v4.5l3 2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
}
function ScheduleIcon() {
  return <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
    <rect x="3" y="4" width="16" height="15" rx="2" stroke="currentColor" strokeWidth="1.5" />
    <path d="M7 2v4M15 2v4M3 10h16" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <path d="M7 14h2M13 14h2M7 17h2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
}
function BellIcon() {
  return <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
    <path d="M11 3a7 7 0 00-7 7v4l-1.5 2.5h17L18 14V10a7 7 0 00-7-7z"
      stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
    <path d="M9 17.5a2 2 0 004 0" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
}
function ProfileIcon() {
  return <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
    <circle cx="11" cy="8" r="4" stroke="currentColor" strokeWidth="1.5" />
    <path d="M3 19c0-3.3 3.6-6 8-6s8 2.7 8 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
}
// Band search: magnifier
function BandIcon() {
  return <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
    <circle cx="9.5" cy="9.5" r="6" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M14 14l4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    <path d="M7 9.5h5M9.5 7v5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
}
// Gate: wristband icon
function GateIcon() {
  return <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
    <rect x="3" y="5" width="16" height="12" rx="2" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="11" cy="11" r="2.5" stroke="currentColor" strokeWidth="1.5" />
    <path d="M3 11h5.5M13.5 11H19" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
}
// Check-in: calendar + check
function CheckInIcon() {
  return <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
    <rect x="3" y="4" width="16" height="15" rx="2" stroke="currentColor" strokeWidth="1.5" />
    <path d="M7 2v4M15 2v4M3 10h16" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <path d="M7.5 15l2.5 2.5L15 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
}
// Waiver: document + pen
function WaiverIcon() {
  return <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
    <rect x="4" y="3" width="14" height="17" rx="2" stroke="currentColor" strokeWidth="1.5" />
    <path d="M7 8h8M7 12h5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <path d="M12 16l1.5-1.5L15 16" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
}
// Inventory: grid
function InventoryIcon() {
  return <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
    <rect x="3" y="3" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.5"/>
    <rect x="12" y="3" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.5"/>
    <rect x="3" y="12" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M12 15.5h7M15.5 12v7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
}
// Restock: clipboard + arrow up
function RestockIcon() {
  return <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
    <rect x="4" y="4" width="14" height="16" rx="2" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M8 4V3a1 1 0 011-1h4a1 1 0 011 1v1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    <path d="M11 9v6M8.5 11.5L11 9l2.5 2.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
}
// Meals: fork
function MealsIcon() {
  return <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
    <path d="M11 3v4M7 4.5c0 3.5 2 5 4 5s4-1.5 4-5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    <path d="M11 9v10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    <path d="M6 14h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
}
// Safety check: shield + checkmark
function SafetyIcon() {
  return <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
    <path d="M11 3L4 6v5c0 4.5 3 8.5 7 9.5 4-1 7-5 7-9.5V6L11 3z"
      stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
    <path d="M8 11l2 2.5L14 9" stroke="currentColor" strokeWidth="1.5"
      strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
}
// Maintenance: wrench
function MaintenanceIcon() {
  return <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
    <path d="M14.5 4.5a4 4 0 00-4 4c0 .6.1 1.1.3 1.6L4 17a1.4 1.4 0 002 2l6.9-6.8c.5.2 1 .3 1.6.3a4 4 0 000-8z"
      stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
    <path d="M14.5 4.5v3h-3" stroke="currentColor" strokeWidth="1.5"
      strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
}
// Manager: person + star badge
function ManagerIcon() {
  return <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
    <path d="M3 17v-1.5C3 13 6.1 11 11 11s8 2 8 4.5V17" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <circle cx="11" cy="7" r="4" stroke="currentColor" strokeWidth="1.5" />
    <path d="M15 3l1.5 1.5L19 2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
}

// Waiter pad: notepad + fork
function WaiterIcon() {
  return <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
    <rect x="4" y="3" width="14" height="17" rx="2" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M7 7h8M7 10h8M7 13h5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    <path d="M16 18l2.5 2.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
}
// Kitchen: pot/flame
function KitchenIcon() {
  return <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
    <path d="M4 10h14v7a2 2 0 01-2 2H6a2 2 0 01-2-2v-7z" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M3 10h16" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    <path d="M8 10V7c0-1.5 1-2.5 1-4M12 10V7c0-1.5 1-2.5 1-4"
      stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    <path d="M8 15h6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
}
// Bar: cocktail glass
function BarIcon() {
  return <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
    <path d="M5 4l6 8 6-8H5z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
    <path d="M11 12v6M7 18h8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    <path d="M7 8h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
}
// Spa/Gym: leaf + dumbbell
function SpaGymIcon() {
  return <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
    <path d="M11 18C11 18 4 14 4 8.5a7 7 0 0114 0C18 14 11 18 11 18z"
      stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
    <path d="M11 18V10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
}
// Water: wave
function WaterIcon() {
  return <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
    <path d="M2 12c1.5-3 3-3 4.5 0S9.5 15 11 12s3-3 4.5 0 3 3 4.5 0"
      stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M2 7c1.5-3 3-3 4.5 0S9.5 10 11 7s3-3 4.5 0 3 3 4.5 0"
      stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M2 17c1.5-3 3-3 4.5 0S9.5 20 11 17s3-3 4.5 0 3 3 4.5 0"
      stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
}
// Villa: house
function VillaIcon() {
  return <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
    <path d="M3 10L11 3l8 7v9a1 1 0 01-1 1H4a1 1 0 01-1-1V10z"
      stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
    <rect x="8" y="14" width="6" height="6" rx="0.5" stroke="currentColor" strokeWidth="1.5"/>
  </svg>
}

// ── Department helper ──────────────────────────────────────────────────────────

function deptIs(dept: string | null, ...keywords: string[]): boolean {
  if (!dept) return false
  const d = dept.toLowerCase()
  return keywords.some((k) => d.includes(k))
}

// Station departments work on SHARED tablets — those screens show only the
// station's tools. Clock/alerts/profile live on personal phones (no dept) and
// manager tablets (level 5+), never on a station device.
function isStation(dept: string | null): boolean {
  return deptIs(dept, 'kitchen', 'bar', 'front-of-house', 'waiter', 'restaurant',
    'spa', 'gym', 'wellness', 'water', 'activit', 'aqua', 'villa', 'housekeep')
}
// Personal chrome: managers always; staff only when NOT on a station tablet
const personal = (level: number, dept: string | null) => level >= 5 || !isStation(dept)

// ── Nav item definition ─────────────────────────────────────────────────────

interface NavItem {
  id: string       // unique React key (can't use path — some paths repeat across roles)
  path: string
  label: string
  Icon: () => ReactElement
  badge?: boolean
  // Returns true when this item should appear for the given role + department
  visible: (level: number, dept: string | null) => boolean
}

const NAV_ITEMS: NavItem[] = [
  // ── Universal — every logged-in user ────────────────────────────────────────
  {
    id: 'clock',
    path: '/clock',
    label: 'Clock',
    Icon: ClockIcon,
    visible: personal,
  },
  {
    id: 'schedule',
    path: '/schedule',
    label: 'Schedule',
    Icon: ScheduleIcon,
    visible: (level) => level >= 5,  // GET /hr/shifts requires manager (level 5+)
  },
  {
    id: 'alerts',
    path: '/notifications',
    label: 'Alerts',
    Icon: BellIcon,
    badge: true,
    visible: personal,
  },
  {
    id: 'profile',
    path: '/profile',
    label: 'Profile',
    Icon: ProfileIcon,
    visible: (level, dept) => level < 5 && personal(level, dept),
  },

  // ── POS: waiter tablet ───────────────────────────────────────────────────────
  {
    id: 'waiter',
    path: '/pos/tabs',
    label: 'Tables',
    Icon: WaiterIcon,
    visible: (_level, dept) =>
      deptIs(dept, 'waiter', 'restaurant', 'food', 'beverage', 'f&b', 'front-of-house'),
  },

  // ── POS: kitchen queue (full-screen, department-restricted) ─────────────────
  {
    id: 'kitchen',
    path: '/pos/kitchen',
    label: 'Kitchen',
    Icon: KitchenIcon,
    visible: (_level, dept) => deptIs(dept, 'kitchen'),
  },

  // ── POS: bar queue ───────────────────────────────────────────────────────────
  {
    id: 'bar',
    path: '/pos/bar',
    label: 'Bar',
    Icon: BarIcon,
    visible: (_level, dept) => deptIs(dept, 'bar'),
  },

  // ── POS: spa + gym service payment ──────────────────────────────────────────
  {
    id: 'spa-gym',
    path: '/pos/spa',
    label: 'Services',
    Icon: SpaGymIcon,
    visible: (_level, dept) => deptIs(dept, 'spa', 'gym', 'wellness', 'massage', 'beauty', 'fitness'),
  },

  // ── Waiver + Safety + Payment: water activities ──────────────────────────────
  {
    id: 'waiver',
    path: '/gate/waiver',
    label: 'Waiver',
    Icon: WaiverIcon,
    visible: (_level, dept) => deptIs(dept, 'water', 'activit', 'aqua'),
  },
  {
    id: 'safety-check',
    path: '/equipment/safety-check',
    label: 'Safety',
    Icon: SafetyIcon,
    visible: (_level, dept) => deptIs(dept, 'water', 'activit', 'aqua'),
  },
  {
    id: 'water-pay',
    path: '/pos/water-pay',
    label: 'Payment',
    Icon: WaterIcon,
    visible: (_level, dept) => deptIs(dept, 'water', 'activit', 'aqua'),
  },

  // ── Villa: villa staff + front desk (level 3-4) ──────────────────────────────
  {
    id: 'villa',
    path: '/villa',
    label: 'Villa',
    Icon: VillaIcon,
    visible: (level, dept) =>
      deptIs(dept, 'villa', 'housekeep') || (level >= 3 && level <= 4),
  },

  // ── Gate / Front Desk tablet (level 3–4) ────────────────────────────────────
  {
    id: 'gate-hub',
    path: '/gate/hub',
    label: 'Gate',
    Icon: GateIcon,
    visible: (level) => level >= 3 && level <= 4,
  },
  {
    id: 'checkin',
    path: '/front-desk/checkin',
    label: 'Check-In',
    Icon: CheckInIcon,
    visible: (level) => level >= 3 && level <= 4,
  },
  // Band Lookup — gate tablets only (level 3–4): staff on personal phones don't need this
  {
    id: 'band-lookup',
    path: '/gate/band-lookup',
    label: 'Band',
    Icon: BandIcon,
    visible: (level) => level >= 3 && level < 5,
  },

  // ── Manager / Department Head tablet (level 5+) ──────────────────────────────
  {
    id: 'inventory',
    path: '/inventory/count',
    label: 'Inventory',
    Icon: InventoryIcon,
    visible: (level) => level >= 5,
  },
  {
    id: 'restock',
    path: '/inventory/purchase-request',
    label: 'Restock',
    Icon: RestockIcon,
    visible: (level) => level >= 5,
  },
  // Staff meals: only on manager tablets — level 1 staff use shared station devices
  {
    id: 'meals',
    path: '/inventory/quick-entry',
    label: 'Meals',
    Icon: MealsIcon,
    visible: (level) => level >= 5,
  },
  {
    id: 'maintenance',
    path: '/equipment/maintenance',
    label: 'Service',
    Icon: MaintenanceIcon,
    visible: (level) => level >= 5,
  },
  {
    id: 'manager',
    path: '/manager',
    label: 'Manager',
    Icon: ManagerIcon,
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
  const department = user?.department ?? null

  const visibleItems = NAV_ITEMS.filter((item) => item.visible(roleLevel, department))

  // Shares the same TanStack cache key as NotificationsScreen → no extra network request
  const { data: inbox } = useQuery<Notification[]>({
    queryKey: ['notifications', 'inbox'],
    queryFn: () => api.get<Notification[]>('/notifications/inbox').then((r) => r.data),
    staleTime: 30_000,
  })
  const badgeCount = inbox?.length ?? 0

  function signOut() { clearAuth(); navigate('/pin') }

  // Apply saved font-size preference from IDB at session start
  useEffect(() => { void loadFontSizePref() }, [])

  // Station tablets skip the clock screen — login drops each straight on its
  // station home. Must stay BELOW every hook: an early return above a hook
  // crashes React with error #310 (hooks order changed between renders).
  if (location.pathname === '/clock' && roleLevel < 5) {
    if (deptIs(department, 'kitchen'))                          return <Navigate to="/pos/kitchen" replace />
    if (deptIs(department, 'bar'))                              return <Navigate to="/pos/bar" replace />
    if (deptIs(department, 'front-of-house', 'waiter', 'restaurant')) return <Navigate to="/pos/tabs" replace />
    if (deptIs(department, 'spa', 'gym', 'wellness'))           return <Navigate to="/pos/spa" replace />
    if (deptIs(department, 'water', 'activit', 'aqua'))         return <Navigate to="/gate/waiver" replace />
    if (deptIs(department, 'villa', 'housekeep'))               return <Navigate to="/villa" replace />
    if (deptIs(department, 'gate', 'entry', 'secur'))           return <Navigate to="/gate/hub" replace />
  }

  return (
    <div className="h-screen flex">
      <IdleBrand />
      <OfflineBanner />

      {/* ── Left Nav Rail (sm+) ─────────────────────────────────── */}
      <aside className="hidden sm:flex flex-col w-16 lg:w-52 shrink-0 border-r border-white/5"
        style={{ background: 'rgba(11, 17, 32, 0.95)', backdropFilter: 'blur(20px)' }}>

        {/* Logo */}
        <div className="h-14 flex items-center justify-center lg:justify-start lg:px-4 border-b border-white/5">
          <span className="text-white font-bold font-serif text-lg">
            <span className="hidden lg:block">Kurahia</span>
            <span className="lg:hidden">K</span>
          </span>
        </div>

        {/* Nav items */}
        <nav className="flex-1 py-2 space-y-0.5 overflow-y-auto" aria-label="Main navigation">
          {visibleItems.map(({ id, path, label, Icon, badge }) => (
            <NavLink key={id} to={path} end={path === '/clock'}
              className={({ isActive }) => [
                'flex items-center gap-3 px-3 lg:px-4 py-2.5 mx-1 rounded-lg transition-colors',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400',
                isActive
                  ? 'bg-white/8 text-white border-l-2 border-emerald-400'
                  : 'text-white/40 hover:text-white/70 hover:bg-white/3 border-l-2 border-transparent',
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
        <div className="p-2 border-t border-white/5">
          <div className="flex items-center gap-2 px-2">
            <div className="w-8 h-8 rounded-full bg-emerald-500/20 border border-emerald-500/20
              flex items-center justify-center text-emerald-400 text-xs font-bold shrink-0">
              {user?.username?.[0]?.toUpperCase() ?? '?'}
            </div>
            <div className="hidden lg:block flex-1 min-w-0">
              <p className="text-xs font-medium text-white truncate">{user?.username}</p>
              <button onClick={signOut} className="text-[10px] text-red-400/50 hover:text-red-400">
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
          style={{ background: 'rgba(11, 17, 32, 0.9)' }}>
          <span className="text-lg font-bold font-serif text-white">Kurahia</span>
          <button onClick={signOut}
            className="w-8 h-8 rounded-full bg-emerald-500/20 flex items-center justify-center
              text-emerald-400 text-sm font-bold" aria-label="Sign out">
            {user?.username?.[0]?.toUpperCase() ?? '?'}
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
                  <div className="w-7 h-7 rounded-full border-2 border-emerald-500 border-t-transparent animate-spin" />
                </div>
              }>
                <Outlet />
              </Suspense>
            </motion.div>
          </AnimatePresence>
        </main>

        {/* Mobile bottom nav (sm: hidden since sidebar replaces it) */}
        <nav className="sm:hidden shrink-0 flex border-t border-white/5"
          style={{ background: 'rgba(11, 17, 32, 0.95)' }}
          aria-label="Main navigation">
          {visibleItems.slice(0, 5).map(({ id, path, label, Icon, badge }) => (
            <NavLink key={id} to={path} end={path === '/clock'}
              className={({ isActive }) => [
                'flex-1 flex flex-col items-center justify-center gap-0.5 py-2',
                'min-h-[56px] relative transition-colors',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400 focus-visible:ring-inset',
                isActive ? 'text-emerald-400' : 'text-white/30 hover:text-white/60',
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
