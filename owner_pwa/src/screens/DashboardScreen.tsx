import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { Skeleton, StatusBadge } from '@shared'
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

interface SuggestionItem {
  id: string
  subject: string
  status: string
  submitted_by: string
}

interface SuggestionsData {
  management: SuggestionItem[]
  owner_private: SuggestionItem[]
}

interface EquipmentData {
  total: number
  due_service: { id: string; name: string; type: string; last_service: string | null }[]
  in_maintenance: { id: string; name: string }[]
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

const gridVariants = {
  animate: { transition: { staggerChildren: 0.05 } },
}

const tileVariants = {
  initial: { opacity: 0, y: 16 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.28, ease: 'easeOut' as const } },
}

// ── Shared tile wrappers ──────────────────────────────────────────────────────

function TileCard({
  title,
  href,
  children,
}: {
  title: string
  href?: string
  children: React.ReactNode
}) {
  const navigate = useNavigate()
  return (
    <div
      role={href ? 'button' : undefined}
      tabIndex={href ? 0 : undefined}
      onClick={href ? () => navigate(href) : undefined}
      onKeyDown={href ? (e) => { if (e.key === 'Enter') navigate(href) } : undefined}
      className={[
        'rounded-2xl bg-cream-card border border-cream-alt p-4 space-y-2',
        href ? 'cursor-pointer hover:shadow-sm hover:border-primary-light/40 transition-all active:scale-[0.99] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-main' : '',
      ].join(' ')}
    >
      <p className="text-[10px] font-semibold tracking-widest uppercase text-ink-tertiary">{title}</p>
      {children}
    </div>
  )
}

function TileSkeleton() {
  return (
    <div className="rounded-2xl bg-cream-card border border-cream-alt p-4 space-y-3">
      <Skeleton variant="text" className="w-24 h-3" />
      <Skeleton variant="text" className="w-32 h-8" />
      <Skeleton variant="text" className="w-40 h-3" />
    </div>
  )
}

function TileError({ label }: { label: string }) {
  return (
    <TileCard title={label}>
      <p className="text-2xl font-bold tabular-nums text-ink-tertiary">—</p>
      <p className="text-xs text-status-failed">Couldn't load</p>
    </TileCard>
  )
}

// ── Tiles ─────────────────────────────────────────────────────────────────────

function RevenueTile() {
  const { data, isLoading, isError } = useQuery<OverviewData>({
    queryKey: ['dash-overview'],
    queryFn: () => api.get<OverviewData>('/dashboard/overview').then((r) => r.data),
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: true,
  })

  if (isLoading) return <TileSkeleton />
  if (isError)   return <TileError label="Revenue Today" />

  const byMethod = data!.revenue.by_method
  const parts    = Object.entries(byMethod).map(([k, v]) => `${k} ${formatKsh(v)}`).join(' · ')

  return (
    <TileCard title="Revenue Today" href="/finance">
      <p className="text-3xl font-bold tabular-nums text-ink-primary">
        {formatKsh(data!.revenue.total)}
      </p>
      {parts ? (
        <p className="text-xs text-ink-tertiary truncate">{parts}</p>
      ) : (
        <p className="text-xs text-ink-tertiary">No payments recorded yet</p>
      )}
    </TileCard>
  )
}

function ActiveGuestsTile() {
  const { data, isLoading, isError } = useQuery<OverviewData>({
    queryKey: ['dash-overview'],   // shares cache with RevenueTile — no extra request
    queryFn: () => api.get<OverviewData>('/dashboard/overview').then((r) => r.data),
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: true,
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
        {data!.bookings.arrivals_today} arriving · {data!.bookings.departures_today} departing today
      </p>
    </TileCard>
  )
}

function OpenBookingsTile() {
  const { data, isLoading, isError } = useQuery<BookingsData>({
    queryKey: ['dash-bookings'],
    queryFn: () => api.get<BookingsData>('/dashboard/bookings').then((r) => r.data),
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: true,
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
    queryFn: () => api.get<StaffData>('/dashboard/staff').then((r) => r.data),
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: true,
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
    queryFn: () => api.get<AlertItem[]>('/dashboard/alerts').then((r) => r.data),
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: true,
  })

  if (isLoading) return <TileSkeleton />
  if (isError)   return <TileError label="Judge Alerts" />

  const alerts = data!
  const count  = alerts.length

  return (
    <TileCard title="Judge Alerts" href="/alerts">
      <p className={`text-3xl font-bold tabular-nums ${alertCountColor(count)}`}>
        {count}
      </p>
      {count === 0 ? (
        <p className="text-xs text-ink-tertiary">No open alerts</p>
      ) : (
        <div className="space-y-1 mt-1">
          {alerts.slice(0, 3).map((a) => (
            <p key={a.id} className="text-xs text-ink-secondary truncate">
              <span className={`font-semibold ${a.severity === 'HIGH' ? 'text-status-failed' : 'text-status-pending'}`}>
                {a.severity}
              </span>
              {' · '}{a.description.slice(0, 55)}{a.description.length > 55 ? '…' : ''}
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
    queryFn: () => api.get<InventoryData>('/dashboard/inventory').then((r) => r.data),
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: true,
  })

  if (isLoading) return <TileSkeleton />
  if (isError)   return <TileError label="Inventory" />

  const low = data!.low_stock_count
  const lowItems = data!.items.filter((i) => i.is_low).slice(0, 3).map((i) => i.name)

  return (
    <TileCard title="Low Stock" href="/settings">
      <p className={`text-3xl font-bold tabular-nums ${low === 0 ? 'text-status-paid' : 'text-status-failed'}`}>
        {low}
      </p>
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
    queryFn: () => api.get<FinanceData>('/dashboard/finance').then((r) => r.data),
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: true,
  })

  if (isLoading) return <TileSkeleton />
  if (isError)   return <TileError label="Financial Health" />

  const { reconciliation_status, open_shortfalls, unmatched_mpesa, pending_approvals } = data!

  return (
    <TileCard title="Financial Health" href="/finance">
      <StatusBadge status={reconBadge(reconciliation_status)} />
      <div className="text-xs text-ink-tertiary space-y-0.5">
        <p>Shortfalls: <span className={open_shortfalls > 0 ? 'text-status-failed font-semibold' : ''}>{open_shortfalls}</span></p>
        <p>Unmatched M-Pesa: <span className={unmatched_mpesa > 0 ? 'text-status-pending font-semibold' : ''}>{unmatched_mpesa}</span></p>
        <p>Pending approvals: {pending_approvals}</p>
      </div>
    </TileCard>
  )
}

function FeedbackTile() {
  const { data, isLoading, isError } = useQuery<FeedbackData>({
    queryKey: ['dash-feedback'],
    queryFn: () => api.get<FeedbackData>('/dashboard/feedback').then((r) => r.data),
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: true,
  })

  if (isLoading) return <TileSkeleton />
  if (isError)   return <TileError label="Guest Feedback" />

  const avg          = data!.overall_avg
  const commentCount = data!.recent_comments.length

  return (
    <TileCard title="Feedback Score" href="/finance">
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
    queryFn: () => api.get<SuggestionsData>('/dashboard/suggestions').then((r) => r.data),
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: true,
  })

  if (isLoading) return <TileSkeleton />
  if (isError)   return <TileError label="Suggestions" />

  // Backend returns ALL suggestions; filter for NEW (unread) on frontend
  const newMgmt    = data!.management.filter((s) => s.status === 'NEW').length
  const newPrivate = data!.owner_private.filter((s) => s.status === 'NEW').length
  const total      = newMgmt + newPrivate

  return (
    <TileCard title="Suggestions" href="/settings">
      <p className={`text-3xl font-bold tabular-nums ${total === 0 ? 'text-ink-tertiary' : 'text-ink-primary'}`}>
        {total}
      </p>
      <p className="text-xs text-ink-tertiary">
        Owner-private: {newPrivate} · Management: {newMgmt}
      </p>
    </TileCard>
  )
}

function EquipmentTile() {
  const { data, isLoading, isError } = useQuery<EquipmentData>({
    queryKey: ['dash-equipment'],
    queryFn: () => api.get<EquipmentData>('/dashboard/equipment').then((r) => r.data),
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: true,
  })

  if (isLoading) return <TileSkeleton />
  if (isError)   return <TileError label="Equipment" />

  const due  = data!.due_service      // array, not count
  const inMx = data!.in_maintenance.length

  return (
    <TileCard title="Equipment" href="/settings">
      <p className={`text-3xl font-bold tabular-nums ${due.length > 0 ? 'text-status-pending' : 'text-status-paid'}`}>
        {due.length}
      </p>
      <p className="text-xs text-ink-tertiary">
        {due.length === 0 ? `All ${data!.total} items serviced` : `due service · ${inMx} in maintenance`}
      </p>
      {due.length > 0 && (
        <p className="text-xs text-ink-secondary truncate">
          {due.slice(0, 2).map((e) => e.name).join(', ')}{due.length > 2 ? ` +${due.length - 2} more` : ''}
        </p>
      )}
    </TileCard>
  )
}

// ── Top bar ───────────────────────────────────────────────────────────────────

function TopBar({ onRefresh }: { onRefresh: () => void }) {
  const overview  = useQuery<OverviewData>({ queryKey: ['dash-overview'],  staleTime: 5 * 60_000 })
  const alerts    = useQuery<AlertItem[]>({ queryKey: ['dash-alerts'],    staleTime: 5 * 60_000 })
  const bookings  = useQuery<BookingsData>({ queryKey: ['dash-bookings'],  staleTime: 5 * 60_000 })

  const revenue     = overview.data?.revenue.total
  const alertCount  = alerts.data?.length
  const activeGuests = bookings.data
    ? Object.values(bookings.data.occupancy_by_type).reduce((a, b) => a + b, 0)
    : undefined

  return (
    <div className="flex items-center gap-4 bg-cream-card rounded-2xl border border-cream-alt p-3 mb-4">
      <div className="flex-1 flex items-center gap-6 overflow-x-auto scrollbar-none min-w-0">
        <div className="shrink-0">
          <p className="text-[10px] font-semibold tracking-widest uppercase text-ink-tertiary">Revenue</p>
          <p className="text-base font-bold tabular-nums text-ink-primary leading-tight">
            {revenue !== undefined ? formatKsh(revenue) : '—'}
          </p>
        </div>
        <div className="w-px h-8 bg-cream-alt shrink-0" />
        <div className="shrink-0">
          <p className="text-[10px] font-semibold tracking-widest uppercase text-ink-tertiary">Alerts Open</p>
          <p className={`text-base font-bold tabular-nums leading-tight ${alertCount !== undefined ? alertCountColor(alertCount) : 'text-ink-tertiary'}`}>
            {alertCount !== undefined ? alertCount : '—'}
          </p>
        </div>
        <div className="w-px h-8 bg-cream-alt shrink-0" />
        <div className="shrink-0">
          <p className="text-[10px] font-semibold tracking-widest uppercase text-ink-tertiary">Active Bookings</p>
          <p className="text-base font-bold tabular-nums text-ink-primary leading-tight">
            {activeGuests !== undefined ? activeGuests : '—'}
          </p>
        </div>
      </div>

      {/* Refresh all button */}
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
  ['dash-overview'],
  ['dash-inventory'],
  ['dash-finance'],
  ['dash-bookings'],
  ['dash-staff'],
  ['dash-alerts'],
  ['dash-feedback'],
  ['dash-suggestions'],
  ['dash-equipment'],
]

export default function DashboardScreen() {
  const queryClient = useQueryClient()

  function refreshAll() {
    DASHBOARD_QUERY_KEYS.forEach((key) => queryClient.invalidateQueries({ queryKey: key }))
  }

  return (
    <div className="p-4 max-w-5xl mx-auto">
      <div className="mb-4">
        <h1 className="text-xl font-bold text-ink-primary">Dashboard</h1>
        <p className="text-sm text-ink-tertiary">Waterfront Kurahia · Owner view</p>
      </div>

      <TopBar onRefresh={refreshAll} />

      <motion.div
        variants={gridVariants}
        initial="initial"
        animate="animate"
        className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3"
      >
        {[
          <RevenueTile    key="revenue"    />,
          <ActiveGuestsTile key="guests"  />,
          <OpenBookingsTile key="bookings" />,
          <StaffOnDutyTile  key="staff"   />,
          <AlertsTile       key="alerts"  />,
          <LowStockTile     key="stock"   />,
          <FinanceTile      key="finance" />,
          <FeedbackTile     key="feedback"/>,
          <SuggestionsTile  key="suggestions"/>,
          <EquipmentTile    key="equipment" />,
        ].map((tile, i) => (
          <motion.div key={i} variants={tileVariants}>
            {tile}
          </motion.div>
        ))}
      </motion.div>
    </div>
  )
}
