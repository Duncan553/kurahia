import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useQuery } from '@tanstack/react-query'
import { ResponsiveContainer, BarChart, Bar, Tooltip } from 'recharts'
import { RequireRole } from '../components/AuthGate'
import { useAuthStore } from '../stores/authStore'
import { ErrorBoundary } from '@shared'
import api from '../lib/axios'

interface InvItem {
  id: string; name: string; unit: string; current_stock: string
  reorder_level: string; below_reorder: boolean
}
interface BudgetRow {
  department: string; budget: string; spent: string; remaining: string
  pct_used: number; over_budget: boolean
}
interface PurchaseReq {
  id: string; item_name: string; quantity: string; status: string
  department: string; system_generated: boolean
}

function Glass({ children, className = '', onClick }: {
  children: React.ReactNode; className?: string; onClick?: () => void
}) {
  return (
    <motion.div
      whileHover={onClick ? { y: -2, boxShadow: '0 12px 40px rgba(0,0,0,0.4)' } : undefined}
      whileTap={onClick ? { scale: 0.98 } : undefined}
      onClick={onClick}
      className={`rounded-2xl border border-white/8 overflow-hidden ${onClick ? 'cursor-pointer' : ''} ${className}`}
      style={{ background: 'rgba(20, 50, 50, 0.55)', backdropFilter: 'blur(20px)', WebkitBackdropFilter: 'blur(20px)' }}
    >
      <div className="relative">
        <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-white/15 to-transparent" />
        {children}
      </div>
    </motion.div>
  )
}

function Label({ children }: { children: React.ReactNode }) {
  return <p className="text-[10px] font-bold tracking-[0.2em] uppercase text-emerald-300/50 mb-3">{children}</p>
}

// ── Inventory Behavior (full-width, hero position) ──────────────────────────

function InventorySection() {
  const navigate = useNavigate()
  const { data: items = [] } = useQuery<InvItem[]>({
    queryKey: ['mgr-inventory'],
    queryFn: () => api.get<InvItem[]>('/inventory/items').then(r => Array.isArray(r.data) ? r.data : []),
    staleTime: 30_000, refetchInterval: 60_000,
  })

  const low = items.filter(i => i.below_reorder)
  const chartData = items.slice(0, 14).map(i => ({
    name: i.name.length > 6 ? i.name.slice(0, 6) + '…' : i.name,
    stock: parseFloat(i.current_stock),
    reorder: parseFloat(i.reorder_level),
    isLow: i.below_reorder,
  }))

  return (
    <Glass className="col-span-full">
      <div className="p-5">
        <div className="flex items-center justify-between mb-4">
          <Label>Stock Behavior</Label>
          <motion.button whileTap={{ scale: 0.95 }}
            onClick={() => navigate('/inventory/count')}
            className="text-[10px] text-emerald-300 font-semibold hover:text-emerald-200 transition-colors">
            View All →
          </motion.button>
        </div>
        <div className="grid grid-cols-3 gap-4 mb-4">
          <div>
            <p className="text-3xl font-bold tabular-nums text-white">{items.length}</p>
            <p className="text-xs text-emerald-200/40">Total Items</p>
          </div>
          <div>
            <p className={`text-3xl font-bold tabular-nums ${low.length > 0 ? 'text-status-failed' : 'text-emerald-400'}`}>
              {low.length}
            </p>
            <p className="text-xs text-emerald-200/40">Need Restock</p>
          </div>
          <div>
            <p className="text-3xl font-bold tabular-nums text-emerald-400">{items.length - low.length}</p>
            <p className="text-xs text-emerald-200/40">Healthy</p>
          </div>
        </div>
        {chartData.length > 0 && (
          <div className="h-32">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
                <Bar dataKey="stock" radius={[4, 4, 0, 0]}
                  fill="rgba(16, 185, 129, 0.5)"
                  activeBar={{ fill: 'rgba(16, 185, 129, 0.8)' }} />
                <Bar dataKey="reorder" radius={[4, 4, 0, 0]}
                  fill="rgba(239, 68, 68, 0.25)" />
                <Tooltip
                  contentStyle={{ background: '#0a1f1f', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 10, fontSize: 11, color: '#fff' }}
                  labelStyle={{ color: '#6ee7b7' }}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
        {low.length > 0 && (
          <div className="mt-3 pt-3 border-t border-white/5 space-y-1.5">
            {low.slice(0, 4).map(i => (
              <div key={i.id} className="flex items-center justify-between">
                <span className="text-sm text-white">{i.name}</span>
                <span className="text-xs text-status-failed tabular-nums font-semibold">
                  {parseFloat(i.current_stock)} / {parseFloat(i.reorder_level)} {i.unit}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </Glass>
  )
}

// ── Budget Burn ──────────────────────────────────────────────────────────────

function BudgetSection() {
  const period = new Date().toISOString().slice(0, 7)
  const { data } = useQuery<{ budgets: BudgetRow[] }>({
    queryKey: ['mgr-budgets', period],
    queryFn: () => api.get(`/finance/budgets/status?period=${period}`).then(r => r.data),
    staleTime: 5 * 60_000,
  })
  const rows = (Array.isArray(data) ? data : data?.budgets ?? []).filter(r => parseFloat(r.budget) > 0)

  return (
    <Glass>
      <div className="p-5">
        <Label>Budget Burn</Label>
        {rows.length === 0 ? (
          <p className="text-sm text-emerald-200/40">No budgets set</p>
        ) : (
          <div className="space-y-3">
            {rows.slice(0, 5).map(r => (
              <div key={r.department}>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-white">{r.department}</span>
                  <span className={`font-bold tabular-nums ${r.over_budget ? 'text-status-failed' : r.pct_used > 80 ? 'text-status-pending' : 'text-emerald-400'}`}>
                    {Math.round(r.pct_used)}%
                  </span>
                </div>
                <div className="h-2 rounded-full bg-white/5 overflow-hidden">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${Math.min(r.pct_used, 100)}%` }}
                    transition={{ duration: 0.8, ease: 'easeOut' }}
                    className={`h-full rounded-full ${
                      r.over_budget ? 'bg-status-failed' : r.pct_used > 80 ? 'bg-status-pending' : 'bg-emerald-500'
                    }`}
                  />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </Glass>
  )
}

// ── Pending Approvals ────────────────────────────────────────────────────────

function ApprovalsSection() {
  const navigate = useNavigate()
  const { data: pending = [] } = useQuery<PurchaseReq[]>({
    queryKey: ['mgr-pending'],
    queryFn: () => api.get<PurchaseReq[]>('/inventory/purchase-requests', { params: { status: 'PENDING' } })
      .then(r => Array.isArray(r.data) ? r.data : []),
    staleTime: 60_000,
  })
  const { data: drafts = [] } = useQuery<PurchaseReq[]>({
    queryKey: ['mgr-drafts'],
    queryFn: () => api.get<PurchaseReq[]>('/inventory/purchase-requests', { params: { status: 'DRAFT', system_generated: 'true' } })
      .then(r => Array.isArray(r.data) ? r.data : []),
    staleTime: 60_000,
  })

  return (
    <Glass>
      <div className="p-5">
        <Label>Approvals</Label>
        <div className="grid grid-cols-2 gap-3 mb-3">
          <div>
            <p className={`text-3xl font-bold tabular-nums ${pending.length > 0 ? 'text-status-pending' : 'text-white/50'}`}>
              {pending.length}
            </p>
            <p className="text-xs text-emerald-200/40">Waiting</p>
          </div>
          <div>
            <p className="text-3xl font-bold tabular-nums text-emerald-400">{drafts.length}</p>
            <p className="text-xs text-emerald-200/40">Auto-drafted</p>
          </div>
        </div>
        {pending.length > 0 && (
          <motion.button whileTap={{ scale: 0.97 }}
            onClick={() => navigate('/manager/purchases')}
            className="w-full py-3 rounded-xl bg-emerald-500/15 text-emerald-300 text-sm font-semibold
              border border-emerald-500/20 hover:bg-emerald-500/25 transition-colors">
            Review →
          </motion.button>
        )}
      </div>
    </Glass>
  )
}

// ── Quick Nav (everything accessible, not hidden) ───────────────────────────

const SECTIONS = [
  { label: 'Schedule',   path: '/manager/shifts',     icon: '📅', desc: 'Create & manage shifts' },
  { label: 'Staff',      path: '/manager/staff',      icon: '👥', desc: 'Accounts & access' },
  { label: 'Menu',       path: '/manager/menu',       icon: '🍽', desc: 'Items, prices, recipes' },
  { label: 'Attendance', path: '/manager/attendance',  icon: '✓',  desc: "Today's roster" },
  { label: 'Front Desk', path: '/manager/front-desk',  icon: '🏨', desc: 'Arrivals & occupancy' },
  { label: 'Cash',       path: '/manager/cash',        icon: '💰', desc: 'Reconcile handovers' },
  { label: 'Leave',      path: '/manager/leave',       icon: '📋', desc: 'Approve requests' },
  { label: 'Purchases',  path: '/manager/purchases',   icon: '🛒', desc: 'Review & budget' },
]

function QuickNav() {
  const navigate = useNavigate()
  return (
    <Glass className="col-span-full">
      <div className="p-5">
        <Label>Quick Access</Label>
        <div className="grid grid-cols-4 md:grid-cols-8 gap-2">
          {SECTIONS.map(s => (
            <motion.button key={s.path}
              whileTap={{ scale: 0.92 }}
              whileHover={{ y: -2 }}
              onClick={() => navigate(s.path)}
              className="flex flex-col items-center gap-1.5 py-3 rounded-xl
                border border-white/5 hover:border-emerald-400/20 hover:bg-white/5
                transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400"
            >
              <span className="text-xl">{s.icon}</span>
              <span className="text-[10px] text-white/80 font-semibold leading-tight">{s.label}</span>
            </motion.button>
          ))}
        </div>
      </div>
    </Glass>
  )
}

// ── Main ─────────────────────────────────────────────────────────────────────

export default function ManagerScreen() {
  const navigate = useNavigate()
  const user = useAuthStore(s => s.user)
  const clearAuth = useAuthStore(s => s.clearAuth)

  const hour = new Date().getHours()
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'

  return (
    <RequireRole minLevel={5}>
      <div className="min-h-screen p-4 md:p-6"
        style={{ background: 'linear-gradient(145deg, #0c1f1f 0%, #1a3636 50%, #0f2626 100%)' }}>
        <div className="max-w-5xl mx-auto">

          {/* Greeting + account */}
          <div className="mb-6 flex items-end justify-between">
            <div>
              <p className="text-sm text-emerald-300/60">{greeting},</p>
              <h1 className="font-serif text-3xl md:text-4xl font-bold text-white tracking-tight">
                {user?.username ?? 'Manager'}
              </h1>
              <p className="text-xs text-emerald-200/40 mt-1">
                Operations Hub · {new Date().toLocaleDateString('en-KE', { weekday: 'long', day: 'numeric', month: 'long' })}
              </p>
            </div>
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-emerald-500/20 border border-emerald-500/30
                flex items-center justify-center text-emerald-300 font-bold">
                {user?.username?.[0]?.toUpperCase() ?? '?'}
              </div>
              <button onClick={() => { clearAuth(); navigate('/pin') }}
                className="text-xs text-status-failed/50 hover:text-status-failed transition-colors">
                Sign out
              </button>
            </div>
          </div>

          {/* Dashboard grid */}
          <motion.div
            initial="hidden" animate="visible"
            variants={{ visible: { transition: { staggerChildren: 0.1 } } }}
            className="grid grid-cols-1 md:grid-cols-2 gap-4"
          >
            {/* Stock Behavior — full width hero */}
            <motion.div variants={{ hidden: { opacity: 0, y: 20 }, visible: { opacity: 1, y: 0 } }}
              className="col-span-full">
              <ErrorBoundary level="tile"><InventorySection /></ErrorBoundary>
            </motion.div>

            {/* Budget + Approvals side by side */}
            <motion.div variants={{ hidden: { opacity: 0, y: 20 }, visible: { opacity: 1, y: 0 } }}>
              <ErrorBoundary level="tile"><BudgetSection /></ErrorBoundary>
            </motion.div>
            <motion.div variants={{ hidden: { opacity: 0, y: 20 }, visible: { opacity: 1, y: 0 } }}>
              <ErrorBoundary level="tile"><ApprovalsSection /></ErrorBoundary>
            </motion.div>

            {/* Quick Nav — full width, all features visible */}
            <motion.div variants={{ hidden: { opacity: 0, y: 20 }, visible: { opacity: 1, y: 0 } }}
              className="col-span-full">
              <ErrorBoundary level="tile"><QuickNav /></ErrorBoundary>
            </motion.div>
          </motion.div>
        </div>
      </div>
    </RequireRole>
  )
}
