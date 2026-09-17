/**
 * ResourcesScreen — the villas, venues and water craft the resort rents out.
 *
 * /bookable-resources has had full CRUD since Phase A with no caller in any of
 * the three PWAs. So a manager could not create a villa, change its nightly
 * rate, or take one out of service: the only resources that existed were the
 * ones seeded into the database. Every booking screen reads this list, and
 * nothing could write to it.
 *
 * Disable, never delete (engineering invariant 6): a villa taken out of service
 * still owns its past bookings, so it is archived rather than removed.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Input, Select, FormField, Button, Modal, useToastStore, ErrorBoundary, EmptyState } from '@shared'
import { RequireRole } from '../components/AuthGate'
import api from '../lib/axios'
import { useAuthStore } from '@shared'

interface Resource {
  id: string; name: string; resource_type: string
  base_price: string; capacity: number | null
  department_id: string | null; is_active: boolean
}
interface Dept { id: string; name: string }

const TYPES = [
  { value: 'VILLA',          label: 'Villa — guests sleep here' },
  { value: 'EVENT_VENUE',    label: 'Event venue — weddings, conferences' },
  { value: 'WATER_ACTIVITY', label: 'Water craft — kayak, boat, jet ski' },
  { value: 'OTHER',          label: 'Other' },
]
const TYPE_LABEL: Record<string, string> = {
  VILLA: 'Villa', EVENT_VENUE: 'Venue', WATER_ACTIVITY: 'Water', OTHER: 'Other',
}

const BLANK = { name: '', resource_type: 'VILLA', base_price: '', capacity: '', department_id: '' }

const extractErr = (e: unknown) =>
  (e as { response?: { data?: { error?: string } } })?.response?.data?.error
  ?? 'Something went wrong. Try again.'

/**
 * Equipment — the craft and kit a guest is put on or handed.
 *
 * POST /equipment has existed since Phase A with no caller in any app, so the
 * water post's pre-use safety check — the one thing standing between a guest
 * and a jet ski with no kill-switch lanyard — could never run: its screen said
 * "No equipment configured. Ask the owner to add equipment records first" and
 * the owner had nowhere to add them.
 *
 * The types below are the ones with a checklist behind them
 * (app/equipment/safety_templates.py). Anything else is accepted by the API but
 * has no checklist, so the safety screen would have nothing to ask.
 */
const EQUIPMENT_TYPES = [
  { value: 'jetski',      label: 'Jet ski' },
  { value: 'motorboat',   label: 'Motorboat' },
  { value: 'paddle_boat', label: 'Paddle boat' },
  { value: 'bicycle',     label: 'Bicycle' },
]

interface EquipmentRow {
  id: string
  name: string
  equipment_type: string
  status: string
  is_active: boolean
  is_due_service?: boolean
}

function EquipmentSection() {
  const qc = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  const [adding, setAdding] = useState(false)
  const [name, setName] = useState('')
  const [type, setType] = useState('jetski')
  const [interval, setInterval_] = useState('')

  const { data: items = [], isLoading } = useQuery<EquipmentRow[]>({
    queryKey: ['equipment'],
    queryFn: () => api.get<EquipmentRow[]>('/equipment').then(r => Array.isArray(r.data) ? r.data : []),
    staleTime: 60_000,
  })

  const createMut = useMutation({
    mutationFn: () => api.post('/equipment', {
      name: name.trim(),
      equipment_type: type,
      service_interval_days: interval ? parseInt(interval, 10) : undefined,
    }).then(r => r.data),
    onSuccess: () => {
      addToast({ type: 'success', message: `${name.trim()} added. The water post can check it before use.` })
      setName(''); setInterval_(''); setAdding(false)
      qc.invalidateQueries({ queryKey: ['equipment'] })
    },
    onError: (e) => addToast({ type: 'error',
      message: (e as { response?: { data?: { error?: string } } })?.response?.data?.error
        ?? 'Could not add that.' }),
  })

  const disableMut = useMutation({
    mutationFn: (eq: EquipmentRow) => api.post(`/equipment/${eq.id}/disable`),
    onSuccess: () => {
      addToast({ type: 'success', message: 'Taken out of service.' })
      qc.invalidateQueries({ queryKey: ['equipment'] })
    },
  })

  return (
    <section className="mt-10">
      <header className="mb-4 flex items-start justify-between gap-4">
        <div>
          <p className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary">What we put guests on</p>
          <h2 className="text-2xl font-bold font-serif text-ink-primary">Equipment</h2>
          <p className="text-sm text-ink-secondary mt-1">
            Each one gets a pre-use safety check at the water post before a guest touches it.
          </p>
        </div>
        <Button variant="ghost" onClick={() => setAdding(a => !a)}>{adding ? 'Cancel' : '+ Add'}</Button>
      </header>

      {adding && (
        <form
          onSubmit={e => { e.preventDefault(); if (name.trim()) createMut.mutate() }}
          className="glass-card rounded-2xl p-4 mb-4 space-y-3">
          <Input label="Name" placeholder="e.g. Jet ski #2" value={name}
            onChange={e => setName(e.target.value)} />
          <Select label="Type" value={type} onChange={e => setType(e.target.value)}
            options={EQUIPMENT_TYPES} />
          <Input label="Service every (days, optional)" type="number" min="1"
            placeholder="e.g. 90" value={interval}
            onChange={e => setInterval_(e.target.value)} />
          <Button type="submit" disabled={!name.trim() || createMut.isPending}>
            Add equipment
          </Button>
        </form>
      )}

      {isLoading ? (
        <p className="text-sm text-ink-tertiary">Loading…</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-ink-tertiary">
          Nothing registered yet. The water post cannot run a safety check until a boat or
          jet ski is on this list.
        </p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {items.map(eq => (
            <div key={eq.id} className="glass-card rounded-2xl p-4 flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="font-semibold text-ink-primary truncate">{eq.name}</p>
                <p className="text-[10px] font-bold uppercase tracking-wider text-primary-dark mt-0.5">
                  {EQUIPMENT_TYPES.find(t => t.value === eq.equipment_type)?.label ?? eq.equipment_type}
                  {eq.is_due_service ? ' · service due' : ''}
                </p>
              </div>
              <button onClick={() => disableMut.mutate(eq)}
                className="text-[11px] px-2 py-1 rounded-lg text-ink-tertiary hover:underline shrink-0">
                Out of service
              </button>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

export default function ResourcesScreen() {
  const qc = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState<Resource | null>(null)
  const [f, setF] = useState(BLANK)

  const { data: resources = [], isLoading } = useQuery<Resource[]>({
    queryKey: ['bookable-resources'],
    queryFn: () => api.get<Resource[]>('/bookable-resources', { params: { include_disabled: true } })
      .then(r => Array.isArray(r.data) ? r.data : []),
    staleTime: 60_000,
  })
  const { data: meta } = useQuery<{ departments: Dept[] }>({
    queryKey: ['users-meta'],
    queryFn: () => api.get('/auth/users/meta').then(r => r.data),
    staleTime: 5 * 60_000,
  })
  const departments = meta?.departments ?? []
  const roleLevel = useAuthStore(s => s.user?.role_level ?? 0)

  const done = (msg: string) => {
    qc.invalidateQueries({ queryKey: ['bookable-resources'] })
    qc.invalidateQueries({ queryKey: ['villa-availability'] })
    addToast({ type: 'success', message: msg })
    setF(BLANK); setAdding(false); setEditing(null)
  }
  const fail = (e: unknown) => addToast({ type: 'error', message: extractErr(e) })

  // The rate is the owner's to set (app/bookings/resources.py) — the same rule
  // that keeps wages off a manager's screen. This form sent base_price on every
  // PATCH regardless, so a manager correcting a villa's SLEEPS count had the
  // whole edit thrown back at them with "Only the owner can change resource
  // pricing" — about a price they had not touched. Send the field only when the
  // person is allowed to change it.
  // A venue's hire fee is the exception: running the spaces is the manager's job
  // (decided 17 Sep 2026), so the backend lets them set it. A villa rate is not.
  const isVenue = f.resource_type === 'EVENT_VENUE'
  const mayPrice = roleLevel >= 10 || isVenue
  const body = () => ({
    name: f.name.trim(),
    resource_type: f.resource_type,
    ...(mayPrice ? { base_price: f.base_price || '0' } : {}),
    capacity: f.capacity ? parseInt(f.capacity, 10) : null,
    department_id: f.department_id || null,
  })

  const createMut = useMutation({
    mutationFn: () => api.post('/bookable-resources', body()),
    onSuccess: () => done('Added. It is now bookable.'),
    onError: fail,
  })
  const editMut = useMutation({
    mutationFn: () => api.patch(`/bookable-resources/${editing!.id}`, body()),
    onSuccess: () => done('Updated.'),
    onError: fail,
  })
  const toggleMut = useMutation({
    mutationFn: (r: Resource) =>
      api.post(`/bookable-resources/${r.id}/${r.is_active ? 'disable' : 'enable'}`),
    onSuccess: (_d, r) => done(r.is_active
      ? 'Taken out of service. Past bookings are untouched.'
      : 'Back in service.'),
    onError: fail,
  })

  function openEdit(r: Resource) {
    setEditing(r)
    setF({
      name: r.name, resource_type: r.resource_type,
      base_price: r.base_price ?? '', capacity: r.capacity?.toString() ?? '',
      department_id: r.department_id ?? '',
    })
  }

  const fields = (
    <div className="flex flex-col gap-3">
      <FormField label="Name" htmlFor="r-name" required>
        <Input id="r-name" required placeholder="e.g. Lakeview Villa 2"
          value={f.name} onChange={e => setF({ ...f, name: e.target.value })} />
      </FormField>
      <FormField label="What is it" htmlFor="r-type" required>
        <Select id="r-type" required value={f.resource_type}
          onChange={e => setF({ ...f, resource_type: e.target.value })} options={TYPES} />
      </FormField>
      <div className="grid grid-cols-2 gap-3">
        <FormField label={isVenue ? 'Hire fee (KSh)' : 'Nightly / session rate (KSh)'} htmlFor="r-price" required>
          <Input id="r-price" required type="number" min="0" step="0.01" inputMode="decimal"
            placeholder="0.00" value={f.base_price}
            readOnly={!mayPrice}
            title={mayPrice ? undefined : 'Only the owner sets the rate'}
            onChange={e => setF({ ...f, base_price: e.target.value })} />
        </FormField>
        <FormField label={isVenue ? 'Guests it holds' : 'Sleeps / seats'} htmlFor="r-cap">
          <Input id="r-cap" type="number" min="0" step="1" inputMode="numeric" placeholder="Optional"
            value={f.capacity} onChange={e => setF({ ...f, capacity: e.target.value })} />
        </FormField>
      </div>
      <FormField label="Department" htmlFor="r-dept">
        <Select id="r-dept" value={f.department_id}
          onChange={e => setF({ ...f, department_id: e.target.value })}
          options={[
            { value: '', label: 'No department' },
            ...departments.map(d => ({ value: d.id, label: d.name })),
          ]} />
      </FormField>
    </div>
  )

  const active = resources.filter(r => r.is_active)
  const archived = resources.filter(r => !r.is_active)

  return (
    <RequireRole minLevel={5}>
      <ErrorBoundary level="tile">
        <div className="p-4 md:p-6 max-w-4xl mx-auto">
          <header className="mb-6 flex items-start justify-between gap-4">
            <div>
              <p className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary">What we rent</p>
              <h1 className="text-3xl md:text-4xl font-bold font-serif text-ink-primary">Villas &amp; Venues</h1>
              <p className="text-sm text-ink-secondary mt-1">
                Everything a guest can book. Front desk books from this list.
              </p>
            </div>
            <Button onClick={() => { setF(BLANK); setAdding(true) }}>+ Add</Button>
          </header>

          {isLoading ? (
            <div className="py-16 flex justify-center">
              <div className="w-7 h-7 rounded-full border-2 border-primary-main border-t-transparent animate-spin" />
            </div>
          ) : resources.length === 0 ? (
            <EmptyState
              icon={
                <svg width="40" height="40" viewBox="0 0 40 40" fill="none" aria-hidden="true">
                  <path d="M6 20L20 8l14 12v14a2 2 0 01-2 2H8a2 2 0 01-2-2V20z"
                    stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
                  <path d="M16 34V24h8v10" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
                </svg>
              }
              title="Nothing is bookable yet"
              description="Add the villas, venues and craft guests can book. Front desk picks from this list." />
          ) : (
            <div className="flex flex-col gap-6">
              <div className="grid gap-3 sm:grid-cols-2">
                {active.map(r => (
                  <div key={r.id} className="glass-card rounded-2xl p-4 flex flex-col gap-1.5">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="font-semibold text-ink-primary truncate">{r.name}</p>
                        <p className="text-[10px] font-bold uppercase tracking-wider text-primary-dark mt-0.5">
                          {TYPE_LABEL[r.resource_type] ?? r.resource_type}
                        </p>
                      </div>
                      <div className="flex gap-1 shrink-0">
                        <button onClick={() => openEdit(r)}
                          className="text-[11px] px-2 py-1 rounded-lg text-primary-dark hover:underline">
                          Edit
                        </button>
                        <button onClick={() => toggleMut.mutate(r)}
                          className="text-[11px] px-2 py-1 rounded-lg text-ink-tertiary hover:underline">
                          Take out
                        </button>
                      </div>
                    </div>
                    <p className="text-sm text-ink-secondary tabular-nums">
                      KSh {parseFloat(r.base_price || '0').toLocaleString()}
                      {r.capacity ? <span className="text-ink-tertiary"> · {r.resource_type === 'EVENT_VENUE' ? 'holds' : 'sleeps'} {r.capacity}</span> : null}
                    </p>
                  </div>
                ))}
              </div>

              {archived.length > 0 && (
                <div>
                  <p className="text-[11px] font-semibold tracking-wider uppercase text-ink-tertiary mb-2">
                    Out of service — kept because past bookings reference them
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {archived.map(r => (
                      <button key={r.id} onClick={() => toggleMut.mutate(r)}
                        className="text-xs px-2.5 py-1 rounded-full glass-surface text-ink-tertiary
                          hover:text-ink-primary">
                        {r.name} · put back
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          <Modal open={adding} onClose={() => setAdding(false)} title="Add something bookable" size="sm">
            <form onSubmit={e => { e.preventDefault(); createMut.mutate() }} className="flex flex-col gap-4">
              {fields}
              <Button type="submit" loading={createMut.isPending} disabled={!f.name.trim()}>Add</Button>
            </form>
          </Modal>

          <Modal open={!!editing} onClose={() => setEditing(null)}
            title={`Edit — ${editing?.name ?? ''}`} size="sm">
            <form onSubmit={e => { e.preventDefault(); editMut.mutate() }} className="flex flex-col gap-4">
              {fields}
              <Button type="submit" loading={editMut.isPending} disabled={!f.name.trim()}>Save changes</Button>
            </form>
          </Modal>
          <EquipmentSection />
        </div>
      </ErrorBoundary>
    </RequireRole>
  )
}
