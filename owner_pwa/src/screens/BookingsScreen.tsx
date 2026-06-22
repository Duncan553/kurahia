import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Drawer, Button, StatusBadge, useToastStore, Skeleton, SearchInput } from '@shared'
import type { StatusValue } from '@shared'
import api from '../lib/axios'

// ── Types ─────────────────────────────────────────────────────────────────────

interface Booking {
  id: string
  resource_name: string | null
  guest_name: string
  guest_phone: string
  number_of_guests: number
  check_in_planned: string | null
  check_out_planned: string | null
  check_in_actual: string | null
  check_out_actual: string | null
  base_total: string
  deposit_required: string
  deposit_paid: string
  status: string
  notes: string | null
}

type StatusFilter = 'CONFIRMED' | 'CHECKED_IN' | 'COMPLETED' | 'CANCELLED' | ''

// ── Helpers ───────────────────────────────────────────────────────────────────

const extractErr = (e: unknown) =>
  (e as { response?: { data?: { error?: string } } })?.response?.data?.error ?? 'Something went wrong.'

const formatKsh = (v: string | number) => {
  const n = parseFloat(String(v))
  if (isNaN(n)) return 'KSh —'
  return `KSh ${n.toLocaleString('en-KE', { minimumFractionDigits: 0 })}`
}

const fmtDate = (iso: string | null) => {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleDateString('en-KE', { day: 'numeric', month: 'short', year: 'numeric' })
}

const fmtTime = (iso: string | null) => {
  if (!iso) return ''
  return new Date(iso).toLocaleTimeString('en-KE', { hour: '2-digit', minute: '2-digit' })
}

function bookingStatus(s: string): StatusValue {
  if (s === 'CONFIRMED') return 'confirmed'
  if (s === 'CHECKED_IN') return 'checked-in'
  if (s === 'COMPLETED' || s === 'CHECKED_OUT') return 'checked-out'
  if (s === 'CANCELLED') return 'cancelled'
  if (s === 'NO_SHOW') return 'no-show'
  return 'pending'
}

function depositStatus(paid: string, required: string) {
  const p = parseFloat(paid)
  const r = parseFloat(required)
  if (r === 0) return null
  if (p >= r) return <span className="text-status-paid font-medium">Deposit paid</span>
  return <span className="text-status-pending font-medium">Deposit: {formatKsh(paid)} / {formatKsh(required)}</span>
}

// ── Booking card ──────────────────────────────────────────────────────────────

function BookingCard({ booking, onSelect }: { booking: Booking; onSelect: () => void }) {
  return (
    <button
      onClick={onSelect}
      className="w-full text-left glass-card rounded-xl p-4
        hover:border-primary-light/50 hover:shadow-sm transition-all
        focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-main"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-white text-sm truncate">{booking.guest_name}</p>
          <p className="text-xs text-slate-300/70 mt-0.5">
            {booking.resource_name ?? 'Unknown resource'}
            {booking.number_of_guests > 1 && ` · ${booking.number_of_guests} guests`}
          </p>
        </div>
        <StatusBadge status={bookingStatus(booking.status)} />
      </div>

      <div className="mt-2 text-xs text-slate-300/70 space-y-0.5">
        <p>
          Check-in: <span className="font-medium text-white">
            {fmtDate(booking.check_in_planned)} {fmtTime(booking.check_in_planned)}
          </span>
        </p>
        {booking.base_total !== '0.00' && (
          <p>Total: <span className="font-medium tabular-nums">{formatKsh(booking.base_total)}</span></p>
        )}
        <p className="text-xs">{depositStatus(booking.deposit_paid, booking.deposit_required)}</p>
      </div>
    </button>
  )
}

// ── Detail drawer ─────────────────────────────────────────────────────────────

function BookingDrawer({
  booking, onClose,
}: {
  booking: Booking; onClose: () => void
}) {
  const qc = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  const [confirmCancel, setConfirmCancel] = useState(false)

  const cancelMut = useMutation({
    mutationFn: () => api.post(`/bookings/${booking.id}/cancel`, {
      idempotency_key: crypto.randomUUID(),
      reason: 'Owner override',
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['bookings'] })
      addToast({ type: 'success', message: 'Booking cancelled.' })
      onClose()
    },
    onError: e => addToast({ type: 'error', message: extractErr(e) }),
  })

  const canCancel = ['CONFIRMED', 'PENDING'].includes(booking.status)

  return (
    <div className="space-y-5">
      {/* Guest info */}
      <div className="rounded-xl bg-white/5 p-4 space-y-2">
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="font-semibold text-white text-base">{booking.guest_name}</p>
            <p className="text-xs text-slate-300/70">{booking.guest_phone}</p>
          </div>
          <StatusBadge status={bookingStatus(booking.status)} />
        </div>
      </div>

      {/* Details */}
      <div className="space-y-3 text-sm">
        <div className="rounded-xl border border-white/10 bg-transparent px-4 py-3 space-y-2">
          {[
            ['Resource', booking.resource_name ?? '—'],
            ['Guests', String(booking.number_of_guests)],
            ['Check-in', `${fmtDate(booking.check_in_planned)} ${fmtTime(booking.check_in_planned)}`],
            ['Check-out', `${fmtDate(booking.check_out_planned)} ${fmtTime(booking.check_out_planned)}`],
            ['Base total', formatKsh(booking.base_total)],
            ['Deposit required', formatKsh(booking.deposit_required)],
            ['Deposit paid', formatKsh(booking.deposit_paid)],
          ].map(([label, value]) => (
            <div key={label} className="flex justify-between gap-2">
              <span className="text-slate-300/70 text-xs">{label}</span>
              <span className="font-medium text-white text-xs tabular-nums text-right">{value}</span>
            </div>
          ))}
          {booking.check_in_actual && (
            <div className="flex justify-between gap-2">
              <span className="text-slate-300/70 text-xs">Actual check-in</span>
              <span className="font-medium text-status-paid text-xs">{fmtDate(booking.check_in_actual)} {fmtTime(booking.check_in_actual)}</span>
            </div>
          )}
          {booking.notes && (
            <div>
              <p className="text-xs text-slate-300/70">Notes</p>
              <p className="text-xs text-white mt-0.5 italic">"{booking.notes}"</p>
            </div>
          )}
        </div>
      </div>

      {/* Cancel action */}
      {canCancel && (
        <div className="space-y-2">
          {!confirmCancel ? (
            <Button
              variant="ghost"
              className="w-full text-status-failed"
              onClick={() => setConfirmCancel(true)}
            >
              Cancel Booking (Owner Override)
            </Button>
          ) : (
            <>
              <p className="text-sm text-status-failed font-medium text-center">Cancel this booking?</p>
              <Button
                variant="danger"
                className="w-full"
                disabled={cancelMut.isPending}
                onClick={() => cancelMut.mutate()}
              >
                {cancelMut.isPending ? 'Cancelling…' : 'Yes, cancel booking'}
              </Button>
              <Button
                variant="ghost"
                className="w-full"
                disabled={cancelMut.isPending}
                onClick={() => setConfirmCancel(false)}
              >
                Keep booking
              </Button>
            </>
          )}
        </div>
      )}

      {!canCancel && (
        <p className="text-xs text-slate-400/50 text-center">
          This booking is {booking.status.toLowerCase()} — cannot be cancelled.
        </p>
      )}
    </div>
  )
}

// ── Main screen ───────────────────────────────────────────────────────────────

const STATUS_TABS: { key: StatusFilter; label: string }[] = [
  { key: 'CONFIRMED',  label: 'Confirmed'  },
  { key: 'CHECKED_IN', label: 'In House'   },
  { key: 'COMPLETED',  label: 'Completed'  },
  { key: '',           label: 'All'        },
]

export default function BookingsScreen() {
  const [searchQ, setSearchQ] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('CONFIRMED')
  const [dateFilter, setDateFilter] = useState('')
  const [selected, setSelected] = useState<Booking | null>(null)

  const params = new URLSearchParams()
  if (statusFilter) params.set('status', statusFilter)
  if (dateFilter)   params.set('date', dateFilter)
  if (searchQ)      params.set('q', searchQ)

  const { data, isLoading, isError } = useQuery<Booking[]>({
    queryKey: ['bookings', statusFilter, dateFilter, searchQ],
    queryFn: () => api.get<Booking[]>(`/bookings?${params}`).then(r => r.data),
    staleTime: 60_000,
  })

  return (
    <div className="p-4 max-w-3xl mx-auto">
      <div className="mb-5">
        <h1 className="text-2xl font-bold text-white font-serif">Bookings</h1>
        <p className="text-xs text-white/30 mt-0.5">Villa & event bookings, deposits, check-in</p>
      </div>

      {/* Filters */}
      <div className="space-y-3 mb-4">
        {/* Status tabs */}
        <div className="flex gap-1 bg-white/5 rounded-xl p-1 overflow-x-auto scrollbar-none" role="tablist">
          {STATUS_TABS.map(t => (
            <button
              key={t.key}
              role="tab"
              aria-selected={statusFilter === t.key}
              onClick={() => setStatusFilter(t.key)}
              className={[
                'shrink-0 flex-1 py-2 rounded-lg text-xs font-semibold transition-colors whitespace-nowrap px-2',
                statusFilter === t.key ? 'bg-transparent text-white shadow-sm' : 'text-slate-300/70 hover:text-white',
              ].join(' ')}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Date filter */}
        <div className="flex items-center gap-2">
          <label htmlFor="booking-date" className="text-xs text-slate-300/70 shrink-0">Check-in date:</label>
          <input
            id="booking-date"
            type="date"
            value={dateFilter}
            onChange={e => setDateFilter(e.target.value)}
            className="flex-1 text-xs border border-white/10 bg-transparent rounded-lg px-2 py-1.5
              text-white focus:outline-none focus:ring-2 focus:ring-primary-main"
          />
          {dateFilter && (
            <button onClick={() => setDateFilter('')}
              className="text-xs text-slate-400/50 hover:text-white">
              Clear
            </button>
          )}
        </div>
      </div>

      <SearchInput value={searchQ} onChange={setSearchQ} placeholder="Search bookings..." label="Search bookings" />

      {searchQ && (data ?? []).length === 0 && !isLoading && (
        <p className="text-sm text-slate-400/50 text-center py-8">No results for &lsquo;{searchQ}&rsquo; &middot; Hakuna kitu</p>
      )}

      {/* List */}
      {isLoading && (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="rounded-xl border border-white/10 bg-transparent p-4 space-y-2">
              <div className="flex justify-between">
                <Skeleton variant="text" className="w-36 h-4" />
                <Skeleton variant="text" className="w-20 h-5 rounded-full" />
              </div>
              <Skeleton variant="text" className="w-48 h-3" />
              <Skeleton variant="text" className="w-32 h-3" />
            </div>
          ))}
        </div>
      )}

      {isError && (
        <div className="rounded-xl border border-status-failed/30 bg-status-failed/5 p-4 text-center">
          <p className="text-sm text-status-failed">Couldn't load bookings.</p>
        </div>
      )}

      {!isLoading && !isError && (data ?? []).length === 0 && (
        <div className="py-12 text-center">
          <p className="text-slate-300/70 text-sm">
            {dateFilter ? `No ${statusFilter || 'bookings'} on ${dateFilter}` : `No ${statusFilter.toLowerCase() || 'bookings'}`}
          </p>
        </div>
      )}

      {!isLoading && !isError && (data ?? []).length > 0 && (
        <div className="space-y-2">
          {(data ?? []).map(b => (
            <BookingCard key={b.id} booking={b} onSelect={() => setSelected(b)} />
          ))}
        </div>
      )}

      {/* Detail drawer */}
      <Drawer open={selected !== null} onClose={() => setSelected(null)} title={selected?.guest_name ?? ''}>
        {selected && (
          <BookingDrawer booking={selected} onClose={() => setSelected(null)} />
        )}
      </Drawer>
    </div>
  )
}
