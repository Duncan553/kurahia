import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Select, Skeleton, EmptyState, StatusBadge, useToastStore } from '@shared'
import type { StatusValue } from '@shared'
import api from '../lib/axios'
import { RequireRole } from '../components/AuthGate'

interface InventoryItem {
  id: string
  name: string
  unit: string
  is_staff_food: boolean
}

interface PurchaseRequest {
  id: string
  item_id: string | null
  item_name: string | null
  quantity: string
  status: string
  created_at: string
}

function statusValue(s: string): StatusValue {
  const map: Record<string, StatusValue> = {
    PENDING:   'pending',
    APPROVED:  'paid',
    REJECTED:  'cancelled',
    FULFILLED: 'checked-out',
  }
  return map[s] ?? 'pending'
}

function genKey() { return crypto.randomUUID() }

export default function PurchaseRequestScreen() {
  const queryClient = useQueryClient()
  const addToast    = useToastStore((s) => s.addToast)

  const [itemId,   setItemId]   = useState('')
  const [qty,      setQty]      = useState('')
  const [notes,    setNotes]    = useState('')
  const [idemKey,  setIdemKey]  = useState(genKey)
  const [touched,  setTouched]  = useState({ item: false, qty: false })

  const touch = (f: keyof typeof touched) => setTouched((p) => ({ ...p, [f]: true }))

  const itemErr = touched.item && !itemId         ? 'Select an item.' : ''
  const qtyErr  = touched.qty  && (!qty || parseFloat(qty) <= 0)
    ? 'Enter a positive quantity.' : ''
  const isValid = !!itemId && !!qty && parseFloat(qty) > 0

  // Shared cache with other screens using /inventory/items
  const { data: items, isLoading: itemsLoading } = useQuery<InventoryItem[]>({
    queryKey: ['inventory-items'],
    queryFn: () => api.get<InventoryItem[]>('/inventory/items').then((r) => r.data),
  })

  const { data: history, isError: historyError } = useQuery<PurchaseRequest[]>({
    queryKey: ['purchase-requests'],
    queryFn: () => api.get<PurchaseRequest[]>('/inventory/purchase-requests').then((r) => r.data),
  })

  const itemOpts = (items ?? []).map((i) => ({ value: i.id, label: `${i.name} (${i.unit})` }))

  const mutation = useMutation({
    mutationFn: () =>
      api.post('/inventory/purchase-requests', {
        item_id:         itemId,
        quantity:        parseFloat(qty),
        notes:           notes.trim() || undefined,
        idempotency_key: idemKey,
      }).then((r) => r.data),

    onSuccess: () => {
      addToast({ type: 'success', message: 'Purchase request submitted.' })
      setItemId('')
      setQty('')
      setNotes('')
      setTouched({ item: false, qty: false })
      setIdemKey(genKey())
      queryClient.invalidateQueries({ queryKey: ['purchase-requests'] })
    },

    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
        ?? 'Request failed. Try again.'
      addToast({ type: 'error', message: msg })
    },
  })

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setTouched({ item: true, qty: true })
    if (!isValid) return
    mutation.mutate()
  }

  return (
    <RequireRole minLevel={5}>
      <div className="p-4 max-w-md mx-auto space-y-6">

        <div>
          <h1 className="text-xl font-bold text-ink-primary">Purchase Request</h1>
          <p className="text-sm text-ink-tertiary">Request restocking — owner approves before purchase</p>
        </div>

        {/* ── Form ─────────────────────────────────────────────────── */}
        <form onSubmit={handleSubmit} noValidate className="space-y-4">
          {itemsLoading ? (
            <Skeleton variant="row" />
          ) : (
            <Select
              label="Item *"
              value={itemId}
              onChange={(e) => { setItemId(e.target.value); touch('item') }}
              onBlur={() => touch('item')}
              options={[{ value: '', label: 'Select item…' }, ...itemOpts]}
              disabled={mutation.isPending}
            />
          )}
          {itemErr && <p className="text-sm text-status-failed -mt-2">{itemErr}</p>}

          <div>
            <label className="block text-sm font-medium text-ink-secondary mb-1.5">Quantity *</label>
            <input
              type="number"
              min="0.001"
              step="0.001"
              inputMode="decimal"
              placeholder="0"
              value={qty}
              onChange={(e) => setQty(e.target.value)}
              onBlur={() => touch('qty')}
              disabled={mutation.isPending}
              className="w-full rounded-xl border border-cream-alt bg-white px-4 py-3
                text-base text-ink-primary focus:outline-none focus:border-primary-dark
                focus:ring-2 focus:ring-primary-dark/20 disabled:opacity-50"
            />
          </div>
          {qtyErr && <p className="text-sm text-status-failed -mt-2">{qtyErr}</p>}

          <div>
            <label className="block text-sm font-medium text-ink-secondary mb-1.5">Notes (optional)</label>
            <textarea
              rows={3}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              disabled={mutation.isPending}
              placeholder="Reason, urgency, preferred supplier…"
              className="w-full rounded-xl border border-cream-alt bg-white px-4 py-3
                text-sm text-ink-primary focus:outline-none focus:border-primary-dark
                focus:ring-2 focus:ring-primary-dark/20 disabled:opacity-50 resize-none"
            />
          </div>

          <button
            type="submit"
            disabled={mutation.isPending}
            className={[
              'w-full py-4 rounded-2xl text-base font-semibold transition-all',
              'bg-primary-dark text-cream-card hover:bg-primary-dark/90 active:scale-[0.99]',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark focus-visible:ring-offset-2',
              'disabled:opacity-50 disabled:cursor-not-allowed',
            ].join(' ')}
          >
            {mutation.isPending ? (
              <span className="flex items-center justify-center gap-2">
                <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
                  <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" strokeOpacity="0.3"/>
                  <path d="M21 12a9 9 0 01-9 9" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                </svg>
                Submitting…
              </span>
            ) : 'Submit Request'}
          </button>
        </form>

        {/* ── History ──────────────────────────────────────────────── */}
        <div>
          <p className="text-xs font-medium text-ink-tertiary uppercase tracking-widest mb-3">
            Recent requests (30 days)
          </p>

          {historyError && (
            <p className="text-sm text-ink-tertiary text-center py-4">
              Couldn't load history — form still works above.
            </p>
          )}

          {!historyError && history?.length === 0 && (
            <EmptyState
              icon={<svg width="40" height="40" viewBox="0 0 40 40" fill="none" aria-hidden="true">
                <rect x="8" y="6" width="24" height="30" rx="3" stroke="currentColor" strokeWidth="1.5"/>
                <path d="M13 14h14M13 20h10M13 26h8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
              </svg>}
              title="No purchase requests yet."
            />
          )}

          {history && history.length > 0 && (
            <div className="space-y-2">
              {history.map((r) => (
                <div key={r.id}
                  className="flex items-center justify-between rounded-xl
                    bg-cream-alt/30 border border-cream-alt px-4 py-3 gap-2">
                  <div className="min-w-0">
                    <p className="font-medium text-ink-primary text-sm truncate">
                      {r.item_name ?? 'Item'}
                    </p>
                    <p className="text-xs text-ink-tertiary tabular-nums">
                      Qty: {parseFloat(r.quantity).toLocaleString()}
                    </p>
                  </div>
                  <StatusBadge status={statusValue(r.status)} size="sm" />
                </div>
              ))}
            </div>
          )}
        </div>

      </div>
    </RequireRole>
  )
}
