import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Skeleton, EmptyState, Modal, Button, Input, Select, FormField, useToastStore, ErrorBoundary } from '@shared'
import api from '../lib/axios'
import { RequireRole } from '../components/AuthGate'
import { useKioskStore } from '../stores/kioskStore'
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

type Tab = 'arrivals' | 'departures' | 'occupancy'

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
  const activateKiosk = useKioskStore((s) => s.activateKiosk)
  const [tab,       setTab]       = useState<Tab>('arrivals')
  // Deposit capture. Recording a deposit had NO UI anywhere in any of the three
  // apps, so confirm always failed with "A deposit of X is required to confirm"
  // and no booking could ever reach CHECKED_IN. POST /booking-payments existed the whole
  // time (app/bookings/deposits.py).
  const [depositFor, setDepositFor] = useState<Arrival | null>(null)
  const [depositAmt, setDepositAmt] = useState('')
  const [depositMethod, setDepositMethod] = useState('CASH')
  const [errorOpen, setErrorOpen] = useState(false)
  const [errorMsg,  setErrorMsg]  = useState('')

  const { data, isLoading, isError, refetch } = useQuery<FrontDeskData>({
    queryKey: ['front-desk-today'],
    queryFn: () => api.get<FrontDeskData>('/front-desk/today').then((r) => r.data),
    refetchInterval: 60_000,
  })

  const pendingIds = new Set((data?.pending_waivers ?? []).map((w) => w.booking_id))

  /**
   * HELD -> CONFIRMED. This step had NO caller in any of the three PWAs, which
   * made front desk a dead end: a villa booking made through the app's own
   * /villa screen lands HELD, VALID_BOOKING_TRANSITIONS
   * (app/models/booking.py) only allows CHECKED_IN from CONFIRMED, and the only
   * button offered here was "Check In" — so the backend correctly refused with
   * "Cannot move booking from HELD to CHECKED_IN" and there was no way forward.
   * POST /bookings/<id>/confirm existed the whole time (app/bookings/core.py).
   */
  const depositMutation = useMutation({
    mutationFn: (v: { bookingId: string; amount: string; method: string }) =>
      api.post('/booking-payments', {
        booking_id: v.bookingId,
        purpose: 'DEPOSIT',
        method: v.method,
        amount: v.amount,
        idempotency_key: crypto.randomUUID(),
      }).then((r) => r.data),
    onSuccess: () => {
      addToast({ type: 'success', message: 'Deposit recorded.' })
      setDepositFor(null)
      setDepositAmt('')
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
          <h1 className="text-2xl font-bold text-ink-primary font-serif">Front Desk</h1>
          <p className="text-xs text-ink-tertiary mt-0.5">Booking check-in and admission</p>
        </div>

        {/* ── Tab bar ──────────────────────────────────────────────── */}
        <div className="flex gap-1 bg-white/6 rounded-xl p-1">
          {(['arrivals', 'departures', 'occupancy'] as Tab[]).map((t) => {
            const count = t === 'arrivals' ? arrivals.length
              : t === 'departures' ? departures.length
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
                            activateKiosk(user.username)
                            navigate(`/kiosk/waiver/${a.booking_id}`)
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
                )
              })}
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
                  className="flex items-center justify-between
                    rounded-xl bg-white/4 glass-card px-4 py-3">
                  <div>
                    <p className="font-medium text-ink-primary">{o.guest_name}</p>
                    <p className="text-xs text-ink-tertiary">{o.resource ?? '—'}</p>
                  </div>
                  <span className="text-sm tabular-nums text-ink-secondary font-medium">
                    KSh {parseFloat(o.tab_balance).toLocaleString()} on tab
                  </span>
                </div>
              ))}
            </div>
          )
        )}

      </div>

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
                { value: 'BANK_TRANSFER', label: 'Bank transfer' },
              ]}
            />
          </FormField>
          <div className="flex gap-2 justify-end">
            <Button variant="ghost" size="sm" onClick={() => setDepositFor(null)}>Cancel</Button>
            <Button
              variant="primary" size="sm"
              loading={depositMutation.isPending}
              onClick={() => depositFor && depositMutation.mutate({
                bookingId: depositFor.booking_id,
                amount: depositAmt,
                method: depositMethod,
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
