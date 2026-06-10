import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { RequireRole } from '../components/AuthGate'
import ScreenHero from '../components/ScreenHero'
import { useAuthStore } from '../stores/authStore'

interface Tile {
  label: string
  description: string
  path: string
  Icon: () => React.ReactElement
}

function FrontDeskIcon() {
  return <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
    <rect x="3" y="8" width="22" height="15" rx="2" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M9 8V6a5 5 0 0110 0v2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    <path d="M14 15v-3M12 15h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
}
function AttendanceIcon() {
  return <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
    <circle cx="14" cy="10" r="5" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M5 24c0-5 4-8 9-8s9 3 9 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    <path d="M19 16l2 2 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
}
function ShiftIcon() {
  return <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
    <rect x="4" y="5" width="20" height="19" rx="2" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M9 3v4M19 3v4M4 12h20" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    <path d="M9 17h4M9 20.5h6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
}
function LeaveIcon() {
  return <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
    <rect x="4" y="5" width="20" height="19" rx="2" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M9 3v4M19 3v4M4 12h20" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    <path d="M9 17l3 3 7-6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
}
function CashIcon() {
  return <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
    <rect x="3" y="8" width="22" height="14" rx="2" stroke="currentColor" strokeWidth="1.5"/>
    <circle cx="14" cy="15" r="3" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M7 15h0M21 15h0" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
  </svg>
}
function PurchaseIcon() {
  return <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
    <path d="M4 5h3l2.5 11h12l2.5-8H9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <circle cx="12" cy="21" r="1.5" stroke="currentColor" strokeWidth="1.5"/>
    <circle cx="19" cy="21" r="1.5" stroke="currentColor" strokeWidth="1.5"/>
  </svg>
}

const TILES: Tile[] = [
  {
    label: 'Front Desk',
    description: 'Arrivals, departures, occupancy',
    path: '/manager/front-desk',
    Icon: FrontDeskIcon,
  },
  {
    label: 'Attendance',
    description: "Today's roster + week summary",
    path: '/manager/attendance',
    Icon: AttendanceIcon,
  },
  {
    label: 'Shifts',
    description: 'Schedule and cancel shifts',
    path: '/manager/shifts',
    Icon: ShiftIcon,
  },
  {
    label: 'Leave',
    description: 'Approve or reject leave requests',
    path: '/manager/leave',
    Icon: LeaveIcon,
  },
  {
    label: 'Cash',
    description: 'Reconcile staff cash handovers',
    path: '/manager/cash',
    Icon: CashIcon,
  },
  {
    label: 'Purchases',
    description: 'Review and propose budgets',
    path: '/manager/purchases',
    Icon: PurchaseIcon,
  },
]

function roleName(level: number) {
  if (level >= 10) return 'Owner'
  if (level >= 5)  return 'Manager'
  if (level >= 3)  return 'Gate Staff'
  return 'Staff'
}

export default function ManagerScreen() {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const clearAuth = useAuthStore((s) => s.clearAuth)

  function signOut() { clearAuth(); navigate('/pin') }

  return (
    <RequireRole minLevel={5}>
      <div className="max-w-lg mx-auto">

        <ScreenHero title="MANAGER." subtitle="DAILY OPS" />

        <motion.div
          className="p-4 grid grid-cols-2 gap-3"
          initial="hidden"
          animate="visible"
          variants={{ visible: { transition: { staggerChildren: 0.07 } } }}
        >
          {TILES.map(({ label, description, path, Icon }) => (
            <motion.button
              key={path}
              variants={{ hidden: { opacity: 0, y: 14 }, visible: { opacity: 1, y: 0 } }}
              transition={{ duration: 0.25, ease: 'easeOut' }}
              whileHover={{ y: -2 }}
              whileTap={{ scale: 0.97 }}
              onClick={() => navigate(path)}
              className="flex flex-col items-start gap-3 p-4 rounded-2xl border border-cream-alt
                bg-cream-card hover:bg-cream-alt/40 transition-colors text-left
                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark"
            >
              <span className="text-primary-dark">
                <Icon />
              </span>
              <div>
                <p className="text-sm font-semibold text-ink-primary">{label}</p>
                <p className="text-xs text-ink-tertiary mt-0.5 leading-snug">{description}</p>
              </div>
            </motion.button>
          ))}

          {/* Account tile — spans full width, always last */}
          <motion.div
            variants={{ hidden: { opacity: 0, y: 14 }, visible: { opacity: 1, y: 0 } }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
            className="col-span-2 flex items-center justify-between gap-4 p-4
              rounded-2xl border border-cream-alt bg-cream-card"
          >
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-primary-dark flex items-center justify-center
                text-cream-card text-base font-bold shrink-0">
                {user?.username?.[0]?.toUpperCase() ?? '?'}
              </div>
              <div>
                <p className="text-sm font-semibold text-ink-primary">{user?.username}</p>
                <p className="text-xs text-ink-tertiary">
                  {roleName(user?.role_level ?? 0)}
                  {user?.department ? ` · ${user.department}` : ''}
                </p>
              </div>
            </div>
            <button
              onClick={signOut}
              className="shrink-0 px-4 py-2 rounded-xl border-2 border-status-failed/30
                text-status-failed text-xs font-semibold
                hover:bg-status-failed/10 active:bg-status-failed/20 transition-colors
                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-status-failed"
            >
              Sign out
            </button>
          </motion.div>
        </motion.div>
      </div>
    </RequireRole>
  )
}
