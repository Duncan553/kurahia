import { Suspense, useEffect } from 'react'
import type { ReactElement } from 'react'
import { useLocation, useNavigate, NavLink, Outlet } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { OfflineBanner, InstallPrompt } from '@shared'
import { useAuthStore } from '../stores/authStore'
import { kvGet, kvSet } from '../lib/idb'
import { loadFontSizePref } from '../lib/fontSizePref'

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
function ApprovalsIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <rect x="3" y="3" width="14" height="14" rx="2" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M7 10l2 2 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
}
function FinanceIcon() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <circle cx="10" cy="10" r="7" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M10 6v1.5M10 12.5V14M7.5 8.5C7.5 7.5 8.5 7 10 7s2.5.5 2.5 1.5-1 1.5-2.5 1.5-2.5.5-2.5 1.5S8 13 10 13s2.5-.5 2.5-1.5"
      stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
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
  { path: '/dashboard',           label: 'Dashboard', Icon: DashboardIcon  },
  { path: '/alerts',              label: 'Alerts',    Icon: AlertsIcon     },
  { path: '/finance',             label: 'Finance',   Icon: FinanceIcon    },
  { path: '/purchase-approvals',  label: 'Approvals', Icon: ApprovalsIcon  },
  { path: '/reconciliation',      label: 'Recon',     Icon: ReconIcon      },
  { path: '/payroll',             label: 'Payroll',   Icon: PayrollIcon    },
  { path: '/staff',               label: 'Staff',     Icon: StaffIcon      },
  { path: '/bookings',            label: 'Bookings',  Icon: BookingsIcon   },
  { path: '/settings',            label: 'Settings',  Icon: SettingsIcon   },
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
      aria-label={label}
      className={({ isActive }) => [
        'flex items-center gap-3 px-4 py-3 rounded-lg mx-2 transition-colors',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#fa5c29]',
        isActive
          ? 'bg-[#fa5c29]/10 text-[#ffb59f] border-l-2 border-[#fa5c29]'
          : 'text-[#aa8980] hover:bg-white/5 hover:text-[#f9dcd5]',
      ].join(' ')}
    >
      <span className="shrink-0"><Icon /></span>
      <span className="hidden lg:block text-sm font-medium" aria-hidden="true">{label}</span>
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

  // Apply saved font-size preference from IDB at session start
  useEffect(() => { void loadFontSizePref() }, [])

  return (
    <div className="h-screen flex">

      {/* ── Sidebar — hidden on mobile, icons-only on tablet, full on desktop ── */}
      <aside className="hidden sm:flex flex-col w-16 lg:w-56 shrink-0 border-r border-white/5"
        style={{ background: 'rgba(30, 16, 12, 0.95)', backdropFilter: 'blur(20px)' }}>

        {/* Logo — matches Stitch: circle icon + "Kurahia" + "WATERFRONT CLUB" */}
        <div className="p-4 lg:p-5 border-b border-white/5">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-full bg-[#fa5c29]/15 border border-[#fa5c29]/20 flex items-center justify-center shrink-0">
              <span className="text-[#ffb59f] text-sm font-serif font-bold">K</span>
            </div>
            <div className="hidden lg:block">
              <p className="text-sm font-serif font-bold text-[#f9dcd5]">Kurahia</p>
              <p className="text-[8px] tracking-[0.2em] uppercase text-[#ffb59f]/60">Waterfront Club</p>
            </div>
          </div>
        </div>

        {/* Nav links */}
        <nav className="flex-1 py-4 space-y-0.5" aria-label="Owner navigation">
          {SIDEBAR_ITEMS.map((item) => <SideLink key={item.path} {...item} />)}
        </nav>

        {/* Member Portal button — per Stitch design */}
        <div className="px-3 pb-3 hidden lg:block">
          <button className="w-full py-2.5 rounded-lg bg-[#fa5c29] text-white text-xs font-bold tracking-wider
            hover:bg-[#ffb59f] transition-colors">
            Member Portal
          </button>
        </div>

        {/* Support + Log Out */}
        <div className="border-t border-white/5 p-3 space-y-1">
          <button className="flex items-center gap-3 w-full px-2 py-2 rounded-lg text-[#aa8980] hover:text-[#f9dcd5] transition-colors text-sm">
            <svg width="16" height="16" viewBox="0 0 20 20" fill="none"><circle cx="10" cy="10" r="7" stroke="currentColor" strokeWidth="1.5"/><path d="M10 7v3M10 13h.01" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
            <span className="hidden lg:block text-xs">Support</span>
          </button>
          <button onClick={signOut}
            className="flex items-center gap-3 w-full px-2 py-2 rounded-lg text-[#aa8980] hover:text-[#f9dcd5] transition-colors text-sm">
            <SignOutIcon />
            <span className="hidden lg:block text-xs">Log Out</span>
          </button>
        </div>
      </aside>

      {/* ── Right side: top bar + content + mobile bottom nav ─────────────── */}
      <div className="flex flex-col flex-1 min-w-0">

        {/* Top bar */}
        <header className="h-12 shrink-0 flex items-center justify-between px-4 border-b border-white/5"
          style={{ background: 'rgba(30, 16, 12, 0.9)', backdropFilter: 'blur(16px)' }}>
          <div className="flex items-center gap-1">
            <span className="sm:hidden text-base font-bold font-serif text-[#f9dcd5]">Kurahia</span>
            <span className="hidden sm:block text-sm font-medium text-[#f9dcd5]">Kurahia Dashboard</span>
          </div>
          <div className="hidden sm:flex items-center gap-1">
            <NavLink to="/" end className={({ isActive }) =>
              `px-3 py-1.5 rounded-md text-xs font-semibold transition-colors ${isActive ? 'bg-[#fa5c29] text-white' : 'text-[#aa8980] hover:text-[#f9dcd5]'}`
            }>Revenue Today</NavLink>
            <NavLink to="/alerts" className={({ isActive }) =>
              `px-3 py-1.5 rounded-md text-xs font-semibold transition-colors ${isActive ? 'bg-[#fa5c29] text-white' : 'text-[#aa8980] hover:text-[#f9dcd5]'}`
            }>Alerts Count</NavLink>
            <NavLink to="/bookings" className={({ isActive }) =>
              `px-3 py-1.5 rounded-md text-xs font-semibold transition-colors ${isActive ? 'bg-[#fa5c29] text-white' : 'text-[#aa8980] hover:text-[#f9dcd5]'}`
            }>Bookings</NavLink>
          </div>
          <div className="flex items-center gap-3">
            <button aria-label="Search" className="text-[#aa8980] hover:text-[#f9dcd5] transition-colors">
              <svg width="16" height="16" viewBox="0 0 20 20" fill="none"><circle cx="9" cy="9" r="5.5" stroke="currentColor" strokeWidth="1.5"/><path d="M13 13l4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
            </button>
            <button onClick={signOut} aria-label="Sign out"
              className="sm:hidden w-7 h-7 rounded-full bg-[#fa5c29]/20 flex items-center justify-center text-[#ffb59f] text-xs font-bold">
              {user?.username?.[0]?.toUpperCase() ?? '?'}
            </button>
          </div>
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

        {/* Mobile bottom nav — hidden on sm+ */}
        <nav className="sm:hidden shrink-0 flex border-t border-white/5"
          style={{ background: 'rgba(30, 16, 12, 0.95)' }}
          aria-label="Owner navigation">
          {SIDEBAR_ITEMS.map(({ path, label, Icon }) => (
            <NavLink
              key={path}
              to={path}
              end={path === '/dashboard'}
              className={({ isActive }) => [
                'flex-1 flex flex-col items-center justify-center gap-0.5 py-2 min-h-[56px]',
                'transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#fa5c29] focus-visible:ring-inset',
                isActive ? 'text-[#fa5c29]' : 'text-[#aa8980] hover:text-[#f9dcd5]',
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
