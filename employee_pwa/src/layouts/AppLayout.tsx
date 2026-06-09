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
function GateIcon() {
  return <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
    <rect x="3" y="5" width="16" height="12" rx="2" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="11" cy="11" r="2.5" stroke="currentColor" strokeWidth="1.5" />
    <path d="M3 11h5.5M13.5 11H19" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
}
function CheckInIcon() {
  return <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
    <rect x="3" y="4" width="16" height="15" rx="2" stroke="currentColor" strokeWidth="1.5" />
    <path d="M7 2v4M15 2v4M3 10h16" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <path d="M7.5 15l2.5 2.5L15 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
}
function WaiverIcon() {
  return <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
    <rect x="4" y="3" width="14" height="17" rx="2" stroke="currentColor" strokeWidth="1.5" />
    <path d="M7 8h8M7 12h5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <path d="M12 16l1.5-1.5L15 16" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
}
function ManagerIcon() {
  return <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true">
    <path d="M3 17v-1.5C3 13 6.1 11 11 11s8 2 8 4.5V17" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <circle cx="11" cy="7" r="4" stroke="currentColor" strokeWidth="1.5" />
    <path d="M15 3l1.5 1.5L19 2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
}

// ── Role-aware top bar stats ────────────────────────────────────────────────

function TopBarStats({ roleLevel }: { roleLevel: number }) {
  // Numbers are "—" placeholders — real data wired in F-7+ via TanStack Query
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
  path: string; label: string; Icon: () => ReactElement
  minLevel: number; maxLevel?: number; badge?: boolean
}

const NAV_ITEMS: NavItem[] = [
  { path: '/clock',                label: 'Clock',      Icon: ClockIcon,    minLevel: 0 },
  { path: '/schedule',             label: 'Schedule',   Icon: ScheduleIcon, minLevel: 0 },
  { path: '/notifications',        label: 'Alerts',     Icon: BellIcon,     minLevel: 0, badge: true },
  // Level 1–2 only: waiver standalone (level 3+ access waiver from the Gate screen)
  { path: '/gate/waiver',          label: 'Waiver',     Icon: WaiverIcon,   minLevel: 1, maxLevel: 2 },
  // Level 3+: issue bands + check-in
  { path: '/gate/issue',           label: 'Issue',      Icon: GateIcon,     minLevel: 3 },
  { path: '/front-desk/checkin',   label: 'Check-In',   Icon: CheckInIcon,  minLevel: 3 },
  { path: '/profile',              label: 'Profile',    Icon: ProfileIcon,  minLevel: 0 },
  { path: '/manager',              label: 'Manager',    Icon: ManagerIcon,  minLevel: 5 },
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

  const visibleItems = NAV_ITEMS.filter(
    (item) => roleLevel >= item.minLevel && (item.maxLevel === undefined || roleLevel <= item.maxLevel)
  )

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
          className="w-8 h-8 rounded-full bg-sage-dark flex items-center justify-center
            text-cream-card text-sm font-bold focus-visible:ring-2 focus-visible:ring-sage-dark"
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
        {visibleItems.map(({ path, label, Icon, badge }) => (
          <NavLink
            key={path}
            to={path}
            end={path === '/clock'}
            className={({ isActive }) => [
              'flex-1 flex flex-col items-center justify-center gap-0.5 py-2',
              'min-h-[56px] relative transition-colors',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sage-dark focus-visible:ring-inset',
              isActive ? 'text-sage-dark' : 'text-ink-tertiary hover:text-ink-secondary',
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
