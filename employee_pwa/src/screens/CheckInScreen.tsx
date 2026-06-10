import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Skeleton, EmptyState, Modal, useToastStore } from '@shared'
import api from '../lib/axios'
import { RequireRole } from '../components/AuthGate'

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
      <div className="h-1 rounded-full bg-cream-alt overflow-hidden">
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
  const [tab,       setTab]       = useState<Tab>('arrivals')
  const [errorOpen, setErrorOpen] = useState(false)
  const [errorMsg,  setErrorMsg]  = useState('')

  const { data, isLoading, isError, refetch } = useQuery<FrontDeskData>({
    queryKey: ['front-desk-today'],
    queryFn: () => api.get<FrontDeskData>('/front-desk/today').then((r) => r.data),
  })

  const pendingIds = new Set((data?.pending_waivers ?? []).map((w) => w.booking_id))

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
            <div key={i} className="rounded-2xl bg-cream-alt/40 p-4 space-y-2">
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
      <div className="p-4 max-w-md mx-auto space-y-4">

        {/* ── Header ───────────────────────────────────────────────── */}
        <div>
          <h1 className="text-xl font-bold text-ink-primary">Front Desk</h1>
          <p className="text-sm text-ink-tertiary">{data?.date ?? 'Today'}</p>
        </div>

        {/* ── Tab bar ──────────────────────────────────────────────── */}
        <div className="flex gap-1 bg-cream-alt/50 rounded-xl p-1">
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
                    ? 'bg-cream-card shadow-sm text-ink-primary'
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
                    className="rounded-2xl bg-cream-alt/30 border border-cream-alt p-4">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="font-semibold text-ink-primary truncate">{a.guest_name}</p>
                        <p className="text-xs text-ink-tertiary">{a.resource ?? 'No resource'}</p>
                      </div>
                      <button
                        onClick={() => checkInMutation.mutate(a.booking_id)}
                        disabled={waiverBlocked || checkInMutation.isPending}
                        className={[
                          'shrink-0 px-4 py-2 rounded-xl text-sm font-semibold transition-all',
                          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark',
                          waiverBlocked
                            ? 'bg-cream-alt text-ink-tertiary cursor-not-allowed'
                            : 'bg-primary-dark text-cream-card hover:bg-primary-dark/90 active:scale-[0.98]',
                          'disabled:opacity-60',
                        ].join(' ')}
                      >
                        {checkInMutation.isPending ? '…' : 'Check In'}
                      </button>
                    </div>
                    {waiverBlocked && (
                      <p className="mt-2 text-xs text-status-failed flex items-center gap-1.5">
                        <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
                          <circle cx="6" cy="6" r="5"/>
                        </svg>
                        Waiver required before check-in
                      </p>
                    )}
                    <DepositBar paid={a.deposit_paid} required={a.deposit_required} />
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
                    className="rounded-2xl bg-cream-alt/30 border border-cream-alt p-4">
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
            <div className="space-y-2">
              {occupancy.map((o) => (
                <div key={o.booking_id}
                  className="flex items-center justify-between
                    rounded-xl bg-cream-alt/30 border border-cream-alt px-4 py-3">
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
      <Modal open={errorOpen} onClose={() => setErrorOpen(false)} title="Action failed">
        <p className="text-base text-ink-secondary mb-6">{errorMsg}</p>
        <button
          onClick={() => setErrorOpen(false)}
          className="w-full py-3 rounded-xl bg-cream-alt text-ink-primary font-medium
            hover:bg-cream-alt/70 transition-colors"
        >
          OK
        </button>
      </Modal>
    </RequireRole>
  )
}
