import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Skeleton, EmptyState, Modal, Button, Input, Select, FormField, useToastStore, ErrorBoundary, PaymentRef } from '@shared'
import api from '../lib/axios'
import { RequireRole } from '../components/AuthGate'
import { useAuthStore } from '../stores/authStore'

interface Arrival {
  booking_id: string
  guest_name: string
  resource: string | null
  status: string
  deposit_paid: string
  deposit_required: string
}

interface Departure {
  booking_id: string
  guest_name: string
  resource: string | null
  tab_id: string | null
  tab_balance: string
}

interface Occupant {
  booking_id: string
  guest_name: string
  resource: string | null
  tab_id: string | null
  tab_balance: string
}

interface PendingWaiver {
  booking_id: string
  guest_name: string
  resource: string
  check_in: string
}

interface FrontDeskData {
  date: string
  arrivals: Arrival[]
  departures: Departure[]
  occupancy: Occupant[]
  pending_waivers: PendingWaiver[]
}

type Tab = 'arrivals' | 'departures' | 'occupancy' | 'rooms'

// Room readiness, read-only, on the screen where the decision is made.
// "Which villa can I give this guest?" is asked at the desk with the guest
// standing there, and the answer lived on a tablet in another department. The
// desk either walked over or guessed — and a guess walks a guest to a room
// that has not been cleaned. GET /housekeeping/status now admits front desk;
// starting and completing a clean stay with the people who do the cleaning.
interface CleaningRow {
  // Null for a villa that has never been cleaned — /housekeeping/status returns
  // a placeholder row so the villa still appears. There is no record to act on
  // until one exists, which is why the key and the buttons both guard on it.
  id: string | null
  resource_name: string | null
  status: 'DIRTY' | 'CLEANING' | 'CLEAN' | 'INSPECTED' | string
  assigned_to_name?: string | null
  cleaners?: string[]
  updated_at?: string | null
}

const ROOM_STATE: Record<string, { label: string; tone: string }> = {
  INSPECTED: { label: 'Ready',        tone: 'var(--color-leaf-green)' },
  CLEAN:     { label: 'Clean',        tone: 'var(--color-leaf-green)' },
  CLEANING:  { label: 'Being cleaned', tone: 'var(--color-tea-brown)' },
  DIRTY:     { label: 'Not cleaned',  tone: 'var(--color-stamp-red)' },
}

function DepositBar({ paid, required }: { paid: string; required: string }) {
  const p = parseFloat(paid)
  const r = parseFloat(required)
  const pct = r > 0 ? Math.min(100, Math.round((p / r) * 100)) : 0
  const full = pct >= 100
  return (
    <div className="mt-1.5">
      <div className="flex justify-between text-[10px] text-ink-tertiary mb-0.5">
        <span>Deposit</span>
        <span className="tabular-nums">KSh {p.toLocaleString()} / {r.toLocaleString()}</span>
      </div>
      <div className="h-1 rounded-full bg-white/5 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${full ? 'bg-status-paid' : 'bg-primary-main'}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

export default function CheckInScreen() {
  const queryClient = useQueryClient()
  const addToast    = useToastStore((s) => s.addToast)
  const navigate    = useNavigate()
  const user        = useAuthStore((s) => s.user)
  const [tab,       setTab]       = useState<Tab>('arrivals')
  // Deposit capture. Recording a deposit had NO UI anywhere in any of the three
  // apps, so confirm always failed with "A deposit of X is required to confirm"
  // and no booking could ever reach CHECKED_IN. POST /booking-payments existed the whole
  // time (app/bookings/deposits.py).
  const [depositFor, setDepositFor] = useState<Arrival | null>(null)
  const [depositAmt, setDepositAmt] = useState('')
  const [depositMethod, setDepositMethod] = useState('CASH')
  const [depositRef, setDepositRef] = useState('')
  // The guest register. Booking holds ONE name plus number_of_guests as an
  // integer, so everyone else in the villa was part of a number. This is where
  // they get names — and where charging rights are granted deliberately rather
  // than by being in the room.
  const [guestsFor, setGuestsFor] = useState<Occupant | null>(null)
  const [newName, setNewName] = useState('')
  const [newId, setNewId] = useState('')

  const [errorOpen, setErrorOpen] = useState(false)
  const [errorMsg,  setErrorMsg]  = useState('')

  const { data, isLoading, isError, refetch } = useQuery<FrontDeskData>({
    queryKey: ['front-desk-today'],
    queryFn: () => api.get<FrontDeskData>('/front-desk/today').then((r) => r.data),
    refetchInterval: 60_000,
  })

  const pendingIds = new Set((data?.pending_waivers ?? []).map((w) => w.booking_id))

  const { data: register } = useQuery<{
    lead_guest: string; lead_id_number: string | null; number_of_guests: number
    unnamed_count: number
    occupants: { id: string; full_name: string; id_number: string | null; may_charge: boolean }[]
  }>({
    queryKey: ['occupants', guestsFor?.booking_id],
    queryFn: () => api.get(`/bookings/${guestsFor!.booking_id}/occupants`).then(r => r.data),
    enabled: !!guestsFor,
  })

  const addOccupant = useMutation({
    mutationFn: () => api.post(`/bookings/${guestsFor!.booking_id}/occupants`, {
      full_name: newName.trim(),
      id_number: newId.trim() || null,
    }),
    onSuccess: () => {
      addToast({ type: 'success', message: 'Added to the register.' })
      setNewName(''); setNewId('')
      queryClient.invalidateQueries({ queryKey: ['occupants', guestsFor?.booking_id] })
    },
    onError: (e: unknown) => {
      const msg = (e as { response?: { data?: { error?: string } } })?.response?.data?.error
      addToast({ type: 'error', message: msg ?? 'Could not add that person.' })
    },
  })

  const setMayCharge = useMutation({
    mutationFn: (v: { id: string; may_charge: boolean }) =>
      api.patch(`/bookings/${guestsFor!.booking_id}/occupants/${v.id}`, { may_charge: v.may_charge }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['occupants', guestsFor?.booking_id] }),
  })

  /**
   * HELD -> CONFIRMED. This step had NO caller anywhere in any of the three
   * PWAs, which made front desk a dead end: a villa booking made through the
   * app's own /villa screen lands HELD, VALID_BOOKING_TRANSITIONS
   * (app/models/booking.py) only allows CHECKED_IN from CONFIRMED, and the only
   * button offered here was "Check In" — so the backend correctly refused with
   * "Cannot move booking from HELD to CHECKED_IN" and there was no way forward.
   * POST /bookings/<id>/confirm existed the whole time (app/bookings/core.py).
   */
  const depositMutation = useMutation({
    mutationFn: (v: { bookingId: string; amount: string; method: string; ref: string }) =>
      api.post('/booking-payments', {
        booking_id: v.bookingId,
        purpose: 'DEPOSIT',
        method: v.method,
        amount: v.amount,
        // deposits.py has always read mpesa_code off this payload; nothing
        // ever put one in it, so a deposit could not be matched at close of day.
        ...(v.method === 'MPESA' && v.ref.trim() ? { mpesa_code: v.ref.trim() } : {}),
        ...(v.method === 'CARD'  && v.ref.trim() ? { card_ref:   v.ref.trim() } : {}),
        idempotency_key: crypto.randomUUID(),
      }).then((r) => r.data),
    onSuccess: () => {
      addToast({ type: 'success', message: 'Deposit recorded.' })
      setDepositFor(null)
      setDepositAmt('')
      setDepositRef('')
      queryClient.invalidateQueries({ queryKey: ['front-desk-today'] })
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
        ?? 'Could not record the deposit. Try again.'
      setErrorMsg(msg)
      setErrorOpen(true)
    },
  })

  const confirmMutation = useMutation({
    mutationFn: (bookingId: string) =>
      api.post(`/bookings/${bookingId}/confirm`).then((r) => r.data),
    onSuccess: (_, bookingId) => {
      const guest = data?.arrivals.find((a) => a.booking_id === bookingId)?.guest_name ?? 'Guest'
      addToast({ type: 'success', message: `${guest}'s booking confirmed. Ready to check in.` })
      queryClient.invalidateQueries({ queryKey: ['front-desk-today'] })
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
        ?? 'Could not confirm the booking. Try again.'
      setErrorMsg(msg)
      setErrorOpen(true)
    },
  })

  const checkInMutation = useMutation({
    mutationFn: (bookingId: string) =>
      api.post(`/bookings/${bookingId}/check-in`).then((r) => r.data),
    onSuccess: (_, bookingId) => {
      const guest = data?.arrivals.find((a) => a.booking_id === bookingId)?.guest_name ?? 'Guest'
      addToast({ type: 'success', message: `${guest} checked in. Villa tab opened.` })
      queryClient.invalidateQueries({ queryKey: ['front-desk-today'] })
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
        ?? 'Check-in failed. Try again.'
      setErrorMsg(msg)
      setErrorOpen(true)
    },
  })

  const checkOutMutation = useMutation({
    mutationFn: (bookingId: string) =>
      api.post(`/bookings/${bookingId}/check-out`).then((r) => r.data),
    onSuccess: (_, bookingId) => {
      const guest = data?.departures.find((d) => d.booking_id === bookingId)?.guest_name ?? 'Guest'
      addToast({ type: 'success', message: `${guest} checked out. Tab closed.` })
      queryClient.invalidateQueries({ queryKey: ['front-desk-today'] })
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { error?: string; outstanding_balance?: string } } })
        ?.response?.data
      setErrorMsg(msg?.error ?? 'Check-out failed. Ensure tab balance is cleared.')
      setErrorOpen(true)
    },
  })

  // These four hooks sit ABOVE the loading and error guards on purpose. Placed
  // after them, React ran fewer hooks on the first (loading) render than on the
  // second and threw "Rendered more hooks than during the previous render",
  // blanking the whole screen. Rules of hooks: same calls, same order, every
  // render — early returns are what make that easy to break.
  // Only fetched when the tab is open — the desk does not need it to check
  // somebody in, and a 403 here must never break the rest of the screen.
  const { data: rooms = [], isError: roomsError } = useQuery<CleaningRow[]>({
    queryKey: ['front-desk-rooms'],
    queryFn: () => api.get<CleaningRow[]>('/housekeeping/status').then(r => r.data),
    enabled: tab === 'rooms',
    staleTime: 30_000,
  })

  // Housekeepers to name. The desk records the work; the RECORD still says who
  // did it, otherwise the audit row reads as though a receptionist cleaned six
  // villas single-handed.
  const { data: keepers = [] } = useQuery<{ id: string; username: string; department: string | null }[]>({
    queryKey: ['housekeepers'],
    queryFn: () => api.get<{ id: string; username: string; department: string | null }[]>('/auth/users')
      .then(r => r.data.filter(u => (u.department ?? '').toLowerCase().includes('housekeep'))),
    enabled: tab === 'rooms',
    staleTime: 5 * 60_000,
  })

  // A villa is usually cleaned by two, so this holds a LIST per room rather
  // than one name. Chips beat a multi-select on a tablet: every option is one
  // tap, and who is selected is readable without opening anything.
  const [keeperFor, setKeeperFor] = useState<Record<string, string[]>>({})
  const toggleKeeper = (roomId: string, userId: string) =>
    setKeeperFor((k) => {
      const cur = k[roomId] ?? []
      return { ...k, [roomId]: cur.includes(userId) ? cur.filter(x => x !== userId) : [...cur, userId] }
    })

  const roomAct = useMutation({
    mutationFn: async (v: { rec: CleaningRow; action: 'start' | 'complete' | 'inspect' }) => {
      // Naming the cleaner happens first, so START carries the attribution
      // rather than leaving it on whoever tapped the button.
      // First name picked is the LEAD — the one accountable for the room —
      // and the rest ride along in housekeeper_ids.
      const chosen = v.rec.id ? (keeperFor[v.rec.id] ?? []) : []
      if (v.action === 'start' && chosen.length && !v.rec.assigned_to_name) {
        await api.post('/housekeeping/assign', {
          cleaning_id: v.rec.id,
          housekeeper_id: chosen[0],
          housekeeper_ids: chosen.slice(1),
        })
      }
      return api.post(`/housekeeping/${v.rec.id}/${v.action}`)
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['front-desk-rooms'] }),
    onError: (e) => addToast({ type: 'error',
      message: (e as { response?: { data?: { error?: string } } })?.response?.data?.error
        ?? 'Could not update the room.' }),
  })

  // ── LOADING ───────────────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <RequireRole minLevel={3}>
        <div className="p-4 space-y-3">
          {[1,2,3].map((i) => (
            <div key={i} className="rounded-2xl bg-white/5 p-4 space-y-2">
              <Skeleton variant="text" className="w-48" />
              <Skeleton variant="text" className="w-32" />
              <Skeleton variant="badge" className="h-1 w-full" />
            </div>
          ))}
        </div>
      </RequireRole>
    )
  }

  // ── ERROR ─────────────────────────────────────────────────────────────────
  if (isError) {
    return (
      <RequireRole minLevel={3}>
        <div className="flex flex-col items-center justify-center min-h-[50vh] p-6">
          <EmptyState
            icon={<svg width="48" height="48" viewBox="0 0 48 48" fill="none" aria-hidden="true">
              <circle cx="24" cy="24" r="20" stroke="currentColor" strokeWidth="2"/>
              <path d="M24 14v12M24 32v2" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"/>
            </svg>}
            title="Couldn't load today's data."
            description="Check your connection and retry."
            actionLabel="Retry"
            onAction={() => refetch()}
          />
        </div>
      </RequireRole>
    )
  }

  const arrivals   = data?.arrivals   ?? []
  const departures = data?.departures ?? []
  const occupancy  = data?.occupancy  ?? []

  return (
    <RequireRole minLevel={3}>
      <ErrorBoundary level="tile">
      <div className="p-4 max-w-6xl mx-auto space-y-6">

        {/* ── Header ───────────────────────────────────────────────── */}
        <div>
          <div className="flex items-start justify-between gap-3">
            <h1 className="text-2xl font-bold text-ink-primary font-serif">Front House</h1>
            {/* Where front desk adds a guest. Until now the only booking form
                lived on the villa/housekeeping screen. */}
            <button onClick={() => navigate('/front-desk/new-booking')}
              className="shrink-0 px-4 py-2 rounded-xl text-sm font-semibold
                bg-primary-main text-white hover:opacity-90 active:scale-[0.98]
                transition-all focus-visible:outline-none focus-visible:ring-2
                focus-visible:ring-primary-dark">
              + New booking
            </button>
          </div>
          <p className="text-xs text-ink-tertiary mt-0.5">Booking check-in and admission</p>
        </div>

        {/* ── Tab bar ──────────────────────────────────────────────── */}
        <div className="flex gap-1 bg-white/6 rounded-xl p-1">
          {(['arrivals', 'departures', 'occupancy', 'rooms'] as Tab[]).map((t) => {
            const count = t === 'arrivals' ? arrivals.length
              : t === 'departures' ? departures.length
              : t === 'rooms' ? rooms.filter(r => r.status === 'DIRTY').length
              : occupancy.length
            return (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={[
                  'flex-1 py-2 min-h-[44px] rounded-lg text-xs font-medium capitalize transition-all',
                  tab === t
                    ? 'bg-transparent shadow-sm text-ink-primary'
                    : 'text-ink-tertiary hover:text-ink-secondary',
                ].join(' ')}
              >
                {t} {count > 0 && <span className="font-bold">({count})</span>}
              </button>
            )
          })}
        </div>

        {/* ── Arrivals ─────────────────────────────────────────────── */}
        {tab === 'arrivals' && (
          arrivals.length === 0 ? (
            <EmptyState
              icon={<svg width="48" height="48" viewBox="0 0 48 48" fill="none" aria-hidden="true">
                <rect x="12" y="14" width="24" height="26" rx="3" stroke="currentColor" strokeWidth="2"/>
                <path d="M20 14v-3a4 4 0 018 0v3" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                <path d="M18 26h12M18 32h8" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
              </svg>}
              title="No arrivals today."
              description="Floor is yours."
            />
          ) : (
            <div className="space-y-3">
              {arrivals.map((a) => {
                const waiverBlocked = pendingIds.has(a.booking_id)
                return (
                  <div key={a.booking_id}
                    className="rounded-2xl bg-white/4 glass-card p-4">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="font-semibold text-ink-primary truncate">{a.guest_name}</p>
                        <p className="text-xs text-ink-tertiary">{a.resource ?? 'No resource'}</p>
                      </div>
                      <button
                        onClick={() => (a.status === 'HELD'
                          ? confirmMutation.mutate(a.booking_id)
                          : checkInMutation.mutate(a.booking_id))}
                        disabled={waiverBlocked || checkInMutation.isPending || confirmMutation.isPending}
                        className={[
                          'shrink-0 px-4 py-2 rounded-xl text-sm font-semibold transition-all',
                          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark',
                          waiverBlocked
                            ? 'bg-white/5 text-ink-tertiary cursor-not-allowed'
                            : 'bg-primary-main text-white hover:bg-primary-dark active:scale-[0.98]',
                          'disabled:opacity-60',
                        ].join(' ')}
                      >
                        {/* A HELD booking must be confirmed first — the state
                            machine has no HELD -> CHECKED_IN edge. */}
                        {checkInMutation.isPending || confirmMutation.isPending
                          ? '…'
                          : a.status === 'HELD' ? 'Confirm' : 'Check In'}
                      </button>
                    </div>
                    {waiverBlocked && (
                      <div className="mt-2 space-y-2">
                        <p className="text-xs text-status-failed flex items-center gap-1.5">
                          <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
                            <circle cx="6" cy="6" r="5"/>
                          </svg>
                          Waiver required before check-in
                        </p>
                        <button
                          onClick={() => {
                            if (!user?.username) return
                            // Used to activateKiosk() then navigate to
                            // /kiosk/waiver/:bookingId — a route that exists in
                            // employee_pwa but NOT here. So the tablet locked
                            // itself into kiosk mode (PIN required to leave) and
                            // then rendered Not Found: staff were stranded on a
                            // dead screen they could not back out of.
                            // Goes to this app's own waiver form instead, with
                            // the booking already filled in.
                            navigate(`/gate/waiver?booking=${encodeURIComponent(a.booking_id)}`)
                          }}
                          className="w-full min-h-[44px] rounded-xl border border-primary-main
                            text-primary-dark text-sm font-semibold
                            hover:bg-primary-main/5 active:scale-[0.98] transition-all
                            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark"
                        >
                          Waiver Kiosk →
                        </button>
                      </div>
                    )}
                    <DepositBar paid={a.deposit_paid} required={a.deposit_required} />
                    {parseFloat(a.deposit_paid) < parseFloat(a.deposit_required) && (
                      <button
                        onClick={() => {
                          setDepositFor(a)
                          // Pre-fill the outstanding balance — the common case.
                          setDepositAmt(String(
                            Math.max(0, parseFloat(a.deposit_required) - parseFloat(a.deposit_paid))
                          ))
                        }}
                        className="mt-2 min-h-[44px] w-full rounded-xl px-4 py-2 text-sm font-semibold
                          glass-card text-ink-primary hover:border-primary-main
                          focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-main"
                      >
                        Record deposit
                      </button>
                    )}
                  </div>
                )
              })}
            </div>
          )
        )}

        {/* ── Departures ───────────────────────────────────────────── */}
        {tab === 'departures' && (
          departures.length === 0 ? (
            <EmptyState
              icon={<svg width="48" height="48" viewBox="0 0 48 48" fill="none" aria-hidden="true">
                <circle cx="24" cy="24" r="20" stroke="currentColor" strokeWidth="2"/>
                <path d="M16 24h16M24 16l8 8-8 8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>}
              title="No departures today."
            />
          ) : (
            <div className="space-y-3">
              {departures.map((d) => {
                const balance = parseFloat(d.tab_balance)
                const hasBalance = balance > 0
                return (
                  <div key={d.booking_id}
                    className="rounded-2xl bg-white/4 glass-card p-4">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="font-semibold text-ink-primary truncate">{d.guest_name}</p>
                        <p className="text-xs text-ink-tertiary">{d.resource ?? 'No resource'}</p>
                        {hasBalance && (
                          <p className="text-xs text-status-pending font-medium mt-0.5 tabular-nums">
                            Outstanding: KSh {balance.toLocaleString()}
                          </p>
                        )}
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                      {/* The bill, at the moment they ask for it. Check-out is
                          blocked while a balance stands, so front desk needs to
                          show the guest WHAT they owe, not just that they do. */}
                      {d.tab_id && (
                        <button
                          onClick={() => navigate(`/folio/${d.tab_id}`)}
                          className="shrink-0 px-3 py-2 rounded-xl text-sm font-semibold
                            text-primary-dark border border-primary-main/30
                            hover:bg-primary-main/5 active:scale-[0.98] transition-all
                            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark">
                          Bill
                        </button>
                      )}
                      <button
                        onClick={() => checkOutMutation.mutate(d.booking_id)}
                        disabled={checkOutMutation.isPending}
                        className={[
                          'shrink-0 px-4 py-2 rounded-xl text-sm font-semibold transition-all',
                          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ink-tertiary',
                          hasBalance
                            ? 'bg-status-pending/10 text-status-pending border border-status-pending/30'
                            : 'bg-ink-tertiary/10 text-ink-primary border border-ink-tertiary/20',
                          'hover:opacity-80 active:scale-[0.98] disabled:opacity-50',
                        ].join(' ')}
                      >
                        {checkOutMutation.isPending ? '…' : 'Check Out'}
                      </button>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )
        )}

        {/* ── Rooms — readiness, read-only ──────────────────────────── */}
        {tab === 'rooms' && (
          roomsError ? (
            <p className="text-sm text-ink-tertiary px-1 py-6">
              Room readiness is not available on this account.
            </p>
          ) : rooms.length === 0 ? (
            <p className="text-sm text-ink-tertiary px-1 py-6">
              No villas configured yet.
            </p>
          ) : (
            <div className="flex flex-col gap-2">
              {/* Not-cleaned first: the desk is looking for what it CANNOT
                  give out as much as for what it can. */}
              {[...rooms]
                .sort((a, b) => (a.status === 'DIRTY' ? -1 : 0) - (b.status === 'DIRTY' ? -1 : 0))
                .map((r) => {
                  const st = ROOM_STATE[r.status] ?? { label: r.status, tone: 'var(--color-ink-tertiary)' }
                  return (
                    // Keyed on the villa, not the record: three villas with no
                    // cleaning record all carried id=null, so React saw three
                    // children with the same key and duplicated rows on every
                    // re-render — Villa 6 and Villa 14 each appeared twice.
                    <div key={r.id ?? `res-${r.resource_name}`}
                      className="flex items-center justify-between gap-3 px-4 py-3 rounded-xl glass-card">
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-ink-primary truncate">
                          {r.resource_name ?? 'Villa'}
                        </p>
                        {(r.cleaners?.length ? r.cleaners.join(' + ') : r.assigned_to_name) && (
                          <p className="text-xs text-ink-tertiary mt-0.5 truncate">
                            {r.cleaners?.length ? r.cleaners.join(' + ') : r.assigned_to_name}
                          </p>
                        )}
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        {r.id && r.status === 'DIRTY' && !r.assigned_to_name && keepers.length > 0 && (
                          <div className="flex flex-wrap gap-1 items-center">
                            <span className="text-[10px] uppercase tracking-wider text-ink-tertiary mr-1">
                              Cleaned by
                            </span>
                            {keepers.map(k => {
                              const on = !!(r.id && (keeperFor[r.id] ?? []).includes(k.id))
                              return (
                                <button key={k.id} type="button"
                                  aria-pressed={on}
                                  onClick={() => r.id && toggleKeeper(r.id, k.id)}
                                  className={`text-[11px] px-2 py-1 rounded-full border transition-colors ${
                                    on ? 'bg-primary-main text-white border-primary-main'
                                       : 'border-white/15 text-ink-tertiary hover:text-ink-secondary'}`}>
                                  {k.username}
                                </button>
                              )
                            })}
                          </div>
                        )}
                        {r.id && r.status === 'DIRTY' && (
                          <Button size="sm" variant="primary" loading={roomAct.isPending}
                            disabled={!r.assigned_to_name && !(r.id && (keeperFor[r.id] ?? []).length)}
                            onClick={() => roomAct.mutate({ rec: r, action: 'start' })}>
                            Start
                          </Button>
                        )}
                        {r.id && r.status === 'CLEANING' && (
                          <Button size="sm" variant="primary" loading={roomAct.isPending}
                            onClick={() => roomAct.mutate({ rec: r, action: 'complete' })}>
                            Done
                          </Button>
                        )}
                        {r.id && r.status === 'CLEAN' && (
                          <Button size="sm" variant="secondary" loading={roomAct.isPending}
                            onClick={() => roomAct.mutate({ rec: r, action: 'inspect' })}>
                            Ready for guest
                          </Button>
                        )}
                        <span className="text-xs font-semibold uppercase tracking-wider w-24 text-right"
                              style={{ color: st.tone }}>
                          {st.label}
                        </span>
                      </div>
                    </div>
                  )
                })}
              <p className="text-[11px] text-ink-tertiary px-1 pt-1">
                Name who cleaned it — the record keeps their name, not yours.
              </p>
            </div>
          )
        )}

        {/* ── Occupancy ─────────────────────────────────────────────── */}
        {tab === 'occupancy' && (
          occupancy.length === 0 ? (
            <EmptyState
              icon={<svg width="48" height="48" viewBox="0 0 48 48" fill="none" aria-hidden="true">
                <rect x="10" y="16" width="28" height="22" rx="3" stroke="currentColor" strokeWidth="2"/>
                <path d="M16 16v-4a8 8 0 0116 0v4" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
              </svg>}
              title="No guests currently checked in."
            />
          ) : (
            <div className="space-y-4">
              {occupancy.map((o) => (
                <div key={o.booking_id}
                  className="rounded-xl bg-white/4 glass-card px-4 py-3 flex flex-col gap-2">
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="font-medium text-ink-primary truncate">{o.guest_name}</p>
                      <p className="text-xs text-ink-tertiary">{o.resource ?? '—'}</p>
                    </div>
                    <span className="text-sm tabular-nums text-ink-secondary font-medium shrink-0">
                      KSh {parseFloat(o.tab_balance).toLocaleString()} on tab
                    </span>
                  </div>

                  {/* Occupancy is where a live guest IS. Departures only lists
                      bookings whose PLANNED checkout is today, so a guest
                      leaving early never showed up anywhere actionable. These
                      are the same three steps, on the row that always exists. */}
                  <div className="flex flex-wrap gap-2">
                    <button
                      onClick={() => setGuestsFor(o)}
                      className="px-3 py-1.5 rounded-lg text-xs font-semibold
                        text-ink-secondary border border-white/15
                        hover:text-ink-primary active:scale-[0.98] transition-all
                        focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ink-tertiary">
                      Who's staying
                    </button>
                    {o.tab_id && (
                      <button
                        onClick={() => navigate(`/folio/${o.tab_id}`)}
                        className="px-3 py-1.5 rounded-lg text-xs font-semibold
                          text-primary-dark border border-primary-main/30
                          hover:bg-primary-main/5 active:scale-[0.98] transition-all
                          focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark">
                        Bill &amp; pay
                      </button>
                    )}
                    <button
                      onClick={() => checkOutMutation.mutate(o.booking_id)}
                      disabled={checkOutMutation.isPending}
                      className="px-3 py-1.5 rounded-lg text-xs font-semibold
                        text-ink-primary border border-ink-tertiary/20
                        hover:opacity-80 active:scale-[0.98] disabled:opacity-50 transition-all
                        focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ink-tertiary">
                      Check out
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )
        )}

      </div>

      {/* ── Guest register ─────────────────────────────────────────── */}
      <Modal open={!!guestsFor} onClose={() => setGuestsFor(null)}
        title={`Who's staying — ${guestsFor?.resource ?? ''}`} size="sm">
        <div className="flex flex-col gap-4">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-wider text-ink-tertiary">Lead guest</p>
            <p className="text-sm font-semibold text-ink-primary">{register?.lead_guest}</p>
            <p className="text-xs text-ink-tertiary">
              {register?.lead_id_number ? `ID ${register.lead_id_number}` : 'No ID on file'}
              {' · liable for the bill'}
            </p>
          </div>

          {register && register.unnamed_count > 0 && (
            <div className="rounded-xl px-3 py-2 bg-status-pending/10 border border-status-pending/25">
              <p className="text-xs text-status-pending">
                Booked for {register.number_of_guests} — <strong>{register.unnamed_count} still
                unnamed</strong>. Anyone unnamed cannot be checked against this villa.
              </p>
            </div>
          )}

          {(register?.occupants ?? []).length > 0 && (
            <ul className="flex flex-col gap-2">
              {register!.occupants.map(o => (
                <li key={o.id} className="flex items-center justify-between gap-2
                  rounded-xl bg-white/4 px-3 py-2">
                  <div className="min-w-0">
                    <p className="text-sm text-ink-primary truncate">{o.full_name}</p>
                    <p className="text-[10px] text-ink-tertiary">
                      {o.id_number ? `ID ${o.id_number}` : 'no ID'}
                    </p>
                  </div>
                  {/* Charging rights are granted deliberately, never by being
                      listed — the lead guest is the one liable by default. */}
                  <label className="flex items-center gap-1.5 text-[11px] text-ink-secondary shrink-0">
                    <input type="checkbox" checked={o.may_charge}
                      onChange={e => setMayCharge.mutate({ id: o.id, may_charge: e.target.checked })}
                      className="w-4 h-4 accent-primary-main" />
                    may charge
                  </label>
                </li>
              ))}
            </ul>
          )}

          <form onSubmit={e => { e.preventDefault(); addOccupant.mutate() }}
            className="flex flex-col gap-2 pt-2 border-t border-white/10">
            <Input aria-label="Full name" placeholder="Full name"
              value={newName} onChange={e => setNewName(e.target.value)} />
            <Input aria-label="ID number" placeholder="ID number (optional)"
              value={newId} onChange={e => setNewId(e.target.value)} />
            <Button type="submit" disabled={!newName.trim()} loading={addOccupant.isPending}>
              Add to register
            </Button>
          </form>
        </div>
      </Modal>

      {/* ── Error modal ──────────────────────────────────────────────────── */}
      <Modal open={!!depositFor} onClose={() => setDepositFor(null)} title="Record deposit" size="sm">
        <div className="space-y-4">
          <p className="text-sm text-ink-secondary">
            {depositFor?.guest_name} — {depositFor?.resource ?? 'No resource'}
          </p>
          <FormField label="Amount (KSh)" htmlFor="deposit-amount" required>
            <Input
              id="deposit-amount"
              type="number"
              inputMode="decimal"
              min="1"
              value={depositAmt}
              onChange={(e) => setDepositAmt(e.target.value)}
            />
          </FormField>
          <FormField label="Method" htmlFor="deposit-method" required>
            <Select
              id="deposit-method"
              value={depositMethod}
              onChange={(e) => setDepositMethod(e.target.value)}
              options={[
                { value: 'CASH',          label: 'Cash' },
                { value: 'MPESA',         label: 'M-Pesa' },
                { value: 'CARD',          label: 'Card' },
              ]}
            />
          </FormField>
          <PaymentRef method={depositMethod} value={depositRef} onChange={setDepositRef} />
          <div className="flex gap-2 justify-end">
            <Button variant="ghost" size="sm" onClick={() => setDepositFor(null)}>Cancel</Button>
            <Button
              variant="primary" size="sm"
              loading={depositMutation.isPending}
              onClick={() => depositFor && depositMutation.mutate({
                bookingId: depositFor.booking_id,
                amount: depositAmt,
                method: depositMethod,
                ref: depositRef,
              })}
            >
              Record
            </Button>
          </div>
        </div>
      </Modal>

      <Modal open={errorOpen} onClose={() => setErrorOpen(false)} title="Action failed">
        <p className="text-base text-ink-secondary mb-6">{errorMsg}</p>
        <button
          onClick={() => setErrorOpen(false)}
          className="w-full py-3 rounded-xl bg-white/5 text-ink-primary font-medium
            hover:bg-white/10 transition-colors"
        >
          OK
        </button>
      </Modal>
      </ErrorBoundary>
    </RequireRole>
  )
}
