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
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <circle cx="10" cy="10" r="7.5" stroke="currentColor" strokeWidth="1.5" />
    <path d="M10 6v4.5l3 2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
}
function ScheduleIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <rect x="3" y="3.5" width="14" height="14" rx="2" stroke="currentColor" strokeWidth="1.5" />
    <path d="M7 1.5v4M13 1.5v4M3 9h14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M7 12.5h2M12 12.5h2M7 15.5h2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
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
function BandIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <circle cx="8.5" cy="8.5" r="5.5" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M13 13l4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M6 8.5h5M8.5 6v5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
}
// Gate: wristband icon
function GateIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <rect x="2.5" y="4.5" width="15" height="11" rx="2" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="10" cy="10" r="2.5" stroke="currentColor" strokeWidth="1.5" />
    <path d="M2.5 10h5M12.5 10h5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
}
// Check-in: calendar + check
function CheckInIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <rect x="3" y="3.5" width="14" height="14" rx="2" stroke="currentColor" strokeWidth="1.5" />
    <path d="M7 1.5v4M13 1.5v4M3 9h14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M7 13l2.5 2.5L14 11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
}
// Waiver: document + pen
function WaiverIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <rect x="4" y="2" width="12" height="16" rx="2" stroke="currentColor" strokeWidth="1.5" />
    <path d="M7 7h6M7 10.5h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M11.5 14.5l1.5-1.5L14.5 14.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
}
// Inventory: grid
function InventoryIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <rect x="2.5" y="2.5" width="6" height="6" rx="1.5" stroke="currentColor" strokeWidth="1.5"/>
    <rect x="11.5" y="2.5" width="6" height="6" rx="1.5" stroke="currentColor" strokeWidth="1.5"/>
    <rect x="2.5" y="11.5" width="6" height="6" rx="1.5" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M11.5 14.5h6M14.5 11.5v6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
}
// Restock: clipboard + arrow up
function RestockIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <rect x="3.5" y="3.5" width="13" height="15" rx="2" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M7.5 3.5V2.5a1 1 0 011-1h3a1 1 0 011 1v1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M10 8.5v5.5M7.5 11L10 8.5l2.5 2.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
}
// Meals: utensils
function MealsIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M10 2.5v4M6.5 3.5c0 3 1.5 4.5 3.5 4.5s3.5-1.5 3.5-4.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M10 8v9.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M5.5 13h9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
}
// Safety check: shield + checkmark
function SafetyIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M10 2.5L3.5 5.5v4.5c0 4 2.5 7.5 6.5 8.5 4-1 6.5-4.5 6.5-8.5V5.5L10 2.5z"
      stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M7.5 10l2 2.5L13.5 8.5" stroke="currentColor" strokeWidth="1.5"
      strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
}
// Maintenance: wrench
function MaintenanceIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M13.5 4a3.5 3.5 0 00-3.5 3.5c0 .5.1 1 .3 1.4L3.5 15.5a1.2 1.2 0 001.7 1.7l6.6-6.8c.4.2.9.3 1.4.3A3.5 3.5 0 0013.5 4z"
      stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M13.5 4v2.5h-2.5" stroke="currentColor" strokeWidth="1.5"
      strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
}
// Manager: person + check badge
function ManagerIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M3 16v-1c0-2.5 3-4.5 7-4.5s7 2 7 4.5v1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    <circle cx="10" cy="6.5" r="3.5" stroke="currentColor" strokeWidth="1.5" />
    <path d="M14 2.5l1.5 1.5L18 1.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
}

// Waiter pad: notepad + pen stroke
function WaiterIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <rect x="3.5" y="2" width="13" height="16" rx="2" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M7 6h6M7 9h6M7 12h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M15 16.5l2 2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
}
// Kitchen: pot/flame
function KitchenIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M3.5 9h13v6.5a2 2 0 01-2 2h-9a2 2 0 01-2-2V9z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M3 9h14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M7.5 9V6.5c0-1.2.8-2 .8-3.5M12 9V6.5c0-1.2.8-2 .8-3.5"
      stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M7.5 13.5h5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
}
// Bar: cocktail glass
function BarIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M4.5 3.5l5.5 7.5 5.5-7.5H4.5z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M10 11v5.5M6.5 16.5h7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M6.5 7h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
}
// Spa/Gym: leaf
function SpaGymIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M10 17C10 17 3.5 13 3.5 8a6.5 6.5 0 0113 0C16.5 13 10 17 10 17z"
      stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M10 17V9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
}
// Water: wave
function WaterIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M2 11c1.3-2.5 2.6-2.5 4 0s2.6 2.5 4 0 2.6-2.5 4 0 2.6 2.5 4 0"
      stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M2 6.5c1.3-2.5 2.6-2.5 4 0s2.6 2.5 4 0 2.6-2.5 4 0 2.6 2.5 4 0"
      stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M2 15.5c1.3-2.5 2.6-2.5 4 0s2.6 2.5 4 0 2.6-2.5 4 0 2.6 2.5 4 0"
      stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
}
// Villa: house
function VillaIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M3 9.5L10 3l7 6.5v8a1 1 0 01-1 1H4a1 1 0 01-1-1v-8z"
      stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <rect x="7.5" y="13" width="5" height="5.5" rx="0.5" stroke="currentColor" strokeWidth="1.5"/>
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
// Personal chrome: managers always; gate staff (level 3-4) always; level 1 only when NOT on station
const personal = (level: number, dept: string | null) => level >= 3 || !isStation(dept)

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
        style={{ background: 'rgba(30, 16, 12, 0.95)', backdropFilter: 'blur(20px)' }}>

        {/* Logo */}
        <div className="h-14 flex items-center justify-center lg:justify-start lg:px-4 border-b border-white/5">
          <span className="text-[#f9dcd5] font-bold font-serif text-lg">
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
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#fa5c29]',
                isActive
                  ? 'bg-[#fa5c29]/10 text-[#ffb59f]'
                  : 'text-[#aa8980] hover:text-[#f9dcd5] hover:bg-white/5',
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
            <div className="w-8 h-8 rounded-full bg-[#fa5c29]/20 border border-[#fa5c29]/20
              flex items-center justify-center text-[#fa5c29] text-xs font-bold shrink-0">
              {user?.username?.[0]?.toUpperCase() ?? '?'}
            </div>
            <div className="hidden lg:block flex-1 min-w-0">
              <p className="text-xs font-medium text-[#f9dcd5] truncate">{user?.username}</p>
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
          style={{ background: 'rgba(30, 16, 12, 0.9)' }}>
          <span className="text-lg font-bold font-serif text-[#f9dcd5]">Kurahia</span>
          <button onClick={signOut}
            className="w-8 h-8 rounded-full bg-[#fa5c29]/20 flex items-center justify-center
              text-[#fa5c29] text-sm font-bold" aria-label="Sign out">
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
                  <div className="w-7 h-7 rounded-full border-2 border-[#fa5c29] border-t-transparent animate-spin" />
                </div>
              }>
                <Outlet />
              </Suspense>
            </motion.div>
          </AnimatePresence>
        </main>

        {/* Mobile bottom nav (sm: hidden since sidebar replaces it) */}
        <nav className="sm:hidden shrink-0 flex border-t border-white/5"
          style={{ background: 'rgba(30, 16, 12, 0.95)' }}
          aria-label="Main navigation">
          {visibleItems.slice(0, 5).map(({ id, path, label, Icon, badge }) => (
            <NavLink key={id} to={path} end={path === '/clock'}
              className={({ isActive }) => [
                'flex-1 flex flex-col items-center justify-center gap-0.5 py-2',
                'min-h-[56px] relative transition-colors',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#fa5c29] focus-visible:ring-inset',
                isActive ? 'text-[#fa5c29]' : 'text-[#aa8980] hover:text-[#f9dcd5]',
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
