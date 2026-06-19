import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { AreaChart, Area, PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts'
import { Skeleton, StatusBadge, ErrorBoundary } from '@shared'
import type { StatusValue } from '@shared'
import api from '../lib/axios'

// ── Types ─────────────────────────────────────────────────────────────────────

interface OverviewData {
  period: string
  revenue: { total: string; by_tab_type: Record<string, string>; by_method: Record<string, string> }
  staff: { on_duty: number; on_duty_names: string[] }
  bookings: { active: number; arrivals_today: number; departures_today: number }
  inventory_alerts: number
  top_alerts: { id: string; type: string; severity: string; description: string }[]
  week_calendar: { title: string; date: string; is_peak: boolean; type: string }[]
}

interface RevenueHistoryRow { date: string; revenue: string }

interface InventoryData {
  total_skus: number
  low_stock_count: number
  items: { id: string; name: string; current_stock: string; reorder_level: string; is_low: boolean }[]
}

interface FinanceData {
  period: string
  total_revenue: string
  reconciliation_status: 'green' | 'yellow' | 'red'
  open_shortfalls: number
  unmatched_mpesa: number
  pending_approvals: number
}

interface BookingsData {
  occupancy_by_type: Record<string, number>
  arrivals_today: { id: string; guest: string }[]
  departures_today: { id: string; guest: string }[]
  pending_deposits: { id: string; guest: string }[]
  pending_waivers_tomorrow: { booking_id: string; guest: string }[]
}

interface StaffData {
  active_employees: number
  on_duty: number
  absent_today: number
  open_disputes: { management: number; owner_private: number }
  new_suggestions: { management: number; owner_private: number }
  top_performers: { name: string; score: number }[]
}

interface AlertItem {
  id: string
  type: string
  severity: string
  description: string
  status: string
}

interface FeedbackData {
  period: string
  overall_avg: string | null
  by_department: { department: string; avg_score: string; count: number }[]
  recent_comments: { score: number; comment: string; guest: string }[]
}

interface SuggestionItem { id: string; subject: string; status: string; submitted_by: string }
interface SuggestionsData { management: SuggestionItem[]; owner_private: SuggestionItem[] }

interface EquipmentData {
  total: number
  due_service: { id: string; name: string; type: string; last_service: string | null }[]
  in_maintenance: { id: string; name: string }[]
}

interface PurchaseRequest {
  id: string; item_name: string; quantity: string; status: string
  department: string; requested_by: string; estimated_cost: string | null
}

interface BudgetRow {
  department: string; budget: string; spent: string; remaining: string
  pct_used: number; over_budget: boolean
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatKsh(val: string | number | undefined): string {
  if (val === undefined || val === null) return 'KSh —'
  const n = typeof val === 'string' ? parseFloat(val) : val
  if (isNaN(n)) return 'KSh —'
  return `KSh ${n.toLocaleString('en-KE', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
}

function formatAvg(val: string | null | undefined): string {
  if (!val) return '— / 5'
  const n = parseFloat(val)
  return isNaN(n) ? '— / 5' : `${n.toFixed(1)} / 5`
}

function alertCountColor(count: number): string {
  if (count === 0) return 'text-status-paid'
  if (count <= 3)  return 'text-status-pending'
  return 'text-status-failed'
}

function reconBadge(status: string): StatusValue {
  if (status === 'green') return 'paid'
  if (status === 'yellow') return 'pending'
  return 'failed'
}

// ── Tile animation variants ───────────────────────────────────────────────────

const gridVariants = { animate: { transition: { staggerChildren: 0.04 } } }
const tileVariants = {
  initial: { opacity: 0, y: 14 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.25, ease: 'easeOut' as const } },
}

// ── Shared tile primitives ────────────────────────────────────────────────────

function TileCard({
  title, href, children, className = '',
}: {
  title: string; href?: string; children: React.ReactNode; className?: string
}) {
  const navigate = useNavigate()
  return (
    <div
      role={href ? 'button' : undefined}
      tabIndex={href ? 0 : undefined}
      onClick={href ? () => navigate(href) : undefined}
      onKeyDown={href ? (e) => { if (e.key === 'Enter') navigate(href) } : undefined}
      className={[
        'rounded-2xl p-4 space-y-2 border border-white/10 shadow-lg',
        href ? 'cursor-pointer hover:shadow-xl hover:border-white/20 transition-all active:scale-[0.99] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400' : '',
        className,
        'glass-card',
      ].join(' ')}
    >
      <p className="text-[10px] font-semibold tracking-widest uppercase text-slate-400">{title}</p>
      {children}
    </div>
  )
}

function TileSkeleton({ className = '' }: { className?: string }) {
  return (
    <div className={`rounded-2xl p-4 space-y-3 glass-card-sage ${className}`}>
      <Skeleton variant="text" className="w-24 h-3" />
      <Skeleton variant="text" className="w-32 h-8" />
      <Skeleton variant="text" className="w-40 h-3" />
    </div>
  )
}

function TileError({ label, className = '' }: { label: string; className?: string }) {
  return (
    <TileCard title={label} className={className}>
      <p className="text-2xl font-bold tabular-nums text-slate-500">—</p>
      <p className="text-xs text-status-failed">Couldn't load</p>
    </TileCard>
  )
}

// ── Hero tile — revenue + 7-day bar chart ────────────────────────────────────

function HeroTile() {
  const { data: overview, isLoading: ovLoad, isError: ovErr, dataUpdatedAt } = useQuery<OverviewData>({
    queryKey: ['dash-overview'],
    queryFn: () => api.get<OverviewData>('/dashboard/overview').then(r => r.data),
    staleTime: 30_000,
    refetchInterval: 60_000,
  })
  const { data: hist, isLoading: hLoad } = useQuery<RevenueHistoryRow[]>({
    queryKey: ['dash-revenue-history'],
    queryFn: () => api.get<RevenueHistoryRow[]>('/finance/revenue-history?days=7').then(r => r.data),
    staleTime: 5 * 60_000,
  })

  const isLoading = ovLoad || hLoad

  if (isLoading) {
    return (
      <div className="rounded-2xl p-5 space-y-3 col-span-full gradient-hero">
        <Skeleton variant="text" className="w-32 h-3 bg-white/20" />
        <Skeleton variant="text" className="w-48 h-10 bg-white/20" />
        <Skeleton variant="text" className="w-full h-16 bg-white/20" />
      </div>
    )
  }

  const chartData = (hist ?? []).map(r => ({
    date: r.date.slice(5),   // MM-DD
    rev: parseFloat(r.revenue),
  }))
  const today = parseFloat(overview?.revenue.total ?? '0')
  const byMethod = overview?.revenue.by_method ?? {}
  const yesterday = chartData.length >= 2 ? chartData[chartData.length - 2]?.rev ?? 0 : 0
  const delta = yesterday > 0 ? ((today - yesterday) / yesterday * 100) : 0
  const updatedAgo = dataUpdatedAt ? Math.floor((Date.now() - dataUpdatedAt) / 1000) : null

  const methodColors: Record<string, string> = {
    CASH: '#E4D2B0', MPESA: '#28633D', CARD: '#C68A28', BANK_TRANSFER: '#4A7889',
  }
  const pieData = Object.entries(byMethod)
    .filter(([, v]) => parseFloat(v) > 0)
    .map(([k, v]) => ({ name: k, value: parseFloat(v) }))

  return (
    <div className="rounded-2xl col-span-full gradient-hero overflow-hidden">
      <div className="grid grid-cols-1 md:grid-cols-[1fr_280px] gap-0">
        {/* Left — Revenue + bar chart */}
        <div className="p-5 md:p-6">
          <p className="text-[10px] font-semibold tracking-widest uppercase text-white/70 mb-1">Revenue Today</p>
          {ovErr ? (
            <p className="text-3xl font-bold tabular-nums text-white/50">KSh —</p>
          ) : (
            <>
              <p className="text-4xl md:text-5xl font-bold tabular-nums text-white leading-tight">
                {formatKsh(today)}
              </p>
              <div className="flex items-center gap-2 mt-2 flex-wrap">
                {delta !== 0 && (
                  <span className={`text-xs font-bold px-2 py-1 rounded-full ${
                    delta > 0 ? 'bg-status-paid/30 text-white' : 'bg-status-failed/30 text-white'
                  }`}>
                    {delta > 0 ? '↗' : '↘'} {Math.abs(delta).toFixed(0)}%
                  </span>
                )}
                {updatedAgo !== null && updatedAgo < 120 && (
                  <span className="text-[10px] text-white/40">
                    {updatedAgo < 5 ? 'just now' : `${updatedAgo}s ago`}
                  </span>
                )}
              </div>
            </>
          )}
          <div className="mt-4 h-20" aria-label="7-day revenue trend">
            {chartData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData} margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
                  <defs>
                    <linearGradient id="revGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="rgba(255,255,255,0.4)" />
                      <stop offset="100%" stopColor="rgba(255,255,255,0)" />
                    </linearGradient>
                  </defs>
                  <Area type="monotone" dataKey="rev" stroke="rgba(255,255,255,0.6)" strokeWidth={2}
                    fill="url(#revGrad)" />
                  <Tooltip
                    contentStyle={{ background: '#1A3636', border: 'none', borderRadius: 8, fontSize: 11 }}
                    labelStyle={{ color: '#E4D2B0' }}
                    formatter={(v: unknown) => [formatKsh(v as number), 'Revenue']}
                    labelFormatter={(label: unknown) => String(label)}
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-end gap-1">
                {Array.from({ length: 7 }).map((_, i) => (
                  <div key={i} className="flex-1 bg-white/15 rounded-sm" style={{ height: '40%' }} />
                ))}
              </div>
            )}
          </div>
          <p className="text-[10px] text-white/40 mt-1">Last 7 days</p>
        </div>

        {/* Right — Payment method donut */}
        <div className="p-5 md:p-6 md:border-l border-white/10 flex flex-col items-center justify-center">
          <p className="text-[10px] font-semibold tracking-widest uppercase text-white/60 mb-3">By Method</p>
          {pieData.length > 0 ? (
            <>
              <div className="w-32 h-32">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={pieData} dataKey="value" cx="50%" cy="50%"
                      innerRadius={35} outerRadius={55} paddingAngle={3} strokeWidth={0}>
                      {pieData.map((entry, i) => (
                        <Cell key={i} fill={methodColors[entry.name] ?? '#756859'} />
                      ))}
                    </Pie>
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div className="mt-3 space-y-1.5 w-full">
                {pieData.map(d => (
                  <div key={d.name} className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full shrink-0"
                        style={{ background: methodColors[d.name] ?? '#756859' }} />
                      <span className="text-white/70">{d.name === 'BANK_TRANSFER' ? 'Bank' : d.name}</span>
                    </div>
                    <span className="tabular-nums font-semibold text-white">{formatKsh(d.value)}</span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <p className="text-xs text-white/40">No payments today</p>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Pending Approvals tile ────────────────────────────────────────────────────

function PendingApprovalsTile() {
  const { data, isLoading, isError } = useQuery<PurchaseRequest[]>({
    queryKey: ['purchase-requests'],
    queryFn: () => api.get<PurchaseRequest[]>('/inventory/purchase-requests').then(r => r.data),
    staleTime: 2 * 60_000,
  })

  if (isLoading) return <TileSkeleton />
  if (isError)   return <TileError label="Purchase Approvals" />

  const pending = (data ?? []).filter(r => r.status === 'PENDING' && r.estimated_cost !== null)

  return (
    <TileCard title="Purchase Approvals" href="/purchase-approvals">
      <p className={`text-3xl font-bold tabular-nums ${pending.length === 0 ? 'text-slate-500' : 'text-status-pending'}`}>
        {pending.length}
      </p>
      {pending.length === 0 ? (
        <p className="text-xs text-slate-400">No approvals waiting</p>
      ) : (
        <div className="space-y-1">
          {pending.slice(0, 2).map(r => (
            <p key={r.id} className="text-xs text-slate-400 truncate">
              <span className="font-medium text-white">{r.item_name}</span>
              {r.estimated_cost && <span className="text-status-pending"> · {formatKsh(r.estimated_cost)}</span>}
            </p>
          ))}
          {pending.length > 2 && (
            <p className="text-xs text-slate-500">+{pending.length - 2} more</p>
          )}
        </div>
      )}
    </TileCard>
  )
}

// ── Budget burn tile ──────────────────────────────────────────────────────────

function BudgetBurnTile() {
  const period = new Date().toISOString().slice(0, 7)
  const { data, isLoading, isError } = useQuery<{ budgets: BudgetRow[]; period: string }>({
    queryKey: ['dash-budgets', period],
    queryFn: () => api.get(`/finance/budgets/status?period=${period}`).then(r => r.data),
    staleTime: 5 * 60_000,
  })

  if (isLoading) return <TileSkeleton />
  if (isError)   return <TileError label="Budget Burn" />

  const budgets = Array.isArray(data) ? data : (data?.budgets ?? [])
  const rows = budgets.filter(r => parseFloat(r.budget) > 0)

  return (
    <TileCard title="Budget Burn" href="/finance">
      {rows.length === 0 ? (
        <p className="text-xs text-slate-500">No budgets set — go to Finance to configure.</p>
      ) : (
        <div className="space-y-2">
          {rows.slice(0, 3).map(r => (
            <div key={r.department}>
              <div className="flex justify-between text-xs mb-0.5">
                <span className="text-slate-400 truncate">{r.department}</span>
                <span className={`font-semibold tabular-nums ${r.over_budget ? 'text-status-failed' : 'text-white'}`}>
                  {Math.round(r.pct_used)}%
                </span>
              </div>
              <div className="h-1.5 rounded-full bg-cream-alt overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${r.over_budget ? 'bg-status-failed' : 'bg-accent-cool'}`}
                  style={{ width: `${Math.min(r.pct_used, 100)}%` }}
                />
              </div>
            </div>
          ))}
          {rows.length > 3 && (
            <p className="text-xs text-slate-500">+{rows.length - 3} more depts</p>
          )}
        </div>
      )}
    </TileCard>
  )
}

// ── Calendar tile ─────────────────────────────────────────────────────────────

interface CalendarEntry { id: string; title: string; date: string; is_peak: boolean; type: string }
interface CalendarData { calendar_entries: CalendarEntry[]; events: { id: string; name: string; date: string }[] }

function CalendarTile() {
  const { data, isLoading, isError } = useQuery<CalendarData>({
    queryKey: ['dash-calendar'],
    queryFn: () => api.get<CalendarData>('/dashboard/calendar').then(r => r.data),
    staleTime: 10 * 60_000,
  })

  if (isLoading) return <TileSkeleton />
  if (isError)   return <TileError label="Calendar" />

  const entries = (data?.calendar_entries ?? []).slice(0, 3)
  const events  = (data?.events ?? []).slice(0, 2)

  return (
    <TileCard title="Upcoming">
      {entries.length === 0 && events.length === 0 ? (
        <p className="text-xs text-slate-500">No upcoming events</p>
      ) : (
        <div className="space-y-1.5">
          {entries.map(e => (
            <div key={e.id} className="flex items-start gap-2">
              <span className={`shrink-0 mt-0.5 w-1.5 h-1.5 rounded-full ${e.is_peak ? 'bg-status-failed' : 'bg-status-neutral'}`} />
              <div className="min-w-0">
                <p className="text-xs font-medium text-white truncate">{e.title}</p>
                <p className="text-[10px] text-slate-500">{e.date}</p>
              </div>
            </div>
          ))}
          {events.map(e => (
            <div key={e.id} className="flex items-start gap-2">
              <span className="shrink-0 mt-0.5 w-1.5 h-1.5 rounded-full bg-primary-main" />
              <div className="min-w-0">
                <p className="text-xs font-medium text-white truncate">{e.name}</p>
                <p className="text-[10px] text-slate-500">{e.date}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </TileCard>
  )
}

// ── Existing tiles (kept, some hrefs fixed) ───────────────────────────────────

function ActiveGuestsTile() {
  const { data, isLoading, isError } = useQuery<OverviewData>({
    queryKey: ['dash-overview'],
    queryFn: () => api.get<OverviewData>('/dashboard/overview').then(r => r.data),
    staleTime: 5 * 60_000,
  })
  if (isLoading) return <TileSkeleton />
  if (isError)   return <TileError label="Active Guests" />
  const active = data!.bookings.active
  return (
    <TileCard title="Active Guests" href="/bookings">
      <p className={`text-3xl font-bold tabular-nums ${active === 0 ? 'text-slate-500' : 'text-white'}`}>
        {active}
      </p>
      <p className="text-xs text-slate-400">
        {data!.bookings.arrivals_today} arriving · {data!.bookings.departures_today} departing
      </p>
    </TileCard>
  )
}

function OpenBookingsTile() {
  const { data, isLoading, isError } = useQuery<BookingsData>({
    queryKey: ['dash-bookings'],
    queryFn: () => api.get<BookingsData>('/dashboard/bookings').then(r => r.data),
    staleTime: 5 * 60_000,
  })
  if (isLoading) return <TileSkeleton />
  if (isError)   return <TileError label="Bookings" />
  const total = Object.values(data!.occupancy_by_type).reduce((a, b) => a + b, 0)
  return (
    <TileCard title="Open Bookings" href="/bookings">
      <p className={`text-3xl font-bold tabular-nums ${total === 0 ? 'text-slate-500' : 'text-white'}`}>
        {total}
      </p>
      <p className="text-xs text-slate-400">
        {data!.arrivals_today.length} arrivals · {data!.departures_today.length} departures today
      </p>
      {data!.pending_deposits.length > 0 && (
        <p className="text-xs text-status-pending font-medium">
          {data!.pending_deposits.length} pending deposit{data!.pending_deposits.length !== 1 ? 's' : ''}
        </p>
      )}
    </TileCard>
  )
}

function StaffOnDutyTile() {
  const { data, isLoading, isError } = useQuery<StaffData>({
    queryKey: ['dash-staff'],
    queryFn: () => api.get<StaffData>('/dashboard/staff').then(r => r.data),
    staleTime: 5 * 60_000,
  })
  if (isLoading) return <TileSkeleton />
  if (isError)   return <TileError label="Staff On Duty" />
  const { on_duty, active_employees, absent_today } = data!
  return (
    <TileCard title="Staff On Duty" href="/staff">
      <p className="text-3xl font-bold tabular-nums text-white">{on_duty}</p>
      <p className="text-xs text-slate-400">
        of {active_employees} active · {absent_today} absent today
      </p>
    </TileCard>
  )
}

function AlertsTile() {
  const { data, isLoading, isError } = useQuery<AlertItem[]>({
    queryKey: ['dash-alerts'],
    queryFn: () => api.get<AlertItem[]>('/dashboard/alerts').then(r => r.data),
    staleTime: 5 * 60_000,
  })
  if (isLoading) return <TileSkeleton />
  if (isError)   return <TileError label="Judge Alerts" />
  const count = data!.length
  return (
    <TileCard title="Judge Alerts" href="/alerts">
      <p className={`text-3xl font-bold tabular-nums ${alertCountColor(count)}`}>{count}</p>
      {count === 0 ? (
        <p className="text-xs text-slate-400">No open alerts</p>
      ) : (
        <div className="space-y-1 mt-1">
          {data!.slice(0, 3).map(a => (
            <p key={a.id} className="text-xs text-slate-400 truncate">
              <span className={`font-semibold ${a.severity === 'HIGH' ? 'text-status-failed' : 'text-status-pending'}`}>
                {a.severity}
              </span>{' · '}{a.description.slice(0, 52)}{a.description.length > 52 ? '…' : ''}
            </p>
          ))}
        </div>
      )}
    </TileCard>
  )
}

function LowStockTile() {
  const { data, isLoading, isError } = useQuery<InventoryData>({
    queryKey: ['dash-inventory'],
    queryFn: () => api.get<InventoryData>('/dashboard/inventory').then(r => r.data),
    staleTime: 5 * 60_000,
  })
  if (isLoading) return <TileSkeleton />
  if (isError)   return <TileError label="Inventory" />
  const low = data!.low_stock_count
  const lowItems = data!.items.filter(i => i.is_low).slice(0, 3).map(i => i.name)
  return (
    <TileCard title="Low Stock">
      <p className={`text-3xl font-bold tabular-nums ${low === 0 ? 'text-status-paid' : 'text-status-failed'}`}>{low}</p>
      {low === 0 ? (
        <p className="text-xs text-slate-400">All {data!.total_skus} SKUs stocked</p>
      ) : (
        <p className="text-xs text-slate-400 truncate">{lowItems.join(', ')}{low > 3 ? ` +${low - 3} more` : ''}</p>
      )}
    </TileCard>
  )
}

function FinanceTile() {
  const { data, isLoading, isError } = useQuery<FinanceData>({
    queryKey: ['dash-finance'],
    queryFn: () => api.get<FinanceData>('/dashboard/finance').then(r => r.data),
    staleTime: 5 * 60_000,
  })
  if (isLoading) return <TileSkeleton />
  if (isError)   return <TileError label="Financial Health" />
  const { reconciliation_status, open_shortfalls, unmatched_mpesa } = data!
  return (
    <TileCard title="Financial Health" href="/finance">
      <StatusBadge status={reconBadge(reconciliation_status)} />
      <div className="text-xs text-slate-400 space-y-0.5 mt-1">
        <p>Shortfalls: <span className={open_shortfalls > 0 ? 'text-status-failed font-semibold' : ''}>{open_shortfalls}</span></p>
        <p>Unmatched M-Pesa: <span className={unmatched_mpesa > 0 ? 'text-status-pending font-semibold' : ''}>{unmatched_mpesa}</span></p>
      </div>
    </TileCard>
  )
}

function FeedbackTile() {
  const { data, isLoading, isError } = useQuery<FeedbackData>({
    queryKey: ['dash-feedback'],
    queryFn: () => api.get<FeedbackData>('/dashboard/feedback').then(r => r.data),
    staleTime: 5 * 60_000,
  })
  if (isLoading) return <TileSkeleton />
  if (isError)   return <TileError label="Guest Feedback" />
  const avg = data!.overall_avg
  const commentCount = data!.recent_comments.length
  return (
    <TileCard title="Feedback Score">
      <p className={`text-3xl font-bold tabular-nums ${avg ? 'text-white' : 'text-slate-500'}`}>
        {formatAvg(avg)}
      </p>
      <p className="text-xs text-slate-400">
        {commentCount > 0 ? `${commentCount} recent comment${commentCount !== 1 ? 's' : ''}` : 'No feedback this period'}
      </p>
    </TileCard>
  )
}

function SuggestionsTile() {
  const { data, isLoading, isError } = useQuery<SuggestionsData>({
    queryKey: ['dash-suggestions'],
    queryFn: () => api.get<SuggestionsData>('/dashboard/suggestions').then(r => r.data),
    staleTime: 5 * 60_000,
  })
  if (isLoading) return <TileSkeleton />
  if (isError)   return <TileError label="Suggestions" />
  const newMgmt    = data!.management.length
  const newPrivate = data!.owner_private.length
  const total      = newMgmt + newPrivate
  return (
    <TileCard title="Suggestions">
      <p className={`text-3xl font-bold tabular-nums ${total === 0 ? 'text-slate-500' : 'text-white'}`}>
        {total}
      </p>
      <p className="text-xs text-slate-400">Owner-private: {newPrivate} · Management: {newMgmt}</p>
    </TileCard>
  )
}

function EquipmentTile() {
  const { data, isLoading, isError } = useQuery<EquipmentData>({
    queryKey: ['dash-equipment'],
    queryFn: () => api.get<EquipmentData>('/dashboard/equipment').then(r => r.data),
    staleTime: 5 * 60_000,
  })
  if (isLoading) return <TileSkeleton />
  if (isError)   return <TileError label="Equipment" />
  const due = data!.due_service
  const inMx = data!.in_maintenance.length
  return (
    <TileCard title="Equipment">
      <p className={`text-3xl font-bold tabular-nums ${due.length > 0 ? 'text-status-pending' : 'text-status-paid'}`}>
        {due.length}
      </p>
      <p className="text-xs text-slate-400">
        {due.length === 0
          ? `All ${data!.total} items serviced`
          : `due service · ${inMx} in maintenance`}
      </p>
      {due.length > 0 && (
        <p className="text-xs text-slate-400 truncate">
          {due.slice(0, 2).map(e => e.name).join(', ')}{due.length > 2 ? ` +${due.length - 2} more` : ''}
        </p>
      )}
    </TileCard>
  )
}

// ── Top bar strip ─────────────────────────────────────────────────────────────

function TopBar({ onRefresh }: { onRefresh: () => void }) {
  const overview = useQuery<OverviewData>({
    queryKey: ['dash-overview'],
    queryFn: () => api.get<OverviewData>('/dashboard/overview').then(r => r.data),
    staleTime: 5 * 60_000,
  })
  const alerts = useQuery<AlertItem[]>({
    queryKey: ['dash-alerts'],
    queryFn: () => api.get<AlertItem[]>('/dashboard/alerts').then(r => r.data),
    staleTime: 5 * 60_000,
  })

  return (
    <div className="flex items-center gap-4 rounded-2xl p-3 mb-4 glass-card">
      <div className="flex-1 flex items-center gap-6 overflow-x-auto scrollbar-none min-w-0">
        <div className="shrink-0">
          <p className="text-[10px] font-semibold tracking-widest uppercase text-slate-400">Revenue Today</p>
          <p className="text-base font-bold tabular-nums text-white leading-tight">
            {overview.data ? formatKsh(overview.data.revenue.total) : '—'}
          </p>
        </div>
        <div className="w-px h-8 bg-cream-alt shrink-0" />
        <div className="shrink-0">
          <p className="text-[10px] font-semibold tracking-widest uppercase text-slate-400">Alerts Open</p>
          <p className={`text-base font-bold tabular-nums leading-tight ${alerts.data !== undefined ? alertCountColor(alerts.data.length) : 'text-slate-500'}`}>
            {alerts.data !== undefined ? alerts.data.length : '—'}
          </p>
        </div>
        <div className="w-px h-8 bg-cream-alt shrink-0" />
        <div className="shrink-0">
          <p className="text-[10px] font-semibold tracking-widest uppercase text-slate-400">Staff on Duty</p>
          <p className="text-base font-bold tabular-nums text-white leading-tight">
            {overview.data?.staff.on_duty ?? '—'}
          </p>
        </div>
      </div>
      <button
        onClick={onRefresh}
        className="shrink-0 w-9 h-9 flex items-center justify-center rounded-xl
          border border-cream-alt hover:bg-cream-alt transition-colors
          focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-main"
        aria-label="Refresh all tiles"
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
          <path d="M13.5 8A5.5 5.5 0 112.5 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
          <path d="M13.5 5v3h-3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </button>
    </div>
  )
}

// ── Main screen ───────────────────────────────────────────────────────────────

const DASHBOARD_QUERY_KEYS = [
  ['dash-overview'], ['dash-revenue-history'], ['dash-inventory'], ['dash-finance'],
  ['dash-bookings'], ['dash-staff'], ['dash-alerts'], ['dash-feedback'],
  ['dash-suggestions'], ['dash-equipment'], ['dash-calendar'], ['purchase-requests'],
]

export default function DashboardScreen() {
  const queryClient = useQueryClient()

  function refreshAll() {
    DASHBOARD_QUERY_KEYS.forEach(key => queryClient.invalidateQueries({ queryKey: key }))
  }

  const tiles = [
    <ErrorBoundary key="guests"      level="tile"><ActiveGuestsTile     /></ErrorBoundary>,
    <ErrorBoundary key="bookings"    level="tile"><OpenBookingsTile     /></ErrorBoundary>,
    <ErrorBoundary key="staff"       level="tile"><StaffOnDutyTile      /></ErrorBoundary>,
    <ErrorBoundary key="alerts"      level="tile"><AlertsTile           /></ErrorBoundary>,
    <ErrorBoundary key="stock"       level="tile"><LowStockTile         /></ErrorBoundary>,
    <ErrorBoundary key="approvals"   level="tile"><PendingApprovalsTile /></ErrorBoundary>,
    <ErrorBoundary key="budget"      level="tile"><BudgetBurnTile       /></ErrorBoundary>,
    <ErrorBoundary key="finance"     level="tile"><FinanceTile          /></ErrorBoundary>,
    <ErrorBoundary key="feedback"    level="tile"><FeedbackTile         /></ErrorBoundary>,
    <ErrorBoundary key="suggestions" level="tile"><SuggestionsTile      /></ErrorBoundary>,
    <ErrorBoundary key="equipment"   level="tile"><EquipmentTile        /></ErrorBoundary>,
    <ErrorBoundary key="calendar"    level="tile"><CalendarTile         /></ErrorBoundary>,
  ]

  const hour = new Date().getHours()
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'

  return (
    <div className="min-h-screen p-4 md:p-6">
      <div className="max-w-6xl mx-auto">
      <div className="mb-6 flex items-end justify-between">
        <div>
          <p className="text-sm text-slate-400">{greeting},</p>
          <h1 className="font-serif text-3xl md:text-4xl font-bold text-white tracking-tight">
            Wachira
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            Waterfront Country Club &middot; {new Date().toLocaleDateString('en-KE', { weekday: 'long', day: 'numeric', month: 'long' })}
          </p>
        </div>
        <TopBar onRefresh={refreshAll} />
      </div>

      <motion.div
        variants={gridVariants}
        initial="initial"
        animate="animate"
        className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3"
      >
        {/* Hero tile spans full width */}
        <motion.div variants={tileVariants} className="col-span-full">
          <HeroTile />
        </motion.div>

        {/* Remaining tiles */}
        {tiles.map((tile, i) => (
          <motion.div key={i} variants={tileVariants}>
            {tile}
          </motion.div>
        ))}
      </motion.div>
      </div>
    </div>
  )
}
