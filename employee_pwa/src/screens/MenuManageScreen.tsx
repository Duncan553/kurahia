import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Button, Select, Skeleton, useToastStore } from '@shared'
import api from '../lib/axios'

// Manager: add, edit price, disable and re-enable everything the resort sells.
// prep_station controls routing: KITCHEN/BAR → that queue; NONE → spa, gym,
// water — served instantly, no queue.

interface MenuItem {
  id: string; name: string; price: string; category: string | null
  prep_station: string; department_id: string; is_active: boolean
}
interface Meta { departments: { id: string; name: string }[] }

const BLANK = { name: '', price: '', category: '', station: 'KITCHEN', deptId: '' }
const STATIONS = [
  { value: 'KITCHEN', label: 'Kitchen (food queue)' },
  { value: 'BAR',     label: 'Bar (drinks queue)' },
  { value: 'NONE',    label: 'No queue (spa / gym / activities)' },
]
const extractErr = (e: unknown) =>
  (e as { response?: { data?: { error?: string } } })?.response?.data?.error ?? 'Something went wrong.'

export default function MenuManageScreen() {
  const qc = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  const [f, setF] = useState(BLANK)
  const [adding, setAdding] = useState(false)
  const [priceEdit, setPriceEdit] = useState<{ id: string; price: string } | null>(null)

  const { data: items = [], isLoading } = useQuery<MenuItem[]>({
    queryKey: ['menu-manage'],
    queryFn: () => api.get<MenuItem[]>('/menu/items?include_disabled=true').then(r => r.data),
  })
  const { data: meta } = useQuery<Meta>({
    queryKey: ['users-meta'],
    queryFn: () => api.get<Meta>('/auth/users/meta').then(r => r.data),
  })

  const ok = (msg: string) => {
    qc.invalidateQueries({ queryKey: ['menu-manage'] })
    qc.invalidateQueries({ queryKey: ['menu-items'] })
    addToast({ type: 'success', message: msg })
  }
  const fail = (e: unknown) => addToast({ type: 'error', message: extractErr(e) })

  const createMut = useMutation({
    mutationFn: () => api.post('/menu/items', {
      name: f.name.trim(), price: f.price, category: f.category.trim() || null,
      prep_station: f.station, department_id: f.deptId,
    }),
    onSuccess: () => { ok('Item added to the menu.'); setF(BLANK); setAdding(false) },
    onError: fail,
  })

  const toggleMut = useMutation({
    mutationFn: (it: MenuItem) => api.post(`/menu/items/${it.id}/${it.is_active ? 'disable' : 'enable'}`),
    onSuccess: (_d, it) => ok(it.is_active ? 'Item removed from sale.' : 'Item back on sale.'),
    onError: fail,
  })

  const priceMut = useMutation({
    mutationFn: ({ id, price }: { id: string; price: string }) =>
      api.patch(`/menu/items/${id}`, { price }),
    onSuccess: () => { ok('Price updated.'); setPriceEdit(null) },
    onError: fail,
  })

  // Group by department for a scannable list
  const deptName = (id: string) => meta?.departments.find(d => d.id === id)?.name ?? '—'
  const grouped = items.reduce<Record<string, MenuItem[]>>((acc, it) => {
    ;(acc[deptName(it.department_id)] ??= []).push(it); return acc
  }, {})

  return (
    <div className="p-4 max-w-lg mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold font-serif text-ink-primary">Menu &amp; Services</h1>
        <Button variant="primary" size="sm" onClick={() => setAdding(a => !a)}>
          {adding ? 'Close' : '+ Add Item'}
        </Button>
      </div>

      {/* Add form */}
      {adding && (
        <form
          onSubmit={e => { e.preventDefault(); createMut.mutate() }}
          className="p-4 rounded-2xl border border-cream-alt bg-cream-card space-y-3">
          <input required placeholder="Name — e.g. Grilled Tilapia, 60-min Massage"
            value={f.name} onChange={e => setF({ ...f, name: e.target.value })}
            className="w-full rounded-xl border border-cream-alt bg-cream-card px-4 py-3 text-sm
              focus:outline-none focus:border-primary-dark" />
          <div className="grid grid-cols-2 gap-2">
            <input required type="number" min="0" step="0.01" inputMode="decimal" placeholder="Price (KSh)"
              value={f.price} onChange={e => setF({ ...f, price: e.target.value })}
              className="rounded-xl border border-cream-alt bg-cream-card px-4 py-3 text-sm
                focus:outline-none focus:border-primary-dark" />
            <input placeholder="Category (optional)"
              value={f.category} onChange={e => setF({ ...f, category: e.target.value })}
              className="rounded-xl border border-cream-alt bg-cream-card px-4 py-3 text-sm
                focus:outline-none focus:border-primary-dark" />
          </div>
          <Select label="Routes to" required value={f.station} onChange={e => setF({ ...f, station: e.target.value })}
            options={STATIONS} />
          <Select label="Department" required value={f.deptId} onChange={e => setF({ ...f, deptId: e.target.value })}
            options={[{ value: '', label: 'Department…' },
              ...(meta?.departments ?? []).map(d => ({ value: d.id, label: d.name }))]} />
          <Button type="submit" variant="primary" size="lg" className="w-full"
            loading={createMut.isPending}>
            Add to Menu
          </Button>
        </form>
      )}

      {isLoading && <div className="space-y-2">{[1,2,3].map(i => <Skeleton key={i} variant="row" />)}</div>}

      {/* Item list grouped by department */}
      {Object.entries(grouped).map(([dept, deptItems]) => (
        <div key={dept}>
          <p className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary mb-2">{dept}</p>
          <div className="space-y-2">
            {deptItems.map(it => (
              <div key={it.id}
                className={`flex items-center gap-3 p-3 rounded-xl border border-cream-alt bg-cream-card
                  ${!it.is_active ? 'opacity-50' : ''}`}>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-ink-primary truncate">{it.name}</p>
                  <p className="text-xs text-ink-tertiary">
                    {it.prep_station === 'NONE' ? 'no queue' : it.prep_station.toLowerCase()}
                    {it.category ? ` · ${it.category}` : ''}
                  </p>
                </div>
                {priceEdit?.id === it.id ? (
                  <>
                    <input autoFocus type="number" min="0" step="0.01" inputMode="decimal"
                      value={priceEdit.price}
                      onChange={e => setPriceEdit({ id: it.id, price: e.target.value })}
                      onKeyDown={e => e.key === 'Enter' && priceMut.mutate(priceEdit)}
                      className="w-24 rounded-lg border border-primary-dark px-2 py-1.5 text-sm tabular-nums" />
                    <Button variant="primary" size="sm" loading={priceMut.isPending}
                      onClick={() => priceMut.mutate(priceEdit)}>Save</Button>
                  </>
                ) : (
                  <button onClick={() => setPriceEdit({ id: it.id, price: it.price })}
                    className="text-sm font-bold tabular-nums text-ink-primary underline decoration-dotted">
                    KSh {parseFloat(it.price).toLocaleString('en-KE')}
                  </button>
                )}
                <Button variant={it.is_active ? 'ghost' : 'primary'} size="sm"
                  loading={toggleMut.isPending && toggleMut.variables?.id === it.id}
                  onClick={() => toggleMut.mutate(it)}>
                  {it.is_active ? 'Remove' : 'Restore'}
                </Button>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
