import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  BarChart, Bar, XAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from 'recharts'
import { Skeleton } from '@shared'
import api from '../lib/axios'

// ── Types ─────────────────────────────────────────────────────────────────────

interface FinanceDashboard {
  period: string
  revenue: { today: string; week: string; month: string }
  budgets: { department: string; budget: string; spent: string; remaining: string; pct_used: number; over_budget: boolean }[]
  open_shortfalls: number
  no_receipt_purchases: number
  judge_alerts_open: number
}

interface RevenueHistoryRow { date: string; revenue: string }

interface BudgetRow {
  department: string; budget: string; spent: string; remaining: string
  pct_used: number; over_budget: boolean
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const formatKsh = (v: string | number | undefined, compact = false): string => {
  if (!v && v !== 0) return 'KSh —'
  const n = typeof v === 'string' ? parseFloat(v) : v
  if (isNaN(n)) return 'KSh —'
  if (compact) {
    if (n >= 1_000_000) return `KSh ${(n / 1_000_000).toFixed(1)}M`
    if (n >= 1_000)     return `KSh ${(n / 1_000).toFixed(0)}k`
  }
  return `KSh ${n.toLocaleString('en-KE', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
}

const now = new Date()
const PERIODS = Array.from({ length: 3 }, (_, i) => {
  const d = new Date(now.getFullYear(), now.getMonth() - i, 1)
  return d.toISOString().slice(0, 7)
})

// ── KPI strip ─────────────────────────────────────────────────────────────────

function KpiCard({ label, value, sub, danger = false }: {
  label: string; value: string; sub?: string; danger?: boolean
}) {
  return (
    <div className="glass-card rounded-2xl p-4 space-y-1">
      <p className="text-[10px] font-semibold tracking-widest uppercase text-slate-300/70">{label}</p>
      <p className={`text-2xl font-bold tabular-nums ${danger ? 'text-status-failed' : 'text-white'}`}>
        {value}
      </p>
      {sub && <p className="text-xs text-slate-400/50">{sub}</p>}
    </div>
  )
}

// ── Revenue section ───────────────────────────────────────────────────────────

function RevenueSection({ period }: { period: string }) {
  const days = 30
  const { data: dash, isLoading: dLoad } = useQuery<FinanceDashboard>({
    queryKey: ['finance-dashboard', period],
    queryFn: () => api.get<FinanceDashboard>(`/finance/dashboard?period=${period}`).then(r => r.data),
    staleTime: 5 * 60_000,
  })
  const { data: hist, isLoading: hLoad } = useQuery<RevenueHistoryRow[]>({
    queryKey: ['dash-revenue-history', days],
    queryFn: () => api.get<RevenueHistoryRow[]>(`/finance/revenue-history?days=${days}`).then(r => r.data),
    staleTime: 5 * 60_000,
  })

  const isLoading = dLoad || hLoad

  const chartData = (hist ?? []).map(r => ({
    date: r.date.slice(5),
    rev: parseFloat(r.revenue),
  }))

  if (isLoading) {
    return (
      <div className="space-y-3">
        <div className="grid grid-cols-3 gap-3">
          {[0, 1, 2].map(i => (
            <div key={i} className="rounded-2xl border border-white/10 p-4 space-y-2">
              <Skeleton variant="text" className="w-16 h-3" />
              <Skeleton variant="text" className="w-24 h-6" />
            </div>
          ))}
        </div>
        <Skeleton variant="text" className="w-full h-32 rounded-2xl" />
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-3">
        <KpiCard label="Today"  value={formatKsh(dash?.revenue.today,  true)} />
        <KpiCard label="Week"   value={formatKsh(dash?.revenue.week,   true)} />
        <KpiCard label="Month"  value={formatKsh(dash?.revenue.month,  true)} />
      </div>

      {/* 30-day bar chart */}
      <div className="glass-card rounded-2xl p-4">
        <p className="text-[10px] font-semibold tracking-widest uppercase text-slate-300/70 mb-3">
          Daily Revenue — last {days} days
        </p>
        {chartData.length > 0 ? (
          <div className="h-32">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData} margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
                <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#5C5147' }} tickLine={false} axisLine={false}
                  interval={Math.floor(chartData.length / 6)} />
                <Tooltip
                  contentStyle={{ background: '#1F1B14', border: 'none', borderRadius: 8, fontSize: 11 }}
                  labelStyle={{ color: '#ECE3D0' }}
                  formatter={(v: unknown) => [formatKsh(v as number), 'Revenue']}
                  labelFormatter={(l: unknown) => String(l)}
                />
                <Bar dataKey="rev" fill="#3C7A8C" radius={[3, 3, 0, 0]}
                  activeBar={{ fill: '#4A9BAF' }} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="h-32 flex items-center justify-center">
            <p className="text-xs text-slate-300/70">No revenue data yet</p>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Budget burn section ───────────────────────────────────────────────────────

function BudgetSection({ period }: { period: string }) {
  const { data: rows, isLoading } = useQuery<BudgetRow[]>({
    queryKey: ['finance-budgets', period],
    queryFn: () => api.get<BudgetRow[]>(`/finance/budgets/status?period=${period}`).then(r => r.data),
    staleTime: 5 * 60_000,
  })

  const active = (rows ?? []).filter(r => parseFloat(r.budget) > 0)

  // Donut chart data
  const donutData = active.slice(0, 5).map(r => ({
    name: r.department,
    value: parseFloat(r.spent),
  })).filter(d => d.value > 0)

  const DONUT_COLORS = ['#B4533C', '#3C7A8C', '#8A6320', '#3D6640', '#8C7E6F']

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton variant="text" className="w-full h-40 rounded-2xl" />
        {[0, 1, 2].map(i => <Skeleton key={i} variant="text" className="h-12 rounded-xl" />)}
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {active.length === 0 ? (
        <div className="rounded-2xl border border-white/10 p-6 text-center">
          <p className="text-sm text-slate-400/50">No budgets set for this period.</p>
          <p className="text-xs text-slate-400/50 mt-1">Add budgets via Finance → Budgets to track department spend.</p>
        </div>
      ) : (
        <>
          {/* Spend donut */}
          {donutData.length > 0 && (
            <div className="glass-card rounded-2xl p-4">
              <p className="text-[10px] font-semibold tracking-widest uppercase text-slate-300/70 mb-2">
                Spend by Department
              </p>
              <div className="h-44">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={donutData} cx="50%" cy="50%" innerRadius={48} outerRadius={68}
                      dataKey="value" nameKey="name">
                      {donutData.map((_, i) => (
                        <Cell key={i} fill={DONUT_COLORS[i % DONUT_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={{ background: '#1F1B14', border: 'none', borderRadius: 8, fontSize: 11 }}
                      formatter={(v: unknown) => [formatKsh(v as number), 'Spent']}
                    />
                    <Legend iconSize={8} iconType="circle"
                      formatter={(v: string) => <span style={{ fontSize: 10, color: '#5C5147' }}>{v}</span>} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Department bars */}
          <div className="space-y-2">
            {active.map(r => (
              <div key={r.department} className="glass-card rounded-xl px-4 py-3">
                <div className="flex items-center justify-between gap-2 mb-1.5">
                  <p className="text-sm font-medium text-white truncate">{r.department}</p>
                  <div className="shrink-0 text-right">
                    <span className={`text-xs font-bold tabular-nums ${r.over_budget ? 'text-status-failed' : 'text-white'}`}>
                      {Math.round(r.pct_used)}%
                    </span>
                    {r.over_budget && <span className="ml-1 text-[10px] text-status-failed">OVER</span>}
                  </div>
                </div>
                <div className="h-2 rounded-full bg-white/5 overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all ${r.over_budget ? 'bg-status-failed' : 'bg-accent-cool'}`}
                    style={{ width: `${Math.min(r.pct_used, 100)}%` }}
                  />
                </div>
                <div className="flex justify-between text-[10px] text-slate-400/50 mt-1 tabular-nums">
                  <span>Spent: {formatKsh(r.spent, true)}</span>
                  <span>Budget: {formatKsh(r.budget, true)}</span>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

// ── Reconciliation status strip ───────────────────────────────────────────────

function ReconStrip({ period }: { period: string }) {
  const { data: dash } = useQuery<FinanceDashboard>({
    queryKey: ['finance-dashboard', period],
    queryFn: () => api.get<FinanceDashboard>(`/finance/dashboard?period=${period}`).then(r => r.data),
    staleTime: 5 * 60_000,
  })
  const navigate = useNavigate()

  if (!dash) return null

  const items = [
    { label: 'Open shortfalls', value: dash.open_shortfalls, danger: dash.open_shortfalls > 0, path: '/reconciliation' },
    { label: 'Judge alerts open', value: dash.judge_alerts_open, danger: dash.judge_alerts_open > 0, path: '/alerts' },
  ]

  return (
    <div className="grid grid-cols-2 gap-3">
      {items.map(i => (
        <button
          key={i.label}
          onClick={() => navigate(i.path)}
          className="glass-card rounded-2xl px-4 py-3 text-left
            hover:shadow-sm hover:border-primary-light/40 transition-all
            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-main"
        >
          <p className="text-[10px] font-semibold tracking-widest uppercase text-slate-300/70">{i.label}</p>
          <p className={`text-2xl font-bold tabular-nums mt-1 ${i.danger ? 'text-status-failed' : 'text-status-paid'}`}>
            {i.value}
          </p>
        </button>
      ))}
    </div>
  )
}

// ── Main screen ───────────────────────────────────────────────────────────────

type Section = 'revenue' | 'budget'

export default function FinanceScreen() {
  const [period, setPeriod] = useState(PERIODS[0])
  const [section, setSection] = useState<Section>('revenue')

  return (
    <div className="p-4 max-w-3xl mx-auto">
      <div className="flex items-center justify-between gap-3 mb-5">
        <div>
          <h1 className="text-2xl font-bold text-white font-serif">Finance</h1>
          <p className="text-xs text-white/30 mt-0.5">Revenue, expenses, reconciliation summaries</p>
        </div>
        {/* Period picker */}
        <label className="sr-only" htmlFor="finance-period">Period</label>
        <select
          id="finance-period"
          value={period}
          onChange={e => setPeriod(e.target.value)}
          aria-label="Select period"
          className="text-xs border border-white/10 bg-transparent rounded-lg px-2 py-1.5
            text-slate-300/70 focus:outline-none focus:ring-2 focus:ring-primary-main"
        >
          {PERIODS.map(p => <option key={p} value={p}>{p}</option>)}
        </select>
      </div>

      {/* Section tabs */}
      <div className="flex gap-1 bg-white/5 rounded-xl p-1 mb-4" role="tablist">
        {([['revenue', 'Revenue'], ['budget', 'Budget Burn']] as [Section, string][]).map(([key, label]) => (
          <button
            key={key}
            role="tab"
            aria-selected={section === key}
            onClick={() => setSection(key)}
            className={[
              'flex-1 py-2 rounded-lg text-xs font-semibold transition-colors',
              section === key ? 'bg-transparent text-white shadow-sm' : 'text-slate-300/70 hover:text-white',
            ].join(' ')}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Reconciliation status — always visible */}
      <ReconStrip period={period} />

      <div className="mt-4">
        {section === 'revenue' && <RevenueSection period={period} />}
        {section === 'budget'  && <BudgetSection  period={period} />}
      </div>
    </div>
  )
}
