import { useParams, useNavigate } from 'react-router-dom'
import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { Skeleton, Button, useToastStore } from '@shared'
import api from '../lib/axios'

interface MenuItem {
  id: string; name: string; price: string; category: string | null
  prep_station: string; in_stock: boolean | null
}
interface OrderItem { id: string; name: string | null; quantity: string; status: string }
interface TabDetail {
  id: string; reference: string | null; status: string; balance: string
  charges: { id: string; description: string; amount: string }[]
  payments: { id: string; method: string; amount: string }[]
  orders: { id: string; status: string; items: OrderItem[] }[]
}

// Item lifecycle: PENDING/RECEIVED → kitchen/bar working; READY → waiter serves;
// SERVED/CANCELLED → resolved. Tabs only close once every item is resolved.
const ITEM_BADGE: Record<string, string> = {
  PENDING:   'bg-cream-alt text-ink-tertiary',
  RECEIVED:  'bg-status-pending/10 text-status-pending',
  READY:     'bg-status-paid/10 text-status-paid',
  SERVED:    'bg-cream-alt text-ink-tertiary',
  CANCELLED: 'bg-status-failed/10 text-status-failed',
}

const kes = (v: string | number) =>
  `KSh ${parseFloat(String(v)).toLocaleString('en-KE', { minimumFractionDigits: 0 })}`
const extractErr = (e: unknown) =>
  (e as { response?: { data?: { error?: string } } })?.response?.data?.error ?? 'Something went wrong.'
const METHODS = ['CASH', 'MPESA', 'CARD', 'BANK_TRANSFER']

export default function WaiterTabDetailScreen() {
  const { id: tabId } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const addToast = useToastStore(s => s.addToast)

  const [draft, setDraft] = useState<Record<string, number>>({})
  const [view, setView] = useState<'menu' | 'bill'>('menu')
  const [pay, setPay] = useState({ method: 'CASH', amount: '' })
  const [idem, setIdem] = useState(() => crypto.randomUUID())

  const { data: tab, isLoading } = useQuery<TabDetail>({
    queryKey: ['tab', tabId],
    queryFn: () => api.get<TabDetail>(`/tabs/${tabId}`).then(r => r.data),
    refetchInterval: 15_000, // READY badges appear without manual refresh
  })

  const { data: items = [] } = useQuery<MenuItem[]>({
    queryKey: ['menu-items'],
    queryFn: () => api.get<MenuItem[]>('/menu/items').then(r => r.data),
    // Poll every 30s so sold-out items grey immediately; pauses when tab is hidden
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
    // Waiters sell food + drinks only — spa/gym/water services never appear here
    select: (all) => all.filter(i => i.prep_station === 'KITCHEN' || i.prep_station === 'BAR'),
  })

  // Group items by category for the scrollable menu
  const grouped = useMemo(() =>
    items.reduce<Record<string, MenuItem[]>>((acc, item) => {
      const cat = item.category ?? 'Other'
      ;(acc[cat] ??= []).push(item)
      return acc
    }, {})
  , [items])

  const draftTotal = useMemo(() =>
    Object.entries(draft).reduce((sum, [id, qty]) => {
      const item = items.find(i => i.id === id)
      return item ? sum + parseFloat(item.price) * qty : sum
    }, 0)
  , [draft, items])

  const draftCount = Object.values(draft).reduce((s, q) => s + q, 0)
  const bal = parseFloat(tab?.balance ?? '0')

  const sendMut = useMutation({
    mutationFn: async () => {
      const orderItems = Object.entries(draft)
        .filter(([, q]) => q > 0)
        .map(([menu_item_id, quantity]) => ({ menu_item_id, quantity }))
      const { data: order } = await api.post('/orders', { tab_id: tabId, items: orderItems })
      await api.post(`/orders/${order.id}/send`)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tab', tabId] })
      qc.invalidateQueries({ queryKey: ['my-tabs'] })
      setDraft({})
      addToast({ type: 'success', message: 'Order sent to kitchen / bar.' })
    },
    onError: (e) => addToast({ type: 'error', message: extractErr(e) }),
  })

  const payMut = useMutation({
    mutationFn: () =>
      api.post(`/tabs/${tabId}/payments`, { method: pay.method, amount: pay.amount, idempotency_key: idem }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tab', tabId] })
      qc.invalidateQueries({ queryKey: ['my-tabs'] })
      setPay(p => ({ ...p, amount: '' }))
      setIdem(crypto.randomUUID())
      addToast({ type: 'success', message: 'Payment recorded.' })
    },
    onError: (e) => addToast({ type: 'error', message: extractErr(e) }),
  })

  const itemMut = useMutation({
    mutationFn: ({ id, action }: { id: string; action: 'serve' | 'cancel' }) =>
      api.post(`/order-items/${id}/${action}`,
        action === 'cancel' ? { reason: 'Cancelled by waiter' } : undefined),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tab', tabId] })
      qc.invalidateQueries({ queryKey: ['notifications', 'inbox'] })
    },
    onError: (e) => addToast({ type: 'error', message: extractErr(e) }),
  })

  const closeMut = useMutation({
    mutationFn: () => api.post(`/tabs/${tabId}/close`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['my-tabs'] })
      addToast({ type: 'success', message: 'Table closed.' })
      navigate('/pos/tabs')
    },
    onError: (e) => addToast({ type: 'error', message: extractErr(e) }),
  })

  if (isLoading) return (
    <div className="p-4 space-y-3">{[1,2,3,4].map(i => <Skeleton key={i} variant="row" />)}</div>
  )

  return (
    <div className="flex flex-col h-full">

      {/* Header */}
      <div className="px-4 pt-4 pb-2 flex items-center gap-3 border-b border-cream-alt shrink-0">
        <button onClick={() => navigate('/pos/tabs')}
          className="text-ink-tertiary hover:text-ink-primary text-sm">← Back</button>
        <p className="flex-1 font-bold text-ink-primary">{tab?.reference ?? 'Walk-in'}</p>
        {/* Negative balance = unspent band credit (KSh 3,000 gate payment) */}
        <span className={`text-sm font-bold tabular-nums ${bal > 0 ? 'text-status-failed' : 'text-status-paid'}`}>
          {bal < 0 ? `Credit ${kes(-bal)}` : kes(tab?.balance ?? '0')}
        </span>
      </div>

      {/* Menu / Bill tabs */}
      <div className="flex border-b border-cream-alt shrink-0">
        {(['menu', 'bill'] as const).map(v => (
          <button key={v} onClick={() => setView(v)}
            className={`flex-1 py-3 text-sm font-semibold capitalize transition-colors ${
              view === v
                ? 'text-primary-dark border-b-2 border-primary-dark'
                : 'text-ink-tertiary hover:text-ink-secondary'
            }`}>
            {v === 'menu' ? `Menu${draftCount > 0 ? ` (${draftCount})` : ''}` : 'Bill'}
          </button>
        ))}
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto">

        {/* ── Menu ──────────────────────────────────────────── */}
        {view === 'menu' && (
          <div className="p-4 space-y-6 pb-28">
            {Object.entries(grouped).map(([cat, catItems]) => (
              <div key={cat}>
                <p className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary mb-3">{cat}</p>
                <div className="space-y-2">
                  {catItems.map(item => {
                    const qty      = draft[item.id] ?? 0
                    const soldOut  = item.in_stock === false
                    return (
                      <div key={item.id}
                        className={`flex items-center gap-3 p-3 rounded-xl border border-cream-alt bg-cream-card
                          ${soldOut ? 'opacity-50' : ''}`}>
                        <div className="flex-1 min-w-0">
                          <p className={`text-sm font-semibold text-ink-primary ${soldOut ? 'line-through' : ''}`}>
                            {item.name}
                          </p>
                          <p className="text-xs text-ink-tertiary tabular-nums">
                            {soldOut ? 'Sold out' : kes(item.price)}
                          </p>
                        </div>
                        {!soldOut && (
                          <div className="flex items-center gap-2 shrink-0">
                            {qty > 0 && (
                              <>
                                <motion.button whileTap={{ scale: 0.85 }}
                                  aria-label={`Remove one ${item.name}`}
                                  onClick={() => setDraft(d => ({ ...d, [item.id]: Math.max(0, (d[item.id] ?? 0) - 1) }))}
                                  className="w-8 h-8 rounded-full bg-cream-alt text-ink-primary font-bold
                                    flex items-center justify-center">−</motion.button>
                                <span className="w-5 text-center text-sm font-bold tabular-nums">{qty}</span>
                              </>
                            )}
                            <motion.button whileTap={{ scale: 0.85 }}
                              aria-label={`Add ${item.name}`}
                              onClick={() => setDraft(d => ({ ...d, [item.id]: (d[item.id] ?? 0) + 1 }))}
                              className="w-8 h-8 rounded-full bg-primary-dark text-cream-card font-bold
                                flex items-center justify-center">+</motion.button>
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* ── Bill ──────────────────────────────────────────── */}
        {view === 'bill' && (
          <div className="p-4 space-y-4">

            {/* Order items — serve READY items, cancel mistakes. A tab can
                only close once every item is SERVED or CANCELLED. */}
            {(tab?.orders ?? []).some(o => o.items.length > 0) && (
              <div>
                <p className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary mb-2">Kitchen / Bar</p>
                {tab!.orders.flatMap(o => o.items).map(oi => (
                  <div key={oi.id} className="flex items-center gap-2 py-2 border-b border-cream-alt last:border-0">
                    <span className="flex-1 text-sm text-ink-secondary truncate">
                      {oi.quantity}× {oi.name}
                    </span>
                    <span className={`text-[9px] font-bold uppercase px-1.5 py-0.5 rounded ${ITEM_BADGE[oi.status] ?? ''}`}>
                      {oi.status}
                    </span>
                    {oi.status === 'READY' && (
                      <motion.button whileTap={{ scale: 0.92 }}
                        onClick={() => itemMut.mutate({ id: oi.id, action: 'serve' })}
                        disabled={itemMut.isPending}
                        className="px-3 py-1.5 rounded-lg text-xs font-semibold
                          bg-primary-dark text-cream-card disabled:opacity-50">
                        Served ✓
                      </motion.button>
                    )}
                    {(oi.status === 'PENDING' || oi.status === 'RECEIVED') && (
                      <motion.button whileTap={{ scale: 0.92 }}
                        onClick={() => itemMut.mutate({ id: oi.id, action: 'cancel' })}
                        disabled={itemMut.isPending}
                        className="px-3 py-1.5 rounded-lg text-xs font-semibold
                          border border-status-failed/40 text-status-failed disabled:opacity-50">
                        Cancel
                      </motion.button>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Charges */}
            {(tab?.charges ?? []).length > 0 && (
              <div>
                <p className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary mb-2">Charges</p>
                <div>
                  {tab!.charges.map(c => (
                    <div key={c.id} className="flex justify-between py-2 border-b border-cream-alt last:border-0">
                      <span className="text-sm text-ink-secondary">{c.description}</span>
                      <span className="text-sm tabular-nums font-semibold">{kes(c.amount)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Payments */}
            {(tab?.payments ?? []).length > 0 && (
              <div>
                <p className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary mb-2">Payments</p>
                <div>
                  {tab!.payments.map(p => (
                    <div key={p.id} className="flex justify-between py-2 border-b border-cream-alt last:border-0">
                      <span className="text-sm text-ink-secondary">{p.method}</span>
                      <span className="text-sm tabular-nums font-semibold text-status-paid">−{kes(p.amount)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Balance total — negative means the guest still has band credit */}
            <div className="flex justify-between items-center p-3 rounded-xl bg-ink-primary text-cream-card">
              <span className="font-semibold text-sm">{bal < 0 ? 'Band credit left' : 'Balance due'}</span>
              <span className="text-lg font-bold tabular-nums">{bal < 0 ? kes(-bal) : kes(tab?.balance ?? '0')}</span>
            </div>

            {/* Payment form */}
            {bal > 0 && tab?.status !== 'CLOSED' && (
              <div className="space-y-3">
                <p className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary">Record Payment</p>
                <div className="grid grid-cols-2 gap-2">
                  {METHODS.map(m => (
                    <button key={m} onClick={() => setPay(p => ({ ...p, method: m }))}
                      className={`py-2 rounded-xl text-sm font-semibold border transition-colors ${
                        pay.method === m
                          ? 'bg-primary-dark text-cream-card border-primary-dark'
                          : 'bg-cream-card text-ink-secondary border-cream-alt hover:border-primary-dark/50'
                      }`}>
                      {m === 'BANK_TRANSFER' ? 'Bank' : m.charAt(0) + m.slice(1).toLowerCase()}
                    </button>
                  ))}
                </div>
                <input
                  type="number" min="0" step="0.01" inputMode="decimal"
                  placeholder={`Amount (KSh) — due ${kes(bal)}`}
                  value={pay.amount}
                  onChange={e => setPay(p => ({ ...p, amount: e.target.value }))}
                  className="w-full rounded-xl border border-cream-alt bg-cream-card px-4 py-3
                    text-base text-ink-primary focus:outline-none focus:border-primary-dark"
                />
                <Button variant="primary" size="lg" className="w-full" loading={payMut.isPending}
                  onClick={() => payMut.mutate()}>
                  Record Payment
                </Button>
              </div>
            )}

            {/* Close tab */}
            {bal <= 0 && tab?.status !== 'CLOSED' && (
              <Button variant="primary" size="lg" className="w-full" loading={closeMut.isPending}
                onClick={() => closeMut.mutate()}>
                Close Table ✓
              </Button>
            )}

            {tab?.status === 'CLOSED' && (
              <p className="text-center text-sm text-status-paid font-semibold py-2">✓ Table closed</p>
            )}
          </div>
        )}
      </div>

      {/* Sticky send-order bar when draft has items */}
      {view === 'menu' && draftCount > 0 && (
        <div className="shrink-0 p-4 border-t border-cream-alt bg-cream-card">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-ink-secondary">
              {draftCount} item{draftCount !== 1 ? 's' : ''}
            </span>
            <span className="text-sm font-bold tabular-nums">{kes(draftTotal)}</span>
          </div>
          <Button variant="primary" size="lg" className="w-full" loading={sendMut.isPending}
            onClick={() => sendMut.mutate()}>
            Send Order →
          </Button>
        </div>
      )}
    </div>
  )
}
