import type { ReactElement } from 'react'
import { useLocation, useNavigate, NavLink, Outlet } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { OfflineBanner, InstallPrompt } from '@shared'
import { useAuthStore } from '../stores/authStore'
import { kvGet, kvSet } from '../lib/idb'

// ── Sidebar + bottom nav icons ──────────────────────────────────────────────

function DashboardIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <rect x="2" y="2" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.5" />
    <rect x="11" y="2" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.5" />
    <rect x="2" y="11" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.5" />
    <rect x="11" y="11" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.5" />
  </svg>
}

function AlertsIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M10 3a6 6 0 00-6 6v3.5L2.5 15h15L16 12.5V9a6 6 0 00-6-6z"
      stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
    <path d="M8.5 15.5a1.5 1.5 0 003 0" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <circle cx="15" cy="4" r="2.5" fill="var(--color-status-failed)" />
  </svg>
}
function StaffIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <circle cx="7" cy="7" r="3" stroke="currentColor" strokeWidth="1.5" />
    <path d="M2 17c0-2.8 2.2-5 5-5s5 2.2 5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <circle cx="14" cy="7" r="2.5" stroke="currentColor" strokeWidth="1.5" />
    <path d="M17 17c0-2.2-1.3-4-3-4.7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
}
function BookingsIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <rect x="3" y="4" width="14" height="13" rx="2" stroke="currentColor" strokeWidth="1.5" />
    <path d="M7 2v4M13 2v4M3 9h14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <path d="M7 13h2M11 13h2M7 16h2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
}
function PayrollIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <circle cx="8" cy="7" r="3.5" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M2 17c0-3.3 2.7-6 6-6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    <path d="M13 10v7M10 13h6M10 17h6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
}
function ReconIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <rect x="2" y="5" width="16" height="11" rx="1.5" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M6 5V3.5M14 5V3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    <path d="M5 10h3M9 10h6M5 13h4M11 13h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
}
function SettingsIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <circle cx="10" cy="10" r="3" stroke="currentColor" strokeWidth="1.5" />
    <path d="M10 2v2M10 16v2M2 10h2M16 10h2M4.22 4.22l1.42 1.42M14.36 14.36l1.42 1.42M4.22 15.78l1.42-1.42M14.36 5.64l1.42-1.42"
      stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
}
function SignOutIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M8 10h9M14 7l3 3-3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M12 4H5a2 2 0 00-2 2v8a2 2 0 002 2h7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
  </svg>
}

// ── Nav items ───────────────────────────────────────────────────────────────

interface NavItem { path: string; label: string; Icon: () => ReactElement }

const SIDEBAR_ITEMS: NavItem[] = [
  { path: '/dashboard',       label: 'Dashboard', Icon: DashboardIcon },
  { path: '/alerts',          label: 'Alerts',    Icon: AlertsIcon    },
  { path: '/reconciliation',  label: 'Recon',     Icon: ReconIcon     },
  { path: '/payroll',         label: 'Payroll',   Icon: PayrollIcon   },
  { path: '/staff',           label: 'Staff',     Icon: StaffIcon     },
  { path: '/bookings',        label: 'Bookings',  Icon: BookingsIcon  },
  { path: '/settings',        label: 'Settings',  Icon: SettingsIcon  },
]

// ── Page transition ─────────────────────────────────────────────────────────

const pageVariants = {
  initial: { opacity: 0, x: 20 },
  animate: { opacity: 1, x: 0  },
  exit:    { opacity: 0        },
}

// ── Shared sidebar link ─────────────────────────────────────────────────────

function SideLink({ path, label, Icon }: NavItem) {
  return (
    <NavLink
      to={path}
      end={path === '/dashboard'}
      className={({ isActive }) => [
        'flex items-center gap-3 px-4 py-3 rounded-lg mx-2 transition-colors',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark',
        isActive
          ? 'bg-primary-dark/20 text-cream-card'
          : 'text-cream-card/60 hover:bg-cream-card/10 hover:text-cream-card',
      ].join(' ')}
    >
      <span className="shrink-0"><Icon /></span>
      <span className="hidden lg:block text-sm font-medium">{label}</span>
    </NavLink>
  )
}

// ── AppLayout ───────────────────────────────────────────────────────────────

export default function AppLayout() {
  const location = useLocation()
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const clearAuth = useAuthStore((s) => s.clearAuth)

  function signOut() { clearAuth(); navigate('/pin') }

  return (
    <div className="h-screen flex bg-cream-card">

      {/* ── Sidebar — hidden on mobile, icons-only on tablet, full on desktop ── */}
      <aside className="hidden sm:flex flex-col w-14 lg:w-60 bg-ink-primary shrink-0">

        {/* Logo */}
        <div className="h-14 flex items-center px-4 border-b border-cream-card/10">
          <span className="text-cream-card font-bold font-serif text-lg leading-none">
            <span className="hidden lg:block">Kurahia</span>
            <span className="lg:hidden">K</span>
          </span>
        </div>

        {/* Nav links */}
        <nav className="flex-1 py-3 space-y-1" aria-label="Owner navigation">
          {SIDEBAR_ITEMS.map((item) => <SideLink key={item.path} {...item} />)}
        </nav>

        {/* User + sign out */}
        <div className="border-t border-cream-card/10 p-3 flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-primary-dark flex items-center justify-center
            text-cream-card text-sm font-bold shrink-0">
            {user?.username?.[0]?.toUpperCase() ?? '?'}
          </div>
          <div className="hidden lg:block flex-1 min-w-0">
            <p className="text-xs font-medium text-cream-card truncate">{user?.username}</p>
            <p className="text-[10px] text-cream-card/50">Owner</p>
          </div>
          <button onClick={signOut} aria-label="Sign out"
            className="text-cream-card/50 hover:text-cream-card transition-colors shrink-0">
            <SignOutIcon />
          </button>
        </div>
      </aside>

      {/* ── Right side: top bar + content + mobile bottom nav ─────────────── */}
      <div className="flex flex-col flex-1 min-w-0">

        {/* Top bar */}
        <header className="h-14 shrink-0 flex items-center justify-between px-4
          bg-cream-card border-b border-cream-alt">
          <span className="sm:hidden text-lg font-bold font-serif text-ink-primary">Kurahia</span>
          <div className="hidden sm:flex items-center gap-5 text-xs text-ink-tertiary">
            <span><span className="font-semibold text-ink-primary">—</span> revenue today</span>
            <span><span className="font-semibold text-ink-primary">—</span> alerts open</span>
            <span><span className="font-semibold text-ink-primary">—</span> bookings this weekend</span>
          </div>
          {/* Mobile sign-out */}
          <button onClick={signOut}
            className="sm:hidden w-8 h-8 rounded-full bg-primary-dark flex items-center justify-center
              text-cream-card text-sm font-bold"
            aria-label="Sign out">
            {user?.username?.[0]?.toUpperCase() ?? '?'}
          </button>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto">
          <OfflineBanner />
          {/* Install card on the dashboard only — polite, 7-day dismiss cooldown */}
          {(location.pathname === '/' || location.pathname.startsWith('/dashboard')) &&
            <InstallPrompt kvGet={kvGet} kvSet={kvSet} />}
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

        {/* Mobile bottom nav — hidden on sm+ */}
        <nav className="sm:hidden shrink-0 flex border-t border-cream-alt bg-cream-card"
          aria-label="Owner navigation">
          {SIDEBAR_ITEMS.map(({ path, label, Icon }) => (
            <NavLink
              key={path}
              to={path}
              end={path === '/dashboard'}
              className={({ isActive }) => [
                'flex-1 flex flex-col items-center justify-center gap-0.5 py-2 min-h-[56px]',
                'transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark focus-visible:ring-inset',
                isActive ? 'text-primary-dark' : 'text-ink-tertiary hover:text-ink-secondary',
              ].join(' ')}
            >
              <Icon />
              <span className="text-[9px] font-medium leading-none">{label}</span>
            </NavLink>
          ))}
        </nav>

      </div>
    </div>
  )
}
