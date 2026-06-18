import { useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { Skeleton, EmptyState, StatusBadge } from '@shared'
import type { StatusValue } from '@shared'
import api from '../lib/axios'
import { formatTime, formatDayLabel, toDateKey, todayKey, nextNDays } from '../lib/format'

interface Shift {
  id: string
  employee_id: string
  employee_name: string
  start: string
  end: string
  role: string
  status: string
}

// Map backend shift status strings → StatusBadge variants
function shiftStatus(s: string): StatusValue {
  const map: Record<string, StatusValue> = {
    SCHEDULED: 'confirmed',
    PUBLISHED: 'confirmed',
    ACTIVE: 'active',
    COMPLETED: 'checked-out',
    CANCELLED: 'cancelled',
    PENDING: 'pending',
  }
  return map[s.toUpperCase()] ?? 'confirmed'
}

const DAYS = nextNDays(7)
const TODAY = todayKey()

export default function ScheduleScreen() {
  const containerRef = useRef<HTMLDivElement>(null)
  const touchStart = useRef(0)
  const [pullProgress, setPullProgress] = useState(0)

  const { data: shifts, isLoading, isError, refetch, dataUpdatedAt } = useQuery<Shift[]>({
    queryKey: ['shifts'],
    queryFn: () => api.get<Shift[]>('/hr/shifts').then((r) => r.data),
  })

  // Group shifts by Nairobi date key
  const byDay = new Map<string, Shift[]>()
  for (const s of shifts ?? []) {
    const key = toDateKey(s.start)
    if (!byDay.has(key)) byDay.set(key, [])
    byDay.get(key)!.push(s)
  }

  // Pull-to-refresh gesture
  function onTouchStart(e: React.TouchEvent) {
    if ((containerRef.current?.scrollTop ?? 1) === 0) {
      touchStart.current = e.touches[0].clientY
    }
  }
  function onTouchMove(e: React.TouchEvent) {
    const delta = e.touches[0].clientY - touchStart.current
    if (delta > 0 && (containerRef.current?.scrollTop ?? 1) === 0) {
      setPullProgress(Math.min(delta / 80, 1))
    }
  }
  function onTouchEnd() {
    if (pullProgress >= 1) refetch()
    setPullProgress(0)
    touchStart.current = 0
  }

  // ── LOADING ─────────────────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="p-4 space-y-3">
        {Array.from({ length: 7 }).map((_, i) => (
          <div key={i} className="space-y-2">
            <Skeleton variant="text" className="w-24" />
            <Skeleton variant="row" />
          </div>
        ))}
      </div>
    )
  }

  // ── ERROR (with cached data fallback) ────────────────────────────────────────
  if (isError && !shifts) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[calc(100vh-8rem)] p-6">
        <EmptyState
          icon={
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none" aria-hidden="true">
              <rect x="8" y="8" width="32" height="36" rx="3" stroke="currentColor" strokeWidth="2" />
              <path d="M16 6v6M32 6v6M8 22h32" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              <path d="M20 30h8M24 26v8" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
            </svg>
          }
          title="Couldn't load your schedule."
          description="Check your connection and try again."
          actionLabel="Retry"
          onAction={() => refetch()}
        />
      </div>
    )
  }

  // ── EMPTY ────────────────────────────────────────────────────────────────────
  const allEmpty = DAYS.every((d) => !byDay.has(d))
  if (!isError && allEmpty) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[calc(100vh-8rem)] p-6">
        <EmptyState
          icon={
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none" aria-hidden="true">
              <rect x="8" y="8" width="32" height="36" rx="3" stroke="currentColor" strokeWidth="2" />
              <path d="M16 6v6M32 6v6M8 22h32" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              <path d="M18 32h12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
          }
          title="No shifts scheduled this week."
          description="Check with your manager."
        />
      </div>
    )
  }

  return (
    <div
      ref={containerRef}
      className="overflow-y-auto"
      onTouchStart={onTouchStart}
      onTouchMove={onTouchMove}
      onTouchEnd={onTouchEnd}
    >
      {/* Pull-to-refresh indicator */}
      {pullProgress > 0 && (
        <div
          className="flex items-center justify-center overflow-hidden transition-all bg-primary-light/30"
          style={{ height: `${pullProgress * 48}px` }}
        >
          <svg
            className="text-primary-dark"
            style={{ opacity: pullProgress, transform: `rotate(${pullProgress * 360}deg)` }}
            width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true"
          >
            <path d="M10 3v4M10 13v4M3 10h4M13 10h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        </div>
      )}

      {/* Staleness banner when error + cached data */}
      {isError && shifts && dataUpdatedAt && (
        <div className="mx-4 mt-4 px-3 py-2 rounded-lg bg-status-pending/10 text-status-pending text-xs">
          Showing cached schedule — last updated{' '}
          {Math.floor((Date.now() - dataUpdatedAt) / 60_000)} min ago.
          <button
            onClick={() => refetch()}
            className="ml-2 min-h-[44px] inline-flex items-center underline font-medium
              text-status-pending hover:text-status-pending/80 transition-colors
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-status-pending rounded"
          >Retry</button>
        </div>
      )}

      <motion.div
        className="p-4 space-y-4"
        initial="hidden"
        animate="visible"
        variants={{ visible: { transition: { staggerChildren: 0.05 } } }}
      >
        {DAYS.map((dayKey) => {
          const isToday = dayKey === TODAY
          const dayShifts = byDay.get(dayKey) ?? []
          // Format the day label from the key
          const label = formatDayLabel(dayKey + 'T12:00:00')

          return (
            <motion.div
              key={dayKey}
              variants={{ hidden: { opacity: 0, y: 10 }, visible: { opacity: 1, y: 0 } }}
              transition={{ duration: 0.22, ease: 'easeOut' }}
            >
              {/* Day header */}
              <p className={[
                'text-xs font-semibold uppercase tracking-wider mb-2',
                isToday ? 'text-primary-dark' : 'text-slate-400/50',
              ].join(' ')}>
                {isToday ? `Today · ${label}` : label}
              </p>

              {/* Shifts for this day */}
              {dayShifts.length === 0 ? (
                <div className={[
                  'rounded-xl border px-4 py-3',
                  isToday
                    ? 'bg-primary-light/20 border-primary-dark/20'
                    : 'bg-white/5/30 border-white/10',
                ].join(' ')}>
                  <p className="text-sm text-slate-400/50">No shift</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {dayShifts.map((shift) => (
                    <div
                      key={shift.id}
                      className={[
                        'rounded-xl border px-4 py-3 flex items-center justify-between gap-3',
                        isToday
                          ? 'bg-primary-light/20 border-primary-dark/20'
                          : 'bg-transparent border-white/10',
                      ].join(' ')}
                    >
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-white">
                          {formatTime(shift.start)} – {formatTime(shift.end)}
                        </p>
                        <p className="text-xs text-slate-400/50 mt-0.5 truncate">{shift.role}</p>
                      </div>
                      <StatusBadge status={shiftStatus(shift.status)} />
                    </div>
                  ))}
                </div>
              )}
            </motion.div>
          )
        })}
      </motion.div>
    </div>
  )
}
