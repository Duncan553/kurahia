import { useState, useMemo } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Select, useToastStore } from '@shared'
import api from '../lib/axios'
import { useAuthStore } from '../stores/authStore'

interface InventoryItem {
  id: string
  name: string
  unit: string
  is_staff_food: boolean
}

interface MovementResponse {
  movement_id: string
  item: string
  quantity: string
}

type Tab = 'spoilage' | 'staff-meal'

function genKey() { return crypto.randomUUID() }

function ItemQtyForm({
  label,
  items,
  itemsLoading,
  onSubmit,
  requireReason,
  isPending,
}: {
  label: string
  items: InventoryItem[]
  itemsLoading: boolean
  onSubmit: (itemId: string, qty: string, reason: string) => void
  requireReason: boolean
  isPending: boolean
}) {
  const [itemId, setItemId]   = useState('')
  const [qty,    setQty]      = useState('')
  const [reason, setReason]   = useState('')
  const [touched, setTouched] = useState({ item: false, qty: false, reason: false })

  const touch = (f: keyof typeof touched) => setTouched((p) => ({ ...p, [f]: true }))

  const itemErr   = touched.item   && !itemId                                  ? 'Select an item.' : ''
  const qtyErr    = touched.qty    && (!qty || parseFloat(qty) <= 0)           ? 'Enter a positive quantity.' : ''
  const reasonErr = touched.reason && requireReason && reason.trim().length < 5 ? 'Reason must be at least 5 characters.' : ''
  const isValid   = !!itemId && !!qty && parseFloat(qty) > 0
    && (!requireReason || reason.trim().length >= 5)

  const opts = items.map((i) => ({ value: i.id, label: `${i.name} (${i.unit})` }))

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setTouched({ item: true, qty: true, reason: true })
    if (!isValid) return
    onSubmit(itemId, qty, reason)
    // Reset after submit
    setItemId('')
    setQty('')
    setReason('')
    setTouched({ item: false, qty: false, reason: false })
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-4">
      {itemsLoading ? (
        <div className="h-12 rounded-xl bg-cream-alt/60 animate-pulse" />
      ) : (
        <Select
          label={`${label} *`}
          value={itemId}
          onChange={(e) => { setItemId(e.target.value); touch('item') }}
          onBlur={() => touch('item')}
          options={[{ value: '', label: 'Select item…' }, ...opts]}
          disabled={isPending}
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
          disabled={isPending}
          className="w-full rounded-xl border border-cream-alt bg-white px-4 py-3
            text-base text-ink-primary focus:outline-none focus:border-sage-dark
            focus:ring-2 focus:ring-sage-dark/20 disabled:opacity-50"
        />
      </div>
      {qtyErr && <p className="text-sm text-status-failed -mt-2">{qtyErr}</p>}

      {requireReason && (
        <div>
          <label className="block text-sm font-medium text-ink-secondary mb-1.5">
            Reason * <span className="font-normal text-ink-tertiary">(min 5 chars)</span>
          </label>
          <textarea
            rows={3}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            onBlur={() => touch('reason')}
            disabled={isPending}
            placeholder="e.g. Fridge failure overnight, chicken spoiled"
            className="w-full rounded-xl border border-cream-alt bg-white px-4 py-3
              text-sm text-ink-primary focus:outline-none focus:border-sage-dark
              focus:ring-2 focus:ring-sage-dark/20 disabled:opacity-50 resize-none"
          />
          {reasonErr && <p className="text-sm text-status-failed mt-1">{reasonErr}</p>}
        </div>
      )}

      <button
        type="submit"
        disabled={isPending}
        className={[
          'w-full py-4 rounded-2xl text-base font-semibold transition-all',
          'bg-sage-dark text-cream-card hover:bg-sage-dark/90 active:scale-[0.99]',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sage-dark focus-visible:ring-offset-2',
          'disabled:opacity-50 disabled:cursor-not-allowed',
        ].join(' ')}
      >
        {isPending ? (
          <span className="flex items-center justify-center gap-2">
            <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" strokeOpacity="0.3"/>
              <path d="M21 12a9 9 0 01-9 9" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            </svg>
            Saving…
          </span>
        ) : 'Record'}
      </button>
    </form>
  )
}

export default function QuickEntryScreen() {
  const addToast  = useToastStore((s) => s.addToast)
  const user      = useAuthStore((s) => s.user)
  const roleLevel = user?.role_level ?? 0
  const [tab, setTab] = useState<Tab>(roleLevel >= 5 ? 'spoilage' : 'staff-meal')

  const { data: items, isLoading: itemsLoading } = useQuery<InventoryItem[]>({
    queryKey: ['inventory-items'],
    queryFn: () => api.get<InventoryItem[]>('/inventory/items').then((r) => r.data),
  })

  const staffFoodItems = useMemo(() => (items ?? []).filter((i) => i.is_staff_food), [items])
  const allItems       = items ?? []

  const [spoilageKey,  setSpoilageKey]  = useState(genKey)
  const [mealKey,      setMealKey]      = useState(genKey)

  const spoilageMutation = useMutation({
    mutationFn: ({ itemId, qty, reason }: { itemId: string; qty: string; reason: string }) =>
      api.post<MovementResponse>('/inventory/movements/spoilage', {
        item_id:         itemId,
        quantity:        parseFloat(qty),
        notes:           reason,
        idempotency_key: spoilageKey,
      }).then((r) => r.data),
    onSuccess: (data) => {
      addToast({ type: 'success', message: `Spoilage recorded: ${data.quantity} of ${data.item}.` })
      setSpoilageKey(genKey())
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
        ?? 'Spoilage not saved. Check connection and retry.'
      addToast({ type: 'error', message: msg })
    },
  })

  const mealMutation = useMutation({
    mutationFn: ({ itemId, qty }: { itemId: string; qty: string }) =>
      api.post<MovementResponse>('/inventory/movements/staff-meal', {
        item_id:         itemId,
        quantity:        parseFloat(qty),
        idempotency_key: mealKey,
      }).then((r) => r.data),
    onSuccess: (data) => {
      addToast({ type: 'success', message: `Staff meal recorded: ${data.quantity} of ${data.item}.` })
      setMealKey(genKey())
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
        ?? 'Staff meal not saved. Check connection and retry.'
      addToast({ type: 'error', message: msg })
    },
  })

  return (
    <div className="p-4 max-w-md mx-auto space-y-5">

      <div>
        <h1 className="text-xl font-bold text-ink-primary">Quick Entry</h1>
        <p className="text-sm text-ink-tertiary">Log spoilage or staff meals</p>
      </div>

      {/* ── Tab bar ─────────────────────────────────────────────── */}
      <div className="flex gap-1 bg-cream-alt/50 rounded-xl p-1">
        {roleLevel >= 5 && (
          <button
            onClick={() => setTab('spoilage')}
            className={[
              'flex-1 py-2 rounded-lg text-xs font-medium transition-all',
              tab === 'spoilage'
                ? 'bg-cream-card shadow-sm text-ink-primary'
                : 'text-ink-tertiary hover:text-ink-secondary',
            ].join(' ')}
          >
            Spoilage
          </button>
        )}
        <button
          onClick={() => setTab('staff-meal')}
          className={[
            'flex-1 py-2 rounded-lg text-xs font-medium transition-all',
            tab === 'staff-meal'
              ? 'bg-cream-card shadow-sm text-ink-primary'
              : 'text-ink-tertiary hover:text-ink-secondary',
          ].join(' ')}
        >
          Staff Meal
        </button>
      </div>

      {/* ── SPOILAGE TAB (level 5+ only) ────────────────────────── */}
      {tab === 'spoilage' && roleLevel >= 5 && (
        <ItemQtyForm
          label="Item"
          items={allItems}
          itemsLoading={itemsLoading}
          requireReason={true}
          isPending={spoilageMutation.isPending}
          onSubmit={(itemId, qty, reason) =>
            spoilageMutation.mutate({ itemId, qty, reason })
          }
        />
      )}

      {/* ── STAFF MEAL TAB (level 1+) ────────────────────────────── */}
      {tab === 'staff-meal' && (
        staffFoodItems.length === 0 && !itemsLoading ? (
          <p className="text-center text-sm text-ink-tertiary py-6">
            No staff-food items configured yet. Ask your manager.
          </p>
        ) : (
          <ItemQtyForm
            label="Staff-food item"
            items={staffFoodItems}
            itemsLoading={itemsLoading}
            requireReason={false}
            isPending={mealMutation.isPending}
            onSubmit={(itemId, qty) =>
              mealMutation.mutate({ itemId, qty })
            }
          />
        )
      )}
    </div>
  )
}
