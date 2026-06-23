import { useState, useMemo } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { Skeleton, EmptyState, Button, useToastStore } from '@shared'
import { useAuthStore } from '../stores/authStore'
import api from '../lib/axios'

interface MenuItem { id: string; name: string; price: string; category: string | null }
interface StockItem { id: string; name: string; unit: string; current_stock: string; reorder_level: string; below_reorder: boolean }

const kes = (v: string | number) =>
  `KSh ${parseFloat(String(v)).toLocaleString('en-KE', { minimumFractionDigits: 0 })}`
const extractErr = (e: unknown) =>
  (e as { response?: { data?: { error?: string } } })?.response?.data?.error ?? 'Something went wrong.'
const METHODS = ['CASH', 'MPESA', 'CARD', 'BANK_TRANSFER']

export default function ServicePayScreen() {
  const dept = useAuthStore(s => s.user?.department)
  const addToast = useToastStore(s => s.addToast)

  const [draft, setDraft] = useState<Record<string, number>>({})
  const [pay, setPay] = useState({ method: 'CASH', amount: '' })
  const [stage, setStage] = useState<'select' | 'pay'>('select')
  const [tab, setTab] = useState<'pos' | 'stock' | 'request'>('pos')
  const [requestText, setRequestText] = useState('')
  const idem = useState(() => crypto.randomUUID())[0]

  const { data: items = [], isLoading } = useQuery<MenuItem[]>({
    queryKey: ['service-menu', dept],
    queryFn: () => api.get<MenuItem[]>(`/menu/items?dept_name=${encodeURIComponent(dept ?? '')}`).then(r => r.data),
    staleTime: 5 * 60_000, enabled: !!dept,
  })

  const { data: stockItems = [] } = useQuery<StockItem[]>({
    queryKey: ['service-stock', dept],
    queryFn: () => api.get<StockItem[]>('/inventory/items').then(r => Array.isArray(r.data) ? r.data : []),
    staleTime: 60_000, refetchInterval: 60_000,
  })

  const total = useMemo(() =>
    Object.entries(draft).reduce((sum, [id, qty]) => {
      const item = items.find(i => i.id === id)
      return item ? sum + parseFloat(item.price) * qty : sum
    }, 0)
  , [draft, items])
  const draftCount = Object.values(draft).reduce((s, q) => s + q, 0)

  const checkoutMut = useMutation({
    mutationFn: async () => {
      const paid = parseFloat(pay.amount)
      if (!pay.amount || isNaN(paid) || paid <= 0) throw new Error('Enter the amount collected.')
      if (paid < total) throw new Error(`Amount KSh ${paid.toLocaleString()} is less than total KSh ${total.toLocaleString()}.`)
      const orderItems = Object.entries(draft).filter(([, q]) => q > 0).map(([menu_item_id, quantity]) => ({ menu_item_id, quantity }))
      const { data: newTab } = await api.post('/tabs', { idempotency_key: idem })
      const { data: order } = await api.post('/orders', { tab_id: newTab.id, items: orderItems })
      await api.post(`/orders/${order.id}/send`)
      await api.post(`/tabs/${newTab.id}/payments`, { method: pay.method, amount: String(total), idempotency_key: crypto.randomUUID() })
      await api.post(`/tabs/${newTab.id}/close`)
    },
    onSuccess: () => {
      setDraft({}); setPay(p => ({ ...p, amount: '' })); setStage('select')
      addToast({ type: 'success', message: 'Payment recorded & tab closed.' })
    },
    onError: (e) => addToast({ type: 'error', message: e instanceof Error ? e.message : extractErr(e) }),
  })

  const requestMut = useMutation({
    mutationFn: () => api.post('/suggestions', {
      category: 'MANAGEMENT', subject: `Restock request from ${dept}`,
      body: requestText,
    }),
    onSuccess: () => {
      setRequestText('')
      addToast({ type: 'success', message: 'Request sent to manager.' })
    },
    onError: (e) => addToast({ type: 'error', message: extractErr(e) }),
  })

  const lowStock = stockItems.filter(i => i.below_reorder)
  const deptName = dept ?? 'Services'

  return (
    <div className="min-h-screen p-4 md:p-6">
      <div className="max-w-3xl mx-auto">

        {/* Header */}
        <div className="mb-4">
          <h1 className="text-2xl font-bold font-serif text-white">{deptName}</h1>
          <p className="text-xs text-ink-tertiary mt-0.5">Sell · View Stock · Request Restock</p>
        </div>

        {/* Tab switcher */}
        <div className="flex rounded-xl overflow-hidden border border-white/10 mb-4">
          {([['pos', 'Sell'], ['stock', 'Stock'], ['request', 'Request']] as const).map(([key, label]) => (
            <button key={key} onClick={() => setTab(key)}
              className={`flex-1 py-2.5 text-xs font-semibold transition-colors ${
                tab === key ? 'bg-white/10 text-white' : 'text-ink-tertiary hover:text-ink-secondary'
              }`}>
              {label}
              {key === 'stock' && lowStock.length > 0 && (
                <span className="ml-1 text-status-failed">({lowStock.length})</span>
              )}
            </button>
          ))}
        </div>

        {/* POS Tab */}
        {tab === 'pos' && (
          <>
            {isLoading && <div className="space-y-2">{[1,2,3].map(i => <Skeleton key={i} variant="row" />)}</div>}
            {!isLoading && items.length === 0 && (
              <EmptyState
                icon={
                  <svg width="48" height="48" viewBox="0 0 24 24" fill="none" className="text-ink-tertiary">
                    <path d="M12 2l3.09 6.26L22 9.27l-5 4.87L18.18 21 12 17.77 5.82 21 7 14.14l-5-4.87 6.91-1.01L12 2z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                }
                title={`No services set up for ${deptName} yet. Ask manager to add items.`}
              />
            )}
            {stage === 'select' && items.length > 0 && (
              <>
                <div className="space-y-2">
                  {items.map(item => {
                    const qty = draft[item.id] ?? 0
                    return (
                      <motion.div key={item.id} whileTap={{ scale: 0.98 }}
                        className="flex items-center gap-3 p-4 glass-card">
                        <div className="flex-1 min-w-0">
                          <p className="font-semibold text-white">{item.name}</p>
                          <p className="text-sm text-ink-tertiary tabular-nums">{kes(item.price)}</p>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          {qty > 0 && (
                            <>
                              <button onClick={() => setDraft(d => ({ ...d, [item.id]: Math.max(0, (d[item.id] ?? 0) - 1) }))}
                                className="w-9 h-9 rounded-full bg-white/5 text-white font-bold flex items-center justify-center">−</button>
                              <span className="w-6 text-center font-bold tabular-nums text-white">{qty}</span>
                            </>
                          )}
                          <button onClick={() => setDraft(d => ({ ...d, [item.id]: (d[item.id] ?? 0) + 1 }))}
                            className="w-9 h-9 rounded-full bg-[#fa5c29] text-white font-bold flex items-center justify-center">+</button>
                        </div>
                      </motion.div>
                    )
                  })}
                </div>
                {draftCount > 0 && (
                  <div className="border-t border-white/10 pt-4 mt-4 space-y-3">
                    <div className="flex justify-between items-center">
                      <span className="text-sm text-ink-secondary">{draftCount} item{draftCount !== 1 ? 's' : ''}</span>
                      <span className="text-lg font-bold tabular-nums text-white">{kes(total)}</span>
                    </div>
                    <Button variant="primary" size="lg" className="w-full" onClick={() => setStage('pay')}>
                      Proceed to Payment →
                    </Button>
                  </div>
                )}
              </>
            )}
            {stage === 'pay' && (
              <div className="space-y-4">
                <div className="glass-card p-4 text-center">
                  <p className="text-xs text-ink-tertiary mb-1">Collect</p>
                  <p className="text-3xl font-bold tabular-nums text-white">{kes(total)}</p>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  {METHODS.map(m => (
                    <button key={m} onClick={() => setPay(p => ({ ...p, method: m }))}
                      className={`py-3 rounded-xl text-sm font-semibold border transition-colors ${
                        pay.method === m ? 'bg-[#fa5c29] text-white border-[#fa5c29]' : 'text-ink-secondary border-white/10'
                      }`}>
                      {m === 'BANK_TRANSFER' ? 'Bank' : m.charAt(0) + m.slice(1).toLowerCase()}
                    </button>
                  ))}
                </div>
                <input type="number" min="0" step="0.01" inputMode="decimal"
                  placeholder="Amount received (KSh)"
                  value={pay.amount} onChange={e => setPay(p => ({ ...p, amount: e.target.value }))}
                  className="w-full rounded-xl border border-white/10 bg-transparent px-4 py-3 text-white focus:outline-none focus:border-[#fa5c29]" />
                <button onClick={() => setPay(p => ({ ...p, amount: String(total) }))}
                  className="w-full py-2 rounded-xl text-sm border border-white/10 text-ink-secondary hover:bg-white/5">
                  Exact — {kes(total)}
                </button>
                <div className="flex gap-2">
                  <Button variant="ghost" size="lg" className="flex-1" onClick={() => setStage('select')}>← Back</Button>
                  <Button variant="primary" size="lg" className="flex-1" loading={checkoutMut.isPending}
                    onClick={() => checkoutMut.mutate()}>Confirm</Button>
                </div>
              </div>
            )}
          </>
        )}

        {/* Stock View Tab */}
        {tab === 'stock' && (
          <div className="space-y-3">
            {stockItems.length === 0 ? (
              <p className="text-sm text-ink-tertiary text-center py-8">No stock items for {deptName}</p>
            ) : (
              <>
                {lowStock.length > 0 && (
                  <div className="rounded-xl border border-status-failed/30 bg-status-failed/10 p-3">
                    <p className="text-sm text-status-failed font-semibold">
                      {lowStock.length} item{lowStock.length !== 1 ? 's' : ''} below reorder level
                    </p>
                  </div>
                )}
                {stockItems.map(it => {
                  const stock = parseFloat(it.current_stock)
                  const reorder = parseFloat(it.reorder_level)
                  const pct = reorder > 0 ? Math.min((stock / (reorder * 2)) * 100, 100) : 100
                  return (
                    <div key={it.id} className="glass-card p-3">
                      <div className="flex justify-between text-sm mb-1">
                        <span className="text-white">{it.name}</span>
                        <span className={`tabular-nums font-bold ${it.below_reorder ? 'text-status-failed' : 'text-emerald-400'}`}>
                          {stock} {it.unit}
                        </span>
                      </div>
                      <div className="h-1.5 rounded-full bg-white/5 overflow-hidden">
                        <div className={`h-full rounded-full ${it.below_reorder ? 'bg-status-failed' : 'bg-emerald-500'}`}
                          style={{ width: `${pct}%` }} />
                      </div>
                    </div>
                  )
                })}
              </>
            )}
          </div>
        )}

        {/* Request Tab */}
        {tab === 'request' && (
          <div className="space-y-4">
            <div className="glass-card p-4">
              <p className="text-sm text-white mb-2">Request restock or supplies from the manager:</p>
              <textarea
                rows={4} value={requestText} onChange={e => setRequestText(e.target.value)}
                placeholder="e.g. Need more massage oil, running low on towels..."
                className="w-full rounded-xl border border-white/10 bg-transparent px-4 py-3
                  text-sm text-white placeholder:text-ink-tertiary resize-none
                  focus:outline-none focus:border-[#fa5c29]"
              />
              <Button variant="primary" size="md" className="w-full mt-3"
                loading={requestMut.isPending}
                disabled={!requestText.trim()}
                onClick={() => requestMut.mutate()}>
                Send Request to Manager
              </Button>
            </div>
            <p className="text-xs text-ink-tertiary text-center">
              Your request goes to the manager as a suggestion. They'll handle restocking.
            </p>
          </div>
        )}

      </div>
    </div>
  )
}
