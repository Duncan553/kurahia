import type { ReactElement } from 'react'
import { useLocation, useNavigate, NavLink, Outlet } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { useQuery } from '@tanstack/react-query'
import { useAuthStore } from '../stores/authStore'
import api from '../lib/axios'
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

// ── Department helper ──────────────────────────────────────────────────────────

function deptIs(dept: string | null, ...keywords: string[]): boolean {
  if (!dept) return false
  const d = dept.toLowerCase()
  return keywords.some((k) => d.includes(k))
}

// ── Role-aware top bar stats ────────────────────────────────────────────────

function TopBarStats({ roleLevel }: { roleLevel: number }) {
  if (roleLevel >= 5) return (
    <div className="hidden sm:flex items-center gap-4 text-xs text-ink-tertiary">
      <span><span className="font-semibold text-ink-primary">—</span> approvals</span>
      <span><span className="font-semibold text-ink-primary">—</span> alerts</span>
      <span><span className="font-semibold text-ink-primary">—</span> on duty</span>
    </div>
  )
  if (roleLevel >= 3) return (
    <div className="hidden sm:flex items-center gap-4 text-xs text-ink-tertiary">
      <span><span className="font-semibold text-ink-primary">—</span> wristbands</span>
      <span><span className="font-semibold text-ink-primary">—</span> headcount</span>
    </div>
  )
  return (
    <div className="hidden sm:flex items-center gap-4 text-xs text-ink-tertiary">
      <span><span className="font-semibold text-ink-primary">—</span> open tabs</span>
      <span><span className="font-semibold text-ink-primary">—</span> tables</span>
    </div>
  )
}

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
    visible: () => true,
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
    visible: () => true,
  },
  {
    id: 'profile',
    path: '/profile',
    label: 'Profile',
    Icon: ProfileIcon,
    visible: (level) => level < 5,  // managers use the Account tile in Manager hub instead
  },

  // ── Waiver + Safety: water activities station only ──────────────────────────
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

  // ── Gate / Front Desk tablet (level 3–4) ────────────────────────────────────
  {
    id: 'issue',
    path: '/gate/issue',
    label: 'Issue',
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
  // Band Lookup — level 1+: any staff can look up a band (waiter charging to tab, spa, etc.)
  {
    id: 'band-lookup',
    path: '/gate/band-lookup',
    label: 'Band',
    Icon: BandIcon,
    visible: (level) => level >= 1,
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
  // Staff meals: any staff (level 1+) can log; spoilage requires manager
  {
    id: 'meals',
    path: '/inventory/quick-entry',
    label: 'Meals',
    Icon: MealsIcon,
    visible: (level) => level >= 1,  // POST /inventory/movements/staff-meal allows level 1+
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

  return (
    <div className="h-screen flex flex-col bg-cream-card">

      {/* ── Top bar ─────────────────────────────────────────────── */}
      <header className="h-14 shrink-0 flex items-center justify-between px-4
        bg-cream-card border-b border-cream-alt">
        <span className="text-lg font-bold font-serif text-ink-primary">Kurahia</span>
        <TopBarStats roleLevel={roleLevel} />
        <button
          onClick={signOut}
          className="w-8 h-8 rounded-full bg-primary-dark flex items-center justify-center
            text-cream-card text-sm font-bold focus-visible:ring-2 focus-visible:ring-primary-dark"
          aria-label="Sign out"
        >
          {user?.username?.[0]?.toUpperCase() ?? '?'}
        </button>
      </header>

      {/* ── Page content ────────────────────────────────────────── */}
      <main className="flex-1 overflow-y-auto">
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
            <Outlet />
          </motion.div>
        </AnimatePresence>
      </main>

      {/* ── Bottom nav ──────────────────────────────────────────── */}
      <nav className="shrink-0 flex border-t border-cream-alt bg-cream-card"
        aria-label="Main navigation">
        {visibleItems.map(({ id, path, label, Icon, badge }) => (
          <NavLink
            key={id}
            to={path}
            end={path === '/clock'}
            className={({ isActive }) => [
              'flex-1 flex flex-col items-center justify-center gap-0.5 py-2',
              'min-h-[56px] relative transition-colors',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark focus-visible:ring-inset',
              isActive ? 'text-primary-dark' : 'text-ink-tertiary hover:text-ink-secondary',
            ].join(' ')}
          >
            <span className="relative">
              <Icon />
              {badge && badgeCount > 0 && (
                <span className="absolute -top-1 -right-1 min-w-[16px] h-4 rounded-full
                  bg-status-failed text-cream-card text-[10px] font-bold
                  flex items-center justify-center px-1">
                  {badgeCount > 9 ? '9+' : badgeCount}
                </span>
              )}
            </span>
            <span className="text-[10px] font-medium leading-none">{label}</span>
          </NavLink>
        ))}
      </nav>

    </div>
  )
}
