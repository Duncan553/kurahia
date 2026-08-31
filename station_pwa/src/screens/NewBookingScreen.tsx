/**
 * NewBookingScreen — front desk takes a guest in.
 *
 * POST /bookings has always allowed FRONT_DESK_LEVEL, but the only screen that
 * called it was VillaScreen, gated to `deptIs(d,'villa','housekeep')`. So the
 * housekeeper who cleans the room took the guest's name, phone and dates, and
 * the desk that actually receives the guest could not. This is that form, in
 * the right hands.
 *
 * It also captures guest_id_number, which the backend has accepted since Phase A
 * (core.py passes it to get_or_create_guest_record) and which NO screen in any
 * of the three apps has ever sent. Without it a guest register is names only,
 * and returning guests are matched on phone number alone.
 */
import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Input, Select, FormField, Button, useToastStore, ErrorBoundary, resortToday, resortDatePlus } from '@shared'
import { RequireRole } from '../components/AuthGate'
import api from '../lib/axios'

interface Resource {
  id: string; name: string; resource_type: string
  base_price: string; capacity: number | null; available: boolean
}

const extractErr = (e: unknown) =>
  (e as { response?: { data?: { error?: string } } })?.response?.data?.error
  ?? 'Could not create that booking. Try again.'

export default function NewBookingScreen() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const addToast = useToastStore(s => s.addToast)

  const [checkin,  setCheckin]  = useState(resortToday)
  const [checkout, setCheckout] = useState(() => resortDatePlus(1))
  const [resourceId, setResourceId] = useState('')
  const [name,  setName]  = useState('')
  const [phone, setPhone] = useState('')
  const [idNum, setIdNum] = useState('')
  const [guests, setGuests] = useState('1')
  const [idem] = useState(() => crypto.randomUUID())

  // Availability is re-checked for the exact dates chosen — the backend also
  // locks the resource row and re-checks on insert, so this is guidance, not
  // the guarantee. Two desks booking the same villa still cannot both win.
  const { data: resources = [], isLoading } = useQuery<Resource[]>({
    queryKey: ['availability', checkin, checkout],
    queryFn: () => api.get<Resource[]>('/bookings/availability', {
      params: {
        resource_type: 'VILLA',
        from: `${checkin}T14:00:00`,
        to: `${checkout}T11:00:00`,
      },
    }).then(r => Array.isArray(r.data) ? r.data : []),
    enabled: !!checkin && !!checkout && checkout > checkin,
    staleTime: 30_000,
  })

  const free = resources.filter(r => r.available)
  const chosen = useMemo(() => resources.find(r => r.id === resourceId), [resources, resourceId])

  const nights = useMemo(() => {
    const a = new Date(checkin), b = new Date(checkout)
    return Math.max(0, Math.round((b.getTime() - a.getTime()) / 86_400_000))
  }, [checkin, checkout])

  // Shown before they commit, because a 30% deposit on a villa is required
  // before the booking can be confirmed and front desk should not discover
  // that at the confirm step with the guest standing there.
  const estimate = chosen ? parseFloat(chosen.base_price) * nights : 0
  const deposit = estimate * 0.30

  const create = useMutation({
    mutationFn: () => api.post('/bookings', {
      resource_id: resourceId,
      guest_name: name.trim(),
      guest_phone: phone.trim(),
      guest_id_number: idNum.trim() || null,
      number_of_guests: parseInt(guests, 10) || 1,
      check_in_planned_utc:  `${checkin}T14:00:00`,
      check_out_planned_utc: `${checkout}T11:00:00`,
      idempotency_key: idem,
    }).then(r => r.data),
    onSuccess: () => {
      addToast({ type: 'success', message: `${name.trim()} booked into ${chosen?.name}. Take the deposit to confirm.` })
      qc.invalidateQueries({ queryKey: ['front-desk-today'] })
      qc.invalidateQueries({ queryKey: ['availability'] })
      // Arrivals is where the deposit, confirm and check-in steps live.
      navigate('/front-desk/checkin')
    },
    onError: (e) => addToast({ type: 'error', message: extractErr(e) }),
  })

  const overCapacity = !!chosen?.capacity && parseInt(guests, 10) > chosen.capacity
  const ready = !!resourceId && !!name.trim() && !!phone.trim()
    && nights > 0 && !overCapacity

  return (
    <RequireRole minLevel={3}>
      <ErrorBoundary level="tile">
        <div className="p-4 md:p-6 max-w-2xl mx-auto">
          <button onClick={() => navigate(-1)}
            className="text-xs text-ink-tertiary hover:text-ink-primary mb-4">← Back</button>

          <header className="mb-6">
            <p className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary">Front desk</p>
            <h1 className="text-3xl md:text-4xl font-bold font-serif text-ink-primary">New Booking</h1>
            <p className="text-sm text-ink-secondary mt-1">
              Take the guest's details and put them in a villa.
            </p>
          </header>

          <form onSubmit={e => { e.preventDefault(); create.mutate() }}
            className="glass-card rounded-2xl p-5 flex flex-col gap-4">

            <div className="grid grid-cols-2 gap-3">
              <FormField label="Arriving" htmlFor="ci" required>
                <Input id="ci" required type="date" value={checkin}
                  onChange={e => { setCheckin(e.target.value); setResourceId('') }} />
              </FormField>
              <FormField label="Leaving" htmlFor="co" required>
                <Input id="co" required type="date" value={checkout}
                  onChange={e => { setCheckout(e.target.value); setResourceId('') }} />
              </FormField>
            </div>

            {nights <= 0 ? (
              <p className="text-xs text-status-failed">
                Leaving must be after arriving.
              </p>
            ) : (
              <p className="text-xs text-ink-tertiary">
                {nights} night{nights === 1 ? '' : 's'} · check-in 14:00, check-out 11:00
              </p>
            )}

            <FormField label="Villa" htmlFor="res" required>
              {isLoading ? (
                <p className="text-sm text-ink-tertiary py-2">Checking what's free…</p>
              ) : free.length === 0 ? (
                <p className="text-sm text-status-pending py-2">
                  Nothing free for those dates. Try different dates.
                </p>
              ) : (
                <Select id="res" required value={resourceId}
                  onChange={e => setResourceId(e.target.value)}
                  options={[
                    { value: '', label: 'Pick a villa…' },
                    ...free.map(r => ({
                      value: r.id,
                      label: `${r.name} — KSh ${parseFloat(r.base_price).toLocaleString()}/night`
                        + (r.capacity ? ` · sleeps ${r.capacity}` : ''),
                    })),
                  ]} />
              )}
            </FormField>

            <div className="h-px bg-white/10" />

            <FormField label="Guest name" htmlFor="gn" required>
              <Input id="gn" required placeholder="As it appears on their ID"
                value={name} onChange={e => setName(e.target.value)} />
            </FormField>

            <div className="grid grid-cols-2 gap-3">
              <FormField label="Phone" htmlFor="gp" required>
                <Input id="gp" required type="tel" inputMode="tel" placeholder="+254…"
                  value={phone} onChange={e => setPhone(e.target.value)} />
              </FormField>
              <FormField label="ID number" htmlFor="gid">
                <Input id="gid" placeholder="Recommended"
                  value={idNum} onChange={e => setIdNum(e.target.value)} />
              </FormField>
            </div>

            {/* Phone is the unique key on GuestRecord, so without an ID a
                returning family sharing a handset merges into one guest. */}
            {!idNum.trim() && (
              <p className="text-[11px] text-ink-tertiary -mt-2">
                Without an ID this guest is matched by phone number alone on their next stay.
              </p>
            )}

            <FormField label="How many staying" htmlFor="gc" required>
              <Input id="gc" required type="number" min="1" step="1" inputMode="numeric"
                value={guests} onChange={e => setGuests(e.target.value)} />
            </FormField>

            {overCapacity && (
              <p className="text-xs text-status-failed -mt-2">
                {chosen?.name} sleeps {chosen?.capacity}. Pick a bigger villa or reduce the number.
              </p>
            )}
            {parseInt(guests, 10) > 1 && !overCapacity && (
              <p className="text-[11px] text-ink-tertiary -mt-2">
                You'll name the other {parseInt(guests, 10) - 1} on the Occupancy tab after check-in.
              </p>
            )}

            {chosen && nights > 0 && (
              <div className="rounded-xl glass-surface px-4 py-3 flex flex-col gap-1">
                <div className="flex justify-between text-sm">
                  <span className="text-ink-tertiary">{nights} night{nights === 1 ? '' : 's'}</span>
                  <span className="text-ink-primary font-semibold tabular-nums">
                    KSh {estimate.toLocaleString()}
                  </span>
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-ink-tertiary">Deposit needed to confirm (30%)</span>
                  <span className="text-primary-dark font-semibold tabular-nums">
                    KSh {deposit.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                  </span>
                </div>
              </div>
            )}

            <Button type="submit" disabled={!ready} loading={create.isPending}>
              Create booking
            </Button>
            <p className="text-[11px] text-ink-tertiary text-center">
              Nothing is charged yet. Take the deposit on Arrivals, then confirm and check in.
            </p>
          </form>
        </div>
      </ErrorBoundary>
    </RequireRole>
  )
}
