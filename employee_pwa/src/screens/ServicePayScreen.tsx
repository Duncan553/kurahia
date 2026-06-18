import { useState, useMemo } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Skeleton, EmptyState, Button, useToastStore } from '@shared'
import { useAuthStore } from '../stores/authStore'
import api from '../lib/axios'

interface MenuItem { id: string; name: string; price: string; category: string | null }

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
  const idem = useState(() => crypto.randomUUID())[0]

  const { data: items = [], isLoading } = useQuery<MenuItem[]>({
    queryKey: ['service-menu', dept],
    queryFn: () =>
      api.get<MenuItem[]>(`/menu/items?dept_name=${encodeURIComponent(dept ?? '')}`).then(r => r.data),
    staleTime: 5 * 60_000,
    enabled: !!dept,
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
      if (!pay.amount || isNaN(paid) || paid <= 0)
        throw new Error('Enter the amount collected.')
      if (paid < total)
        throw new Error(`Amount KSh ${paid.toLocaleString()} is less than total KSh ${total.toLocaleString()}.`)
      const orderItems = Object.entries(draft)
        .filter(([, q]) => q > 0)
        .map(([menu_item_id, quantity]) => ({ menu_item_id, quantity }))
      const { data: tab }   = await api.post('/tabs', { idempotency_key: idem })
      const { data: order } = await api.post('/orders', { tab_id: tab.id, items: orderItems })
      await api.post(`/orders/${order.id}/send`)
      await api.post(`/tabs/${tab.id}/payments`, {
        method: pay.method, amount: String(total),
        idempotency_key: crypto.randomUUID(),
      })
      await api.post(`/tabs/${tab.id}/close`)
    },
    onSuccess: () => {
      setDraft({}); setPay(p => ({ ...p, amount: '' })); setStage('select')
      addToast({ type: 'success', message: 'Payment recorded.' })
    },
    onError: (e) => {
      const msg = e instanceof Error ? e.message : extractErr(e)
      addToast({ type: 'error', message: msg })
    },
  })

  return (
    <div className="p-4 max-w-lg mx-auto space-y-4">
      <h1 className="text-xl font-bold font-serif text-white">{dept ?? 'Services'}</h1>

      {isLoading && <div className="space-y-2">{[1,2,3].map(i => <Skeleton key={i} variant="row" />)}</div>}

      {!isLoading && items.length === 0 && (
        <EmptyState
          icon={<svg width="40" height="40" viewBox="0 0 40 40" fill="none" aria-hidden="true">
            <circle cx="20" cy="20" r="14" stroke="currentColor" strokeWidth="1.5"/>
            <path d="M14 20h12M20 14v12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
          </svg>}
          title={`No services set up for ${dept ?? 'this department'} yet. Ask your manager to add menu items.`}
        />
      )}

      {/* Service picker */}
      {stage === 'select' && items.length > 0 && (
        <>
          <div className="space-y-2">
            {items.map(item => {
              const qty = draft[item.id] ?? 0
              return (
                <div key={item.id}
                  className="flex items-center gap-3 p-4 rounded-2xl border border-white/10 bg-transparent">
                  <div className="flex-1 min-w-0">
                    <p className="font-semibold text-white">{item.name}</p>
                    <p className="text-sm text-slate-400/50 tabular-nums">{kes(item.price)} / person</p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {qty > 0 && (
                      <>
                        <button
                          onClick={() => setDraft(d => ({ ...d, [item.id]: Math.max(0, (d[item.id] ?? 0) - 1) }))}
                          className="w-9 h-9 rounded-full bg-white/5 text-white font-bold
                            flex items-center justify-center">−</button>
                        <span className="w-6 text-center font-bold tabular-nums">{qty}</span>
                      </>
                    )}
                    <button
                      onClick={() => setDraft(d => ({ ...d, [item.id]: (d[item.id] ?? 0) + 1 }))}
                      className="w-9 h-9 rounded-full bg-primary-dark text-cream-card font-bold
                        flex items-center justify-center">+</button>
                  </div>
                </div>
              )
            })}
          </div>

          {draftCount > 0 && (
            <div className="border-t border-white/10 pt-4 space-y-3">
              <div className="flex justify-between items-center">
                <span className="text-sm text-slate-300/70">
                  {draftCount} person{draftCount !== 1 ? 's' : ''}
                </span>
                <span className="font-bold tabular-nums">{kes(total)}</span>
              </div>
              <Button variant="primary" size="lg" className="w-full" onClick={() => setStage('pay')}>
                Proceed to Payment →
              </Button>
            </div>
          )}
        </>
      )}

      {/* Payment stage */}
      {stage === 'pay' && (
        <div className="space-y-4">
          <div className="p-4 rounded-2xl border border-white/10 bg-transparent">
            <p className="text-sm text-slate-400/50 mb-1">Total to collect</p>
            <p className="text-2xl font-bold tabular-nums text-white">{kes(total)}</p>
          </div>

          <div className="grid grid-cols-2 gap-2">
            {METHODS.map(m => (
              <button key={m} onClick={() => setPay(p => ({ ...p, method: m }))}
                className={`py-3 rounded-xl text-sm font-semibold border transition-colors ${
                  pay.method === m
                    ? 'bg-primary-dark text-cream-card border-primary-dark'
                    : 'bg-transparent text-slate-300/70 border-white/10 hover:border-primary-dark/50'
                }`}>
                {m === 'BANK_TRANSFER' ? 'Bank' : m.charAt(0) + m.slice(1).toLowerCase()}
              </button>
            ))}
          </div>

          <div className="space-y-2">
            <label htmlFor="service-pay-amount" className="sr-only">Amount received (KSh)</label>
            <input
              id="service-pay-amount"
              type="number" min="0" step="0.01" inputMode="decimal"
              placeholder={`Amount received (KSh)`}
              value={pay.amount}
              onChange={e => setPay(p => ({ ...p, amount: e.target.value }))}
              className="w-full rounded-xl border border-white/10 bg-transparent px-4 py-3
                text-base text-white focus:outline-none focus:border-primary-dark"
            />
            <button
              type="button"
              onClick={() => setPay(p => ({ ...p, amount: String(total) }))}
              className="w-full py-2 rounded-xl text-sm font-semibold border border-white/10
                text-slate-300/70 hover:bg-white/5 transition-colors">
              Exact — {kes(total)}
            </button>
          </div>

          <div className="flex gap-2">
            <Button variant="ghost" size="lg" className="flex-1" onClick={() => setStage('select')}>
              ← Back
            </Button>
            <Button variant="primary" size="lg" className="flex-1" loading={checkoutMut.isPending}
              onClick={() => checkoutMut.mutate()}>
              Confirm &amp; Pay
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
