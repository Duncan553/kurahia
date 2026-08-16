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
      className={`glass-card ${onClick ? 'cursor-pointer' : ''} ${className}`}>
      <div className="relative h-px bg-gradient-to-r from-transparent via-white/15 to-transparent" />
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

  const ACTIONS: { label: string; desc: string; path: string; svg: React.ReactNode }[] = [
    { label: 'Staff', desc: 'Create accounts & assign tablets', path: '/manager/staff', svg: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
        <circle cx="7.5" cy="6" r="3" stroke="currentColor" strokeWidth="1.5"/>
        <path d="M2 17c0-3 2.5-5 5.5-5s5.5 2 5.5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        <path d="M15 9v4M17 11h-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    ) },
    { label: 'Menu', desc: 'Add items, set prices & recipes', path: '/manager/menu', svg: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
        <rect x="3" y="1" width="14" height="18" rx="2" stroke="currentColor" strokeWidth="1.5"/>
        <path d="M7 6h6M7 10h6M7 14h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    ) },
    { label: 'Shifts', desc: 'Schedule who works when', path: '/manager/shifts', svg: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
        <rect x="3" y="3" width="14" height="14" rx="2" stroke="currentColor" strokeWidth="1.5"/>
        <path d="M7 1v4M13 1v4M3 8h14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    ) },
    { label: 'Attendance', desc: "Today's roster — who clocked in", path: '/manager/attendance', svg: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
        <circle cx="10" cy="7" r="3.5" stroke="currentColor" strokeWidth="1.5"/>
        <path d="M3 18c0-3.5 3-6 7-6s7 2.5 7 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        <path d="M13.5 13l2 2 3-3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    ) },
    { label: 'Front Desk', desc: 'Arrivals, departures, occupancy', path: '/manager/front-desk', svg: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
        <rect x="2" y="6" width="16" height="11" rx="2" stroke="currentColor" strokeWidth="1.5"/>
        <path d="M7 6V4a3 3 0 016 0v2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        <circle cx="10" cy="11.5" r="1.5" stroke="currentColor" strokeWidth="1.5"/>
      </svg>
    ) },
    { label: 'Cash', desc: 'Reconcile staff cash handovers', path: '/manager/cash', svg: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
        <rect x="2" y="5" width="16" height="10" rx="2" stroke="currentColor" strokeWidth="1.5"/>
        <circle cx="10" cy="10" r="2.5" stroke="currentColor" strokeWidth="1.5"/>
        <path d="M5 10h.01M15 10h.01" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    ) },
    { label: 'Leave', desc: 'Approve or reject leave requests', path: '/manager/leave', svg: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
        <rect x="3" y="3" width="14" height="14" rx="2" stroke="currentColor" strokeWidth="1.5"/>
        <path d="M7 1v4M13 1v4M3 8h14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        <path d="M7 12l2 2 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    ) },
    { label: 'Purchases', desc: 'Review restock requests & budgets', path: '/manager/purchases', svg: (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
        <path d="M3 3h2l2 8h8l2-6H7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        <circle cx="9" cy="15" r="1.5" stroke="currentColor" strokeWidth="1.5"/>
        <circle cx="15" cy="15" r="1.5" stroke="currentColor" strokeWidth="1.5"/>
      </svg>
    ) },
  ]

  return (
    <RequireRole minLevel={5}>
      <div className="p-4 md:p-6 max-w-6xl mx-auto">
        <motion.div initial="hidden" animate="visible"
          variants={{ visible: { transition: { staggerChildren: 0.06 } } }}>

          {/* ── Row 1: Greeting + Pending approvals (HERO if > 0) ── */}
          <div className="grid grid-cols-1 md:grid-cols-[1fr_280px] gap-4 mb-8">
            <motion.div variants={anim}>
              <p className="text-sm text-ink-tertiary">{greeting},</p>
              <h1 className="font-serif text-3xl md:text-4xl font-bold text-ink-primary tracking-tight">
                {user?.username ?? 'Manager'}
              </h1>
              <p className="text-xs text-ink-tertiary/60 mt-1">
                Operations · {new Date().toLocaleDateString('en-KE', { weekday: 'long', day: 'numeric', month: 'long' })}
              </p>
            </motion.div>
            <ErrorBoundary level="tile">
              <G onClick={() => navigate('/manager/purchases')}>
                <div className={`p-5 text-center ${pending.length > 0 ? 'py-6' : ''}`}>
                  <p className={`font-bold tabular-nums ${
                    pending.length > 0
                      ? 'text-5xl md:text-6xl text-status-pending'
                      : 'text-4xl text-ink-tertiary/60'
                  }`}>
                    {pending.length}
                  </p>
                  <p className={`text-xs mt-1 ${pending.length > 0 ? 'text-status-pending/80 font-semibold' : 'text-ink-tertiary'}`}>
                    Pending Approvals
                  </p>
                </div>
              </G>
            </ErrorBoundary>
          </div>

          {/* ── Row 2: Stock chart (wide) + Department breakdown ── */}
          <div className="grid grid-cols-1 lg:grid-cols-[2fr_1fr] gap-4 mb-8">
            <ErrorBoundary level="tile">
              <G>
                <div className="p-5">
                  <div className="flex items-center justify-between mb-4">
                    <p className="text-[11px] font-semibold tracking-wider uppercase text-ink-tertiary">Stock Behavior</p>
                    <p className="text-[10px] text-ink-tertiary">How fast your supplies are being used up</p>
                    <button onClick={() => navigate('/inventory/count')} className="text-[10px] text-[#fa5c29] hover:text-[#ffb59f]">View All →</button>
                  </div>
                  <div className="grid grid-cols-3 gap-4 mb-4">
                    <div>
                      <p className="text-2xl font-bold tabular-nums text-ink-primary">{items.length}</p>
                      <p className="text-[10px] text-ink-tertiary">Total</p>
                    </div>
                    <div>
                      <p className={`text-2xl font-bold tabular-nums ${low.length > 0 ? 'text-status-failed' : 'text-status-paid'}`}>{low.length}</p>
                      <p className="text-[10px] text-ink-tertiary">Low</p>
                    </div>
                    <div>
                      <p className="text-2xl font-bold tabular-nums text-status-paid">{items.length - low.length}</p>
                      <p className="text-[10px] text-ink-tertiary">OK</p>
                    </div>
                  </div>
                  {chartData.length > 0 && (
                    <div className="h-24">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={chartData}>
                          <Bar dataKey="stock" fill="rgba(16,185,129,0.4)" radius={[4,4,0,0]} />
                          <Bar dataKey="reorder" fill="rgba(239,68,68,0.2)" radius={[4,4,0,0]} />
                          <Tooltip contentStyle={{ background: '#1e100c', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 10, fontSize: 11, color: '#f9dcd5' }} />
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
                  <p className="text-[11px] font-semibold tracking-wider uppercase text-ink-tertiary mb-3">Stock by Department</p>
                  <div className="space-y-3">
                    {Object.entries(byDept).map(([dept, { total, low: dLow }]) => {
                      const healthPct = total > 0 ? Math.round(((total - dLow) / total) * 100) : 100
                      return (
                        <div key={dept}>
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-sm text-ink-primary/80 font-medium">{dept}</span>
                            <span className="text-xs tabular-nums text-ink-tertiary/80">
                              {total - dLow}/{total} OK
                            </span>
                          </div>
                          <div className="h-1.5 rounded-full bg-white/5 overflow-hidden">
                            <div className={`h-full rounded-full transition-all ${
                              healthPct === 100 ? 'bg-status-paid' : healthPct > 60 ? 'bg-status-pending' : 'bg-status-failed'
                            }`} style={{ width: `${healthPct}%` }} />
                          </div>
                          {dLow > 0 && (
                            <p className="text-[10px] text-status-failed/70 mt-0.5">
                              {dLow} item{dLow !== 1 ? 's' : ''} below reorder level
                            </p>
                          )}
                        </div>
                      )
                    })}
                    {Object.keys(byDept).length === 0 && <p className="text-sm text-ink-tertiary/60">No items</p>}
                  </div>
                </div>
              </G>
            </ErrorBoundary>
          </div>

          {/* ── Row 3: Budget + Low stock ─────────────────────────── */}
          <div className="grid grid-cols-1 lg:grid-cols-[2fr_1fr] gap-4 mb-8">
            <ErrorBoundary level="tile">
              <G>
                <div className="p-5">
                  <p className="text-[11px] font-semibold tracking-wider uppercase text-ink-tertiary mb-1">Budget Burn</p>
                  <p className="text-[10px] text-ink-tertiary mb-3">How much of the monthly budget each department has spent</p>
                  {budgets.length === 0 ? <p className="text-sm text-ink-tertiary/60">No budgets set</p> : (
                    <div className="space-y-3">
                      {budgets.slice(0, 5).map(r => (
                        <div key={r.department}>
                          <div className="flex justify-between text-xs mb-1">
                            <span className="text-ink-secondary">{r.department}</span>
                            <span className={`font-bold tabular-nums ${r.over_budget ? 'text-status-failed' : r.pct_used > 80 ? 'text-status-pending' : 'text-status-paid'}`}>
                              {Math.round(r.pct_used)}%
                            </span>
                          </div>
                          <div className="h-1.5 rounded-full bg-white/5 overflow-hidden">
                            <motion.div initial={{ width: 0 }} animate={{ width: `${Math.min(r.pct_used, 100)}%` }}
                              transition={{ duration: 0.8 }}
                              className={`h-full rounded-full ${r.over_budget ? 'bg-status-failed' : r.pct_used > 80 ? 'bg-status-pending' : 'bg-status-paid'}`} />
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
                  <p className="text-[11px] font-semibold tracking-wider uppercase text-ink-tertiary mb-1">Low Stock</p>
                  <p className="text-[10px] text-ink-tertiary mb-3">Items you need to reorder soon</p>
                  {low.length === 0 ? <p className="text-sm text-status-paid/60">All healthy</p> : (
                    <div className="space-y-2">
                      {low.slice(0, 6).map(i => (
                        <div key={i.id} className="flex justify-between text-sm">
                          <span className="text-ink-secondary truncate">{i.name}</span>
                          <span className="text-status-failed tabular-nums font-semibold shrink-0 ml-2">
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
            <p className="text-[11px] font-semibold tracking-wider uppercase text-ink-tertiary mb-4">Manage</p>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              {ACTIONS.map(a => (
                <motion.button key={a.path}
                  whileHover={{ y: -2 }} whileTap={{ scale: 0.97 }}
                  onClick={() => navigate(a.path)}
                  className="flex flex-col items-start gap-2 p-4 rounded-xl transition-all text-left
                    focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#fa5c29]
                    glass-card hover:bg-white/8"
                  aria-label={`${a.label} — ${a.desc}`}>
                  <span className="text-ink-secondary">{a.svg}</span>
                  <div>
                    <p className="text-xs text-ink-primary font-semibold">{a.label}</p>
                    <p className="text-[9px] text-ink-tertiary mt-0.5 leading-tight">{a.desc}</p>
                  </div>
                </motion.button>
              ))}
            </div>
          </motion.div>

        </motion.div>
      </div>
    </RequireRole>
  )
}
