import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { Skeleton, EmptyState, StatusBadge, ErrorBoundary, Modal, Button, useToastStore } from '@shared'
import type { StatusValue } from '@shared'
import { RequireRole } from '../components/AuthGate'
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

const extractErr = (e: unknown) =>
  (e as { response?: { data?: { error?: string } } })?.response?.data?.error ?? 'Something went wrong.'

interface EventType { id: string; name: string }

/** Create an event. Manager+ per the backend (app/events/core.py) — this
 * screen was read-only (view + acknowledge assignments) with no way for
 * anyone to actually create the event in the first place, anywhere in the app. */
function CreateEventModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  const [title, setTitle] = useState('')
  const [typeId, setTypeId] = useState('')
  const [newTypeName, setNewTypeName] = useState('')
  const [startsAt, setStartsAt] = useState('')
  const [endsAt, setEndsAt] = useState('')
  const [guests, setGuests] = useState('1')
  const [location, setLocation] = useState('')
  const [idem] = useState(() => crypto.randomUUID())

  const { data: types = [] } = useQuery<EventType[]>({
    queryKey: ['event-types'],
    queryFn: () => api.get<EventType[]>('/event-types').then(r => r.data),
    staleTime: 5 * 60_000,
  })

  const createTypeMut = useMutation({
    mutationFn: () => api.post<EventType>('/event-types', { name: newTypeName.trim() }).then(r => r.data),
    onSuccess: (t) => {
      qc.invalidateQueries({ queryKey: ['event-types'] })
      setTypeId(t.id); setNewTypeName('')
    },
    onError: e => addToast({ type: 'error', message: extractErr(e) }),
  })

  const createEventMut = useMutation({
    mutationFn: () => api.post('/events', {
      title: title.trim(),
      event_type_id: typeId,
      starts_at_utc: new Date(startsAt).toISOString(),
      ends_at_utc: new Date(endsAt).toISOString(),
      expected_guests: Number(guests) || 1,
      location: location.trim() || null,
      idempotency_key: idem,
    }),
    onSuccess: () => {
      addToast({ type: 'success', message: 'Event created.' })
      qc.invalidateQueries({ queryKey: ['events', 'upcoming'] })
      setTitle(''); setTypeId(''); setStartsAt(''); setEndsAt(''); setGuests('1'); setLocation('')
      onClose()
    },
    onError: e => addToast({ type: 'error', message: extractErr(e) }),
  })

  const canSubmit = title.trim() && typeId && startsAt && endsAt

  return (
    <Modal open={open} onClose={onClose} title="Create Event" size="md">
      <div className="space-y-4">
        <div>
          <label className="block text-xs font-semibold text-ink-secondary mb-1">Title</label>
          <input value={title} onChange={e => setTitle(e.target.value)}
            placeholder="e.g. Kamau & Wanjiru Wedding"
            className="w-full rounded-lg border border-white/10 bg-transparent px-3 py-2 text-sm text-ink-primary
              placeholder:text-ink-tertiary focus:outline-none focus:ring-2 focus:ring-primary-main" />
        </div>

        <div>
          <label className="block text-xs font-semibold text-ink-secondary mb-1">Event type</label>
          <div className="flex gap-2">
            <select
              style={{ colorScheme: 'dark' }}
              value={typeId} onChange={e => setTypeId(e.target.value)}
              className="flex-1 rounded-lg border border-white/10 bg-transparent px-3 py-2 text-sm text-ink-primary
                focus:outline-none focus:ring-2 focus:ring-primary-main"
            >
              <option value="">Select type...</option>
              {types.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </div>
          <div className="flex gap-2 mt-2">
            <input value={newTypeName} onChange={e => setNewTypeName(e.target.value)}
              placeholder="New type name, e.g. Conference"
              className="flex-1 rounded-lg border border-white/10 bg-transparent px-3 py-2 text-xs text-ink-primary
                placeholder:text-ink-tertiary focus:outline-none focus:ring-2 focus:ring-primary-main" />
            <Button variant="ghost" size="sm" disabled={!newTypeName.trim() || createTypeMut.isPending}
              onClick={() => createTypeMut.mutate()}>
              + Add type
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-semibold text-ink-secondary mb-1">Starts</label>
            <input type="datetime-local" style={{ colorScheme: 'dark' }} value={startsAt}
              onChange={e => setStartsAt(e.target.value)}
              className="w-full rounded-lg border border-white/10 bg-transparent px-3 py-2 text-sm text-ink-primary
                focus:outline-none focus:ring-2 focus:ring-primary-main" />
          </div>
          <div>
            <label className="block text-xs font-semibold text-ink-secondary mb-1">Ends</label>
            <input type="datetime-local" style={{ colorScheme: 'dark' }} value={endsAt}
              onChange={e => setEndsAt(e.target.value)}
              className="w-full rounded-lg border border-white/10 bg-transparent px-3 py-2 text-sm text-ink-primary
                focus:outline-none focus:ring-2 focus:ring-primary-main" />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-semibold text-ink-secondary mb-1">Expected guests</label>
            <input type="number" min="1" value={guests} onChange={e => setGuests(e.target.value)}
              className="w-full rounded-lg border border-white/10 bg-transparent px-3 py-2 text-sm text-ink-primary
                focus:outline-none focus:ring-2 focus:ring-primary-main" />
          </div>
          <div>
            <label className="block text-xs font-semibold text-ink-secondary mb-1">Location (optional)</label>
            <input value={location} onChange={e => setLocation(e.target.value)}
              placeholder="e.g. Lakeside Lawn"
              className="w-full rounded-lg border border-white/10 bg-transparent px-3 py-2 text-sm text-ink-primary
                placeholder:text-ink-tertiary focus:outline-none focus:ring-2 focus:ring-primary-main" />
          </div>
        </div>

        <Button variant="primary" className="w-full"
          disabled={!canSubmit || createEventMut.isPending}
          onClick={() => createEventMut.mutate()}>
          {createEventMut.isPending ? 'Creating…' : 'Create Event'}
        </Button>
      </div>
    </Modal>
  )
}

// ── Main screen ────────────────────────────────────────────────────────────

export default function EventsScreen() {
  const [showCreate, setShowCreate] = useState(false)

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
        <RequireRole minLevel={5}>
          <Button variant="primary" size="sm" className="mt-4" onClick={() => setShowCreate(true)}>
            + Create Event
          </Button>
        </RequireRole>
        <CreateEventModal open={showCreate} onClose={() => setShowCreate(false)} />
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
      <motion.div variants={fadeIn} transition={{ duration: 0.3 }}
        className="mb-6 flex items-start justify-between gap-3">
        <div>
          <h1 className="font-serif text-3xl md:text-4xl font-bold text-ink-primary tracking-tight">
            Upcoming Events
          </h1>
          <p className="text-sm text-ink-secondary mt-1">
            Weddings, conferences, special bookings
          </p>
        </div>
        <RequireRole minLevel={5}>
          <Button variant="primary" size="sm" onClick={() => setShowCreate(true)}>
            + Create Event
          </Button>
        </RequireRole>
      </motion.div>
      <CreateEventModal open={showCreate} onClose={() => setShowCreate(false)} />

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
          <h2 className="text-sm font-bold tracking-widest uppercase text-ink-tertiary mb-3">
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
          <h2 className="text-sm font-bold tracking-widest uppercase text-ink-tertiary mb-3">
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
          <h3 className="font-serif text-lg font-bold text-ink-primary truncate">
            {event.title}
          </h3>
          {event.event_type && (
            <span className="inline-block mt-1 px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wide
              bg-primary-main/10 text-[#fa5c29]">
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
