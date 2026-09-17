import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Skeleton, EmptyState, Button, Input, useToastStore } from '@shared'
import api from '../lib/axios'

/**
 * Events — what every booked event is worth, as the owner needs to see it.
 *
 * The manager runs an event (its menu, its discounts, its bill). The owner sees
 * the result: menu value, what was given away and by whom, what was billed,
 * paid, and is still owed. The one thing the owner SETS here is how far a
 * manager may discount on their own — until it is set, nothing is delegated.
 */

interface EventRow {
  id: string
  title: string
  status: string
  starts_at: string
  expected_guests: number
  venue: { name: string; capacity: number | null } | null
  menu_value: string
  discount: string
  discount_by: string[]
  charged: string
  paid: string
  owing: string
}

const kes = (v: string | number) =>
  `KSh ${parseFloat(String(v)).toLocaleString('en-KE', { maximumFractionDigits: 0 })}`

const extractErr = (e: unknown) =>
  (e as { response?: { data?: { error?: string } } })?.response?.data?.error ?? 'Something went wrong.'

// One owner rule for events, saved to /admin/settings. Until the owner sets it,
// nothing is delegated / required.
function OwnerRule({ settingKey, title, hint, label, saved }: {
  settingKey: 'event_discount_max_percent' | 'event_min_booking_fee'
  title: string; hint: string; label: string; saved: (v: number) => string
}) {
  const qc = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  const { data } = useQuery<Record<string, string>>({
    queryKey: ['admin-settings'],
    queryFn: () => api.get('/admin/settings').then(r => r.data),
  })
  const [value, setValue] = useState('')
  useEffect(() => { if (data) setValue(data[settingKey]) }, [data, settingKey])

  const save = useMutation({
    mutationFn: () => api.patch('/admin/settings', { [settingKey]: Number(value) }),
    onSuccess: () => {
      addToast({ type: 'success', message: saved(Number(value)) })
      qc.invalidateQueries({ queryKey: ['admin-settings'] })
    },
    onError: e => addToast({ type: 'error', message: extractErr(e) }),
  })

  return (
    <div className="glass-card rounded-2xl p-4 flex flex-col sm:flex-row sm:items-end gap-3">
      <div className="flex-1">
        <p className="text-sm font-semibold text-ink-primary">{title}</p>
        <p className="text-xs text-ink-tertiary">{hint}</p>
      </div>
      <Input label={label} value={value} inputMode="numeric" onChange={e => setValue(e.target.value)} />
      <Button disabled={save.isPending || value === data?.[settingKey]} onClick={() => save.mutate()}>Save</Button>
    </div>
  )
}

export default function EventsScreen() {
  const { data: events = [], isLoading, isError } = useQuery<EventRow[]>({
    queryKey: ['dashboard-events'],
    queryFn: () => api.get<EventRow[]>('/dashboard/events').then(r => r.data),
    staleTime: 60_000,
  })

  return (
    <div className="p-4 md:p-6 max-w-5xl mx-auto space-y-4">
      <div>
        <h1 className="text-2xl font-serif font-bold text-ink-primary">Events</h1>
        <p className="text-sm text-ink-secondary">What each event is worth, what was discounted, and what is still owed.</p>
      </div>

      <OwnerRule settingKey="event_discount_max_percent" label="Limit (%)"
        title="How far a manager may discount"
        hint="Per plate, on their own. Above this only you can give it. 0 means only you."
        saved={v => v ? `Managers may now discount event plates up to ${v}%.` : 'Managers may no longer discount events. Only you can.'} />
      <OwnerRule settingKey="event_min_booking_fee" label="Minimum (KSh)"
        title="Minimum booking fee"
        hint="Taken before an event is confirmed and kept if it is cancelled. The manager may ask more, never less. 0 means none required."
        saved={v => v ? `Every event now needs a booking fee of at least KSh ${v.toLocaleString()}.` : 'No booking fee is required.'} />

      {isLoading && [1, 2, 3].map(i => <Skeleton key={i} variant="row" className="h-28" />)}
      {isError && <p className="text-sm text-status-failed">Could not load events.</p>}
      {!isLoading && !isError && events.length === 0 && (
        <EmptyState title="No events booked." description="Events the manager books will show here."
          icon={<svg width="40" height="40" viewBox="0 0 48 48" fill="none" aria-hidden="true">
            <rect x="8" y="6" width="32" height="36" rx="3" stroke="currentColor" strokeWidth="2" />
            <path d="M16 4v6M32 4v6M8 18h32" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>} />
      )}

      {events.map(e => (
        <div key={e.id} className="glass-card rounded-2xl p-4 space-y-3">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="font-serif text-lg font-bold text-ink-primary truncate">{e.title}</p>
              <p className="text-xs text-ink-tertiary">
                {new Date(e.starts_at).toLocaleDateString('en-KE', { weekday: 'short', day: 'numeric', month: 'short' })}
                {e.venue && ` · ${e.venue.name}`} · {e.expected_guests} guests
              </p>
            </div>
            <span className="text-[10px] font-bold uppercase tracking-widest text-ink-secondary shrink-0">
              {e.status.replace('_', ' ').toLowerCase()}
            </span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
            {([['Menu value', e.menu_value], ['Discount', e.discount], ['Billed', e.charged],
               ['Paid', e.paid], ['Owing', e.owing]] as const).map(([label, v]) => (
              <div key={label} className="rounded-lg bg-white/5 p-2">
                <p className="text-[10px] uppercase tracking-widest text-ink-tertiary">{label}</p>
                <p className={`text-sm font-semibold tabular-nums ${
                  label === 'Owing' && Number(v) > 0 ? 'text-status-failed'
                  : label === 'Discount' && Number(v) > 0 ? 'text-status-pending' : 'text-ink-primary'}`}>
                  {kes(v)}
                </p>
              </div>
            ))}
          </div>
          {e.discount_by.length > 0 && (
            <p className="text-xs text-ink-tertiary">Discount given by {e.discount_by.join(', ')}.</p>
          )}
        </div>
      ))}
    </div>
  )
}
