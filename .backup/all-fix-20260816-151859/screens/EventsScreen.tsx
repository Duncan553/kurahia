import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { Skeleton, EmptyState, StatusBadge, ErrorBoundary } from '@shared'
import type { StatusValue } from '@shared'
import api from '../lib/axios'
import { toDateKey, todayKey, formatTime } from '../lib/format'

// ── Types matching backend _event_dict + _assignment_dict ──────────────────

interface EventItem {
  id: string
  title: string
  event_type: string | null
  booking_id: string | null
  starts_at: string   // ISO 8601 UTC
  ends_at: string
  expected_guests: number
  location: string | null
  notes: string | null
  status: string       // PLANNED | CONFIRMED | IN_PROGRESS | COMPLETED | CANCELLED
}

interface Assignment {
  id: string
  event_id: string
  employee_id: string
  employee_name: string | null
  role_on_event: string
  status: string
}

// ── Helpers ────────────────────────────────────────────────────────────────

const NBI = 'Africa/Nairobi'
const TODAY = todayKey()

// Map event status to StatusBadge variants used across the app
function eventStatus(s: string): StatusValue {
  const map: Record<string, StatusValue> = {
    PLANNED: 'pending',
    CONFIRMED: 'confirmed',
    IN_PROGRESS: 'active',
    COMPLETED: 'checked-out',
    CANCELLED: 'cancelled',
  }
  return map[s.toUpperCase()] ?? 'pending'
}

// "Sat, 28 Jun" — short day label in Nairobi tz
function shortDay(iso: string): string {
  return new Intl.DateTimeFormat('en-KE', {
    timeZone: NBI, weekday: 'short', day: 'numeric', month: 'short',
  }).format(new Date(iso))
}

// End of today in Nairobi (used to figure out "this week" boundary)
function endOfWeek(): Date {
  const now = new Date()
  const dayOfWeek = now.getDay() // 0=Sun
  // Days until next Sunday (end of week)
  const daysLeft = dayOfWeek === 0 ? 0 : 7 - dayOfWeek
  const end = new Date(now)
  end.setDate(now.getDate() + daysLeft)
  end.setHours(23, 59, 59, 999)
  return end
}

// ── Animation ──────────────────────────────────────────────────────────────

const fadeIn = { hidden: { opacity: 0, y: 12 }, visible: { opacity: 1, y: 0 } }
const stagger = { visible: { transition: { staggerChildren: 0.06 } } }

// ── Main screen ────────────────────────────────────────────────────────────

export default function EventsScreen() {
  // Fetch upcoming events (PLANNED + CONFIRMED, sorted by start date)
  const { data: events, isLoading, isError, refetch } = useQuery<EventItem[]>({
    queryKey: ['events', 'upcoming'],
    queryFn: () => api.get<EventItem[]>('/events/upcoming').then((r) => r.data),
    refetchInterval: 60_000,
  })

  // ── LOADING ──────────────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="p-4 md:p-6 max-w-6xl mx-auto space-y-4">
        <Skeleton variant="text" className="w-48 h-8" />
        <Skeleton variant="text" className="w-64" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-6">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} variant="row" className="h-36" />
          ))}
        </div>
      </div>
    )
  }

  // ── ERROR ────────────────────────────────────────────────────────────────
  if (isError && !events) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[calc(100vh-8rem)] p-6">
        <EmptyState
          icon={
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none" aria-hidden="true">
              <rect x="8" y="6" width="32" height="36" rx="3" stroke="currentColor" strokeWidth="2" />
              <path d="M16 4v6M32 4v6M8 18h32" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              <path d="M20 28h8M24 24v8" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
            </svg>
          }
          title="Couldn't load events."
          description="Check your connection and try again."
          actionLabel="Retry"
          onAction={() => refetch()}
        />
      </div>
    )
  }

  // ── Partition events: today vs. this week vs. later ─────────────────────
  const weekEnd = endOfWeek()
  const todayEvents: EventItem[] = []
  const weekEvents: EventItem[] = []

  for (const ev of events ?? []) {
    const dateKey = toDateKey(ev.starts_at)
    if (dateKey === TODAY) {
      todayEvents.push(ev)
    } else if (new Date(ev.starts_at) <= weekEnd) {
      weekEvents.push(ev)
    }
    // Events beyond this week are still visible in the full list below
  }

  const allEmpty = (events ?? []).length === 0

  // ── EMPTY STATE ──────────────────────────────────────────────────────────
  if (allEmpty) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[calc(100vh-8rem)] p-6">
        <EmptyState
          icon={
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none" aria-hidden="true">
              <rect x="8" y="6" width="32" height="36" rx="3" stroke="currentColor" strokeWidth="2" />
              <path d="M16 4v6M32 4v6M8 18h32" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              <path d="M18 30h12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
          }
          title="No upcoming events."
          description="When weddings, conferences, or special bookings are scheduled, they'll show up here."
        />
      </div>
    )
  }

  return (
    <motion.div
      className="p-4 md:p-6 max-w-6xl mx-auto"
      initial="hidden"
      animate="visible"
      variants={stagger}
    >
      <ErrorBoundary level="tile">
      {/* ── Page header ──────────────────────────────────────────────── */}
      <motion.div variants={fadeIn} transition={{ duration: 0.3 }} className="mb-6">
        <h1 className="font-serif text-3xl md:text-4xl font-bold text-[#f9dcd5] tracking-tight">
          Upcoming Events
        </h1>
        <p className="text-sm text-ink-secondary mt-1">
          Weddings, conferences, special bookings
        </p>
      </motion.div>

      {/* ── Today's Events (hero section) ────────────────────────────── */}
      {todayEvents.length > 0 && (
        <motion.div variants={fadeIn} transition={{ duration: 0.3 }} className="mb-8">
          <div className="flex items-center gap-2 mb-3">
            <span className="w-2 h-2 rounded-full bg-status-paid animate-pulse" />
            <h2 className="text-sm font-bold tracking-widest uppercase text-status-paid">
              Today
            </h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {todayEvents.map((ev) => (
              <EventCard key={ev.id} event={ev} isToday />
            ))}
          </div>
        </motion.div>
      )}

      {/* ── This Week ────────────────────────────────────────────────── */}
      {weekEvents.length > 0 && (
        <motion.div variants={fadeIn} transition={{ duration: 0.3 }} className="mb-8">
          <h2 className="text-sm font-bold tracking-widest uppercase text-[#aa8980] mb-3">
            This Week
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {weekEvents.map((ev) => (
              <EventCard key={ev.id} event={ev} />
            ))}
          </div>
        </motion.div>
      )}

      {/* ── All Upcoming (full list) ─────────────────────────────────── */}
      {(events ?? []).length > todayEvents.length + weekEvents.length && (
        <motion.div variants={fadeIn} transition={{ duration: 0.3 }}>
          <h2 className="text-sm font-bold tracking-widest uppercase text-[#aa8980] mb-3">
            Coming Up
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {(events ?? [])
              .filter((ev) => !todayEvents.includes(ev) && !weekEvents.includes(ev))
              .map((ev) => (
                <EventCard key={ev.id} event={ev} />
              ))}
          </div>
        </motion.div>
      )}
      </ErrorBoundary>
    </motion.div>
  )
}

// ── EventCard ──────────────────────────────────────────────────────────────

function EventCard({ event, isToday = false }: { event: EventItem; isToday?: boolean }) {
  // Fetch assignments for this event so we can show assigned staff
  const { data: assignments } = useQuery<Assignment[]>({
    queryKey: ['events', event.id, 'assignments'],
    queryFn: () =>
      api.get<Assignment[]>(`/events/${event.id}/assignments`).then((r) => r.data),
    staleTime: 60_000,
  })

  // Active assignments only (not cancelled)
  const activeStaff = (assignments ?? []).filter((a) => a.status !== 'CANCELLED')

  return (
    <div
      className={[
        'glass-card rounded-2xl p-5 flex flex-col gap-3',
        isToday ? 'ring-1 ring-status-paid/40' : '',
      ].join(' ')}
    >
      {/* Top row: title + status badge */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="font-serif text-lg font-bold text-[#f9dcd5] truncate">
            {event.title}
          </h3>
          {event.event_type && (
            <span className="inline-block mt-1 px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wide
              bg-[#fa5c29]/10 text-[#fa5c29]">
              {event.event_type}
            </span>
          )}
        </div>
        <div className="shrink-0">
          <StatusBadge status={eventStatus(event.status)} />
        </div>
      </div>

      {/* Date + time row */}
      <div className="flex items-center gap-4 text-xs text-ink-secondary">
        {/* Calendar icon + date */}
        <span className="flex items-center gap-1.5">
          <svg width="14" height="14" viewBox="0 0 20 20" fill="none" className="text-ink-tertiary shrink-0" aria-hidden="true">
            <rect x="3" y="3.5" width="14" height="14" rx="2" stroke="currentColor" strokeWidth="1.5" />
            <path d="M7 1.5v4M13 1.5v4M3 9h14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          {shortDay(event.starts_at)}
        </span>
        {/* Clock icon + time range */}
        <span className="flex items-center gap-1.5 tabular-nums">
          <svg width="14" height="14" viewBox="0 0 20 20" fill="none" className="text-ink-tertiary shrink-0" aria-hidden="true">
            <circle cx="10" cy="10" r="7.5" stroke="currentColor" strokeWidth="1.5" />
            <path d="M10 6v4.5l3 2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          {formatTime(event.starts_at)} — {formatTime(event.ends_at)}
        </span>
      </div>

      {/* Location + guests row */}
      <div className="flex items-center gap-4 text-xs text-ink-secondary">
        {event.location && (
          <span className="flex items-center gap-1.5">
            <svg width="14" height="14" viewBox="0 0 20 20" fill="none" className="text-ink-tertiary shrink-0" aria-hidden="true">
              <path d="M10 2C6.7 2 4 4.7 4 8c0 4.5 6 10 6 10s6-5.5 6-10c0-3.3-2.7-6-6-6z"
                stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              <circle cx="10" cy="8" r="2" stroke="currentColor" strokeWidth="1.5" />
            </svg>
            {event.location}
          </span>
        )}
        <span className="flex items-center gap-1.5">
          <svg width="14" height="14" viewBox="0 0 20 20" fill="none" className="text-ink-tertiary shrink-0" aria-hidden="true">
            <circle cx="7" cy="7" r="3" stroke="currentColor" strokeWidth="1.5" />
            <path d="M1 17c0-2.8 2.7-4.5 6-4.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            <circle cx="14" cy="8" r="2.5" stroke="currentColor" strokeWidth="1.5" />
            <path d="M10 17c0-2.5 2-4 4-4s4 1.5 4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
          {event.expected_guests} guest{event.expected_guests !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Assigned staff */}
      {activeStaff.length > 0 && (
        <div className="pt-2 border-t border-white/5">
          <p className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary mb-1.5">
            Assigned Staff
          </p>
          <div className="flex flex-wrap gap-1.5">
            {activeStaff.map((a) => (
              <span
                key={a.id}
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px]
                  bg-white/5 text-ink-secondary"
              >
                {/* Tiny user icon */}
                <svg width="10" height="10" viewBox="0 0 20 20" fill="none" className="shrink-0" aria-hidden="true">
                  <circle cx="10" cy="7" r="3.5" stroke="currentColor" strokeWidth="1.5" />
                  <path d="M3 18c0-3.3 3.1-5.5 7-5.5s7 2.2 7 5.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
                {a.employee_name ?? 'Staff'} — {a.role_on_event}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
