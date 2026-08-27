import { useState, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  BarChart, Bar, XAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from 'recharts'
import { Skeleton, Button, useToastStore, resortRecentMonths, resortToday } from '@shared'
import api from '../lib/axios'

// ── Types ─────────────────────────────────────────────────────────────────────

interface FinanceDashboard {
  period: string
  revenue: { today: string; week: string; month: string }
  expenses: { purchases: string; payroll: string; total: string }
  profit_month: string
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

// Resort-local months. This used to be new Date(y, m-i, 1).toISOString(),
// which took LOCAL midnight and converted it to UTC — in Africa/Nairobi (UTC+3)
// that rolls back into the previous month, so the current month was missing
// from the dropdown entirely and P&L defaulted to last month.
const PERIODS = resortRecentMonths(3)

/** Fetch a PDF from the backend using the JWT token, then trigger a browser download. */
const downloadPdf = async (url: string, filename: string) => {
  const { useAuthStore } = await import('../stores/authStore')
  const token = useAuthStore.getState().accessToken
  const baseURL = import.meta.env.VITE_API_URL as string
  const res = await fetch(`${baseURL}${url}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: 'Download failed.' }))
    throw new Error(body.error || 'Download failed.')
  }
  const blob = await res.blob()
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = filename
  link.click()
  URL.revokeObjectURL(link.href)
}

// ── KPI strip ─────────────────────────────────────────────────────────────────

function KpiCard({ label, value, sub, danger = false }: {
  label: string; value: string; sub?: string; danger?: boolean
}) {
  return (
    <div className="glass-card rounded-2xl p-4 space-y-1">
      <p className="text-[10px] font-semibold tracking-widest uppercase text-ink-secondary">{label}</p>
      <p className={`text-2xl font-bold tabular-nums ${danger ? 'text-status-failed' : 'text-ink-primary'}`}>
        {value}
      </p>
      {sub && <p className="text-xs text-ink-tertiary">{sub}</p>}
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

      {/* Expenses + profit for the month — purchases + payroll, set against
          revenue. Was nowhere in the app before: the daily summary PDF had
          revenue only, no expense or profit figure existed anywhere. */}
      <div className="glass-card rounded-2xl p-4">
        <p className="text-[10px] font-semibold tracking-widest uppercase text-ink-secondary mb-3">
          Profit & Loss — {period}
        </p>
        <div className="space-y-1.5 text-sm">
          <div className="flex justify-between">
            <span className="text-ink-secondary">Revenue</span>
            <span className="text-ink-primary font-semibold tabular-nums">{formatKsh(dash?.revenue.month, true)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-ink-secondary">Purchases</span>
            <span className="text-status-failed tabular-nums">−{formatKsh(dash?.expenses.purchases, true)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-ink-secondary">Payroll</span>
            <span className="text-status-failed tabular-nums">−{formatKsh(dash?.expenses.payroll, true)}</span>
          </div>
          <div className="border-t border-white/10 pt-1.5 flex justify-between">
            <span className="text-ink-primary font-semibold">Profit</span>
            <span className={`font-bold tabular-nums ${
              parseFloat(dash?.profit_month ?? '0') >= 0 ? 'text-status-paid' : 'text-status-failed'
            }`}>
              {formatKsh(dash?.profit_month, true)}
            </span>
          </div>
        </div>
      </div>

      {/* 30-day bar chart */}
      <div className="glass-card rounded-2xl p-4">
        <p className="text-[10px] font-semibold tracking-widest uppercase text-ink-secondary mb-3">
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
            <p className="text-xs text-ink-secondary">No revenue data yet</p>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Budget burn section ───────────────────────────────────────────────────────

const extractErr = (e: unknown) =>
  (e as { response?: { data?: { error?: string } } })?.response?.data?.error ?? 'Something went wrong.'

/** Set (or update) a department's budget for a period. Manager+ per the backend
 * (app/finance/budgets.py) — was owner-only until this was explicitly widened;
 * there was previously no UI for this at all anywhere in the app, despite the
 * empty-state hint below pointing users at a "Finance → Budgets" flow that
 * didn't exist. */
function SetBudgetForm({ period }: { period: string }) {
  const qc = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  const [deptId, setDeptId] = useState('')
  const [amount, setAmount] = useState('')

  const { data: meta } = useQuery<{ departments: { id: string; name: string }[] }>({
    queryKey: ['auth-meta'],
    queryFn: () => api.get('/auth/users/meta').then(r => r.data),
    staleTime: 5 * 60_000,
  })

  const setBudgetMut = useMutation({
    mutationFn: () => api.post('/finance/budgets', { department_id: deptId, period, amount }),
    onSuccess: () => {
      addToast({ type: 'success', message: 'Budget set.' })
      qc.invalidateQueries({ queryKey: ['finance-budgets', period] })
      setAmount('')
    },
    onError: e => addToast({ type: 'error', message: extractErr(e) }),
  })

  return (
    <div className="glass-card rounded-2xl p-4 flex flex-wrap items-end gap-3">
      <div className="flex-1 min-w-[140px]">
        <label className="block text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary mb-1">
          Department
        </label>
        <select
          style={{ colorScheme: 'dark' }}
          value={deptId}
          onChange={e => setDeptId(e.target.value)}
          className="w-full rounded-lg border border-white/10 bg-transparent px-3 py-2 text-sm text-ink-primary
            focus:outline-none focus:ring-2 focus:ring-primary-main"
        >
          <option value="">Select department...</option>
          {meta?.departments.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
      </div>
      <div className="w-36">
        <label className="block text-[10px] font-semibold uppercase tracking-wider text-ink-tertiary mb-1">
          Budget (KSh) for {period}
        </label>
        <input
          type="number" min="0" value={amount}
          onChange={e => setAmount(e.target.value)}
          placeholder="e.g. 150000"
          className="w-full rounded-lg border border-white/10 bg-transparent px-3 py-2 text-sm text-ink-primary
            placeholder:text-ink-tertiary focus:outline-none focus:ring-2 focus:ring-primary-main"
        />
      </div>
      <Button
        variant="primary" size="sm"
        disabled={!deptId || !amount || setBudgetMut.isPending}
        onClick={() => setBudgetMut.mutate()}
      >
        {setBudgetMut.isPending ? 'Setting…' : 'Set Budget'}
      </Button>
    </div>
  )
}

function BudgetSection({ period }: { period: string }) {
  // Budgets are still only ever SET per month (SetBudgetForm below always
  // uses the real YYYY-MM period) — this toggle only changes how they're
  // viewed: GET /finance/budgets/status accepts a bare year and sums that
  // year's monthly budgets/spend per department server-side.
  const [granularity, setGranularity] = useState<'month' | 'year'>('month')
  const viewPeriod = granularity === 'year' ? period.slice(0, 4) : period

  // /finance/budgets/status returns { period, budgets: BudgetRow[] }, not a bare array.
  const { data, isLoading } = useQuery<{ budgets: BudgetRow[]; period: string }>({
    queryKey: ['finance-budgets', viewPeriod],
    queryFn: () => api.get(`/finance/budgets/status?period=${viewPeriod}`).then(r => r.data),
    staleTime: 5 * 60_000,
  })
  const rows = Array.isArray(data) ? data : (data?.budgets ?? [])

  const active = rows.filter(r => parseFloat(r.budget) > 0)

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
      <SetBudgetForm period={period} />

      {/* Monthly (this specific month) vs Yearly (that year's 12 months summed) */}
      <div className="flex gap-1 bg-white/5 rounded-xl p-1 w-fit" role="tablist">
        {(['month', 'year'] as const).map(g => (
          <button key={g} role="tab" aria-selected={granularity === g}
            onClick={() => setGranularity(g)}
            className={`px-3 inline-flex items-center min-h-[44px] rounded-lg text-xs font-semibold transition-colors ${
              granularity === g ? 'bg-white/10 text-ink-primary' : 'text-ink-secondary hover:text-ink-primary'
            }`}>
            {g === 'month' ? `Monthly (${period})` : `Yearly (${period.slice(0, 4)})`}
          </button>
        ))}
      </div>

      {active.length === 0 ? (
        <div className="rounded-2xl border border-white/10 p-6 text-center">
          <p className="text-sm text-ink-tertiary">No budgets set for this {granularity === 'year' ? 'year' : 'period'} yet.</p>
          <p className="text-xs text-ink-tertiary mt-1">Set one above to start tracking department spend.</p>
        </div>
      ) : (
        <>
          {/* Spend donut */}
          {donutData.length > 0 && (
            <div className="glass-card rounded-2xl p-4">
              <p className="text-[10px] font-semibold tracking-widest uppercase text-ink-secondary mb-2">
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
                  <p className="text-sm font-medium text-ink-primary truncate">{r.department}</p>
                  <div className="shrink-0 text-right">
                    <span className={`text-xs font-bold tabular-nums ${r.over_budget ? 'text-status-failed' : 'text-ink-primary'}`}>
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
                <div className="flex justify-between text-[10px] text-ink-tertiary mt-1 tabular-nums">
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
          <p className="text-[10px] font-semibold tracking-widest uppercase text-ink-secondary">{i.label}</p>
          <p className={`text-2xl font-bold tabular-nums mt-1 ${i.danger ? 'text-status-failed' : 'text-status-paid'}`}>
            {i.value}
          </p>
        </button>
      ))}
    </div>
  )
}

// ── Main screen ───────────────────────────────────────────────────────────────

type Section = 'revenue' | 'budget' | 'vat'

/**
 * VAT for a period — the figures whoever files the return needs.
 *
 * A bridge, not an eTIMS integration: filing is handled elsewhere, so what the
 * system owes that person is an accurate, reproducible statement of what was
 * sold and how much tax it contained. Every figure is derived from the charge
 * ledger, so running the same period twice gives the same answer and it can
 * never disagree with the receipts.
 */
function VatSection({ period }: { period: string }) {
  // period is YYYY-MM; the endpoint wants day bounds.
  const [y, m] = period.split('-').map(Number)
  const from = `${period}-01`
  const to = new Date(Date.UTC(y, m, 0)).toISOString().slice(0, 10)  // last day of month

  interface RateRow { rate_percent: string; charges: number; gross: string; net: string; tax: string }
  interface Vat {
    pricing: string
    by_rate: RateRow[]
    totals: { gross: string; net: string; tax: string }
    untracked: { charges: number; gross: string; note: string }
  }

  const { data, isLoading, isError } = useQuery<Vat>({
    queryKey: ['vat-summary', from, to],
    queryFn: () => api.get<Vat>(`/finance/vat-summary?from=${from}&to=${to}`).then(r => r.data),
    staleTime: 60_000,
  })

  const kes = (v: string) =>
    `KSh ${parseFloat(v).toLocaleString('en-KE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

  if (isLoading) return <div className="space-y-2">{[1,2].map(i => <Skeleton key={i} variant="card" />)}</div>
  if (isError || !data) return <p className="text-sm text-status-failed py-6">Could not load VAT for {period}.</p>

  return (
    <div className="space-y-4">
      <p className="text-[11px] text-ink-tertiary">{data.pricing}</p>

      <div className="grid sm:grid-cols-3 gap-3">
        {([['Gross', data.totals.gross], ['Net of VAT', data.totals.net], ['VAT', data.totals.tax]] as const)
          .map(([label, value]) => (
          <div key={label} className="glass-card rounded-2xl p-4">
            <p className="text-[10px] font-bold tracking-widest uppercase text-ink-secondary">{label}</p>
            <p className="text-lg font-bold tabular-nums text-ink-primary mt-1">{kes(value)}</p>
          </div>
        ))}
      </div>

      {/* Grouped by the rate that applied AT THE TIME, so a period spanning a
          statutory rate change reports both rather than blending them. */}
      {data.by_rate.length > 0 && (
        <div className="glass-card rounded-2xl p-4 space-y-2">
          <p className="text-[10px] font-bold tracking-widest uppercase text-ink-secondary mb-1">By rate</p>
          {data.by_rate.map(r => (
            <div key={r.rate_percent} className="flex items-center justify-between py-1.5 border-b border-white/10 last:border-0">
              <span className="text-sm text-ink-secondary">{r.rate_percent}% · {r.charges} charges</span>
              <span className="text-sm font-semibold tabular-nums text-ink-primary">
                {kes(r.tax)} <span className="text-xs text-ink-tertiary">of {kes(r.gross)}</span>
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Reported separately, never folded into the totals: their treatment is
          unknown, and handing an accountant a number the resort cannot stand
          behind is worse than showing the gap. */}
      {data.untracked.charges > 0 && (
        <div className="glass-card rounded-2xl p-4 border-l-4 border-l-status-pending">
          <p className="text-sm font-semibold text-status-pending">
            {data.untracked.charges} charges outside these totals — {kes(data.untracked.gross)}
          </p>
          <p className="text-xs text-ink-secondary mt-1">{data.untracked.note}</p>
        </div>
      )}
    </div>
  )
}

export default function FinanceScreen() {
  const [period, setPeriod] = useState(PERIODS[0])
  const [section, setSection] = useState<Section>('revenue')
  const [downloading, setDownloading] = useState(false)

  // Download today's daily summary PDF
  const handleDownloadSummary = useCallback(async () => {
    const today = resortToday()
    setDownloading(true)
    try {
      await downloadPdf(`/reports/daily-summary?date=${today}`, `daily_summary_${today}.pdf`)
    } catch (e) {
      alert((e as Error).message || 'Failed to download summary.')
    } finally {
      setDownloading(false)
    }
  }, [])

  return (
    <div className="p-4 max-w-6xl mx-auto">
      <div className="flex items-center justify-between gap-3 mb-5">
        <div>
          <h1 className="text-2xl font-bold text-ink-primary font-serif">Finance</h1>
          <p className="text-xs text-ink-tertiary mt-0.5">Revenue, expenses, reconciliation summaries</p>
        </div>
        <div className="flex items-center gap-2">
          {/* Download daily summary PDF */}
          <button
            onClick={handleDownloadSummary}
            disabled={downloading}
            className="text-xs border border-white/10 bg-transparent rounded-lg px-3 min-h-[44px]
              text-ink-secondary hover:bg-white/5 transition-colors
              focus:outline-none focus:ring-2 focus:ring-primary-main disabled:opacity-50"
          >
            {downloading ? 'Downloading...' : 'Download Daily Summary'}
          </button>
          {/* Period picker */}
          <label className="sr-only" htmlFor="finance-period">Period</label>
          <select
            id="finance-period"
            style={{ colorScheme: 'dark' }}
            value={period}
            onChange={e => setPeriod(e.target.value)}
            aria-label="Select period"
            className="text-xs border border-white/10 bg-transparent rounded-lg px-2 min-h-[44px]
              text-ink-secondary focus:outline-none focus:ring-2 focus:ring-primary-main"
          >
            {PERIODS.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>
      </div>

      {/* Section tabs */}
      <div className="flex gap-1 bg-white/5 rounded-xl p-1 mb-6" role="tablist">
        {([['revenue', 'Revenue'], ['budget', 'Budget Burn'], ['vat', 'VAT']] as [Section, string][]).map(([key, label]) => (
          <button
            key={key}
            role="tab"
            aria-selected={section === key}
            onClick={() => setSection(key)}
            className={[
              // min-h-[44px] — the section tabs were 32px tall.
              'flex-1 min-h-[44px] rounded-lg text-xs font-semibold transition-colors',
              section === key ? 'bg-white/10 text-ink-primary' : 'text-ink-secondary hover:text-ink-primary',
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
        {section === 'vat'     && <VatSection     period={period} />}
      </div>
    </div>
  )
}
