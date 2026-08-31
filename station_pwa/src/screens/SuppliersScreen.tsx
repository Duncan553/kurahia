/**
 * SuppliersScreen — who the resort buys from.
 *
 * /suppliers has had full CRUD since Phase A and no caller in any PWA, so the
 * supplier list could only ever be empty. Recording a purchase wants a name to
 * attribute it to, and "which supplier is quietly charging more than the others"
 * is unanswerable while nothing is on file.
 *
 * Disable, never delete (engineering invariant 6) — a supplier you stopped using
 * still owns every purchase you made from them.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Input, FormField, Button, Modal, useToastStore, ErrorBoundary, EmptyState } from '@shared'
import { RequireRole } from '../components/AuthGate'
import api from '../lib/axios'

interface Supplier {
  id: string; name: string; contact_person: string | null; phone: string | null
  email: string | null; items_supplied: string | null; payment_terms: string | null
  notes: string | null; is_active: boolean
}

const BLANK = {
  name: '', contact_person: '', phone: '', email: '',
  items_supplied: '', payment_terms: '', notes: '',
}

const extractErr = (e: unknown) =>
  (e as { response?: { data?: { error?: string } } })?.response?.data?.error
  ?? 'Something went wrong. Try again.'

export default function SuppliersScreen() {
  const qc = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState<Supplier | null>(null)
  const [f, setF] = useState(BLANK)

  const { data: suppliers = [], isLoading } = useQuery<Supplier[]>({
    queryKey: ['suppliers'],
    queryFn: () => api.get<Supplier[]>('/suppliers').then(r => Array.isArray(r.data) ? r.data : []),
    staleTime: 60_000,
  })

  const done = (msg: string) => {
    qc.invalidateQueries({ queryKey: ['suppliers'] })
    addToast({ type: 'success', message: msg })
    setF(BLANK); setAdding(false); setEditing(null)
  }
  const fail = (e: unknown) => addToast({ type: 'error', message: extractErr(e) })

  const createMut = useMutation({
    mutationFn: () => api.post('/suppliers', {
      name: f.name.trim(),
      contact_person: f.contact_person.trim() || null,
      phone: f.phone.trim() || null,
      email: f.email.trim() || null,
      items_supplied: f.items_supplied.trim() || null,
      payment_terms: f.payment_terms.trim() || null,
      notes: f.notes.trim() || null,
    }),
    onSuccess: () => done('Supplier added.'),
    onError: fail,
  })

  const editMut = useMutation({
    mutationFn: () => api.patch(`/suppliers/${editing!.id}`, {
      name: f.name.trim(),
      contact_person: f.contact_person.trim() || null,
      phone: f.phone.trim() || null,
      email: f.email.trim() || null,
      items_supplied: f.items_supplied.trim() || null,
      payment_terms: f.payment_terms.trim() || null,
      notes: f.notes.trim() || null,
    }),
    onSuccess: () => done('Supplier updated.'),
    onError: fail,
  })

  const disableMut = useMutation({
    mutationFn: (s: Supplier) => api.post(`/suppliers/${s.id}/disable`),
    onSuccess: () => done('Supplier archived. Their past purchases are untouched.'),
    onError: fail,
  })

  function openEdit(s: Supplier) {
    setEditing(s)
    setF({
      name: s.name, contact_person: s.contact_person ?? '', phone: s.phone ?? '',
      email: s.email ?? '', items_supplied: s.items_supplied ?? '',
      payment_terms: s.payment_terms ?? '', notes: s.notes ?? '',
    })
  }

  const fields = (
    <div className="flex flex-col gap-3">
      <FormField label="Name" htmlFor="s-name" required>
        <Input id="s-name" required placeholder="e.g. Juja Fresh Produce"
          value={f.name} onChange={e => setF({ ...f, name: e.target.value })} />
      </FormField>
      <div className="grid grid-cols-2 gap-3">
        <FormField label="Contact person" htmlFor="s-contact">
          <Input id="s-contact" placeholder="Who you call"
            value={f.contact_person} onChange={e => setF({ ...f, contact_person: e.target.value })} />
        </FormField>
        <FormField label="Phone" htmlFor="s-phone">
          <Input id="s-phone" type="tel" inputMode="tel" placeholder="+254…"
            value={f.phone} onChange={e => setF({ ...f, phone: e.target.value })} />
        </FormField>
      </div>
      <FormField label="Email" htmlFor="s-email">
        <Input id="s-email" type="email" placeholder="Optional"
          value={f.email} onChange={e => setF({ ...f, email: e.target.value })} />
      </FormField>
      <FormField label="What they supply" htmlFor="s-items">
        <Input id="s-items" placeholder="e.g. vegetables, tilapia, cooking oil"
          value={f.items_supplied} onChange={e => setF({ ...f, items_supplied: e.target.value })} />
      </FormField>
      <FormField label="Payment terms" htmlFor="s-terms">
        <Input id="s-terms" placeholder="e.g. cash on delivery, 30 days"
          value={f.payment_terms} onChange={e => setF({ ...f, payment_terms: e.target.value })} />
      </FormField>
      <FormField label="Notes" htmlFor="s-notes">
        <Input id="s-notes" placeholder="Anything worth remembering"
          value={f.notes} onChange={e => setF({ ...f, notes: e.target.value })} />
      </FormField>
    </div>
  )

  const active = suppliers.filter(s => s.is_active)
  const archived = suppliers.filter(s => !s.is_active)

  return (
    <RequireRole minLevel={5}>
      <ErrorBoundary level="tile">
        <div className="p-4 md:p-6 max-w-4xl mx-auto">
          <header className="mb-6 flex items-start justify-between gap-4">
            <div>
              <p className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary">Buying</p>
              <h1 className="text-3xl md:text-4xl font-bold font-serif text-ink-primary">Suppliers</h1>
              <p className="text-sm text-ink-secondary mt-1">
                Who the resort buys from. Purchases are attributed here.
              </p>
            </div>
            <Button onClick={() => { setF(BLANK); setAdding(true) }}>+ Add supplier</Button>
          </header>

          {isLoading ? (
            <div className="py-16 flex justify-center">
              <div className="w-7 h-7 rounded-full border-2 border-primary-main border-t-transparent animate-spin" />
            </div>
          ) : suppliers.length === 0 ? (
            <EmptyState
              icon={
                <svg width="40" height="40" viewBox="0 0 40 40" fill="none" aria-hidden="true">
                  <rect x="7" y="12" width="26" height="21" rx="2" stroke="currentColor" strokeWidth="1.5"/>
                  <path d="M7 18h26M15 12V8M25 12V8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                </svg>
              }
              title="No suppliers on file"
              description="Add the people you buy from, so every purchase can be attributed and compared." />
          ) : (
            <div className="flex flex-col gap-6">
              <div className="grid gap-3 sm:grid-cols-2">
                {active.map(s => (
                  <div key={s.id} className="glass-card rounded-2xl p-4 flex flex-col gap-1.5">
                    <div className="flex items-start justify-between gap-2">
                      <p className="font-semibold text-ink-primary">{s.name}</p>
                      <div className="flex gap-1 shrink-0">
                        <button onClick={() => openEdit(s)}
                          className="text-[11px] px-2 py-1 rounded-lg text-primary-dark hover:underline">
                          Edit
                        </button>
                        <button onClick={() => disableMut.mutate(s)}
                          className="text-[11px] px-2 py-1 rounded-lg text-ink-tertiary hover:underline">
                          Archive
                        </button>
                      </div>
                    </div>
                    {s.items_supplied && <p className="text-xs text-ink-secondary">{s.items_supplied}</p>}
                    {(s.contact_person || s.phone) && (
                      <p className="text-xs text-ink-tertiary">
                        {[s.contact_person, s.phone].filter(Boolean).join(' · ')}
                      </p>
                    )}
                    {s.payment_terms && (
                      <p className="text-[11px] text-ink-tertiary">Terms: {s.payment_terms}</p>
                    )}
                  </div>
                ))}
              </div>

              {archived.length > 0 && (
                <div>
                  <p className="text-[11px] font-semibold tracking-wider uppercase text-ink-tertiary mb-2">
                    Archived — kept because their purchases still reference them
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {archived.map(s => (
                      <span key={s.id}
                        className="text-xs px-2.5 py-1 rounded-full glass-surface text-ink-tertiary">
                        {s.name}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          <Modal open={adding} onClose={() => setAdding(false)} title="Add supplier" size="sm">
            <form onSubmit={e => { e.preventDefault(); createMut.mutate() }} className="flex flex-col gap-4">
              {fields}
              <Button type="submit" loading={createMut.isPending} disabled={!f.name.trim()}>
                Add supplier
              </Button>
            </form>
          </Modal>

          <Modal open={!!editing} onClose={() => setEditing(null)}
            title={`Edit — ${editing?.name ?? ''}`} size="sm">
            <form onSubmit={e => { e.preventDefault(); editMut.mutate() }} className="flex flex-col gap-4">
              {fields}
              <Button type="submit" loading={editMut.isPending} disabled={!f.name.trim()}>
                Save changes
              </Button>
            </form>
          </Modal>
        </div>
      </ErrorBoundary>
    </RequireRole>
  )
}
