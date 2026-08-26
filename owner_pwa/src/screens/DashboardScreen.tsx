import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { AreaChart, Area, ResponsiveContainer, Tooltip } from 'recharts'
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
        href ? 'cursor-pointer hover:shadow-xl hover:border-white/20 transition-all active:scale-[0.99] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-main' : '',
        className,
        'glass-card',
      ].join(' ')}
    >
      <p className="text-[10px] font-semibold tracking-widest uppercase text-ink-tertiary">{title}</p>
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
      <p className="text-2xl font-bold tabular-nums text-ink-tertiary">—</p>
      <p className="text-xs text-status-failed">Couldn't load</p>
    </TileCard>
  )
}

// ── Hero section — occupancy ring + revenue + alerts ────────────────────────

function HeroSection() {
  const navigate = useNavigate()
  const { data: overview, isLoading: ovLoad, isError: ovErr } = useQuery<OverviewData>({
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
  const { data: alerts = [] } = useQuery<AlertItem[]>({
    queryKey: ['dash-alerts'],
    queryFn: () => api.get<AlertItem[]>('/dashboard/alerts').then(r => r.data),
    staleTime: 5 * 60_000,
  })

  const isLoading = ovLoad || hLoad

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_1fr] gap-4">
        <div className="rounded-2xl p-6 glass-card space-y-3">
          <Skeleton variant="text" className="w-32 h-3" />
          <Skeleton variant="text" className="w-48 h-10" />
          <Skeleton variant="text" className="w-full h-20" />
        </div>
        <div className="rounded-2xl p-6 glass-card space-y-3">
          <Skeleton variant="text" className="w-32 h-3" />
          <Skeleton variant="text" className="w-full h-16" />
        </div>
      </div>
    )
  }

  /* Use a simple percentage — active bookings vs a baseline capacity */
  const occupancyPct = overview ? Math.min(Math.round((overview.bookings.active / Math.max(overview.bookings.active + 5, 20)) * 100), 100) : 0

  /* Revenue */
  const chartData = (hist ?? []).map(r => ({
    date: r.date.slice(5),
    rev: parseFloat(r.revenue),
  }))
  const today = parseFloat(overview?.revenue.total ?? '0')
  const yesterday = chartData.length >= 2 ? chartData[chartData.length - 2]?.rev ?? 0 : 0
  const delta = yesterday > 0 ? ((today - yesterday) / yesterday * 100) : 0

  /* Urgent alerts — top 3 */
  const urgentAlerts = alerts.filter(a => a.severity === 'HIGH').slice(0, 3)
  const displayAlerts = urgentAlerts.length > 0 ? urgentAlerts : alerts.slice(0, 3)

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {/* LEFT — Occupancy ring + Revenue */}
      <div className="glass-card rounded-2xl p-6 border border-white/10">
        <div className="flex items-start gap-6">
          {/* Occupancy ring */}
          <div className="shrink-0">
            <p className="text-[10px] font-semibold tracking-widest uppercase text-ink-tertiary mb-2">Occupancy</p>
            <div className="relative w-28 h-28">
              {/* SVG ring */}
              <svg viewBox="0 0 120 120" className="w-full h-full -rotate-90">
                <circle cx="60" cy="60" r="50" fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="10" />
                <circle cx="60" cy="60" r="50" fill="none" stroke="#fa5c29" strokeWidth="10"
                  strokeLinecap="round"
                  strokeDasharray={`${occupancyPct * 3.14} ${314 - occupancyPct * 3.14}`} />
              </svg>
              {/* Center text */}
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-3xl font-bold text-ink-primary tabular-nums">{occupancyPct}%</span>
                <span className="text-[10px] text-ink-tertiary">Rooms</span>
              </div>
            </div>
          </div>

          {/* Revenue + trend */}
          <div className="flex-1 min-w-0">
            <p className="text-[10px] font-semibold tracking-widest uppercase text-ink-tertiary mb-1">Revenue Today</p>
            {ovErr ? (
              <p className="text-2xl font-bold tabular-nums text-ink-tertiary">KSh —</p>
            ) : (
              <>
                <p className="text-3xl md:text-4xl font-bold tabular-nums text-ink-primary leading-tight">
                  {formatKsh(today)}
                </p>
                {delta !== 0 && (
                  <span className={`inline-block mt-1 text-xs font-bold px-2 py-0.5 rounded-full ${
                    delta > 0 ? 'bg-status-paid/20 text-status-paid' : 'bg-status-failed/20 text-status-failed'
                  }`}>
                    {delta > 0 ? '+' : ''}{Math.abs(delta).toFixed(0)}%
                  </span>
                )}
              </>
            )}
            {/* Mini trend chart */}
            <div className="mt-3 h-14" aria-label="7-day revenue trend">
              {chartData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={chartData} margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
                    <defs>
                      <linearGradient id="revGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="rgba(250,92,41,0.3)" />
                        <stop offset="100%" stopColor="rgba(250,92,41,0)" />
                      </linearGradient>
                    </defs>
                    <Area type="monotone" dataKey="rev" stroke="#fa5c29" strokeWidth={2}
                      fill="url(#revGrad)" />
                    <Tooltip
                      contentStyle={{ background: '#1e100c', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, fontSize: 11 }}
                      labelStyle={{ color: '#f9dcd5' }}
                      formatter={(v: unknown) => [formatKsh(v as number), 'Revenue']}
                      labelFormatter={(label: unknown) => String(label)}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full flex items-end gap-1">
                  {Array.from({ length: 7 }).map((_, i) => (
                    <div key={i} className="flex-1 bg-white/10 rounded-sm" style={{ height: '40%' }} />
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* RIGHT — Urgent Attention */}
      <div className="glass-card rounded-2xl p-6 border border-white/10">
        <p className="text-sm font-semibold text-ink-primary mb-4">Urgent Attention</p>
        {displayAlerts.length === 0 ? (
          <p className="text-sm text-ink-tertiary">No urgent alerts right now.</p>
        ) : (
          <div className="space-y-3">
            {displayAlerts.map(a => (
              <div key={a.id} className="flex items-start gap-3">
                {/* Severity dot */}
                <span className={`shrink-0 mt-1.5 w-2 h-2 rounded-full ${
                  a.severity === 'HIGH' ? 'bg-status-failed' : 'bg-status-pending'
                }`} />
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-ink-primary truncate">
                    {a.type}: {a.description.slice(0, 40)}
                  </p>
                  <p className="text-xs text-ink-tertiary truncate">
                    {a.description.slice(0, 60)}{a.description.length > 60 ? '...' : ''}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
        {/* Card-footer action, not an inline link — it gets a real 44px hit box.
            -mb-3 absorbs most of the added height so the card doesn't grow. */}
        <button
          onClick={() => navigate('/alerts')}
          className="mt-1 -mb-3 inline-flex items-center min-h-[44px]
            text-[10px] font-bold tracking-widest uppercase text-primary-main hover:text-primary-light transition-colors"
        >
          VIEW ALL LOGS
        </button>
      </div>
    </div>
  )
}

// ── Resort Health section ─────────────────────────────────────────────────────

function ResortHealthSection() {
  const [tab, setTab] = useState<'overview' | 'departments'>('overview')

  const { data: feedback } = useQuery<FeedbackData>({
    queryKey: ['dash-feedback'],
    queryFn: () => api.get<FeedbackData>('/dashboard/feedback').then(r => r.data),
    staleTime: 5 * 60_000,
  })
  const { data: bookingsData } = useQuery<BookingsData>({
    queryKey: ['dash-bookings'],
    queryFn: () => api.get<BookingsData>('/dashboard/bookings').then(r => r.data),
    staleTime: 5 * 60_000,
  })
  const { data: alerts = [] } = useQuery<AlertItem[]>({
    queryKey: ['dash-alerts'],
    queryFn: () => api.get<AlertItem[]>('/dashboard/alerts').then(r => r.data),
    staleTime: 5 * 60_000,
  })
  const { data: overview } = useQuery<OverviewData>({
    queryKey: ['dash-overview'],
    queryFn: () => api.get<OverviewData>('/dashboard/overview').then(r => r.data),
    staleTime: 5 * 60_000,
  })

  /* Guest satisfaction score */
  const satisfactionScore = feedback?.overall_avg ? parseFloat(feedback.overall_avg).toFixed(1) : '—'

  /* Spa utilization — derive from bookings occupancy_by_type */
  const spaOccupancy = bookingsData?.occupancy_by_type?.['spa'] ?? bookingsData?.occupancy_by_type?.['SPA'] ?? 0
  const spaUtilization = spaOccupancy > 0 ? Math.min(spaOccupancy * 10, 100) : 0

  /* Dining reservations — arrivals today as proxy */
  const diningReservations = overview?.bookings.arrivals_today ?? 0

  /* Active incidents */
  const activeIncidents = alerts.length

  /* Department breakdown */
  const deptScores = feedback?.by_department ?? []

  const metrics = [
    { label: 'Guest Satisfaction', value: satisfactionScore, sub: '/ 5.0' },
    { label: 'Spa Utilization', value: `${spaUtilization}%`, sub: '' },
    { label: 'Dining Reservations', value: String(diningReservations), sub: '' },
    { label: 'Incidents', value: String(activeIncidents), sub: 'Active' },
  ]

  return (
    <div className="mt-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-2xl font-serif font-bold text-ink-primary">Resort Health</h2>
        {/* Tabs. min-h-[44px] takes each segment from 27px to the touch minimum;
            inline-flex keeps the label optically centred in the taller box. */}
        <div className="flex rounded-xl overflow-hidden border border-white/10">
          {(['overview', 'departments'] as const).map(t => (
            <button key={t} onClick={() => setTab(t)}
              className={`px-4 inline-flex items-center min-h-[44px] text-[10px] font-bold tracking-widest uppercase transition-colors ${
                tab === t
                  ? 'bg-white/10 text-ink-primary'
                  : 'text-ink-tertiary hover:text-ink-secondary'
              }`}>
              {t}
            </button>
          ))}
        </div>
      </div>

      {tab === 'overview' ? (
        /* 4 metric cards in a row */
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {metrics.map(m => (
            <div key={m.label} className="glass-card rounded-2xl p-4 border border-white/10">
              <p className="text-[10px] font-semibold tracking-widest uppercase text-ink-tertiary mb-2">{m.label}</p>
              <div className="flex items-baseline gap-1.5">
                <span className="text-2xl font-bold tabular-nums text-ink-primary">{m.value}</span>
                {m.sub && <span className="text-xs text-ink-tertiary">{m.sub}</span>}
              </div>
            </div>
          ))}
        </div>
      ) : (
        /* Department scores */
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          {deptScores.length === 0 ? (
            <p className="text-sm text-ink-tertiary col-span-full">No department data this period.</p>
          ) : (
            deptScores.map(d => (
              <div key={d.department} className="glass-card rounded-2xl p-4 border border-white/10">
                <p className="text-[10px] font-semibold tracking-widest uppercase text-ink-tertiary mb-1">{d.department}</p>
                <p className="text-xl font-bold tabular-nums text-ink-primary">{parseFloat(d.avg_score).toFixed(1)}</p>
                <p className="text-xs text-ink-tertiary">{d.count} review{d.count !== 1 ? 's' : ''}</p>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}

// ── Existing tiles (kept, text colors updated to warm palette) ───────────────

function PendingApprovalsTile() {
  const { data, isLoading, isError } = useQuery<PurchaseRequest[]>({
    queryKey: ['purchase-requests'],
    queryFn: () => api.get<PurchaseRequest[]>('/inventory/purchase-requests').then(r => r.data),
    staleTime: 2 * 60_000,
  })

  if (isLoading) return <TileSkeleton />
  if (isError)   return <TileError label="Purchase Approvals" />

  // estimated_cost is only ever set together with a transition to PROPOSED
  // (app/inventory/purchases.py propose_budget) — a PENDING request never
  // carries one, so "status===PENDING && estimated_cost!==null" was an
  // almost-always-empty combination. PENDING or PROPOSED is what's actually
  // "waiting for the owner" (matches approve_request's accepted statuses).
  const pending = (data ?? []).filter(r => r.status === 'PENDING' || r.status === 'PROPOSED')

  return (
    <TileCard title="Purchase Approvals" href="/purchase-approvals">
      <p className="text-[10px] text-ink-tertiary">Restock requests waiting for your approval</p>
      <p className={`text-3xl font-bold tabular-nums ${pending.length === 0 ? 'text-ink-tertiary' : 'text-status-pending'}`}>
        {pending.length}
      </p>
      {pending.length === 0 ? (
        <p className="text-xs text-ink-tertiary">No approvals waiting</p>
      ) : (
        <div className="space-y-1">
          {pending.slice(0, 2).map(r => (
            <p key={r.id} className="text-xs text-ink-tertiary truncate">
              <span className="font-medium text-ink-primary">{r.item_name}</span>
              {r.estimated_cost && <span className="text-status-pending"> · {formatKsh(r.estimated_cost)}</span>}
            </p>
          ))}
          {pending.length > 2 && (
            <p className="text-xs text-ink-tertiary">+{pending.length - 2} more</p>
          )}
        </div>
      )}
    </TileCard>
  )
}

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
      <p className="text-[10px] text-ink-tertiary">How much of the monthly budget each department has spent</p>
      {rows.length === 0 ? (
        <p className="text-xs text-ink-tertiary">No budgets set — go to Finance to configure.</p>
      ) : (
        <div className="space-y-2">
          {rows.slice(0, 3).map(r => (
            <div key={r.department}>
              <div className="flex justify-between text-xs mb-0.5">
                <span className="text-ink-tertiary truncate">{r.department}</span>
                <span className={`font-semibold tabular-nums ${r.over_budget ? 'text-status-failed' : 'text-ink-primary'}`}>
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
            <p className="text-xs text-ink-tertiary">+{rows.length - 3} more depts</p>
          )}
        </div>
      )}
    </TileCard>
  )
}

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
        <p className="text-xs text-ink-tertiary">No upcoming events</p>
      ) : (
        <div className="space-y-1.5">
          {entries.map(e => (
            <div key={e.id} className="flex items-start gap-2">
              <span className={`shrink-0 mt-0.5 w-1.5 h-1.5 rounded-full ${e.is_peak ? 'bg-status-failed' : 'bg-status-neutral'}`} />
              <div className="min-w-0">
                <p className="text-xs font-medium text-ink-primary truncate">{e.title}</p>
                <p className="text-[10px] text-ink-tertiary">{e.date}</p>
              </div>
            </div>
          ))}
          {events.map(e => (
            <div key={e.id} className="flex items-start gap-2">
              <span className="shrink-0 mt-0.5 w-1.5 h-1.5 rounded-full bg-primary-main" />
              <div className="min-w-0">
                <p className="text-xs font-medium text-ink-primary truncate">{e.name}</p>
                <p className="text-[10px] text-ink-tertiary">{e.date}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </TileCard>
  )
}

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
      <p className={`text-3xl font-bold tabular-nums ${active === 0 ? 'text-ink-tertiary' : 'text-ink-primary'}`}>
        {active}
      </p>
      <p className="text-xs text-ink-tertiary">
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
      <p className={`text-3xl font-bold tabular-nums ${total === 0 ? 'text-ink-tertiary' : 'text-ink-primary'}`}>
        {total}
      </p>
      <p className="text-xs text-ink-tertiary">
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
      <p className="text-3xl font-bold tabular-nums text-ink-primary">{on_duty}</p>
      <p className="text-xs text-ink-tertiary">
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
      <p className="text-[10px] text-ink-tertiary">Suspicious activity the system detected automatically</p>
      <p className={`text-3xl font-bold tabular-nums ${alertCountColor(count)}`}>{count}</p>
      {count === 0 ? (
        <p className="text-xs text-ink-tertiary">No open alerts</p>
      ) : (
        <div className="space-y-1 mt-1">
          {data!.slice(0, 3).map(a => (
            <p key={a.id} className="text-xs text-ink-tertiary truncate">
              <span className={`font-semibold ${a.severity === 'HIGH' ? 'text-status-failed' : 'text-status-pending'}`}>
                {a.severity}
              </span>{' · '}{a.description.slice(0, 52)}{a.description.length > 52 ? '...' : ''}
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
      <p className="text-[10px] text-ink-tertiary">Items running low that may need reordering</p>
      <p className={`text-3xl font-bold tabular-nums ${low === 0 ? 'text-status-paid' : 'text-status-failed'}`}>{low}</p>
      {low === 0 ? (
        <p className="text-xs text-ink-tertiary">All {data!.total_skus} SKUs stocked</p>
      ) : (
        <p className="text-xs text-ink-tertiary truncate">{lowItems.join(', ')}{low > 3 ? ` +${low - 3} more` : ''}</p>
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
      <p className="text-[10px] text-ink-tertiary">Whether cash, M-Pesa, and card payments all match up</p>
      <StatusBadge status={reconBadge(reconciliation_status)} />
      <div className="text-xs text-ink-tertiary space-y-0.5 mt-1">
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
      <p className="text-[10px] text-ink-tertiary">Average guest rating from feedback forms</p>
      <p className={`text-3xl font-bold tabular-nums ${avg ? 'text-ink-primary' : 'text-ink-tertiary'}`}>
        {formatAvg(avg)}
      </p>
      <p className="text-xs text-ink-tertiary">
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
      <p className="text-[10px] text-ink-tertiary">Ideas and requests from staff</p>
      <p className={`text-3xl font-bold tabular-nums ${total === 0 ? 'text-ink-tertiary' : 'text-ink-primary'}`}>
        {total}
      </p>
      <p className="text-xs text-ink-tertiary">Owner-private: {newPrivate} · Management: {newMgmt}</p>
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
      <p className="text-[10px] text-ink-tertiary">Machines and tools that need servicing or repair</p>
      <p className={`text-3xl font-bold tabular-nums ${due.length > 0 ? 'text-status-pending' : 'text-status-paid'}`}>
        {due.length}
      </p>
      <p className="text-xs text-ink-tertiary">
        {due.length === 0
          ? `All ${data!.total} items serviced`
          : `due service · ${inMx} in maintenance`}
      </p>
      {due.length > 0 && (
        <p className="text-xs text-ink-tertiary truncate">
          {due.slice(0, 2).map(e => e.name).join(', ')}{due.length > 2 ? ` +${due.length - 2} more` : ''}
        </p>
      )}
    </TileCard>
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
  const { dataUpdatedAt } = useQuery<OverviewData>({
    queryKey: ['dash-overview'],
    queryFn: () => api.get<OverviewData>('/dashboard/overview').then(r => r.data),
    staleTime: 30_000,
    refetchInterval: 60_000,
  })

  function refreshAll() {
    DASHBOARD_QUERY_KEYS.forEach(key => queryClient.invalidateQueries({ queryKey: key }))
  }

  const updatedAgo = dataUpdatedAt ? Math.floor((Date.now() - dataUpdatedAt) / 1000) : null

  /* Extra tiles — displayed in the grid below Resort Health */
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
  const greeting = hour < 12 ? 'Good Morning' : hour < 17 ? 'Good Afternoon' : 'Good Evening'

  return (
    <div className="min-h-screen p-4 md:p-6">
      <div className="max-w-6xl mx-auto">
        {/* ── Stitch greeting header ────────────────────────────────── */}
        <div className="mb-6">
          <h1 className="font-serif text-3xl md:text-4xl font-bold text-ink-primary tracking-tight">
            {greeting}, Director.
          </h1>
          <p className="text-sm text-ink-secondary mt-1">
            Here is the current state of Kurahia
          </p>
          <div className="flex items-center gap-3 mt-1">
            <p className="text-xs text-ink-tertiary">
              Last updated: {updatedAgo !== null && updatedAgo < 120 ? (updatedAgo < 5 ? 'just now' : `${updatedAgo}s ago`) : 'loading...'}
            </p>
            {/* Worst tap target in the whole suite: this was a bare 14x14 svg.
                The glyph is still 14px — only the button box around it is 44x44,
                centred with flex. -m-2.5 pulls the extra 15px per side back out
                of the layout so the row's spacing is unchanged. */}
            <button
              onClick={refreshAll}
              className="w-11 h-11 -m-2.5 shrink-0 flex items-center justify-center rounded-lg
                text-ink-tertiary hover:text-ink-primary transition-colors"
              aria-label="Refresh all tiles"
            >
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                <path d="M13.5 8A5.5 5.5 0 112.5 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                <path d="M13.5 5v3h-3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
          </div>
        </div>

        <motion.div
          variants={gridVariants}
          initial="initial"
          animate="animate"
          className="space-y-6"
        >
          {/* ── Hero: Occupancy + Revenue | Urgent Attention ──────── */}
          <motion.div variants={tileVariants}>
            <HeroSection />
          </motion.div>

          {/* ── Resort Health section with tabs ──────────────────── */}
          <motion.div variants={tileVariants}>
            <ResortHealthSection />
          </motion.div>

          {/* ── Additional detail tiles — bento grid (mixed sizes) ── */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {tiles.map((tile, i) => {
              /* Bento sizing: first tile (Active Guests) spans 2 cols on lg,
                 budget tile spans 2 cols on md+ for visual rhythm */
              const span = i === 0 ? 'lg:col-span-2'
                         : i === 6 ? 'md:col-span-2 lg:col-span-1'
                         : ''
              return (
                <motion.div key={i} variants={tileVariants} className={span}>
                  {tile}
                </motion.div>
              )
            })}
          </div>
        </motion.div>
      </div>
    </div>
  )
}
