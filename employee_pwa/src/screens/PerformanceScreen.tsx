import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { ErrorBoundary, Skeleton } from '@shared'
import api from '../lib/axios'

/* ── Types ──────────────────────────────────────────────────────────────────── */

interface EmployeeProfile {
  id: string
  full_name: string
  department: string | null
  role: string | null
  is_active: boolean
}

interface PerformanceData {
  employee_id: string
  employee_name: string
  period_start: string
  period_end: string
  punctuality_score: string
  attendance_score: string
  cash_health_score: string
  void_health_score: string
  composite_score: string
  detail: {
    shifts_scheduled: number
    shifts_attended: number
    on_time_clock_ins: number
    cash_shortfalls: number
    void_rate_pct: string
    hours_worked: string
    guest_rating: string | null
  }
  weights: Record<string, string>
}

/* ── Helpers ─────────────────────────────────────────────────────────────────── */

// Score color: green 80+, amber 60-79, red <60
function scoreColor(score: number): string {
  if (score >= 80) return 'text-status-paid'
  if (score >= 60) return 'text-status-pending'
  return 'text-status-failed'
}

function scoreBg(score: number): string {
  if (score >= 80) return 'bg-status-paid'
  if (score >= 60) return 'bg-status-pending'
  return 'bg-status-failed'
}

// Trend indicator: compare to 50 baseline (since we don't have historical)
function trendIcon(score: number): string {
  if (score >= 80) return '↑'   // up arrow
  if (score >= 60) return '→'   // right arrow (flat)
  return '↓'                     // down arrow
}

// Current period defaults
function defaultPeriod(): { start: string; end: string } {
  const now = new Date()
  const start = new Date(now.getFullYear(), now.getMonth(), 1)
  return {
    start: start.toISOString().slice(0, 10),
    end: now.toISOString().slice(0, 10),
  }
}

/* ── Score bar component ─────────────────────────────────────────────────────── */

function ScoreBar({ label, value }: { label: string; value: string }) {
  const n = parseFloat(value)
  return (
    <div>
      <div className="flex items-baseline justify-between mb-1">
        <span className="text-[10px] font-semibold tracking-wider uppercase text-ink-tertiary">
          {label}
        </span>
        <span className={`text-sm font-bold tabular-nums ${scoreColor(n)}`}>
          {n.toFixed(0)}%
        </span>
      </div>
      <div className="h-2 rounded-full bg-white/5 overflow-hidden">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${Math.min(n, 100)}%` }}
          transition={{ duration: 0.6, ease: 'easeOut' }}
          className={`h-full rounded-full ${scoreBg(n)}`}
        />
      </div>
    </div>
  )
}

/* ── Staff card (collapsed) ──────────────────────────────────────────────────── */

function StaffRow({ profile, period, isExpanded, onToggle }: {
  profile: EmployeeProfile
  period: { start: string; end: string }
  isExpanded: boolean
  onToggle: () => void
}) {
  // Fetch performance only when expanded (lazy load)
  const { data: perf, isLoading, isError } = useQuery<PerformanceData>({
    queryKey: ['performance', profile.id, period.start, period.end],
    queryFn: () =>
      api.get<PerformanceData>(
        `/hr/performance/${profile.id}?start_date=${period.start}&end_date=${period.end}`
      ).then(r => r.data),
    enabled: isExpanded,
    staleTime: 60_000,
  })

  const compositeNum = perf ? parseFloat(perf.composite_score) : null

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card rounded-2xl border border-white/10 overflow-hidden"
    >
      {/* Collapsed row — always visible */}
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-3 p-4 text-left
          hover:bg-white/5 transition-colors
          focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-main"
      >
        {/* Avatar circle */}
        <div className="w-10 h-10 rounded-full bg-primary-main/15 border border-primary-main/20
          flex items-center justify-center shrink-0">
          <span className="text-[#fa5c29] text-sm font-bold">
            {profile.full_name.charAt(0).toUpperCase()}
          </span>
        </div>

        {/* Name + department */}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-ink-primary truncate">{profile.full_name}</p>
          <p className="text-[10px] text-ink-tertiary">
            {profile.department ?? 'No department'}
          </p>
        </div>

        {/* Score + trend (if loaded) */}
        {compositeNum !== null && (
          <div className="flex items-center gap-1.5 shrink-0">
            <span className={`text-lg font-bold tabular-nums ${scoreColor(compositeNum)}`}>
              {compositeNum.toFixed(0)}
            </span>
            <span className={`text-sm ${scoreColor(compositeNum)}`}>
              {trendIcon(compositeNum)}
            </span>
          </div>
        )}

        {/* Chevron */}
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true"
          className={`shrink-0 text-ink-tertiary transition-transform ${isExpanded ? 'rotate-180' : ''}`}>
          <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.5"
            strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </button>

      {/* Expanded detail */}
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-4 space-y-4 border-t border-white/5 pt-4">
              {isLoading && (
                <div className="space-y-3">
                  <Skeleton variant="text" className="w-full h-3" />
                  <Skeleton variant="text" className="w-3/4 h-3" />
                  <Skeleton variant="text" className="w-1/2 h-3" />
                </div>
              )}

              {isError && (
                <p className="text-xs text-status-failed">Failed to load performance data.</p>
              )}

              {perf && (
                <>
                  {/* Score bars */}
                  <div className="space-y-3">
                    <ScoreBar label="Punctuality" value={perf.punctuality_score} />
                    <ScoreBar label="Attendance" value={perf.attendance_score} />
                    <ScoreBar label="Cash Health" value={perf.cash_health_score} />
                    <ScoreBar label="Void Health" value={perf.void_health_score} />
                  </div>

                  {/* Detail stats */}
                  <div className="grid grid-cols-2 gap-3">
                    {[
                      { label: 'Shifts Scheduled', val: String(perf.detail.shifts_scheduled) },
                      { label: 'Shifts Attended', val: String(perf.detail.shifts_attended) },
                      { label: 'On-Time Clock-Ins', val: String(perf.detail.on_time_clock_ins) },
                      { label: 'Hours Worked', val: `${parseFloat(perf.detail.hours_worked).toFixed(1)}h` },
                      { label: 'Cash Shortfalls', val: String(perf.detail.cash_shortfalls) },
                      { label: 'Void Rate', val: `${parseFloat(perf.detail.void_rate_pct).toFixed(1)}%` },
                    ].map(s => (
                      <div key={s.label} className="rounded-xl bg-white/5 p-2.5">
                        <p className="text-[10px] text-ink-tertiary">{s.label}</p>
                        <p className="text-sm font-bold tabular-nums text-ink-primary">{s.val}</p>
                      </div>
                    ))}
                  </div>

                  {/* Guest rating (if available) */}
                  {perf.detail.guest_rating && (
                    <div className="rounded-xl bg-white/5 p-2.5">
                      <p className="text-[10px] text-ink-tertiary">Guest Rating</p>
                      <p className="text-sm font-bold tabular-nums text-ink-primary">
                        {perf.detail.guest_rating} / 5
                      </p>
                    </div>
                  )}

                  {/* Period */}
                  <p className="text-[10px] text-ink-tertiary text-right">
                    Period: {perf.period_start} to {perf.period_end}
                  </p>
                </>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}

/* ── Main screen ─────────────────────────────────────────────────────────────── */

export default function PerformanceScreen() {
  const [period] = useState(defaultPeriod)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [search, setSearch] = useState('')

  // Fetch all active employee profiles
  const { data: profiles = [], isLoading, isError } = useQuery<EmployeeProfile[]>({
    queryKey: ['hr-profiles'],
    queryFn: () => api.get<EmployeeProfile[]>('/hr/profiles').then(r => r.data),
    staleTime: 5 * 60_000,
  })

  // Filter active profiles by search
  const filtered = useMemo(() => {
    const active = profiles.filter(p => p.is_active)
    if (!search.trim()) return active
    const q = search.toLowerCase()
    return active.filter(p =>
      p.full_name.toLowerCase().includes(q) ||
      (p.department ?? '').toLowerCase().includes(q)
    )
  }, [profiles, search])

  return (
    <div className="min-h-screen p-4 md:p-6">
      <div className="max-w-3xl mx-auto">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-6"
        >
          <h1 className="font-serif text-2xl md:text-3xl font-bold text-ink-primary">
            Performance
          </h1>
          <p className="text-sm text-ink-secondary mt-1">
            Staff scores for {new Date(period.start).toLocaleDateString('en-KE', { month: 'long', year: 'numeric' })}
          </p>
        </motion.div>

        {/* Search bar */}
        <div className="mb-4">
          <div className="relative">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true"
              className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-tertiary">
              <circle cx="7" cy="7" r="4.5" stroke="currentColor" strokeWidth="1.5"/>
              <path d="M10.5 10.5L13 13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by name or department..."
              className="w-full pl-9 pr-4 py-2.5 rounded-xl bg-white/5 border border-white/10
                text-sm text-ink-primary placeholder:text-ink-tertiary
                focus:outline-none focus:ring-2 focus:ring-[#fa5c29]"
            />
          </div>
        </div>

        {/* Content */}
        <ErrorBoundary level="tile">
          {isLoading && (
            <div className="space-y-3">
              {[1, 2, 3, 4].map(i => (
                <div key={i} className="h-20 rounded-2xl bg-cream-alt animate-pulse" />
              ))}
            </div>
          )}

          {isError && (
            <p className="text-sm text-status-failed text-center py-12">
              Failed to load staff profiles. Check your connection.
            </p>
          )}

          {!isLoading && !isError && filtered.length === 0 && (
            <div className="flex flex-col items-center justify-center py-20 gap-3">
              <span className="text-5xl text-ink-tertiary/40">&#128100;</span>
              <p className="text-ink-tertiary text-lg font-medium">No staff found</p>
              <p className="text-xs text-ink-tertiary">
                {search ? 'Try a different search term.' : 'No active employee profiles.'}
              </p>
            </div>
          )}

          {!isLoading && filtered.length > 0 && (
            <div className="space-y-3">
              {filtered.map(p => (
                <StaffRow
                  key={p.id}
                  profile={p}
                  period={period}
                  isExpanded={expandedId === p.id}
                  onToggle={() => setExpandedId(expandedId === p.id ? null : p.id)}
                />
              ))}
            </div>
          )}
        </ErrorBoundary>
      </div>
    </div>
  )
}
