import { useParams, useNavigate } from 'react-router-dom'
import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { Skeleton, Button, useToastStore, SearchInput, Modal } from '@shared'
import api from '../lib/axios'

interface MenuItem {
  id: string; name: string; price: string; category: string | null
  prep_station: string; in_stock: boolean | null; image_path: string | null
}
interface OrderItem { id: string; name: string | null; quantity: string; status: string; notes: string | null }
interface TabDetail {
  id: string; reference: string | null; status: string; balance: string
  charges: { id: string; description: string; amount: string }[]
  payments: { id: string; method: string; amount: string }[]
  orders: { id: string; status: string; items: OrderItem[] }[]
}

const ITEM_BADGE: Record<string, { bg: string; icon: string }> = {
  PENDING:   { bg: 'bg-white/5 text-ink-tertiary',            icon: '◌' },
  RECEIVED:  { bg: 'bg-status-pending/10 text-status-pending',  icon: '◐' },
  READY:     { bg: 'bg-status-paid/10 text-status-paid',        icon: '✓' },
  SERVED:    { bg: 'bg-white/5 text-ink-tertiary',            icon: '✓' },
  CANCELLED: { bg: 'bg-status-failed/10 text-status-failed',    icon: '×' },
}

const kes = (v: string | number) =>
  `KSh ${parseFloat(String(v)).toLocaleString('en-KE', { minimumFractionDigits: 0 })}`
const extractErr = (e: unknown) =>
  (e as { response?: { data?: { error?: string } } })?.response?.data?.error ?? 'Something went wrong.'
const METHODS = ['CASH', 'MPESA', 'CARD', 'BANK_TRANSFER'] as const

function StationBadge({ station }: { station: string }) {
  const label = station === 'KITCHEN' ? 'Kitchen' : station === 'BAR' ? 'Bar' : 'Self-serve'
  const cls   = station === 'KITCHEN'
    ? 'bg-status-pending/10 text-status-pending'
    : station === 'BAR'
      ? 'bg-primary-light/20 text-primary-dark'
      : 'bg-white/5 text-ink-tertiary'
  return (
    <span className={`text-[9px] font-bold uppercase px-1.5 py-0.5 rounded ${cls}`}>
      {label}
    </span>
  )
}

export default function WaiterTabDetailScreen() {
  const { id: tabId } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const addToast = useToastStore(s => s.addToast)

  const [draft, setDraft] = useState<Record<string, number>>({})
  const [draftNotes, setDraftNotes] = useState<Record<string, string>>({})
  const [mobilePane, setMobilePane] = useState<'menu' | 'order'>('menu')
  const [entryChoice, setEntryChoice] = useState<'pending' | 'menu' | 'order'>('pending')
  const [searchQ, setSearchQ] = useState('')
  const [activeCat, setActiveCat] = useState('All')
  const [pay, setPay] = useState({ method: 'CASH' as string, amount: '' })
  const [idem, setIdem] = useState(() => crypto.randomUUID())
  const [cancelId, setCancelId] = useState<string | null>(null)

  // ── Data ────────────────────────────────────────────────────────────────

  const { data: tab, isLoading } = useQuery<TabDetail>({
    queryKey: ['tab', tabId],
    queryFn: () => api.get<TabDetail>(`/tabs/${tabId}`).then(r => r.data),
    refetchInterval: 15_000,
  })

  const { data: items = [], isLoading: menuLoading } = useQuery<MenuItem[]>({
    queryKey: ['menu-items'],
    queryFn: () => api.get<MenuItem[]>('/menu/items').then(r => r.data),
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
    select: (all) => all.filter(i => i.prep_station === 'KITCHEN' || i.prep_station === 'BAR'),
  })

  // ── Derived ─────────────────────────────────────────────────────────────

  const categories = useMemo(() => {
    const cats = [...new Set(items.map(i => i.category ?? 'Other'))]
    return ['All', ...cats.sort()]
  }, [items])

  const filteredItems = useMemo(() => {
    let list = items
    if (activeCat !== 'All') list = list.filter(i => (i.category ?? 'Other') === activeCat)
    if (searchQ) list = list.filter(i => i.name.toLowerCase().includes(searchQ.toLowerCase()))
    return list
  }, [items, activeCat, searchQ])

  const draftEntries = useMemo(() =>
    Object.entries(draft).filter(([, q]) => q > 0).map(([id, qty]) => {
      const item = items.find(i => i.id === id)
      return { id, qty, name: item?.name ?? '?', price: parseFloat(item?.price ?? '0'), station: item?.prep_station ?? '' }
    })
  , [draft, items])

  const draftTotal = draftEntries.reduce((s, e) => s + e.price * e.qty, 0)
  const draftCount = draftEntries.reduce((s, e) => s + e.qty, 0)
  const bal = parseFloat(tab?.balance ?? '0')
  const allOrderItems = (tab?.orders ?? []).flatMap(o => o.items)

  // ── Mutations ───────────────────────────────────────────────────────────

  const sendMut = useMutation({
    mutationFn: async () => {
      const orderItems = draftEntries.map(e => ({
        menu_item_id: e.id, quantity: e.qty,
        ...(draftNotes[e.id] ? { notes: draftNotes[e.id] } : {}),
      }))
      const { data: order } = await api.post('/orders', { tab_id: tabId, items: orderItems })
      await api.post(`/orders/${order.id}/send`)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['tab', tabId] })
      qc.invalidateQueries({ queryKey: ['my-tabs'] })
      setDraft({})
      setDraftNotes({})
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
      setCancelId(null)
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

  // ── Helpers ─────────────────────────────────────────────────────────────

  function addItem(id: string) {
    setDraft(d => ({ ...d, [id]: (d[id] ?? 0) + 1 }))
  }
  function decItem(id: string) {
    setDraft(d => {
      const next = (d[id] ?? 0) - 1
      if (next <= 0) { const { [id]: _, ...rest } = d; return rest }
      return { ...d, [id]: next }
    })
  }

  if (isLoading) return (
    <div className="p-4 space-y-3">{[1,2,3,4].map(i => <Skeleton key={i} variant="row" />)}</div>
  )

  // ── Menu pane ───────────────────────────────────────────────────────────

  const menuPane = (
    <div className="flex flex-col h-full">
      {/* Category tabs */}
      <div className="shrink-0 px-3 pt-3 pb-2 overflow-x-auto flex gap-2 scrollbar-hide">
        {categories.map(cat => (
          <button key={cat} onClick={() => setActiveCat(cat)}
            className={`px-3 py-1.5 rounded-full text-xs font-semibold whitespace-nowrap transition-colors shrink-0 ${
              activeCat === cat
                ? 'bg-ink-primary text-[#f9dcd5]'
                : 'bg-white/5 text-ink-secondary hover:bg-cream-deep'
            }`}>
            {cat}
          </button>
        ))}
      </div>

      {/* Search */}
      <div className="shrink-0 px-3 pb-2">
        <SearchInput value={searchQ} onChange={v => { setSearchQ(v); if (v) setActiveCat('All') }}
          placeholder="Search menu…" label="Search menu items" />
      </div>

      {/* Item grid */}
      <div className="flex-1 overflow-y-auto px-3 pb-4">
        {menuLoading ? (
          <div className="grid grid-cols-2 gap-4">
            {[1,2,3,4,5,6].map(i => <div key={i} className="h-24 rounded-2xl bg-white/5 animate-pulse" />)}
          </div>
        ) : filteredItems.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 gap-2">
            {searchQ ? (
              <p className="text-sm text-ink-tertiary text-center">
                No results for &lsquo;{searchQ}&rsquo; &middot; Hakuna kitu
              </p>
            ) : items.length === 0 ? (
              <p className="text-sm text-ink-tertiary text-center">
                No menu items yet &middot; Ask manager to add items
              </p>
            ) : (
              <p className="text-sm text-ink-tertiary text-center">
                No items in this category
              </p>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            {filteredItems.map(item => {
              const qty = draft[item.id] ?? 0
              const soldOut = item.in_stock === false
              return (
                <motion.button
                  key={item.id}
                  whileTap={soldOut ? undefined : { scale: 0.96 }}
                  whileHover={soldOut ? undefined : { y: -3 }}
                  onClick={() => !soldOut && addItem(item.id)}
                  disabled={soldOut}
                  aria-label={soldOut ? `${item.name} — sold out` : `Add ${item.name} to order`}
                  className={`relative text-left rounded-2xl overflow-hidden
                    focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#fa5c29]
                    transition-all glass-card
                    ${soldOut ? 'opacity-40 cursor-not-allowed' : 'hover:shadow-xl hover:border-white/15'}`}
                >
                  {/* Photo area */}
                  <div className="h-24 bg-gradient-to-br from-white/5 to-transparent flex items-center justify-center overflow-hidden">
                    {item.image_path ? (
                      <img src={item.image_path} alt={item.name}
                        className="w-full h-full object-cover" />
                    ) : (
                      <svg width="32" height="32" viewBox="0 0 24 24" fill="none" className="opacity-30 text-ink-tertiary">
                        <path d="M3 6l3 6v8M8 6c0 3-1.5 5-3 6M12 3v18M16 6c0 3 1.5 5 3 6M21 6l-3 6v8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                      </svg>
                    )}
                    {soldOut && (
                      <div className="absolute inset-0 bg-[rgba(30,16,12,0.6)] flex items-center justify-center">
                        <span className="text-xs font-bold text-[#f9dcd5]/80 uppercase tracking-wider">Sold Out</span>
                      </div>
                    )}
                  </div>
                  {/* Info */}
                  <div className="p-4">
                    <p className={`text-sm font-semibold text-[#f9dcd5] leading-snug ${soldOut ? 'line-through' : ''}`}>
                      {item.name}
                    </p>
                    <div className="flex items-center justify-between gap-1 mt-1">
                      <p className="text-xs tabular-nums font-bold text-[#ffb59f]">
                        {soldOut ? '—' : kes(item.price)}
                      </p>
                      <StationBadge station={item.prep_station} />
                    </div>
                  </div>
                  {qty > 0 && (
                    <span className="absolute top-2 right-2 min-w-[24px] h-[24px] rounded-full
                      bg-[#fa5c29] text-white flex items-center justify-center
                      text-[11px] font-bold tabular-nums px-1 shadow-lg">
                      {qty}
                    </span>
                  )}
                </motion.button>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )

  // ── Order pane ──────────────────────────────────────────────────────────

  const orderPane = (
    <div className="flex flex-col h-full">
      {/* Tab header */}
      <div className="shrink-0 px-4 pt-4 pb-3 border-b border-white/10">
        <div className="flex items-center justify-between">
          <div>
            <p className="font-bold text-[#f9dcd5] text-lg">{tab?.reference ?? 'Walk-in'}</p>
            <p className="text-xs text-ink-tertiary">Tab #{tabId?.slice(0, 8)}</p>
          </div>
          <span className={`text-sm font-bold tabular-nums px-2 py-1 rounded-lg ${
            bal > 0 ? 'bg-status-failed/10 text-status-failed' : 'bg-status-paid/10 text-status-paid'
          }`}>
            {bal < 0 ? `Credit ${kes(-bal)}` : kes(tab?.balance ?? '0')}
          </span>
        </div>
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">

        {/* Draft items */}
        {draftEntries.length > 0 && (
          <div>
            <p className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary mb-2">New Order</p>
            <AnimatePresence mode="popLayout">
              {draftEntries.map(e => (
                <motion.div key={e.id}
                  layout
                  initial={{ opacity: 0, y: -8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, height: 0, marginBottom: 0 }}
                  transition={{ duration: 0.2 }}
                  className="flex items-center gap-2 py-2 border-b border-white/10 last:border-0"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-[#f9dcd5] truncate">{e.name}</p>
                    <p className="text-xs text-ink-tertiary tabular-nums">{kes(e.price)} each</p>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <motion.button whileTap={{ scale: 0.85 }}
                      aria-label={`Decrease ${e.name} quantity`}
                      onClick={() => decItem(e.id)}
                      className="w-7 h-7 rounded-full bg-white/5 text-[#f9dcd5] font-bold text-sm
                        flex items-center justify-center">−</motion.button>
                    <span className="w-5 text-center text-sm font-bold tabular-nums">{e.qty}</span>
                    <motion.button whileTap={{ scale: 0.85 }}
                      aria-label={`Increase ${e.name} quantity`}
                      onClick={() => addItem(e.id)}
                      className="w-7 h-7 rounded-full bg-[#fa5c29] text-white font-bold text-sm
                        flex items-center justify-center">+</motion.button>
                  </div>
                  <span className="text-sm font-bold tabular-nums text-[#f9dcd5] w-16 text-right shrink-0">
                    {kes(e.price * e.qty)}
                  </span>
                  <div className="w-full mt-1">
                    <input
                      type="text" maxLength={200}
                      placeholder="Add note (e.g. no onions)"
                      aria-label={`Note for ${e.name}`}
                      value={draftNotes[e.id] ?? ''}
                      onChange={ev => setDraftNotes(n => ({ ...n, [e.id]: ev.target.value }))}
                      className="w-full text-xs rounded-lg border border-white/10 bg-transparent px-2 py-1.5
                        text-ink-secondary placeholder:text-ink-tertiary/50
                        focus:outline-none focus:border-[#fa5c29]"
                    />
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>
            <div className="flex justify-between items-center pt-3">
              <span className="text-sm text-ink-secondary">{draftCount} item{draftCount !== 1 ? 's' : ''}</span>
              <span className="text-base font-bold tabular-nums text-[#f9dcd5]">{kes(draftTotal)}</span>
            </div>
          </div>
        )}

        {draftEntries.length === 0 && allOrderItems.length === 0 && (
          <div className="flex flex-col items-center justify-center py-12 gap-2">
            <p className="text-sm text-ink-tertiary text-center">
              Tap menu items to start the order &middot; Karibu
            </p>
          </div>
        )}

        {/* Existing order items */}
        {allOrderItems.length > 0 && (
          <div>
            <p className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary mb-2">Kitchen / Bar</p>
            {allOrderItems.map(oi => {
              const badge = ITEM_BADGE[oi.status] ?? ITEM_BADGE.PENDING
              return (
                <div key={oi.id} className="flex items-center gap-2 py-2 border-b border-white/10 last:border-0">
                  <div className="flex-1 min-w-0">
                    <span className="text-sm text-ink-secondary truncate block">
                      {oi.quantity}× {oi.name}
                    </span>
                    {oi.notes && (
                      <span className="text-xs italic text-ink-tertiary block truncate">
                        {oi.notes}
                      </span>
                    )}
                  </div>
                  <span className={`text-[9px] font-bold uppercase px-1.5 py-0.5 rounded ${badge.bg}`}>
                    {badge.icon} {oi.status}
                  </span>
                  {oi.status === 'READY' && (
                    <motion.button whileTap={{ scale: 0.92 }}
                      onClick={() => itemMut.mutate({ id: oi.id, action: 'serve' })}
                      disabled={itemMut.isPending}
                      className="px-3 py-1.5 rounded-lg text-xs font-semibold
                        bg-[#fa5c29] text-white disabled:opacity-50">
                      Served ✓
                    </motion.button>
                  )}
                  {(oi.status === 'PENDING' || oi.status === 'RECEIVED') && (
                    <motion.button whileTap={{ scale: 0.92 }}
                      onClick={() => setCancelId(oi.id)}
                      disabled={itemMut.isPending}
                      aria-label={`Cancel ${oi.name}`}
                      className="px-3 py-1.5 rounded-lg text-xs font-semibold
                        border border-status-failed/40 text-status-failed disabled:opacity-50">
                      Cancel
                    </motion.button>
                  )}
                </div>
              )
            })}
          </div>
        )}

        {/* Charges */}
        {(tab?.charges ?? []).length > 0 && (
          <div>
            <p className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary mb-2">Charges</p>
            {tab!.charges.map(c => (
              <div key={c.id} className="flex justify-between py-2 border-b border-white/10 last:border-0">
                <span className="text-sm text-ink-secondary">{c.description}</span>
                <span className="text-sm tabular-nums font-semibold">{kes(c.amount)}</span>
              </div>
            ))}
          </div>
        )}

        {/* Payments */}
        {(tab?.payments ?? []).length > 0 && (
          <div>
            <p className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary mb-2">Payments</p>
            {tab!.payments.map(p => (
              <div key={p.id} className="flex justify-between py-2 border-b border-white/10 last:border-0">
                <span className="text-sm text-ink-secondary">{p.method}</span>
                <span className="text-sm tabular-nums font-semibold text-status-paid">−{kes(p.amount)}</span>
              </div>
            ))}
          </div>
        )}

        {/* Balance */}
        <div className="flex justify-between items-center p-3 rounded-xl glass-card text-ink-primary">
          <span className="font-semibold text-sm">{bal < 0 ? 'Band credit left' : 'Balance due'}</span>
          <span className="text-lg font-bold tabular-nums">{bal < 0 ? kes(-bal) : kes(tab?.balance ?? '0')}</span>
        </div>

        {/* Payment form */}
        {bal > 0 && tab?.status !== 'CLOSED' && (
          <div className="space-y-3">
            <p className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary">Record Payment</p>
            <div className="grid grid-cols-2 gap-4">
              {METHODS.map(m => (
                <button key={m} onClick={() => setPay(p => ({ ...p, method: m }))}
                  className={`py-2 rounded-xl text-sm font-semibold border transition-colors ${
                    pay.method === m
                      ? 'bg-[#fa5c29] text-white border-[#fa5c29]'
                      : 'bg-transparent text-ink-secondary border-white/10 hover:border-[#fa5c29]/50'
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
              className="w-full rounded-xl border border-white/10 bg-transparent px-4 py-3
                text-base text-[#f9dcd5] focus:outline-none focus:border-[#fa5c29]"
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

      {/* Sticky send bar */}
      {draftCount > 0 && (
        <div className="shrink-0 p-4 border-t border-white/10 bg-transparent">
          <Button variant="primary" size="lg" className="w-full"
            loading={sendMut.isPending} onClick={() => sendMut.mutate()}>
            Send Order &middot; {kes(draftTotal)}
          </Button>
        </div>
      )}
    </div>
  )

  // ── Cancel confirmation modal ──────────────────────────────────────────

  const cancelItem = cancelId ? allOrderItems.find(oi => oi.id === cancelId) : null
  const cancelModal = (
    <Modal open={!!cancelId} onClose={() => setCancelId(null)} title="Cancel Item">
      {cancelItem && (
        <div className="space-y-4">
          <p className="text-sm text-ink-secondary">
            Cancel <strong>{cancelItem.quantity}× {cancelItem.name}</strong>?
            {cancelItem.status === 'RECEIVED' && ' The kitchen has already started preparing this.'}
          </p>
          <div className="flex gap-2">
            <Button variant="ghost" size="md" className="flex-1" onClick={() => setCancelId(null)}>
              Keep
            </Button>
            <Button variant="primary" size="md" className="flex-1 !bg-status-failed"
              loading={itemMut.isPending}
              onClick={() => itemMut.mutate({ id: cancelId!, action: 'cancel' })}>
              Cancel Item
            </Button>
          </div>
        </div>
      )}
    </Modal>
  )

  // ── Entry choice (new tables only) ─────────────────────────────────────

  const isNewTab = allOrderItems.length === 0 && draftEntries.length === 0
  const showEntryPrompt = isNewTab && entryChoice === 'pending'

  // ── Layout ─────────────────────────────────────────────────────────────

  return (
    <div className="h-full flex flex-col">
      {/* Back + header (always visible) */}
      <div className="shrink-0 px-4 py-3 flex items-center gap-3 border-b border-white/10"
        style={{ background: 'rgba(30, 16, 12, 0.85)', backdropFilter: 'blur(12px)' }}>
        <button onClick={() => navigate('/pos/tabs')}
          aria-label="Back to tables"
          className="text-ink-tertiary hover:text-[#f9dcd5] text-sm transition-colors">
          ← Back
        </button>
        <p className="flex-1 font-bold text-[#f9dcd5] truncate">{tab?.reference ?? 'Walk-in'}</p>
        {draftCount > 0 && (
          <span className="text-xs font-bold text-primary-dark tabular-nums">
            {draftCount} item{draftCount !== 1 ? 's' : ''} · {kes(draftTotal)}
          </span>
        )}
      </div>

      {/* Entry choice prompt for new tables */}
      {showEntryPrompt && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="p-6 flex flex-col items-center justify-center flex-1 gap-4"
        >
          <p className="font-serif text-2xl font-bold text-[#f9dcd5] text-center">
            {tab?.reference ?? 'New Table'}
          </p>
          <p className="text-sm text-ink-secondary text-center">How would you like to start?</p>
          <div className="flex gap-3 w-full max-w-xs">
            <motion.button whileTap={{ scale: 0.97 }}
              onClick={() => { setEntryChoice('menu'); navigate(`/pos/menu/${tabId ?? ''}`) }}
              className="flex-1 py-4 rounded-2xl glass-card text-center">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" className="mx-auto mb-1 text-ink-secondary">
                <path d="M2 4h6a4 4 0 014 4v12a3 3 0 00-3-3H2V4zM22 4h-6a4 4 0 00-4 4v12a3 3 0 013-3h7V4z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
              <span className="text-sm font-semibold text-[#f9dcd5]">Show Menu</span>
              <span className="text-[10px] text-ink-tertiary block mt-0.5">Guest wants to browse</span>
            </motion.button>
            <motion.button whileTap={{ scale: 0.97 }}
              onClick={() => setEntryChoice('order')}
              className="flex-1 py-4 rounded-2xl gradient-hero text-center text-white">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" className="mx-auto mb-1 text-[#f9dcd5]">
                <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
              <span className="text-sm font-semibold">Straight to Order</span>
              <span className="text-[10px] text-[#f9dcd5]/70 block mt-0.5">Guest knows what they want</span>
            </motion.button>
          </div>
        </motion.div>
      )}

      {/* Mobile pane switcher (below md) — hidden during entry prompt */}
      <div className={`md:hidden flex border-b border-white/10 shrink-0 ${showEntryPrompt ? 'hidden' : ''}`}>
        {(['menu', 'order'] as const).map(v => (
          <button key={v} onClick={() => setMobilePane(v)}
            className={`flex-1 py-3 text-sm font-semibold capitalize transition-colors ${
              mobilePane === v
                ? 'text-primary-dark border-b-2 border-[#fa5c29]'
                : 'text-ink-tertiary hover:text-ink-secondary'
            }`}>
            {v === 'menu' ? `Menu${draftCount > 0 ? ` (${draftCount})` : ''}` : 'Order'}
          </button>
        ))}
      </div>

      {/* Desktop: two-pane grid. Mobile: single pane. Hidden during entry prompt. */}
      <div className={`flex-1 min-h-0 md:grid md:grid-cols-[3fr_2fr] divide-x divide-cream-alt ${showEntryPrompt ? 'hidden' : 'hidden md:grid'}`}>
        <div className="overflow-hidden">{menuPane}</div>
        <div className="overflow-hidden bg-transparent">{orderPane}</div>
      </div>

      {/* Mobile: single pane — hidden during entry prompt */}
      <div className={`flex-1 min-h-0 md:hidden ${showEntryPrompt ? 'hidden' : ''}`}>
        {mobilePane === 'menu' ? menuPane : orderPane}
      </div>

      {cancelModal}
    </div>
  )
}
