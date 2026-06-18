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
  reorder_level: string; below_reorder: boolean; department_id: string
}
interface DeptInfo { id: string; name: string }
interface BudgetRow {
  department: string; budget: string; spent: string; remaining: string
  pct_used: number; over_budget: boolean
}
interface PurchaseReq {
  id: string; item_name: string; quantity: string; status: string
}

// ── Glass Card ──────────────────────────────────────────────────────────────

function Glass({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-2xl border border-white/6 overflow-hidden ${className}`}
      style={{ background: 'rgba(15, 23, 42, 0.7)', backdropFilter: 'blur(20px)' }}>
      <div className="relative">
        <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-white/10 to-transparent" />
        {children}
      </div>
    </div>
  )
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return <p className="text-[11px] font-semibold tracking-wider uppercase text-white/30 mb-3">{children}</p>
}

// ── Overview Content ────────────────────────────────────────────────────────

function OverviewContent() {
  const navigate = useNavigate()
  const { data: items = [] } = useQuery<InvItem[]>({
    queryKey: ['mgr-inventory'],
    queryFn: () => api.get<InvItem[]>('/inventory/items').then(r => Array.isArray(r.data) ? r.data : []),
    staleTime: 30_000, refetchInterval: 60_000,
  })
  const { data: meta } = useQuery<{ departments: DeptInfo[] }>({
    queryKey: ['users-meta'],
    queryFn: () => api.get('/auth/users/meta').then(r => r.data),
    staleTime: 5 * 60_000,
  })
  const deptName = (id: string) => meta?.departments.find(d => d.id === id)?.name ?? 'Other'
  const low = items.filter(i => i.below_reorder)
  const byDept = items.reduce<Record<string, { total: number; low: number }>>((acc, i) => {
    const d = deptName(i.department_id)
    if (!acc[d]) acc[d] = { total: 0, low: 0 }
    acc[d].total++
    if (i.below_reorder) acc[d].low++
    return acc
  }, {})
  const chartData = items.slice(0, 14).map(i => ({
    name: i.name.length > 6 ? i.name.slice(0, 6) + '…' : i.name,
    stock: parseFloat(i.current_stock),
    reorder: parseFloat(i.reorder_level),
  }))

  const period = new Date().toISOString().slice(0, 7)
  const { data: budgetData } = useQuery<{ budgets: BudgetRow[] }>({
    queryKey: ['mgr-budgets', period],
    queryFn: () => api.get(`/finance/budgets/status?period=${period}`).then(r => r.data),
    staleTime: 5 * 60_000,
  })
  const budgets = (Array.isArray(budgetData) ? budgetData : budgetData?.budgets ?? []).filter(r => parseFloat(r.budget) > 0)

  const { data: pending = [] } = useQuery<PurchaseReq[]>({
    queryKey: ['mgr-pending'],
    queryFn: () => api.get<PurchaseReq[]>('/inventory/purchase-requests', { params: { status: 'PENDING' } })
      .then(r => Array.isArray(r.data) ? r.data : []),
    staleTime: 60_000,
  })

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-5">

      {/* Stock + Approvals row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Stock metrics */}
        <Glass className="lg:col-span-2">
          <div className="p-5">
            <div className="flex items-center justify-between">
              <SectionLabel>Stock Behavior</SectionLabel>
              <button onClick={() => navigate('/inventory/count')} className="text-[10px] text-emerald-400 font-semibold hover:text-emerald-300">View All →</button>
            </div>
            <div className="grid grid-cols-3 gap-4 mb-4">
              <div>
                <p className="text-3xl font-bold tabular-nums text-white">{items.length}</p>
                <p className="text-xs text-white/30">Total Items</p>
              </div>
              <div>
                <p className={`text-3xl font-bold tabular-nums ${low.length > 0 ? 'text-red-400' : 'text-emerald-400'}`}>
                  {low.length}
                </p>
                <p className="text-xs text-white/30">Need Restock</p>
              </div>
              <div>
                <p className="text-3xl font-bold tabular-nums text-emerald-400">{items.length - low.length}</p>
                <p className="text-xs text-white/30">Healthy</p>
              </div>
            </div>
            {chartData.length > 0 && (
              <div className="h-28">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData}>
                    <Bar dataKey="stock" fill="rgba(16, 185, 129, 0.4)" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="reorder" fill="rgba(239, 68, 68, 0.2)" radius={[4, 4, 0, 0]} />
                    <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 10, fontSize: 11, color: '#fff' }} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
            {/* Department breakdown */}
            {Object.keys(byDept).length > 0 && (
              <div className="mt-4 pt-4 border-t border-white/5">
                <p className="text-[10px] text-white/30 uppercase tracking-wider mb-2">By Department</p>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                  {Object.entries(byDept).map(([dept, { total, low: dLow }]) => (
                    <div key={dept} className="flex items-center justify-between p-2 rounded-lg bg-white/3">
                      <span className="text-xs text-white/70 truncate">{dept}</span>
                      <div className="flex items-center gap-2 shrink-0">
                        <span className="text-xs tabular-nums text-white/50">{total}</span>
                        {dLow > 0 && (
                          <span className="text-[10px] tabular-nums text-red-400 font-bold">⚠ {dLow}</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </Glass>

        {/* Approvals */}
        <Glass>
          <div className="p-5">
            <SectionLabel>Pending</SectionLabel>
            <p className={`text-4xl font-bold tabular-nums ${pending.length > 0 ? 'text-amber-400' : 'text-white/30'}`}>
              {pending.length}
            </p>
            <p className="text-xs text-white/30 mb-4">purchase requests</p>
            {pending.length > 0 && (
              <div className="space-y-1.5">
                {pending.slice(0, 3).map(r => (
                  <p key={r.id} className="text-xs text-white/60 truncate">• {r.item_name}</p>
                ))}
              </div>
            )}
          </div>
        </Glass>
      </div>

      {/* Budget + Low stock row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Glass>
          <div className="p-5">
            <SectionLabel>Budget Burn</SectionLabel>
            {budgets.length === 0 ? (
              <p className="text-sm text-white/30">No budgets configured</p>
            ) : (
              <div className="space-y-3">
                {budgets.slice(0, 5).map(r => (
                  <div key={r.department}>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-white/70">{r.department}</span>
                      <span className={`font-bold tabular-nums ${r.over_budget ? 'text-red-400' : r.pct_used > 80 ? 'text-amber-400' : 'text-emerald-400'}`}>
                        {Math.round(r.pct_used)}%
                      </span>
                    </div>
                    <div className="h-1.5 rounded-full bg-white/5 overflow-hidden">
                      <motion.div initial={{ width: 0 }} animate={{ width: `${Math.min(r.pct_used, 100)}%` }}
                        transition={{ duration: 0.8, ease: 'easeOut' }}
                        className={`h-full rounded-full ${r.over_budget ? 'bg-red-500' : r.pct_used > 80 ? 'bg-amber-500' : 'bg-emerald-500'}`} />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </Glass>

        <Glass>
          <div className="p-5">
            <SectionLabel>Low Stock Items</SectionLabel>
            {low.length === 0 ? (
              <p className="text-sm text-emerald-400/60">All stock healthy ✓</p>
            ) : (
              <div className="space-y-2">
                {low.slice(0, 6).map(i => (
                  <div key={i.id} className="flex justify-between text-sm">
                    <span className="text-white/70 truncate">{i.name}</span>
                    <span className="text-red-400 tabular-nums font-semibold shrink-0 ml-2">
                      {parseFloat(i.current_stock)} {i.unit}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </Glass>
      </div>

      {/* ── Action tiles — ALL features accessible ──────────────── */}
      <div>
        <SectionLabel>Manage</SectionLabel>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: 'Staff',       desc: 'Create accounts, manage access', path: '/manager/staff',      icon: '👥' },
            { label: 'Menu',        desc: 'Add, price, recipes',            path: '/manager/menu',       icon: '🍽' },
            { label: 'Shifts',      desc: 'Schedule everyone',              path: '/manager/shifts',     icon: '📅' },
            { label: 'Attendance',  desc: "Today's roster",                 path: '/manager/attendance', icon: '✓' },
            { label: 'Front Desk',  desc: 'Arrivals, departures',           path: '/manager/front-desk', icon: '🏨' },
            { label: 'Cash',        desc: 'Reconcile handovers',            path: '/manager/cash',       icon: '💰' },
            { label: 'Leave',       desc: 'Approve requests',               path: '/manager/leave',      icon: '📋' },
            { label: 'Purchases',   desc: 'Review & propose',               path: '/manager/purchases',  icon: '🛒' },
          ].map(t => (
            <motion.button key={t.path}
              whileHover={{ y: -3 }}
              whileTap={{ scale: 0.96 }}
              onClick={() => navigate(t.path)}
              className="text-left p-4 rounded-2xl border border-white/6
                hover:border-white/15 transition-all
                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400"
              style={{ background: 'rgba(15, 23, 42, 0.5)', backdropFilter: 'blur(16px)' }}
            >
              <span className="text-xl block mb-2">{t.icon}</span>
              <p className="text-sm font-semibold text-white">{t.label}</p>
              <p className="text-[10px] text-white/40 mt-0.5">{t.desc}</p>
            </motion.button>
          ))}
        </div>
      </div>
    </motion.div>
  )
}

// ── Main Layout ─────────────────────────────────────────────────────────────

export default function ManagerScreen() {
  const user = useAuthStore(s => s.user)

  const hour = new Date().getHours()
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'

  return (
    <RequireRole minLevel={5}>
      <div className="p-4 md:p-6 max-w-5xl mx-auto">

        {/* Greeting */}
        <div className="mb-6">
          <p className="text-sm text-white/30">{greeting},</p>
          <h1 className="font-serif text-2xl md:text-3xl font-bold text-white tracking-tight">
            {user?.username ?? 'Manager'}
          </h1>
          <p className="text-xs text-white/20 mt-1">
            Operations Hub · {new Date().toLocaleDateString('en-KE', { weekday: 'long', day: 'numeric', month: 'long' })}
          </p>
        </div>

        <ErrorBoundary level="tile">
          <OverviewContent />
        </ErrorBoundary>
      </div>
    </RequireRole>
  )
}
