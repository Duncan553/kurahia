import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { Skeleton, EmptyState, StatusBadge, ErrorBoundary, Modal, Drawer, Button, Input, Select, useToastStore } from '@shared'
import type { StatusValue } from '@shared'
import { IfRole } from '../components/AuthGate'
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
  job: string | null
  status: string
}

// What a crew member does — the system acts on it: KITCHEN hears the plates,
// BAR the drinks, SERVICE is told when a dish is ready for pickup.
const JOBS = [
  { value: 'KITCHEN', label: 'Kitchen — cooks the food' },
  { value: 'BAR',     label: 'Bar — prepares the drinks' },
  { value: 'SERVICE', label: 'Service — carries it out' },
  { value: 'SETUP',   label: 'Setup' },
]

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
interface Venue { id: string; name: string; capacity: number | null }

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
  const [venueId, setVenueId] = useState('')
  const [bookingFee, setBookingFee] = useState('')
  // One key per event, not per form. The form stays mounted between opens, so a
  // key made once was reused: every event after the first came back as a
  // "duplicate" of it with a 200, and the screen still said "Event created."
  const [idem, setIdem] = useState(() => crypto.randomUUID())

  const { data: types = [] } = useQuery<EventType[]>({
    queryKey: ['event-types'],
    queryFn: () => api.get<EventType[]>('/event-types').then(r => r.data),
    staleTime: 5 * 60_000,
  })

  // Every event is held somewhere, and the places are the manager's own list
  // (Manage → Villas & venues). The backend refuses no venue, an over-full one,
  // and a space already taken for those hours — this only offers the list.
  const { data: venues = [] } = useQuery<Venue[]>({
    queryKey: ['bookable-resources', 'EVENT_VENUE'],
    queryFn: () => api.get<Venue[]>('/bookable-resources?resource_type=EVENT_VENUE').then(r => r.data),
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
      venue_id: venueId,
      booking_fee: bookingFee.trim() || null,   // empty → the owner's minimum
      idempotency_key: idem,
    }),
    onSuccess: () => {
      addToast({ type: 'success', message: 'Event created.' })
      qc.invalidateQueries({ queryKey: ['events', 'upcoming'] })
      setTitle(''); setTypeId(''); setStartsAt(''); setEndsAt(''); setGuests('1'); setVenueId(''); setBookingFee(''); setIdem(crypto.randomUUID())
      onClose()
    },
    onError: e => addToast({ type: 'error', message: extractErr(e) }),
  })

  const canSubmit = title.trim() && typeId && venueId && startsAt && endsAt

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
            <label className="block text-xs font-semibold text-ink-secondary mb-1">Where</label>
            <select style={{ colorScheme: 'dark' }} value={venueId} onChange={e => setVenueId(e.target.value)}
              className="w-full rounded-lg border border-white/10 bg-transparent px-3 py-2 text-sm text-ink-primary
                focus:outline-none focus:ring-2 focus:ring-primary-main">
              <option value="">Choose a venue…</option>
              {venues.map(v => (
                <option key={v.id} value={v.id}>{v.name}{v.capacity ? ` · holds ${v.capacity}` : ''}</option>
              ))}
            </select>
            {venues.length === 0 && (
              <p className="text-xs text-ink-tertiary mt-1">
                No venues yet. Add the resort&apos;s spaces under Manage → Villas &amp; venues.
              </p>
            )}
          </div>
        </div>

        <div>
          <label className="block text-xs font-semibold text-ink-secondary mb-1">Booking fee (KSh)</label>
          <input value={bookingFee} inputMode="numeric" onChange={e => setBookingFee(e.target.value)}
            placeholder="Leave empty for the owner's minimum"
            className="w-full rounded-lg border border-white/10 bg-transparent px-3 py-2 text-sm text-ink-primary
              placeholder:text-ink-tertiary focus:outline-none focus:ring-2 focus:ring-primary-main" />
          <p className="text-xs text-ink-tertiary mt-1">Taken before confirming. Kept if the event is cancelled.</p>
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
        <IfRole minLevel={5}>
          <Button variant="primary" size="sm" className="mt-4" onClick={() => setShowCreate(true)}>
            + Create Event
          </Button>
        </IfRole>
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
        <IfRole minLevel={5}>
          <Button variant="primary" size="sm" onClick={() => setShowCreate(true)}>
            + Create Event
          </Button>
        </IfRole>
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

// ── Running the event ───────────────────────────────────────────────────────
//
// Everything below this line was missing. The screen could CREATE an event and
// then nothing: the four lifecycle transitions, the staffing, and the whole
// inventory sub-ledger had endpoints and no buttons. A wedding could be
// entered into the system and never confirmed, never staffed, never issued a
// single crate, never closed — it just sat at PLANNED forever.

interface Alloc {
  id: string
  inventory_item_id: string
  item_name: string | null
  allocated_quantity: string
  status: string            // PLANNED | ISSUED | RETURNED | CONSUMED — the backend's words (AllocationStatus). It said ALLOCATED here, so Issue never rendered.
  notes: string | null
}

interface Profile { id: string; full_name: string; is_active?: boolean }
interface InvItem { id: string; name: string; unit: string; is_active?: boolean }

function allocBadge(s: string): StatusValue {
  const map: Record<string, StatusValue> = {
    PLANNED: 'pending', ISSUED: 'active', RETURNED: 'checked-out', CONSUMED: 'resolved',
  }
  return map[s.toUpperCase()] ?? 'info'
}

// Which buttons an event may legally show, mirroring VALID_EVENT_TRANSITIONS
// in the backend. Offering a button the API will refuse is the same mistake as
// the Cash tile that answered "this screen isn't yours" — the UI should only
// show what will work.
const NEXT: Record<string, { label: string; path: string; tone?: 'ghost' }[]> = {
  PLANNED:     [{ label: 'Confirm it',  path: 'confirm' },
                { label: 'Cancel',      path: 'cancel', tone: 'ghost' }],
  CONFIRMED:   [{ label: 'Start',       path: 'start' },
                { label: 'Cancel',      path: 'cancel', tone: 'ghost' }],
  IN_PROGRESS: [{ label: 'Finish',      path: 'complete' }],
  COMPLETED:   [],
  CANCELLED:   [],
}

function RunPanel({ event, onClose }: { event: EventItem; onClose: () => void }) {
  const qc = useQueryClient()
  const addToast = useToastStore(s => s.addToast)

  const [who, setWho] = useState('')
  const [role, setRole] = useState('')
  const [job, setJob] = useState('')
  const [itemId, setItemId] = useState('')
  const [qty, setQty] = useState('')

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['events'] })
    qc.invalidateQueries({ queryKey: ['events', event.id, 'assignments'] })
    qc.invalidateQueries({ queryKey: ['events', event.id, 'inventory'] })
    // Issuing stock moves real stock, so the count screens must not keep
    // showing the pre-issue number.
    qc.invalidateQueries({ queryKey: ['inventory-items-all'] })
  }
  const fail = (e: unknown) => addToast({ message: extractErr(e), type: 'error' })

  const { data: staff = [] } = useQuery<Profile[]>({
    queryKey: ['hr-profiles'],
    queryFn: () => api.get<Profile[]>('/hr/profiles').then(r => Array.isArray(r.data) ? r.data : []),
    staleTime: 5 * 60_000,
  })
  const { data: items = [] } = useQuery<InvItem[]>({
    queryKey: ['inventory-items-all'],
    queryFn: () => api.get<InvItem[]>('/inventory/items').then(r => Array.isArray(r.data) ? r.data : []),
    staleTime: 5 * 60_000,
  })
  const { data: assignments = [] } = useQuery<Assignment[]>({
    queryKey: ['events', event.id, 'assignments'],
    queryFn: () => api.get<Assignment[]>(`/events/${event.id}/assignments`).then(r => Array.isArray(r.data) ? r.data : []),
  })
  const { data: allocs = [] } = useQuery<Alloc[]>({
    queryKey: ['events', event.id, 'inventory'],
    // The API wraps the rows: { allocations, reconciliation }. This used to read the
    // body as an array, got an object, and silently showed "Nothing set aside".
    queryFn: () => api.get<{ allocations: Alloc[] }>(`/events/${event.id}/inventory`)
      .then(r => r.data.allocations ?? []),
  })

  const move = useMutation({
    mutationFn: (path: string) => api.post(`/events/${event.id}/${path}`, {}),
    onSuccess: (_d, path) => {
      addToast({ message: `Event ${path === 'complete' ? 'finished' : path + 'ed'}.`, type: 'success' })
      refresh()
      if (path === 'cancel' || path === 'complete') onClose()
    },
    onError: fail,
  })

  const assign = useMutation({
    mutationFn: () => api.post(`/events/${event.id}/assignments`,
      { employee_id: who, job, role_on_event: role.trim() || null }),
    onSuccess: (r) => {
      const n = (r.data as { notifications_scheduled?: number })?.notifications_scheduled
      addToast({
        // Worth saying out loud: assigning someone to a CONFIRMED event is what
        // sends them their reminders. On a PLANNED event it sends nothing, and
        // a manager who does not know that thinks the staff were told.
        message: n ? `Added. ${n} reminder${n === 1 ? '' : 's'} scheduled.`
                   : 'Added. Reminders go out when the event is confirmed.',
        type: 'success',
      })
      setWho(''); setRole(''); setJob(''); refresh()
    },
    onError: fail,
  })

  const unassign = useMutation({
    mutationFn: (id: string) => api.post(`/events/${event.id}/assignments/${id}/cancel`, {}),
    onSuccess: () => { addToast({ message: 'Taken off the event.', type: 'success' }); refresh() },
    onError: fail,
  })

  const allocate = useMutation({
    mutationFn: () => api.post(`/events/${event.id}/inventory/allocate`, {
      inventory_item_id: itemId,
      allocated_quantity: qty,
      idempotency_key: crypto.randomUUID(),
    }),
    onSuccess: () => {
      // Set aside ≠ gone. Nothing leaves the store until Issue.
      addToast({ message: 'Set aside. Stock has not moved yet.', type: 'success' })
      setItemId(''); setQty(''); refresh()
    },
    onError: fail,
  })

  const allocMove = useMutation({
    mutationFn: ({ id, verb }: { id: string; verb: string }) =>
      api.post(`/events/${event.id}/inventory/${id}/${verb}`, {}),
    onSuccess: (_d, { verb }) => {
      addToast({
        message: verb === 'issue'  ? 'Issued — stock has left the store.'
               : verb === 'return' ? 'Returned — back on the shelf.'
               :                     'Marked used up.',
        type: 'success',
      })
      refresh()
    },
    onError: fail,
  })

  const canEdit = ['PLANNED', 'CONFIRMED'].includes(event.status)
  const live = assignments.filter(a => a.status !== 'CANCELLED')

  return (
    <div className="space-y-5">

      {/* ── Lifecycle ───────────────────────────────────────────── */}
      <div className="flex flex-wrap gap-2">
        {(NEXT[event.status] ?? []).map(b => (
          <Button key={b.path} variant={b.tone} disabled={move.isPending}
            onClick={() => move.mutate(b.path)}>
            {b.label}
          </Button>
        ))}
        {(NEXT[event.status] ?? []).length === 0 && (
          <p className="text-xs text-ink-tertiary">
            This event is {event.status.toLowerCase().replace('_', ' ')}. Nothing left to do.
          </p>
        )}
      </div>

      {/* ── Who is working it ───────────────────────────────────── */}
      <section className="space-y-2">
        <h3 className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary">
          Who is working it
        </h3>
        {live.length === 0 && <p className="text-xs text-ink-tertiary">Nobody yet.</p>}
        {live.map(a => (
          <div key={a.id} className="flex items-center justify-between gap-2 text-sm">
            <span className="text-ink-secondary min-w-0 truncate">
              {a.employee_name ?? 'Staff'} — {a.role_on_event}
              {a.status === 'ACKNOWLEDGED' && <span className="text-ink-tertiary"> · seen it</span>}
            </span>
            {canEdit && (
              <button className="text-xs text-ink-tertiary hover:text-status-failed shrink-0"
                onClick={() => unassign.mutate(a.id)}>Remove</button>
            )}
          </div>
        ))}
        {canEdit && (
          <div className="flex flex-col sm:flex-row gap-2 pt-1">
            <Select label="Person" value={who} onChange={e => setWho(e.target.value)}
              options={[{ value: '', label: 'Pick someone' },
                        ...staff.filter(s => s.is_active !== false)
                                .map(s => ({ value: s.id, label: s.full_name }))]} />
            <Select label="Job" value={job} onChange={e => setJob(e.target.value)}
              options={[{ value: '', label: 'Pick a job' }, ...JOBS]} />
            <Input label="Details (optional)" value={role} onChange={e => setRole(e.target.value)}
              placeholder="e.g. head waiter" />
            <Button className="sm:self-end" disabled={!who || !job || assign.isPending}
              onClick={() => assign.mutate()}>Add</Button>
          </div>
        )}
      </section>

      {/* ── Stock for the event ─────────────────────────────────── */}
      <section className="space-y-2">
        <h3 className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary">
          Stock for the event
        </h3>
        {allocs.length === 0 && <p className="text-xs text-ink-tertiary">Nothing set aside.</p>}
        {allocs.map(a => (
          <div key={a.id} className="flex items-center justify-between gap-2 text-sm">
            <span className="text-ink-secondary min-w-0 truncate">
              {a.item_name ?? 'Item'} × {a.allocated_quantity}
            </span>
            <span className="flex items-center gap-2 shrink-0">
              <StatusBadge status={allocBadge(a.status)} size="sm" />
              {a.status === 'PLANNED' && (
                <button className="text-xs text-[#fa5c29]"
                  onClick={() => allocMove.mutate({ id: a.id, verb: 'issue' })}>Issue</button>
              )}
              {a.status === 'ISSUED' && (<>
                <button className="text-xs text-ink-tertiary hover:text-ink-secondary"
                  onClick={() => allocMove.mutate({ id: a.id, verb: 'return' })}>Came back</button>
                <button className="text-xs text-[#fa5c29]"
                  onClick={() => allocMove.mutate({ id: a.id, verb: 'consume' })}>Used up</button>
              </>)}
            </span>
          </div>
        ))}
        {canEdit && (
          <div className="flex flex-col sm:flex-row gap-2 pt-1">
            <Select label="Item" value={itemId} onChange={e => setItemId(e.target.value)}
              options={[{ value: '', label: 'Pick an item' },
                        ...items.filter(i => i.is_active !== false)
                                .map(i => ({ value: i.id, label: `${i.name} (${i.unit})` }))]} />
            <Input label="How much" value={qty} inputMode="decimal"
              onChange={e => setQty(e.target.value)} placeholder="12" />
            <Button className="sm:self-end"
              disabled={!itemId || !qty.trim() || allocate.isPending}
              onClick={() => allocate.mutate()}>Set aside</Button>
          </div>
        )}
        {!canEdit && allocs.length > 0 && (
          <p className="text-xs text-ink-tertiary">
            Nothing more can be set aside once the event has started.
          </p>
        )}
      </section>

      <MenuAndBill event={event} />
    </div>
  )
}

// ── Menu & bill ─────────────────────────────────────────────────────────────
//
// The event is a special customer. The manager plans dish × plates (with a
// recorded discount), the system checks the store and writes the buy list, and
// on the day the plan goes to the kitchen and bar as real orders on the
// event's own bill. Rules live in app/services/event_menu.py — this only shows
// them and asks.

interface MenuLine {
  id: string; name: string; quantity: string; menu_price: string
  discount_per_unit: string; charged_per_unit: string; line_total: string
  discount_reason: string | null; sent: boolean
}
interface StockRow { name: string; unit: string; needed: string; short: string }
interface EventMenu {
  lines: MenuLine[]
  totals: { menu_value: string; discount: string; to_charge: string }
  stock: { ready: boolean; items: StockRow[] }
}
interface Bill {
  tab_id: string | null; charged: string; paid: string; owing: string
  lines?: { description: string; amount: string }[]
  booking_fee: { amount: string; paid: string; settled: boolean }
  payments?: { method: string; amount: string }[]
}
interface Dish { id: string; name: string; price: string; stock_tracking: string; prep_station: string }

const ksh = (v: string | number) => `KSh ${Number(v).toLocaleString()}`
// Stock quantities come back as "10.0000"; a person reads "10".
const qty = (v: string) => String(Number(v))

function MenuAndBill({ event }: { event: EventItem }) {
  const qc = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  const [dishId, setDishId] = useState('')
  const [plates, setPlates] = useState('')
  const [discount, setDiscount] = useState('')
  const [reason, setReason] = useState('')
  const [payMethod, setPayMethod] = useState('CASH')
  const [payAmount, setPayAmount] = useState('')
  const [payIdem, setPayIdem] = useState(() => crypto.randomUUID())

  const refresh = () => qc.invalidateQueries({ queryKey: ['events', event.id] })
  const fail = (e: unknown) => addToast({ message: extractErr(e), type: 'error' })

  const { data: menu } = useQuery<EventMenu>({
    queryKey: ['events', event.id, 'menu'],
    queryFn: () => api.get<EventMenu>(`/events/${event.id}/menu`).then(r => r.data),
  })
  const { data: bill } = useQuery<Bill>({
    queryKey: ['events', event.id, 'bill'],
    queryFn: () => api.get<Bill>(`/events/${event.id}/bill`).then(r => r.data),
  })
  // Kitchen and bar dishes only, and never one nobody has classified — the
  // backend refuses those anyway; offering them would only produce a refusal.
  const { data: dishes = [] } = useQuery<Dish[]>({
    queryKey: ['menu-items', 'KITCHEN,BAR'],
    queryFn: () => api.get<Dish[]>('/menu/items?station=KITCHEN,BAR').then(r => r.data),
    staleTime: 5 * 60_000,
    select: d => d.filter(i => i.stock_tracking !== 'UNTRACKED'),
  })

  const add = useMutation({
    mutationFn: () => api.post(`/events/${event.id}/menu`, {
      menu_item_id: dishId, quantity: plates,
      discount_per_unit: discount || '0', discount_reason: reason.trim() || null,
    }),
    onSuccess: () => {
      addToast({ message: 'Added to the menu.', type: 'success' })
      setDishId(''); setPlates(''); setDiscount(''); setReason(''); refresh()
    },
    onError: fail,
  })
  const remove = useMutation({
    mutationFn: (id: string) => api.post(`/events/${event.id}/menu/${id}/remove`, {}),
    onSuccess: () => { addToast({ message: 'Taken off the menu.', type: 'success' }); refresh() },
    onError: fail,
  })
  const buyList = useMutation({
    mutationFn: () => api.post<{ written: number }>(`/events/${event.id}/buy-list`, {}).then(r => r.data),
    onSuccess: d => {
      addToast({ message: d.written ? `${d.written} item${d.written === 1 ? '' : 's'} added to purchase requests.`
                                    : 'Already on the purchase requests.', type: 'success' })
      refresh(); qc.invalidateQueries({ queryKey: ['purchase-requests'] })
    },
    onError: fail,
  })
  const send = useMutation({
    mutationFn: () => api.post(`/events/${event.id}/send`, {}),
    onSuccess: () => {
      addToast({ message: 'Sent to the kitchen and bar. Charged to the event bill.', type: 'success' })
      refresh()
    },
    onError: fail,
  })
  const [feeMethod, setFeeMethod] = useState('CASH')
  const [feeIdem, setFeeIdem] = useState(() => crypto.randomUUID())
  const takeFee = useMutation({
    mutationFn: () => api.post(`/events/${event.id}/booking-fee`, {
      method: feeMethod, idempotency_key: feeIdem,
      amount: String(Number(bill!.booking_fee.amount) - Number(bill!.booking_fee.paid)),
    }),
    onSuccess: () => {
      addToast({ message: 'Booking fee taken. The event can be confirmed.', type: 'success' })
      setFeeIdem(crypto.randomUUID()); refresh()
    },
    onError: fail,
  })

  const pay = useMutation({
    mutationFn: () => api.post(`/tabs/${bill!.tab_id}/payments`, {
      method: payMethod, amount: payAmount, idempotency_key: payIdem,
    }),
    onSuccess: () => {
      addToast({ message: 'Payment recorded on the event bill.', type: 'success' })
      setPayAmount(''); setPayIdem(crypto.randomUUID()); refresh()
    },
    onError: fail,
  })

  const open = ['PLANNED', 'CONFIRMED', 'IN_PROGRESS'].includes(event.status)
  const canSend = ['CONFIRMED', 'IN_PROGRESS'].includes(event.status)
  const lines = menu?.lines ?? []
  const unsent = lines.filter(l => !l.sent)
  const short = (menu?.stock.items ?? []).filter(i => Number(i.short) > 0)
  const chosen = dishes.find(d => d.id === dishId)

  return (
    <section className="space-y-3 pt-3 border-t border-white/5">
      <h3 className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary">Menu &amp; bill</h3>

      {lines.length === 0 && <p className="text-xs text-ink-tertiary">No dishes planned yet.</p>}
      {lines.map(l => (
        <div key={l.id} className="flex items-start justify-between gap-2 text-sm">
          <span className="text-ink-secondary min-w-0">
            {l.quantity} × {l.name} · {ksh(l.charged_per_unit)}
            {Number(l.discount_per_unit) > 0 && (
              <span className="text-ink-tertiary"> (menu {ksh(l.menu_price)}, −{ksh(l.discount_per_unit)}: {l.discount_reason})</span>
            )}
            <span className="text-ink-primary"> = {ksh(l.line_total)}</span>
          </span>
          {l.sent
            ? <span className="text-xs text-ink-tertiary shrink-0">Sent</span>
            : <button className="text-xs text-ink-tertiary hover:text-status-failed shrink-0"
                onClick={() => remove.mutate(l.id)}>Remove</button>}
        </div>
      ))}

      {open && (
        <div className="grid grid-cols-2 gap-2">
          <Select label="Dish or drink" value={dishId} onChange={e => setDishId(e.target.value)}
            options={[{ value: '', label: 'Pick one' },
                      ...dishes.map(d => ({ value: d.id, label: `${d.name} · ${ksh(d.price)}` }))]} />
          <Input label="Plates" value={plates} inputMode="numeric" placeholder="150"
            onChange={e => setPlates(e.target.value)} />
          <Input label="Discount per plate (KSh)" value={discount} inputMode="decimal" placeholder="0"
            onChange={e => setDiscount(e.target.value)} />
          <Input label="Why the discount" value={reason} placeholder="e.g. package deal"
            disabled={!Number(discount)} onChange={e => setReason(e.target.value)} />
          <Button className="col-span-2" disabled={!dishId || !plates || add.isPending}
            onClick={() => add.mutate()}>
            Add{chosen && plates ? ` ${plates} × ${chosen.name}` : ''}
          </Button>
        </div>
      )}

      {lines.length > 0 && menu && (
        <div className="grid grid-cols-3 gap-2 text-center">
          {([['Menu value', menu.totals.menu_value], ['Discount', menu.totals.discount],
             ['To charge', menu.totals.to_charge]] as const).map(([label, v]) => (
            <div key={label} className="rounded-lg bg-white/5 p-2">
              <p className="text-[10px] uppercase tracking-widest text-ink-tertiary">{label}</p>
              <p className="text-sm font-semibold tabular-nums text-ink-primary">{ksh(v)}</p>
            </div>
          ))}
        </div>
      )}

      {unsent.length > 0 && menu && (
        menu.stock.ready
          ? <p className="text-xs text-status-paid">The store covers everything planned.</p>
          : (
            <div className="space-y-1">
              <p className="text-xs text-status-failed">
                Short: {short.map(i => `${qty(i.short)} ${i.unit} ${i.name}`).join(', ')}
              </p>
              <Button size="sm" variant="ghost" disabled={buyList.isPending} onClick={() => buyList.mutate()}>
                Put these on purchase requests
              </Button>
            </div>
          )
      )}

      {canSend && unsent.length > 0 && (
        <Button disabled={send.isPending} onClick={() => send.mutate()}>
          Send {unsent.length} to kitchen &amp; bar
        </Button>
      )}

      {bill && Number(bill.booking_fee.amount) > 0 && (
        <div className={`rounded-lg p-2 text-sm flex flex-col sm:flex-row sm:items-end gap-2 ${
          bill.booking_fee.settled ? 'bg-status-paid/10' : 'bg-status-pending/10'}`}>
          <p className="flex-1 text-ink-primary">
            Booking fee {ksh(bill.booking_fee.amount)} —{' '}
            {bill.booking_fee.settled
              ? <span className="text-status-paid">paid</span>
              : <span className="text-status-pending">not paid yet; confirming waits for it</span>}
          </p>
          {!bill.booking_fee.settled && open && (
            <>
              <Select label="Paid by" value={feeMethod} onChange={e => setFeeMethod(e.target.value)}
                options={[{ value: 'CASH', label: 'Cash' }, { value: 'MPESA', label: 'M-Pesa' },
                          { value: 'CARD', label: 'Card' }, { value: 'BANK_TRANSFER', label: 'Bank transfer' }]} />
              <Button disabled={takeFee.isPending} onClick={() => takeFee.mutate()}>Take booking fee</Button>
            </>
          )}
        </div>
      )}

      {bill?.tab_id ? (
        <div className="space-y-2">
          <div className="grid grid-cols-3 gap-2 text-center">
            {([['Billed', bill.charged], ['Paid', bill.paid], ['Owing', bill.owing]] as const).map(([label, v]) => (
              <div key={label} className="rounded-lg bg-white/5 p-2">
                <p className="text-[10px] uppercase tracking-widest text-ink-tertiary">{label}</p>
                <p className="text-sm font-semibold tabular-nums text-ink-primary">{ksh(v)}</p>
              </div>
            ))}
          </div>
          {/* What the bill is made of — the venue hire, every dish sent, every payment. */}
          <div className="space-y-0.5 text-xs">
            {(bill.lines ?? []).map((l, i) => (
              <div key={i} className="flex justify-between gap-2 text-ink-secondary">
                <span className="min-w-0 truncate">{l.description}</span>
                <span className="tabular-nums shrink-0">{ksh(l.amount)}</span>
              </div>
            ))}
            {(bill.payments ?? []).map((p, i) => (
              <div key={`p${i}`} className="flex justify-between gap-2 text-status-paid">
                <span>Paid · {p.method.replace('_', ' ').toLowerCase()}</span>
                <span className="tabular-nums">−{ksh(p.amount)}</span>
              </div>
            ))}
          </div>
          {Number(bill.owing) > 0 && (
            <div className="flex flex-col sm:flex-row gap-2">
              <Select label="Paid by" value={payMethod} onChange={e => setPayMethod(e.target.value)}
                options={[{ value: 'CASH', label: 'Cash' }, { value: 'MPESA', label: 'M-Pesa' },
                          { value: 'CARD', label: 'Card' }, { value: 'BANK_TRANSFER', label: 'Bank transfer' }]} />
              <Input label="Amount (KSh)" value={payAmount} inputMode="decimal"
                onChange={e => setPayAmount(e.target.value)} />
              <Button className="sm:self-end" disabled={!Number(payAmount) || pay.isPending}
                onClick={() => pay.mutate()}>Take payment</Button>
            </div>
          )}
        </div>
      ) : (
        <p className="text-xs text-ink-tertiary">The bill opens when the event is confirmed.</p>
      )}
    </section>
  )
}

// ── EventCard ──────────────────────────────────────────────────────────────

function EventCard({ event, isToday = false }: { event: EventItem; isToday?: boolean }) {
  const [running, setRunning] = useState(false)
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

      {/* The door to everything the screen could not previously do. Manager+
          only, matching the API — every endpoint behind it is MANAGER_LEVEL
          except acknowledging your own assignment. */}
      <IfRole minLevel={5}>
        <div className="pt-2 border-t border-white/5">
          <Button size="sm" variant="ghost" onClick={() => setRunning(true)}>
            Staff &amp; stock
          </Button>
        </div>
      </IfRole>

      <Drawer open={running} onClose={() => setRunning(false)} title={event.title}>
        <RunPanel event={event} onClose={() => setRunning(false)} />
      </Drawer>
    </div>
  )
}
