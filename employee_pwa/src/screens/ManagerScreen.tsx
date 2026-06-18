import { useState } from 'react'
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
}

// ── SVG Icons (proper, not emoji) ───────────────────────────────────────────

function IconSchedule() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><rect x="3" y="3" width="14" height="14" rx="2" stroke="currentColor" strokeWidth="1.5"/><path d="M7 1v4M13 1v4M3 8h14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
}
function IconStaff() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><circle cx="7" cy="6" r="3" stroke="currentColor" strokeWidth="1.5"/><path d="M1 17c0-3 2.5-5 6-5s6 2 6 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/><path d="M14 9v4M16 11h-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
}
function IconMenu() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><rect x="3" y="1" width="14" height="18" rx="2" stroke="currentColor" strokeWidth="1.5"/><path d="M7 6h6M7 10h6M7 14h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
}
function IconAttendance() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><circle cx="10" cy="7" r="4" stroke="currentColor" strokeWidth="1.5"/><path d="M3 18c0-4 3-6 7-6s7 2 7 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/><path d="M13 12l2 2 3-3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
}
function IconFrontDesk() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><rect x="2" y="6" width="16" height="11" rx="2" stroke="currentColor" strokeWidth="1.5"/><path d="M7 6V4a3 3 0 016 0v2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/><path d="M10 11v-2M9 11h2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>
}
function IconCash() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><rect x="2" y="5" width="16" height="10" rx="2" stroke="currentColor" strokeWidth="1.5"/><circle cx="10" cy="10" r="2.5" stroke="currentColor" strokeWidth="1.5"/></svg>
}
function IconLeave() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><rect x="3" y="3" width="14" height="14" rx="2" stroke="currentColor" strokeWidth="1.5"/><path d="M7 1v4M13 1v4M3 8h14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/><path d="M7 12l2 2 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
}
function IconPurchases() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><path d="M3 3h2l2 8h8l2-6H7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/><circle cx="9" cy="15" r="1" stroke="currentColor" strokeWidth="1.5"/><circle cx="14" cy="15" r="1" stroke="currentColor" strokeWidth="1.5"/></svg>
}
function IconStock() {
  return <svg width="20" height="20" viewBox="0 0 20 20" fill="none"><path d="M4 7l2-3h8l2 3v9a1 1 0 01-1 1H5a1 1 0 01-1-1V7z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/><path d="M10 10v3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/><circle cx="10" cy="14.5" r=".5" fill="currentColor"/></svg>
}

const NAV = [
  { key: 'overview',   label: 'Overview',    Icon: IconStock,      path: null },
  { key: 'schedule',   label: 'Schedule',    Icon: IconSchedule,   path: '/manager/shifts' },
  { key: 'staff',      label: 'Staff',       Icon: IconStaff,      path: '/manager/staff' },
  { key: 'menu',       label: 'Menu',        Icon: IconMenu,       path: '/manager/menu' },
  { key: 'attendance', label: 'Attendance',  Icon: IconAttendance,  path: '/manager/attendance' },
  { key: 'frontdesk',  label: 'Front Desk',  Icon: IconFrontDesk,   path: '/manager/front-desk' },
  { key: 'cash',       label: 'Cash',        Icon: IconCash,        path: '/manager/cash' },
  { key: 'leave',      label: 'Leave',       Icon: IconLeave,       path: '/manager/leave' },
  { key: 'purchases',  label: 'Purchases',   Icon: IconPurchases,   path: '/manager/purchases' },
]

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
            <SectionLabel>Stock Behavior</SectionLabel>
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
    </motion.div>
  )
}

// ── Main Layout ─────────────────────────────────────────────────────────────

export default function ManagerScreen() {
  const navigate = useNavigate()
  const user = useAuthStore(s => s.user)
  const clearAuth = useAuthStore(s => s.clearAuth)
  const [active, setActive] = useState('overview')

  const hour = new Date().getHours()
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'

  function handleNav(item: typeof NAV[number]) {
    if (item.path) {
      navigate(item.path)
    } else {
      setActive(item.key)
    }
  }

  return (
    <RequireRole minLevel={5}>
      <div className="h-full flex" style={{ background: '#0b1120' }}>

        {/* ── Left Nav Rail ────────────────────────────────────────── */}
        <aside className="w-16 md:w-56 shrink-0 flex flex-col border-r border-white/5"
          style={{ background: 'rgba(11, 17, 32, 0.95)', backdropFilter: 'blur(20px)' }}>

          {/* Logo */}
          <div className="h-14 flex items-center justify-center md:justify-start md:px-5 border-b border-white/5">
            <span className="text-white font-bold font-serif text-lg">
              <span className="hidden md:block">Kurahia</span>
              <span className="md:hidden">K</span>
            </span>
          </div>

          {/* Nav items */}
          <nav className="flex-1 py-3 space-y-0.5 overflow-y-auto">
            {NAV.map(item => (
              <motion.button key={item.key}
                whileTap={{ scale: 0.97 }}
                onClick={() => handleNav(item)}
                className={`w-full flex items-center gap-3 px-3 md:px-5 py-2.5 transition-colors text-left
                  ${active === item.key && !item.path
                    ? 'bg-white/8 text-white border-l-2 border-emerald-400'
                    : 'text-white/40 hover:text-white/70 hover:bg-white/3 border-l-2 border-transparent'
                  }`}
              >
                <span className="shrink-0 w-5 h-5 flex items-center justify-center"><item.Icon /></span>
                <span className="hidden md:block text-sm font-medium">{item.label}</span>
              </motion.button>
            ))}
          </nav>

          {/* Account */}
          <div className="p-3 border-t border-white/5">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-full bg-emerald-500/20 border border-emerald-500/20
                flex items-center justify-center text-emerald-400 text-xs font-bold shrink-0">
                {user?.username?.[0]?.toUpperCase() ?? '?'}
              </div>
              <div className="hidden md:block flex-1 min-w-0">
                <p className="text-xs font-medium text-white truncate">{user?.username}</p>
                <button onClick={() => { clearAuth(); navigate('/pin') }}
                  className="text-[10px] text-red-400/50 hover:text-red-400">Sign out</button>
              </div>
            </div>
          </div>
        </aside>

        {/* ── Content Area ─────────────────────────────────────────── */}
        <main className="flex-1 overflow-y-auto p-5 md:p-8">
          <div className="max-w-5xl">
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
        </main>
      </div>
    </RequireRole>
  )
}
