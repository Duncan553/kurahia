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
interface PurchaseReq { id: string; item_name: string; quantity: string; status: string }

const anim = { hidden: { opacity: 0, y: 16 }, visible: { opacity: 1, y: 0 } }

function G({ children, className = '', onClick }: {
  children: React.ReactNode; className?: string; onClick?: () => void
}) {
  return (
    <motion.div variants={anim}
      whileHover={onClick ? { y: -3, boxShadow: '0 16px 48px rgba(0,0,0,0.4)' } : undefined}
      whileTap={onClick ? { scale: 0.98 } : undefined}
      onClick={onClick}
      className={`rounded-2xl overflow-hidden ${onClick ? 'cursor-pointer' : ''} ${className}`}
      style={{ background: 'rgba(255,255,255,0.05)', backdropFilter: 'blur(20px)', border: '1px solid rgba(255,255,255,0.1)', boxShadow: '0 8px 32px rgba(0,0,0,0.36)' }}>
      <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-white/15 to-transparent" style={{ position: 'relative' }} />
      {children}
    </motion.div>
  )
}

export default function ManagerScreen() {
  const navigate = useNavigate()
  const user = useAuthStore(s => s.user)

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
  const period = new Date().toISOString().slice(0, 7)
  const { data: budgetData } = useQuery<{ budgets: BudgetRow[] }>({
    queryKey: ['mgr-budgets', period],
    queryFn: () => api.get(`/finance/budgets/status?period=${period}`).then(r => r.data),
    staleTime: 5 * 60_000,
  })
  const { data: pending = [] } = useQuery<PurchaseReq[]>({
    queryKey: ['mgr-pending'],
    queryFn: () => api.get<PurchaseReq[]>('/inventory/purchase-requests', { params: { status: 'PENDING' } })
      .then(r => Array.isArray(r.data) ? r.data : []),
    staleTime: 60_000,
  })

  const deptName = (id: string) => meta?.departments.find(d => d.id === id)?.name ?? 'Other'
  const low = items.filter(i => i.below_reorder)
  const budgets = (Array.isArray(budgetData) ? budgetData : budgetData?.budgets ?? []).filter(r => parseFloat(r.budget) > 0)
  const byDept = items.reduce<Record<string, { total: number; low: number }>>((acc, i) => {
    const d = deptName(i.department_id)
    if (!acc[d]) acc[d] = { total: 0, low: 0 }
    acc[d].total++
    if (i.below_reorder) acc[d].low++
    return acc
  }, {})
  const chartData = items.slice(0, 12).map(i => ({
    name: i.name.length > 5 ? i.name.slice(0, 5) + '…' : i.name,
    stock: parseFloat(i.current_stock),
    reorder: parseFloat(i.reorder_level),
  }))

  const hour = new Date().getHours()
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'

  const ACTIONS = [
    { label: 'Staff',       path: '/manager/staff',      icon: '👥' },
    { label: 'Menu',        path: '/manager/menu',       icon: '🍽' },
    { label: 'Shifts',      path: '/manager/shifts',     icon: '📅' },
    { label: 'Attendance',  path: '/manager/attendance',  icon: '✓' },
    { label: 'Front Desk',  path: '/manager/front-desk',  icon: '🏨' },
    { label: 'Cash',        path: '/manager/cash',        icon: '💰' },
    { label: 'Leave',       path: '/manager/leave',       icon: '📋' },
    { label: 'Purchases',   path: '/manager/purchases',   icon: '🛒' },
  ]

  return (
    <RequireRole minLevel={5}>
      <div className="p-4 md:p-6 max-w-6xl mx-auto">
        <motion.div initial="hidden" animate="visible"
          variants={{ visible: { transition: { staggerChildren: 0.06 } } }}>

          {/* ── Row 1: Greeting + Pending approvals ──────────────── */}
          <div className="grid grid-cols-1 md:grid-cols-[1fr_280px] gap-4 mb-4">
            <motion.div variants={anim}>
              <p className="text-sm text-white/30">{greeting},</p>
              <h1 className="font-serif text-3xl md:text-4xl font-bold text-white tracking-tight">
                {user?.username ?? 'Manager'}
              </h1>
              <p className="text-xs text-white/20 mt-1">
                Operations · {new Date().toLocaleDateString('en-KE', { weekday: 'long', day: 'numeric', month: 'long' })}
              </p>
            </motion.div>
            <ErrorBoundary level="tile">
              <G onClick={() => navigate('/manager/purchases')}>
                <div className="p-5 text-center">
                  <p className={`text-4xl font-bold tabular-nums ${pending.length > 0 ? 'text-amber-400' : 'text-white/20'}`}>
                    {pending.length}
                  </p>
                  <p className="text-xs text-white/30 mt-1">Pending Approvals</p>
                </div>
              </G>
            </ErrorBoundary>
          </div>

          {/* ── Row 2: Stock chart (wide) + Department breakdown ── */}
          <div className="grid grid-cols-1 lg:grid-cols-[2fr_1fr] gap-4 mb-4">
            <ErrorBoundary level="tile">
              <G>
                <div className="p-5">
                  <div className="flex items-center justify-between mb-4">
                    <p className="text-[11px] font-semibold tracking-wider uppercase text-white/30">Stock Behavior</p>
                    <button onClick={() => navigate('/inventory/count')} className="text-[10px] text-emerald-400 hover:text-emerald-300">View All →</button>
                  </div>
                  <div className="grid grid-cols-3 gap-3 mb-4">
                    <div>
                      <p className="text-2xl font-bold tabular-nums text-white">{items.length}</p>
                      <p className="text-[10px] text-white/30">Total</p>
                    </div>
                    <div>
                      <p className={`text-2xl font-bold tabular-nums ${low.length > 0 ? 'text-red-400' : 'text-emerald-400'}`}>{low.length}</p>
                      <p className="text-[10px] text-white/30">Low</p>
                    </div>
                    <div>
                      <p className="text-2xl font-bold tabular-nums text-emerald-400">{items.length - low.length}</p>
                      <p className="text-[10px] text-white/30">OK</p>
                    </div>
                  </div>
                  {chartData.length > 0 && (
                    <div className="h-24">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={chartData}>
                          <Bar dataKey="stock" fill="rgba(16,185,129,0.4)" radius={[4,4,0,0]} />
                          <Bar dataKey="reorder" fill="rgba(239,68,68,0.2)" radius={[4,4,0,0]} />
                          <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 10, fontSize: 11, color: '#fff' }} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  )}
                </div>
              </G>
            </ErrorBoundary>

            <ErrorBoundary level="tile">
              <G>
                <div className="p-5">
                  <p className="text-[11px] font-semibold tracking-wider uppercase text-white/30 mb-3">By Department</p>
                  <div className="space-y-2">
                    {Object.entries(byDept).map(([dept, { total, low: dLow }]) => (
                      <div key={dept} className="flex items-center justify-between py-1.5 border-b border-white/5 last:border-0">
                        <span className="text-sm text-white/70">{dept}</span>
                        <div className="flex items-center gap-2">
                          <span className="text-sm tabular-nums text-white/40">{total}</span>
                          {dLow > 0 && <span className="text-xs text-red-400 font-bold">⚠{dLow}</span>}
                        </div>
                      </div>
                    ))}
                    {Object.keys(byDept).length === 0 && <p className="text-sm text-white/20">No items</p>}
                  </div>
                </div>
              </G>
            </ErrorBoundary>
          </div>

          {/* ── Row 3: Budget + Low stock ─────────────────────────── */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <ErrorBoundary level="tile">
              <G>
                <div className="p-5">
                  <p className="text-[11px] font-semibold tracking-wider uppercase text-white/30 mb-3">Budget Burn</p>
                  {budgets.length === 0 ? <p className="text-sm text-white/20">No budgets set</p> : (
                    <div className="space-y-3">
                      {budgets.slice(0, 5).map(r => (
                        <div key={r.department}>
                          <div className="flex justify-between text-xs mb-1">
                            <span className="text-white/60">{r.department}</span>
                            <span className={`font-bold tabular-nums ${r.over_budget ? 'text-red-400' : r.pct_used > 80 ? 'text-amber-400' : 'text-emerald-400'}`}>
                              {Math.round(r.pct_used)}%
                            </span>
                          </div>
                          <div className="h-1.5 rounded-full bg-white/5 overflow-hidden">
                            <motion.div initial={{ width: 0 }} animate={{ width: `${Math.min(r.pct_used, 100)}%` }}
                              transition={{ duration: 0.8 }}
                              className={`h-full rounded-full ${r.over_budget ? 'bg-red-500' : r.pct_used > 80 ? 'bg-amber-500' : 'bg-emerald-500'}`} />
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </G>
            </ErrorBoundary>

            <ErrorBoundary level="tile">
              <G>
                <div className="p-5">
                  <p className="text-[11px] font-semibold tracking-wider uppercase text-white/30 mb-3">Low Stock</p>
                  {low.length === 0 ? <p className="text-sm text-emerald-400/60">All healthy ✓</p> : (
                    <div className="space-y-2">
                      {low.slice(0, 6).map(i => (
                        <div key={i.id} className="flex justify-between text-sm">
                          <span className="text-white/60 truncate">{i.name}</span>
                          <span className="text-red-400 tabular-nums font-semibold shrink-0 ml-2">
                            {parseFloat(i.current_stock)} {i.unit}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </G>
            </ErrorBoundary>
          </div>

          {/* ── Row 4: Action tiles — ALL features ────────────────── */}
          <motion.div variants={anim}>
            <p className="text-[11px] font-semibold tracking-wider uppercase text-white/30 mb-3">Manage</p>
            <div className="grid grid-cols-4 md:grid-cols-8 gap-2">
              {ACTIONS.map(a => (
                <motion.button key={a.path}
                  whileHover={{ y: -3 }} whileTap={{ scale: 0.94 }}
                  onClick={() => navigate(a.path)}
                  className="flex flex-col items-center gap-1.5 py-3 px-1 rounded-xl transition-all
                    focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400"
                  style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.06)' }}>
                  <span className="text-lg">{a.icon}</span>
                  <span className="text-[9px] text-white/60 font-medium">{a.label}</span>
                </motion.button>
              ))}
            </div>
          </motion.div>

        </motion.div>
      </div>
    </RequireRole>
  )
}
