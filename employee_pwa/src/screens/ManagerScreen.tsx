import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useQuery } from '@tanstack/react-query'
import { RequireRole } from '../components/AuthGate'
import { useAuthStore } from '../stores/authStore'
import api from '../lib/axios'

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
function StaffIcon() {
  return <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
    <circle cx="10" cy="9" r="4" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M3 24c0-4 3.1-6.5 7-6.5s7 2.5 7 6.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    <path d="M19 13v6M22 16h-6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
}
function PurchaseIcon() {
  return <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
    <path d="M4 5h3l2.5 11h12l2.5-8H9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <circle cx="12" cy="21" r="1.5" stroke="currentColor" strokeWidth="1.5"/>
    <circle cx="19" cy="21" r="1.5" stroke="currentColor" strokeWidth="1.5"/>
  </svg>
}

function MenuIcon() {
  return <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
    <rect x="5" y="3" width="18" height="22" rx="2" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M9 9h10M9 14h10M9 19h6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
}
function StockAlertIcon() {
  return <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
    <path d="M5 9l2.5-4h13L23 9v13a2 2 0 01-2 2H7a2 2 0 01-2-2V9z"
      stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
    <path d="M14 13v4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    <circle cx="14" cy="19.5" r="0.75" fill="currentColor"/>
  </svg>
}
function ReorderIcon() {
  return <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
    <path d="M6 8h16M6 14h16M6 20h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    <path d="M22 17v6M19 20h6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
}

const TILES: Tile[] = [
  {
    label: 'Staff',
    description: 'Create accounts, manage access',
    path: '/manager/staff',
    Icon: StaffIcon,
  },
  {
    label: 'Menu',
    description: 'Add, price, remove items & services',
    path: '/manager/menu',
    Icon: MenuIcon,
  },
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

  const { data: alertCount = 0 } = useQuery<number>({
    queryKey: ['stock-alerts-count'],
    queryFn: () =>
      api.get<{ below_reorder: boolean }[]>('/inventory/items')
        .then(r => (Array.isArray(r.data) ? r.data : []).filter(i => i.below_reorder).length),
    refetchInterval: 30_000,
    staleTime: 25_000,
  })

  const { data: reorderCount = 0 } = useQuery<number>({
    queryKey: ['suggested-reorders-count'],
    queryFn: () =>
      api.get<{ id: string }[]>('/inventory/purchase-requests', {
        params: { status: 'DRAFT', system_generated: 'true' },
      }).then(r => (Array.isArray(r.data) ? r.data : []).length),
    refetchInterval: 60_000,
    staleTime: 55_000,
  })

  function signOut() { clearAuth(); navigate('/pin') }

  const hour = new Date().getHours()
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'

  return (
    <RequireRole minLevel={5}>
      <div className="min-h-screen p-4 md:p-6"
        style={{ background: 'linear-gradient(145deg, #0c1f1f 0%, #1a3636 50%, #0f2626 100%)' }}>
        <div className="max-w-2xl mx-auto">

        {/* Greeting header */}
        <div className="mb-6">
          <p className="text-sm text-emerald-300/60">{greeting},</p>
          <h1 className="font-serif text-3xl font-bold text-white tracking-tight">
            {user?.username ?? 'Manager'}
          </h1>
          <p className="text-xs text-emerald-200/40 mt-1">
            Operations Hub &middot; {new Date().toLocaleDateString('en-KE', { weekday: 'long', day: 'numeric', month: 'long' })}
          </p>
        </div>

        {/* Quick stats bar */}
        <div className="grid grid-cols-3 gap-2 mb-5">
          <div className="rounded-xl p-3 text-center border border-white/10"
            style={{ background: 'rgba(20, 50, 50, 0.7)', backdropFilter: 'blur(12px)' }}>
            <p className="text-lg font-bold tabular-nums text-white">{alertCount || '0'}</p>
            <p className="text-[10px] text-emerald-300/50 uppercase tracking-wide">Stock Alerts</p>
          </div>
          <div className="rounded-xl p-3 text-center border border-white/10"
            style={{ background: 'rgba(20, 50, 50, 0.7)', backdropFilter: 'blur(12px)' }}>
            <p className="text-lg font-bold tabular-nums text-white">{reorderCount || '0'}</p>
            <p className="text-[10px] text-emerald-300/50 uppercase tracking-wide">Reorders</p>
          </div>
          <div className="rounded-xl p-3 text-center border border-white/10"
            style={{ background: 'rgba(20, 50, 50, 0.7)', backdropFilter: 'blur(12px)' }}>
            <p className="text-lg font-bold tabular-nums text-white">—</p>
            <p className="text-[10px] text-emerald-300/50 uppercase tracking-wide">On Duty</p>
          </div>
        </div>

        <motion.div
          className="grid grid-cols-2 gap-3"
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
              className="flex flex-col items-start gap-3 p-4 rounded-2xl
                border border-white/10 hover:border-emerald-400/30
                transition-all text-left
                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400"
              style={{ background: 'rgba(20, 50, 50, 0.6)', backdropFilter: 'blur(14px)' }}
            >
              <span className="text-emerald-300">
                <Icon />
              </span>
              <div>
                <p className="text-sm font-semibold text-white">{label}</p>
                <p className="text-xs text-emerald-200/60 mt-0.5 leading-snug">{description}</p>
              </div>
            </motion.button>
          ))}

          {/* Stock Alerts tile — live count badge, polls every 30s */}
          <motion.button
            variants={{ hidden: { opacity: 0, y: 14 }, visible: { opacity: 1, y: 0 } }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
            whileHover={{ y: -2 }}
            whileTap={{ scale: 0.97 }}
            onClick={() => navigate('/inventory/count')}
            className="relative flex flex-col items-start gap-3 p-4 rounded-2xl border border-white/10
              hover:bg-cream-alt/40 transition-colors text-left
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark"
            aria-label={`Stock Alerts — ${alertCount > 0 ? `${alertCount} items below reorder` : 'all levels OK'}`}
          >
            <span className={alertCount > 0 ? 'text-status-failed' : 'text-emerald-300'}>
              <StockAlertIcon />
            </span>
            <div>
              <p className="text-sm font-semibold text-white">Stock Alerts</p>
              <p className="text-xs text-emerald-200/60 mt-0.5 leading-snug">
                {alertCount > 0 ? `${alertCount} item${alertCount !== 1 ? 's' : ''} below reorder` : 'All levels OK'}
              </p>
            </div>
            {alertCount > 0 && (
              <span
                aria-hidden="true"
                className="absolute top-3 right-3 min-w-[20px] h-5 rounded-full bg-status-failed
                  flex items-center justify-center text-[10px] font-bold text-white tabular-nums px-1"
              >
                {alertCount > 9 ? '9+' : alertCount}
              </span>
            )}
          </motion.button>

          {/* Suggested Reorders tile — auto-drafted purchase suggestions */}
          {reorderCount > 0 && (
            <motion.button
              variants={{ hidden: { opacity: 0, y: 14 }, visible: { opacity: 1, y: 0 } }}
              transition={{ duration: 0.25, ease: 'easeOut' }}
              whileHover={{ y: -2 }}
              whileTap={{ scale: 0.97 }}
              onClick={() => navigate('/inventory/purchase-request')}
              className="relative flex flex-col items-start gap-3 p-4 rounded-2xl border border-white/10
                hover:bg-cream-alt/40 transition-colors text-left
                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark"
              aria-label={`Suggested Reorders — ${reorderCount} suggestion${reorderCount !== 1 ? 's' : ''}`}
            >
              <span className="text-emerald-300">
                <ReorderIcon />
              </span>
              <div>
                <p className="text-sm font-semibold text-white">Suggested Reorders</p>
                <p className="text-xs text-emerald-200/60 mt-0.5 leading-snug">
                  {reorderCount} suggestion{reorderCount !== 1 ? 's' : ''} from nightly scan
                </p>
              </div>
              <span
                aria-hidden="true"
                className="absolute top-3 right-3 min-w-[20px] h-5 rounded-full bg-primary-dark
                  flex items-center justify-center text-[10px] font-bold text-white tabular-nums px-1"
              >
                {reorderCount > 9 ? '9+' : reorderCount}
              </span>
            </motion.button>
          )}

          {/* Account tile — spans full width, always last */}
          <motion.div
            variants={{ hidden: { opacity: 0, y: 14 }, visible: { opacity: 1, y: 0 } }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
            className="col-span-2 flex items-center justify-between gap-4 p-4
              rounded-2xl border border-white/10"
          >
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-primary-dark flex items-center justify-center
                text-cream-card text-base font-bold shrink-0">
                {user?.username?.[0]?.toUpperCase() ?? '?'}
              </div>
              <div>
                <p className="text-sm font-semibold text-white">{user?.username}</p>
                <p className="text-xs text-emerald-200/60">
                  {roleName(user?.role_level ?? 0)}
                  {user?.department ? ` · ${user.department}` : ''}
                </p>
              </div>
            </div>
            <button
              onClick={signOut}
              className="shrink-0 min-h-[44px] px-4 rounded-xl border border-status-failed/60
                text-status-failed text-xs font-semibold
                hover:bg-status-failed/10 active:bg-status-failed/20 transition-colors
                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-status-failed"
            >
              Sign out
            </button>
          </motion.div>
        </motion.div>
      </div>
      </div>
    </RequireRole>
  )
}
