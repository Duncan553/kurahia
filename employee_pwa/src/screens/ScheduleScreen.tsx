import { useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Skeleton, EmptyState, StatusBadge, ErrorBoundary } from '@shared'
import type { StatusValue } from '@shared'
import api from '../lib/axios'
import { formatTime, toDateKey, todayKey } from '../lib/format'

interface Shift {
  id: string
  employee_id: string
  employee_name: string
  start: string
  end: string
  role: string
  status: string
}

// Map backend shift status strings to StatusBadge variants
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

// Build 7-day week starting from Monday of the current week
function currentWeekDays(): string[] {
  const now = new Date()
  const dayOfWeek = now.getDay() // 0=Sun
  // Offset to Monday: if Sun (0) go back 6, otherwise go back (dayOfWeek - 1)
  const mondayOffset = dayOfWeek === 0 ? -6 : 1 - dayOfWeek
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(now)
    d.setDate(now.getDate() + mondayOffset + i)
    return new Intl.DateTimeFormat('en-CA', { timeZone: 'Africa/Nairobi' }).format(d)
  })
}

const DAYS = currentWeekDays()
const TODAY = todayKey()

// Animation variants
const fadeIn = { hidden: { opacity: 0, y: 12 }, visible: { opacity: 1, y: 0 } }
const stagger = { visible: { transition: { staggerChildren: 0.06 } } }

// Weekday name from date key (e.g. "2026-06-22" => "Monday")
function weekdayName(dateKey: string): string {
  return new Intl.DateTimeFormat('en-KE', {
    timeZone: 'Africa/Nairobi',
    weekday: 'long',
  }).format(new Date(dateKey + 'T12:00:00'))
}

// Short date label (e.g. "June 22")
function shortDate(dateKey: string): string {
  return new Intl.DateTimeFormat('en-KE', {
    timeZone: 'Africa/Nairobi',
    month: 'long',
    day: 'numeric',
  }).format(new Date(dateKey + 'T12:00:00'))
}

export default function ScheduleScreen() {
  const containerRef = useRef<HTMLDivElement>(null)
  const touchStart = useRef(0)
  const [pullProgress, setPullProgress] = useState(0)

  const { data: shifts, isLoading, isError, refetch, dataUpdatedAt } = useQuery<Shift[]>({
    queryKey: ['shifts'],
    queryFn: () => api.get<Shift[]>('/hr/shifts').then((r) => r.data),
    refetchInterval: 60_000,
  })

  // Group shifts by Nairobi date key
  const byDay = new Map<string, Shift[]>()
  for (const s of shifts ?? []) {
    const key = toDateKey(s.start)
    if (!byDay.has(key)) byDay.set(key, [])
    byDay.get(key)!.push(s)
  }

  // Compute summary stats for the week
  let totalHours = 0
  let shiftCount = 0
  for (const dayKey of DAYS) {
    const dayShifts = byDay.get(dayKey) ?? []
    for (const s of dayShifts) {
      const startMs = new Date(s.start).getTime()
      const endMs = new Date(s.end).getTime()
      totalHours += (endMs - startMs) / 3_600_000
      shiftCount++
    }
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
      <ErrorBoundary level="tile">
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
        className="p-4 md:p-6 max-w-6xl mx-auto"
        initial="hidden"
        animate="visible"
        variants={stagger}
      >
        {/* ── Page header: title + action buttons ─────────────────────── */}
        <motion.div variants={fadeIn} transition={{ duration: 0.3 }}
          className="flex flex-col md:flex-row md:items-start md:justify-between gap-3 mb-6">
          <div>
            <h1 className="font-serif text-3xl md:text-4xl font-bold text-ink-primary tracking-tight">
              My Schedule
            </h1>
            <p className="text-sm text-ink-secondary mt-1">
              Manage your upcoming shifts and time-off requests.
            </p>
          </div>

          {/* Action buttons — link to existing routes */}
          <div className="flex gap-2 shrink-0">
            <Link
              to="/absence"
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-semibold
                glass-card bg-white/5 text-ink-primary hover:bg-white/10 transition-colors"
            >
              Absence Notice
            </Link>
            <Link
              to="/leave"
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-semibold
                bg-primary-main text-white hover:bg-primary-main/90 transition-colors"
            >
              Request Leave
            </Link>
          </div>
        </motion.div>

        {/* ── 7-day grid + Summary sidebar ────────────────────────────── */}
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-4">
          {/* Day cards grid: 4 columns on first row, 3 on second (Mon-Thu / Fri-Sun) */}
          <motion.div variants={fadeIn} transition={{ duration: 0.3 }}>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
              {DAYS.slice(0, 4).map((dayKey) => (
                <DayCard key={dayKey} dayKey={dayKey} isToday={dayKey === TODAY} shifts={byDay.get(dayKey) ?? []} />
              ))}
            </div>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {DAYS.slice(4).map((dayKey) => (
                <DayCard key={dayKey} dayKey={dayKey} isToday={dayKey === TODAY} shifts={byDay.get(dayKey) ?? []} />
              ))}
            </div>
          </motion.div>

          {/* Summary card — right sidebar */}
          <motion.div variants={fadeIn} transition={{ duration: 0.3 }}>
            <div className="glass-card rounded-2xl p-5">
              <h3 className="text-sm font-bold tracking-widest uppercase text-ink-tertiary mb-4">
                Summary
              </h3>
              <div className="grid grid-cols-2 gap-4 mb-4">
                <div className="text-center">
                  <p className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary mb-1">
                    Total Hours
                  </p>
                  <p className="text-3xl font-bold tabular-nums text-ink-primary">
                    {totalHours.toFixed(1)}
                  </p>
                </div>
                <div className="text-center">
                  <p className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary mb-1">
                    Shifts
                  </p>
                  <p className="text-3xl font-bold tabular-nums text-ink-primary">
                    {shiftCount}
                  </p>
                </div>
              </div>
              <Link
                to="/manager/attendance"
                className="text-xs font-semibold text-primary-main hover:text-primary-main/80
                  transition-colors underline underline-offset-2"
              >
                View Full Timesheet
              </Link>
            </div>
          </motion.div>
        </div>

        {/* ── Shift Reminders section ─────────────────────────────────── */}
        <motion.div variants={fadeIn} transition={{ duration: 0.3 }} className="mt-6">
          <div className="glass-card rounded-2xl p-5">
            <h3 className="text-sm font-bold tracking-widest uppercase text-ink-tertiary mb-4 flex items-center gap-2">
              {/* Clock/reminder icon */}
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" className="text-ink-tertiary" aria-hidden="true">
                <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.5" />
                <path d="M12 7v5l3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              Shift Reminders
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-3">
              {[
                'Please clock in at least 10 minutes before your shift starts for handover.',
                'Meal breaks are 45 minutes and must be coordinated with your supervisor.',
                'Uniforms must be pressed and name tags clearly visible at all times.',
                'Absence notices must be submitted through the portal at least 4 hours prior.',
              ].map((reminder, i) => (
                <div key={i} className="flex items-start gap-2.5">
                  <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-[#aa8980] shrink-0" />
                  <p className="text-xs text-ink-secondary leading-relaxed">{reminder}</p>
                </div>
              ))}
            </div>
          </div>
        </motion.div>
      </motion.div>
      </ErrorBoundary>
    </div>
  )
}

/* ── Day card component ──────────────────────────────────────────── */
function DayCard({
  dayKey,
  isToday,
  shifts,
}: {
  dayKey: string
  isToday: boolean
  shifts: Shift[]
}) {
  const dayName = weekdayName(dayKey)
  const dateStr = shortDate(dayKey)

  return (
    <div
      className={[
        'glass-card rounded-2xl p-4 flex flex-col min-h-[140px]',
        isToday ? 'ring-1 ring-status-paid/40' : '',
      ].join(' ')}
    >
      {/* Day header row: weekday + optional today badge */}
      <div className="flex items-center justify-between mb-1">
        <p className={`text-sm font-bold ${isToday ? 'text-status-paid' : 'text-ink-primary'}`}>
          {isToday ? 'Today' : dayName}
        </p>
        {isToday && (
          <span className="px-2 py-0.5 rounded-md text-[9px] font-bold uppercase tracking-wide
            bg-status-paid/20 text-status-paid">
            Active
          </span>
        )}
      </div>

      {/* Date subtitle */}
      <p className="text-[10px] text-ink-tertiary mb-3">
        {isToday ? `${dayName}, ${dateStr}` : dateStr}
      </p>

      {/* Shift content */}
      {shifts.length === 0 ? (
        <div className="flex-1 flex items-center">
          <p className="text-xs text-ink-tertiary italic">No shift scheduled</p>
        </div>
      ) : (
        <div className="flex-1 space-y-2">
          {shifts.map((shift) => (
            <div key={shift.id}>
              {/* Time range */}
              <div className="flex items-center gap-1.5 mb-1">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" className="text-ink-tertiary shrink-0" aria-hidden="true">
                  <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.5" />
                  <path d="M12 7v5l3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <p className="text-xs font-semibold text-ink-primary tabular-nums">
                  {formatTime(shift.start)} — {formatTime(shift.end)}
                </p>
              </div>

              {/* Department / role */}
              <div className="flex items-center gap-1.5">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" className="text-ink-tertiary shrink-0" aria-hidden="true">
                  <path d="M3 21h18M5 21V7l7-4 7 4v14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <p className="text-[10px] text-ink-secondary truncate">{shift.role}</p>
              </div>

              {/* Status badge for non-today cards */}
              {!isToday && (
                <div className="mt-1.5">
                  <StatusBadge status={shiftStatus(shift.status)} />
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
