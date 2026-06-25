import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { ErrorBoundary, StatusBadge } from '@shared'
import type { StatusValue } from '@shared'
import api from '../lib/axios'

/* ── Types ──────────────────────────────────────────────────────────────────── */

interface CalendarEntry {
  id: string
  title: string
  entry_type: string   // HOLIDAY | PEAK | PLANNING_MEETING | EXTERNAL_OBSERVANCE
  date_start: string   // ISO datetime
  date_end: string
  is_peak: boolean
  description: string | null
  planning_trigger_offset_days: number | null
  is_active: boolean
}

/* ── Helpers ─────────────────────────────────────────────────────────────────── */

// Entry type to badge status mapping
function typeStatus(t: string): StatusValue {
  if (t === 'HOLIDAY')          return 'paid'
  if (t === 'PEAK')             return 'failed'
  if (t === 'PLANNING_MEETING') return 'active'
  return 'info' // EXTERNAL_OBSERVANCE
}

// Entry type display color for the calendar dot
function dotColor(t: string): string {
  if (t === 'HOLIDAY')          return 'bg-status-paid'
  if (t === 'PEAK')             return 'bg-status-failed'
  if (t === 'PLANNING_MEETING') return 'bg-[#fa5c29]'
  return 'bg-ink-tertiary'
}

// Format readable date
function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-KE', {
    day: 'numeric', month: 'short',
  })
}

// Get all days in a month as a flat array (with leading empty slots for alignment)
function getMonthGrid(year: number, month: number) {
  // First day of month (0=Sun, 1=Mon, ..., 6=Sat)
  const firstDay = new Date(year, month, 1).getDay()
  // Shift to Monday-start: Mon=0, Tue=1, ... Sun=6
  const startOffset = firstDay === 0 ? 6 : firstDay - 1
  const daysInMonth = new Date(year, month + 1, 0).getDate()

  const cells: (number | null)[] = []
  // Leading empty cells
  for (let i = 0; i < startOffset; i++) cells.push(null)
  // Day numbers
  for (let d = 1; d <= daysInMonth; d++) cells.push(d)
  return cells
}


const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
]

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

/* ── Calendar Grid ───────────────────────────────────────────────────────────── */

function MonthGrid({ year, month, entries }: {
  year: number; month: number; entries: CalendarEntry[]
}) {
  const [selectedDay, setSelectedDay] = useState<number | null>(null)
  const cells = useMemo(() => getMonthGrid(year, month), [year, month])
  const today = new Date()
  const isCurrentMonth = today.getFullYear() === year && today.getMonth() === month
  const todayDate = today.getDate()

  // Build a map: "YYYY-MM-DD" -> entries on that date
  const dateMap = useMemo(() => {
    const map = new Map<string, CalendarEntry[]>()
    for (const e of entries) {
      // An entry can span multiple days; mark each day it covers
      const start = new Date(e.date_start)
      const end = new Date(e.date_end)
      const cursor = new Date(start)
      while (cursor <= end) {
        const key = cursor.toISOString().slice(0, 10)
        const arr = map.get(key) ?? []
        arr.push(e)
        map.set(key, arr)
        cursor.setDate(cursor.getDate() + 1)
      }
    }
    return map
  }, [entries])

  // Entries for selected day
  const selectedKey = selectedDay
    ? `${year}-${String(month + 1).padStart(2, '0')}-${String(selectedDay).padStart(2, '0')}`
    : null
  const selectedEntries = selectedKey ? (dateMap.get(selectedKey) ?? []) : []

  return (
    <div>
      {/* Weekday headers */}
      <div className="grid grid-cols-7 gap-1 mb-2">
        {WEEKDAYS.map(d => (
          <div key={d} className="text-center text-[10px] font-semibold tracking-wider
            uppercase text-ink-tertiary py-1">
            {d}
          </div>
        ))}
      </div>

      {/* Day cells */}
      <div className="grid grid-cols-7 gap-1">
        {cells.map((day, i) => {
          if (day === null) {
            return <div key={`empty-${i}`} className="h-12" />
          }
          const key = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`
          const dayEntries = dateMap.get(key) ?? []
          const isToday = isCurrentMonth && day === todayDate
          const isSelected = day === selectedDay

          return (
            <button
              key={day}
              onClick={() => setSelectedDay(day === selectedDay ? null : day)}
              className={`h-12 rounded-xl flex flex-col items-center justify-center gap-0.5
                transition-all text-sm relative
                ${isToday
                  ? 'bg-[#fa5c29]/20 text-[#fa5c29] font-bold'
                  : isSelected
                    ? 'bg-white/10 text-[#f9dcd5]'
                    : 'text-[#aa8980] hover:bg-white/5 hover:text-[#f9dcd5]'
                }
                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#fa5c29]`}
            >
              <span className="tabular-nums">{day}</span>
              {/* Event dots */}
              {dayEntries.length > 0 && (
                <div className="flex gap-0.5">
                  {dayEntries.slice(0, 3).map((e, j) => (
                    <span key={j} className={`w-1 h-1 rounded-full ${dotColor(e.entry_type)}`} />
                  ))}
                </div>
              )}
            </button>
          )
        })}
      </div>

      {/* Selected day detail */}
      {selectedDay !== null && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          exit={{ opacity: 0, height: 0 }}
          className="mt-4 space-y-2"
        >
          <p className="text-xs font-semibold text-[#f9dcd5]">
            {selectedDay} {MONTH_NAMES[month]}
          </p>
          {selectedEntries.length === 0 ? (
            <p className="text-xs text-ink-tertiary">No entries on this day.</p>
          ) : (
            selectedEntries.map(e => (
              <div key={e.id} className="glass-card rounded-xl p-3 border border-white/10">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-semibold text-[#f9dcd5]">{e.title}</p>
                  <StatusBadge status={typeStatus(e.entry_type)} />
                </div>
                <p className="text-[10px] text-ink-tertiary mt-1">
                  {e.entry_type.replace(/_/g, ' ')}
                  {' · '}
                  {fmtDate(e.date_start)} - {fmtDate(e.date_end)}
                </p>
                {e.description && (
                  <p className="text-xs text-ink-secondary mt-1">{e.description}</p>
                )}
                {e.is_peak && (
                  <span className="inline-block mt-1 text-[10px] font-bold text-status-failed
                    bg-status-failed/15 px-2 py-0.5 rounded-full">
                    PEAK
                  </span>
                )}
              </div>
            ))
          )}
        </motion.div>
      )}
    </div>
  )
}

/* ── Upcoming list (sorted by date_start) ────────────────────────────────────── */

function UpcomingList({ entries }: { entries: CalendarEntry[] }) {
  const upcoming = useMemo(() => {
    const now = new Date()
    return entries
      .filter(e => new Date(e.date_start) >= now)
      .sort((a, b) => new Date(a.date_start).getTime() - new Date(b.date_start).getTime())
      .slice(0, 10)
  }, [entries])

  if (upcoming.length === 0) {
    return <p className="text-xs text-ink-tertiary text-center py-8">No upcoming entries.</p>
  }

  return (
    <div className="space-y-3">
      {upcoming.map(e => (
        <motion.div
          key={e.id}
          initial={{ opacity: 0, x: 10 }}
          animate={{ opacity: 1, x: 0 }}
          className="glass-card rounded-xl p-4 border border-white/10 flex items-start gap-3"
        >
          {/* Date badge */}
          <div className="shrink-0 w-12 text-center">
            <p className="text-lg font-bold tabular-nums text-[#fa5c29]">
              {new Date(e.date_start).getDate()}
            </p>
            <p className="text-[10px] font-semibold uppercase text-ink-tertiary">
              {new Date(e.date_start).toLocaleDateString('en-KE', { month: 'short' })}
            </p>
          </div>
          {/* Entry info */}
          <div className="min-w-0 flex-1">
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm font-semibold text-[#f9dcd5] truncate">{e.title}</p>
              <StatusBadge status={typeStatus(e.entry_type)} size="sm" />
            </div>
            <p className="text-[10px] text-ink-tertiary mt-0.5">
              {e.entry_type.replace(/_/g, ' ')}
              {e.planning_trigger_offset_days && (
                <> · Reminder {e.planning_trigger_offset_days}d before</>
              )}
            </p>
            {e.description && (
              <p className="text-xs text-ink-secondary mt-1 line-clamp-2">{e.description}</p>
            )}
          </div>
        </motion.div>
      ))}
    </div>
  )
}

/* ── Main screen ─────────────────────────────────────────────────────────────── */

export default function CalendarScreen() {
  const today = new Date()
  const [year, setYear] = useState(today.getFullYear())
  const [month, setMonth] = useState(today.getMonth())
  const [view, setView] = useState<'grid' | 'list'>('grid')

  // Fetch entries for the visible month (with some margin)
  const fromDt = new Date(year, month, 1).toISOString()
  const toDt = new Date(year, month + 1, 0).toISOString()

  const { data: entries = [], isLoading, isError } = useQuery<CalendarEntry[]>({
    queryKey: ['calendar-entries', year, month],
    queryFn: () =>
      api.get<CalendarEntry[]>(`/calendar?from=${fromDt}&to=${toDt}`).then(r => r.data),
    staleTime: 60_000,
  })

  // Navigate months
  function prevMonth() {
    if (month === 0) { setMonth(11); setYear(y => y - 1) }
    else setMonth(m => m - 1)
  }
  function nextMonth() {
    if (month === 11) { setMonth(0); setYear(y => y + 1) }
    else setMonth(m => m + 1)
  }

  return (
    <div className="min-h-screen p-4 md:p-6">
      <div className="max-w-2xl mx-auto">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-6"
        >
          <h1 className="font-serif text-2xl md:text-3xl font-bold text-[#f9dcd5]">
            Calendar
          </h1>
          <p className="text-sm text-ink-secondary mt-1">
            Peak dates, holidays, and planning events
          </p>
        </motion.div>

        {/* Month navigation + view toggle */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <button onClick={prevMonth}
              className="w-8 h-8 rounded-lg glass-card flex items-center justify-center
                text-[#aa8980] hover:text-[#f9dcd5] transition-colors"
              aria-label="Previous month">
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                <path d="M10 3L5 8l5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
            <h2 className="text-base font-bold text-[#f9dcd5] min-w-[140px] text-center">
              {MONTH_NAMES[month]} {year}
            </h2>
            <button onClick={nextMonth}
              className="w-8 h-8 rounded-lg glass-card flex items-center justify-center
                text-[#aa8980] hover:text-[#f9dcd5] transition-colors"
              aria-label="Next month">
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                <path d="M6 3l5 5-5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
          </div>

          {/* Grid / List toggle */}
          <div className="flex rounded-xl overflow-hidden border border-white/10">
            {(['grid', 'list'] as const).map(v => (
              <button key={v} onClick={() => setView(v)}
                className={`px-3 py-1.5 text-[10px] font-bold tracking-widest uppercase transition-colors
                  ${view === v
                    ? 'bg-white/10 text-[#f9dcd5]'
                    : 'text-ink-tertiary hover:text-ink-secondary'
                  }`}>
                {v}
              </button>
            ))}
          </div>
        </div>

        {/* Legend */}
        <div className="flex flex-wrap gap-4 mb-4">
          {[
            { label: 'Holiday', color: 'bg-status-paid' },
            { label: 'Peak', color: 'bg-status-failed' },
            { label: 'Planning', color: 'bg-[#fa5c29]' },
            { label: 'Observance', color: 'bg-ink-tertiary' },
          ].map(l => (
            <div key={l.label} className="flex items-center gap-1.5">
              <span className={`w-2 h-2 rounded-full ${l.color}`} />
              <span className="text-[10px] text-ink-tertiary">{l.label}</span>
            </div>
          ))}
        </div>

        {/* Content */}
        <ErrorBoundary level="tile">
          {isLoading && (
            <div className="space-y-2">
              {[1, 2, 3, 4, 5].map(i => (
                <div key={i} className="h-12 rounded-xl bg-cream-alt animate-pulse" />
              ))}
            </div>
          )}

          {isError && (
            <p className="text-sm text-status-failed text-center py-12">
              Failed to load calendar. Check your connection.
            </p>
          )}

          {!isLoading && !isError && view === 'grid' && (
            <div className="glass-card rounded-2xl p-4 border border-white/10">
              <MonthGrid year={year} month={month} entries={entries} />
            </div>
          )}

          {!isLoading && !isError && view === 'list' && (
            <UpcomingList entries={entries} />
          )}
        </ErrorBoundary>
      </div>
    </div>
  )
}
