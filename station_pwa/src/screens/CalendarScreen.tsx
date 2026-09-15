import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { ErrorBoundary, Button, Modal, useToastStore } from '@shared'
import { IfRole } from '../components/AuthGate'
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

// What the entry IS, said in its own words.
//
// This used to borrow StatusBadge by mapping PEAK onto the 'failed' status,
// purely to get the red. StatusBadge carries its own label with its colour,
// so a busy Saturday was badged "Failed" with a cross next to it — the screen
// telling a manager that the resort's best weekend of the month had gone
// wrong. A calendar entry has no status; it has a kind.
const TYPE_CHIP: Record<string, { label: string; cls: string }> = {
  HOLIDAY:             { label: 'Holiday',    cls: 'text-status-paid bg-status-paid/15 border-status-paid/25' },
  PEAK:                { label: 'Peak day',   cls: 'text-status-failed bg-status-failed/15 border-status-failed/25' },
  PLANNING_MEETING:    { label: 'Planning',   cls: 'text-primary-main bg-primary-main/15 border-primary-main/25' },
  EXTERNAL_OBSERVANCE: { label: 'Observance', cls: 'text-ink-tertiary bg-white/5 border-white/10' },
}

function TypeChip({ type }: { type: string }) {
  const c = TYPE_CHIP[type] ?? TYPE_CHIP.EXTERNAL_OBSERVANCE
  return (
    <span className={`shrink-0 inline-flex items-center rounded-full border px-2 py-0.5
      text-[11px] font-semibold ${c.cls}`}>
      {c.label}
    </span>
  )
}

// Entry type display color for the calendar dot
function dotColor(t: string): string {
  if (t === 'HOLIDAY')          return 'bg-status-paid'
  if (t === 'PEAK')             return 'bg-status-failed'
  if (t === 'PLANNING_MEETING') return 'bg-primary-main'
  return 'bg-ink-tertiary'
}

// Format readable date
function fmtDate(iso: string): string {
  // timeZone UTC for the same reason dateMap uses getUTC*: these are dates,
  // and rendering them through the device's clock shifts the day.
  return new Date(iso).toLocaleDateString('en-KE', {
    day: 'numeric', month: 'short', timeZone: 'UTC',
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
  // A calendar entry is a DATE, not an instant, and every read of it here works
  // in UTC to keep it that way.
  //
  // The grid's cell key is a plain `2026-09-25` built from the visible month.
  // Reading the entry through the device's clock put those two out of step:
  // "25 September" arrived as 2026-09-24T21:00:00Z in Nairobi (UTC+3), and a
  // three-day mark on the 25th–27th drew its dots on the 24th–26th. It would
  // have drifted the other way for anyone west of London, so the same holiday
  // would land on different days on the owner's phone and the station tablet.
  //
  // Hence getUTC* throughout, and dates written as midnight UTC on the way in.
  const dateMap = useMemo(() => {
    const map = new Map<string, CalendarEntry[]>()
    const key = (d: Date) =>
      `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`
      + `-${String(d.getUTCDate()).padStart(2, '0')}`
    for (const e of entries) {
      // An entry can span multiple days; mark each day it covers
      const cursor = new Date(e.date_start)
      const end = new Date(e.date_end)
      while (key(cursor) <= key(end)) {
        const arr = map.get(key(cursor)) ?? []
        arr.push(e)
        map.set(key(cursor), arr)
        cursor.setUTCDate(cursor.getUTCDate() + 1)
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
                  ? 'bg-primary-main/20 text-[#fa5c29] font-bold'
                  : isSelected
                    ? 'bg-white/10 text-ink-primary'
                    : 'text-ink-tertiary hover:bg-white/5 hover:text-ink-primary'
                }
                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-main`}
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
          <p className="text-xs font-semibold text-ink-primary">
            {selectedDay} {MONTH_NAMES[month]}
          </p>
          {selectedEntries.length === 0 ? (
            <p className="text-xs text-ink-tertiary">No entries on this day.</p>
          ) : (
            selectedEntries.map(e => (
              <div key={e.id} className="glass-card rounded-xl p-3 border border-white/10">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-semibold text-ink-primary">{e.title}</p>
                  <TypeChip type={e.entry_type} />
                </div>
                <p className="text-[10px] text-ink-tertiary mt-1">
                  {fmtDate(e.date_start)} - {fmtDate(e.date_end)}
                </p>
                {e.description && (
                  <p className="text-xs text-ink-secondary mt-1">{e.description}</p>
                )}
                {e.is_peak && e.entry_type !== 'PEAK' && (
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
              {new Date(e.date_start).getUTCDate()}
            </p>
            <p className="text-[10px] font-semibold uppercase text-ink-tertiary">
              {new Date(e.date_start).toLocaleDateString('en-KE', { month: 'short', timeZone: 'UTC' })}
            </p>
          </div>
          {/* Entry info */}
          <div className="min-w-0 flex-1">
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm font-semibold text-ink-primary truncate">{e.title}</p>
              <TypeChip type={e.entry_type} />
            </div>
            <p className="text-[10px] text-ink-tertiary mt-0.5">
              {fmtDate(e.date_start)}
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


/* ── Mark a date ──────────────────────────────────────────────────────────────
 * POST /calendar has existed the whole time and nothing in any of the three
 * apps called it. So the Calendar could be read and never written: the screen
 * drew a month grid and a legend for four colours that could not appear,
 * forever, because no person had a way to say "the 25th is a peak day".
 * A read-only calendar is not a calendar; it is a picture of one.
 *
 * Manager and above, matching the endpoint's own floor — and IfRole, so
 * everyone else simply does not see the button rather than being told off.
 */
const ENTRY_TYPES = [
  { value: 'PEAK',                 label: 'Peak day',    hint: 'Busy — staff up, stock up' },
  { value: 'HOLIDAY',              label: 'Holiday',     hint: 'Public holiday' },
  { value: 'PLANNING_MEETING',     label: 'Planning',    hint: 'Raises a reminder beforehand' },
  { value: 'EXTERNAL_OBSERVANCE',  label: 'Observance',  hint: 'Good to know, not a peak' },
]

function MarkDateModal({ open, onClose, year, month }: {
  open: boolean; onClose: () => void; year: number; month: number
}) {
  const qc = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  const [title, setTitle] = useState('')
  const [entryType, setEntryType] = useState('PEAK')
  // Default to today when the visible month is the current one, otherwise the
  // 1st — so the field is never empty and never a date in another month.
  const now = new Date()
  const defaultDay = (now.getFullYear() === year && now.getMonth() === month)
    ? now.getDate() : 1
  const iso = (d: number) =>
    `${year}-${String(month + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`
  const [start, setStart] = useState(iso(defaultDay))
  const [end, setEnd] = useState(iso(defaultDay))
  const [offset, setOffset] = useState('')

  const mut = useMutation({
    mutationFn: () => api.post('/calendar', {
      title: title.trim(),
      entry_type: entryType,
      // Midnight UTC, NOT local midnight. `new Date('2026-09-25T00:00:00')`
      // is parsed in the device's zone, so in Nairobi it becomes the 24th at
      // 21:00Z and the mark lands a day early for everyone.
      date_start: `${start}T00:00:00Z`,
      date_end:   `${end}T23:59:59Z`,
      ...(entryType === 'PLANNING_MEETING' && offset.trim()
        ? { planning_trigger_offset_days: parseInt(offset, 10) } : {}),
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['calendar-entries'] })
      setTitle(''); setOffset('')
      onClose()
      addToast({ type: 'success', message: 'Marked on the calendar.' })
    },
    onError: (e) => addToast({ type: 'error',
      message: (e as { response?: { data?: { error?: string } } })
        ?.response?.data?.error ?? 'Could not save that.' }),
  })

  const field = "w-full rounded-xl glass-card bg-transparent px-4 py-3 text-sm "
              + "text-ink-primary focus:outline-none focus:border-primary-main"

  return (
    <Modal open={open} onClose={onClose} title="Mark a date">
      <div className="space-y-4">
        <div>
          <label htmlFor="cal-title"
                 className="block text-[11px] uppercase tracking-wider text-ink-tertiary mb-1">
            What is it
          </label>
          <input id="cal-title" value={title} onChange={e => setTitle(e.target.value)}
                 placeholder="e.g. Madaraka Day weekend" className={field} />
        </div>

        <div>
          <p className="text-[11px] uppercase tracking-wider text-ink-tertiary mb-1">Type</p>
          <div className="grid grid-cols-2 gap-2">
            {ENTRY_TYPES.map(t => (
              <button key={t.value} onClick={() => setEntryType(t.value)}
                className={`p-3 rounded-xl text-left border transition-colors ${
                  entryType === t.value
                    ? 'bg-primary-main text-white border-primary-main'
                    : 'text-ink-secondary border-white/10 hover:border-primary-main/50'
                }`}>
                <span className="block text-sm font-semibold">{t.label}</span>
                <span className="block text-[11px] opacity-80">{t.hint}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label htmlFor="cal-start"
                   className="block text-[11px] uppercase tracking-wider text-ink-tertiary mb-1">
              From
            </label>
            <input id="cal-start" type="date" value={start}
                   onChange={e => { setStart(e.target.value); if (e.target.value > end) setEnd(e.target.value) }}
                   className={field} />
          </div>
          <div>
            <label htmlFor="cal-end"
                   className="block text-[11px] uppercase tracking-wider text-ink-tertiary mb-1">
              To
            </label>
            <input id="cal-end" type="date" value={end} min={start}
                   onChange={e => setEnd(e.target.value)} className={field} />
          </div>
        </div>

        {entryType === 'PLANNING_MEETING' && (
          <div>
            <label htmlFor="cal-offset"
                   className="block text-[11px] uppercase tracking-wider text-ink-tertiary mb-1">
              Remind this many days before
            </label>
            <input id="cal-offset" type="number" min="1" inputMode="numeric"
                   value={offset} onChange={e => setOffset(e.target.value)}
                   placeholder="e.g. 7" className={field} />
            <p className="text-[11px] text-ink-tertiary mt-1">
              Leave blank for no reminder.
            </p>
          </div>
        )}

        <div className="flex gap-2 pt-1">
          <Button variant="ghost" size="lg" className="flex-1" onClick={onClose}>Cancel</Button>
          <Button variant="primary" size="lg" className="flex-1"
                  loading={mut.isPending} disabled={!title.trim()}
                  onClick={() => mut.mutate()}>
            Mark it
          </Button>
        </div>
      </div>
    </Modal>
  )
}

/* ── Main screen ─────────────────────────────────────────────────────────────── */

export default function CalendarScreen() {
  const today = new Date()
  const [year, setYear] = useState(today.getFullYear())
  const [month, setMonth] = useState(today.getMonth())
  const [view, setView] = useState<'grid' | 'list'>('grid')
  const [showMark, setShowMark] = useState(false)

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
          className="mb-6 flex items-start justify-between gap-3"
        >
          <div>
            <h1 className="font-serif text-2xl md:text-3xl font-bold text-ink-primary">
              Calendar
            </h1>
            <p className="text-sm text-ink-secondary mt-1">
              Peak dates, holidays, and planning events
            </p>
          </div>
          <IfRole minLevel={5}>
            <Button variant="primary" size="sm" onClick={() => setShowMark(true)}>
              + Mark a date
            </Button>
          </IfRole>
        </motion.div>
        <MarkDateModal open={showMark} onClose={() => setShowMark(false)}
                       year={year} month={month} />

        {/* Month navigation + view toggle */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <button onClick={prevMonth}
              className="w-8 h-8 rounded-lg glass-card flex items-center justify-center
                text-ink-tertiary hover:text-ink-primary transition-colors"
              aria-label="Previous month">
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                <path d="M10 3L5 8l5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
            <h2 className="text-base font-bold text-ink-primary min-w-[140px] text-center">
              {MONTH_NAMES[month]} {year}
            </h2>
            <button onClick={nextMonth}
              className="w-8 h-8 rounded-lg glass-card flex items-center justify-center
                text-ink-tertiary hover:text-ink-primary transition-colors"
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
                    ? 'bg-white/10 text-ink-primary'
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
            { label: 'Planning', color: 'bg-primary-main' },
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
