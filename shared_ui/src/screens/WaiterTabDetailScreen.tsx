import { useParams, useNavigate } from 'react-router-dom'
import { useState, useMemo, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { Skeleton, Button, useToastStore, SearchInput, Modal, ErrorBoundary, Icon, useIsDesktop } from '../index'
import type { IconName } from '../index'
import api from '../lib/axios'
import { useAuthStore } from '../stores/authStore'

const FRONT_DESK_LEVEL = 3   // must match app/reports/routes.py + app/notifications/core.py

interface MenuItem {
  id: string; name: string; price: string; category: string | null
  prep_station: string; in_stock: boolean | null; image_path: string | null
}
interface OrderItem { id: string; name: string | null; quantity: string; status: string; notes: string | null }
interface TabDetail {
  id: string; reference: string | null; status: string; balance: string
  tab_type: string
  charges: { id: string; description: string; amount: string }[]
  payments: { id: string; method: string; amount: string }[]
  orders: { id: string; status: string; items: OrderItem[] }[]
}

// `icon` is now an IconName from the shared icon system, not a text glyph —
// a typo here becomes a TypeScript error instead of a wrong character on screen.
const ITEM_BADGE: Record<string, { bg: string; icon: IconName }> = {
  PENDING:   { bg: 'bg-white/5 text-ink-tertiary',              icon: 'circle' },
  RECEIVED:  { bg: 'bg-status-pending/10 text-status-pending',  icon: 'progress' },
  READY:     { bg: 'bg-status-paid/10 text-status-paid',        icon: 'check' },
  SERVED:    { bg: 'bg-white/5 text-ink-tertiary',              icon: 'check' },
  CANCELLED: { bg: 'bg-status-failed/10 text-status-failed',    icon: 'x' },
}

const kes = (v: string | number) =>
  `KSh ${parseFloat(String(v)).toLocaleString('en-KE', { minimumFractionDigits: 0 })}`
const extractErr = (e: unknown) =>
  (e as { response?: { data?: { error?: string } } })?.response?.data?.error ?? 'Something went wrong.'
const METHODS = ['CASH', 'MPESA', 'CARD', 'BANK_TRANSFER'] as const

/** Fetch a PDF from the backend using the JWT token, then trigger a browser download. */
const downloadPdf = async (url: string, filename: string) => {
  const { useAuthStore } = await import('../stores/authStore')
  const token = useAuthStore.getState().accessToken
  const baseURL = import.meta.env.VITE_API_URL as string
  const res = await fetch(`${baseURL}${url}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: 'Download failed.' }))
    throw new Error(body.error || 'Download failed.')
  }
  const blob = await res.blob()
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = filename
  link.click()
  URL.revokeObjectURL(link.href)
}

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
  const roleLevel = useAuthStore(s => s.user?.role_level ?? 0)
  const canHandleReceipts = roleLevel >= FRONT_DESK_LEVEL
  // JS breakpoint (not a CSS one) — see the comment on the pane switch below:
  // the desktop and mobile layouts are structurally different, so only ONE of
  // them may exist in the DOM at a time. The declaration was missing entirely,
  // which meant this file did not compile.
  const isDesktop = useIsDesktop()

  const [draft, setDraft] = useState<Record<string, number>>({})
  const [draftNotes, setDraftNotes] = useState<Record<string, string>>({})
  const [mobilePane, setMobilePane] = useState<'menu' | 'order'>('menu')
  const [entryChoice, setEntryChoice] = useState<'pending' | 'menu' | 'order'>('pending')
  const [searchQ, setSearchQ] = useState('')
  const [activeStation, setActiveStation] = useState<'ALL' | 'KITCHEN' | 'BAR'>('ALL')
  const [activeCat, setActiveCat] = useState('All')
  const [pay, setPay] = useState({ method: 'CASH' as string, amount: '' })
  const [idem, setIdem] = useState(() => crypto.randomUUID())
  const [cancelId, setCancelId] = useState<string | null>(null)
  const [receiptPhone, setReceiptPhone] = useState('')
  const [showReceiptModal, setShowReceiptModal] = useState(false)

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
    // NONE = self-serve items with no kitchen/bar prep step (spa & gym services,
    // water-activity add-ons). Fetch the superset here; which of them are
    // actually relevant depends on what kind of tab this is — see stationItems.
    select: (all) => all.filter(i => i.prep_station === 'KITCHEN' || i.prep_station === 'BAR' || i.prep_station === 'NONE'),
  })

  // ── Derived ─────────────────────────────────────────────────────────────

  const stationItems = useMemo(() => {
    // A waiter serving a table (WALK_IN) or delivering to a villa (VILLA,
    // billed on that villa's own tab — same food/drink service, different
    // location) only ever orders food and bar. NONE (self-serve spa/water
    // items) only belongs here when the tab came from redeeming a guest's
    // wristband (BAND) — the one path spa/water staff reach this same screen
    // through, via ServicePayScreen's band lookup. Mixing water-activity
    // tickets into a waiter's own table menu was a real reported bug.
    const relevant = tab?.tab_type === 'BAND' ? items : items.filter(i => i.prep_station !== 'NONE')
    if (activeStation === 'ALL') return relevant
    return relevant.filter(i => i.prep_station === activeStation)
  }, [items, activeStation, tab?.tab_type])

  const categories = useMemo(() => {
    const cats = [...new Set(stationItems.map(i => i.category ?? 'Other'))]
    return ['All', ...cats.sort()]
  }, [stationItems])

  const filteredItems = useMemo(() => {
    let list = stationItems
    if (activeCat !== 'All') list = list.filter(i => (i.category ?? 'Other') === activeCat)
    if (searchQ) list = list.filter(i => i.name.toLowerCase().includes(searchQ.toLowerCase()))
    return list
  }, [stationItems, activeCat, searchQ])

  const draftEntries = useMemo(() =>
    Object.entries(draft).filter(([, q]) => q > 0).map(([id, qty]) => {
      const item = items.find(i => i.id === id)
      return { id, qty, name: item?.name ?? '?', price: parseFloat(item?.price ?? '0'), station: item?.prep_station ?? '' }
    })
  , [draft, items])

  const draftTotal = draftEntries.reduce((s, e) => s + e.price * e.qty, 0)
  const draftCount = draftEntries.reduce((s, e) => s + e.qty, 0)
  const bal = parseFloat(tab?.balance ?? '0')

  // Auto-fill the exact amount owed (charges minus payments minus any band
  // credit already applied — `bal` already IS that math) as soon as it's
  // known, instead of making staff type it or hunt for the "Exact" button.
  // Re-fires after a payment posts and `bal` drops to a smaller remainder
  // (e.g. a deliberate partial payment), so the field always tracks what's
  // actually still owed — but never overwrites an amount staff already typed.
  useEffect(() => {
    if (bal > 0) setPay(p => (p.amount ? p : { ...p, amount: String(bal) }))
  }, [bal])

  const allOrderItems = (tab?.orders ?? []).flatMap(o => o.items)
  // Mirrors the backend's is_tab_closable (app/services/tab.py): only SERVED/CANCELLED
  // are terminal. Balance alone isn't enough — a PENDING/RECEIVED/READY item still
  // blocks close, and the button used to show as ready anyway, then 400 on tap.
  const allItemsResolved = allOrderItems.every(oi => oi.status === 'SERVED' || oi.status === 'CANCELLED')

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

  const receiptMut = useMutation({
    mutationFn: () =>
      api.post('/notifications/send-receipt', { tab_id: tabId, guest_phone: receiptPhone }),
    onSuccess: (res) => {
      const ch = res.data?.channel ?? 'unknown'
      addToast({ type: 'success', message: `Receipt sent via ${ch}.` })
      setShowReceiptModal(false)
      setReceiptPhone('')
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
      {/* Kitchen / Bar station toggle */}
      <div className="shrink-0 px-3 pt-3 pb-1 flex gap-1">
        {([['ALL', 'All'], ['KITCHEN', 'Food'], ['BAR', 'Drinks']] as const).map(([key, label]) => (
          <button key={key} onClick={() => { setActiveStation(key); setActiveCat('All') }}
            className={`flex-1 py-2 rounded-lg text-xs font-semibold transition-colors ${
              activeStation === key
                ? 'bg-primary-main text-white'
                : 'bg-white/5 text-ink-secondary hover:bg-white/8'
            }`}>
            {label}
          </button>
        ))}
      </div>
      {/* Category tabs */}
      <div className="shrink-0 px-3 pt-1 pb-2 overflow-x-auto flex gap-2 scrollbar-hide">
        {categories.map(cat => (
          <button key={cat} onClick={() => setActiveCat(cat)}
            className={`px-3 py-1.5 rounded-full text-xs font-semibold whitespace-nowrap transition-colors shrink-0 ${
              activeCat === cat
                ? 'bg-ink-primary text-cream-card'
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
                    focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-main
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
                      <div className="absolute inset-0 bg-[var(--color-chrome-60)] flex items-center justify-center">
                        <span className="text-xs font-bold text-ink-primary/80 uppercase tracking-wider">Sold Out</span>
                      </div>
                    )}
                  </div>
                  {/* Info */}
                  <div className="p-4">
                    <p className={`text-sm font-semibold text-ink-primary leading-snug ${soldOut ? 'line-through' : ''}`}>
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
                      bg-primary-main text-white flex items-center justify-center
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
            <p className="font-bold text-ink-primary text-lg truncate max-w-xs">{tab?.reference ?? 'Walk-in'}</p>
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
                    <p className="text-sm font-semibold text-ink-primary truncate">{e.name}</p>
                    <p className="text-xs text-ink-tertiary tabular-nums">{kes(e.price)} each</p>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <motion.button whileTap={{ scale: 0.85 }}
                      aria-label={`Decrease ${e.name} quantity`}
                      onClick={() => decItem(e.id)}
                      className="w-7 h-7 rounded-full bg-white/5 text-ink-primary font-bold text-sm
                        flex items-center justify-center">−</motion.button>
                    <span className="w-5 text-center text-sm font-bold tabular-nums">{e.qty}</span>
                    <motion.button whileTap={{ scale: 0.85 }}
                      aria-label={`Increase ${e.name} quantity`}
                      onClick={() => addItem(e.id)}
                      className="w-7 h-7 rounded-full bg-primary-main text-white font-bold text-sm
                        flex items-center justify-center">+</motion.button>
                  </div>
                  <span className="text-sm font-bold tabular-nums text-ink-primary w-16 text-right shrink-0">
                    {kes(e.price * e.qty)}
                  </span>
                  <div className="w-full mt-1">
                    <input
                      type="text" maxLength={200}
                      placeholder="Add note (e.g. no onions)"
                      aria-label={`Note for ${e.name}`}
                      value={draftNotes[e.id] ?? ''}
                      onChange={ev => setDraftNotes(n => ({ ...n, [e.id]: ev.target.value }))}
                      className="w-full text-xs rounded-lg glass-card bg-transparent px-2 py-1.5
                        text-ink-secondary placeholder:text-ink-tertiary/50
                        focus:outline-none focus:border-primary-main"
                    />
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>
            <div className="flex justify-between items-center pt-3">
              <span className="text-sm text-ink-secondary">{draftCount} item{draftCount !== 1 ? 's' : ''}</span>
              <span className="text-base font-bold tabular-nums text-ink-primary">{kes(draftTotal)}</span>
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
                  <span className={`inline-flex items-center gap-1 text-[9px] font-bold uppercase px-1.5 py-0.5 rounded ${badge.bg}`}>
                    <Icon name={badge.icon} size={10} strokeWidth={2.5} /> {oi.status}
                  </span>
                  {oi.status === 'READY' && (
                    <motion.button whileTap={{ scale: 0.92 }}
                      onClick={() => itemMut.mutate({ id: oi.id, action: 'serve' })}
                      disabled={itemMut.isPending}
                      className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-semibold
                        bg-primary-main text-white disabled:opacity-50">
                      Served <Icon name="check" size={13} strokeWidth={2.5} />
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
                      ? 'bg-primary-main text-white border-primary-main'
                      : 'bg-transparent text-ink-secondary border-white/10 hover:border-primary-main/50'
                  }`}>
                  {m === 'BANK_TRANSFER' ? 'Bank' : m.charAt(0) + m.slice(1).toLowerCase()}
                </button>
              ))}
            </div>
            <input
              type="number" min="0" step="0.01" inputMode="decimal"
              placeholder="Amount (KSh)"
              value={pay.amount}
              onChange={e => setPay(p => ({ ...p, amount: e.target.value }))}
              className="w-full rounded-xl glass-card bg-transparent px-4 py-3
                text-base text-ink-primary focus:outline-none focus:border-primary-main"
            />
            <button
              onClick={() => setPay(p => ({ ...p, amount: String(Math.abs(bal)) }))}
              className="w-full py-2.5 rounded-xl glass-card text-sm text-ink-secondary
                hover:bg-white/5 transition-colors">
              Exact — {kes(Math.abs(bal))}
            </button>
            <Button variant="primary" size="lg" className="w-full" loading={payMut.isPending}
              onClick={() => payMut.mutate()}>
              Record Payment
            </Button>
          </div>
        )}

        {/* Close tab */}
        {bal <= 0 && tab?.status !== 'CLOSED' && allItemsResolved && (
          <Button variant="primary" size="lg" className="w-full" loading={closeMut.isPending}
            onClick={() => closeMut.mutate()}>
            <span className="inline-flex items-center gap-2">
              Close Table <Icon name="check" size={18} strokeWidth={2} />
            </span>
          </Button>
        )}
        {bal <= 0 && tab?.status !== 'CLOSED' && !allItemsResolved && (
          <p className="text-center text-xs text-ink-tertiary py-2">
            Waiting on the kitchen/bar to finish and serve every item before this table can close.
          </p>
        )}

        {tab?.status === 'CLOSED' && (
          <div className="space-y-3">
            <p className="flex items-center justify-center gap-1.5 text-sm text-status-paid font-semibold py-2">
              <Icon name="check" size={16} strokeWidth={2} /> Table closed
            </p>
            {canHandleReceipts ? (
              <>
                <button
                  onClick={() => {
                    const ref = tab.reference || `tab_${tabId?.slice(0, 8)}`
                    downloadPdf(`/reports/receipt/${tabId}`, `receipt_${ref.replace(/ /g, '_')}.pdf`)
                      .catch(e => addToast({ type: 'error', message: (e as Error).message }))
                  }}
                  className="w-full py-2.5 rounded-xl glass-card text-sm font-semibold text-ink-primary
                    hover:bg-white/5 transition-colors border border-white/10"
                >
                  Print Receipt (PDF)
                </button>
                <Button variant="ghost" size="md" className="w-full"
                  onClick={() => setShowReceiptModal(true)}>
                  Send Receipt via WhatsApp
                </Button>
              </>
            ) : (
              // Both actions require front desk level+ on the backend (app/reports/routes.py,
              // app/notifications/core.py) — these buttons used to show for every waiter
              // regardless, so closing a table always ended in two dead 403s.
              <p className="text-center text-xs text-ink-tertiary py-2">
                Ask front desk to print or send this receipt.
              </p>
            )}
          </div>
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

  // ── Receipt modal ─────────────────────────────────────────────────────

  const receiptModal = (
    <Modal open={showReceiptModal} onClose={() => setShowReceiptModal(false)} title="Send Receipt">
      <div className="space-y-4">
        <p className="text-sm text-ink-secondary">
          Enter the guest&apos;s phone number to send the receipt via WhatsApp (or SMS).
        </p>
        <input
          type="tel" inputMode="tel"
          placeholder="e.g. 0712345678"
          value={receiptPhone}
          onChange={e => setReceiptPhone(e.target.value)}
          className="w-full rounded-xl glass-card bg-transparent px-4 py-3
            text-base text-ink-primary focus:outline-none focus:border-primary-main"
        />
        <div className="flex gap-2">
          <Button variant="ghost" size="md" className="flex-1"
            onClick={() => { setShowReceiptModal(false); setReceiptPhone('') }}>
            Cancel
          </Button>
          <Button variant="primary" size="md" className="flex-1"
            loading={receiptMut.isPending}
            onClick={() => receiptMut.mutate()}
            disabled={!receiptPhone.trim()}>
            Send Receipt
          </Button>
        </div>
      </div>
    </Modal>
  )

  // ── Entry choice (new tables only) ─────────────────────────────────────

  const isNewTab = allOrderItems.length === 0 && draftEntries.length === 0
  const showEntryPrompt = isNewTab && entryChoice === 'pending'

  // ── Layout ─────────────────────────────────────────────────────────────

  return (
    <div className="h-full flex flex-col">
      <ErrorBoundary level="tile">
      {/* Back + header (always visible) */}
      <div className="shrink-0 px-4 py-3 flex items-center gap-3 border-b border-white/10"
        style={{ background: 'var(--color-chrome-85)', backdropFilter: 'blur(12px)' }}>
        <button onClick={() => navigate('/pos/tabs')}
          aria-label="Back to tables"
          className="text-ink-tertiary hover:text-ink-primary text-sm transition-colors">
          ← Back
        </button>
        <p className="flex-1 font-bold text-ink-primary truncate">{tab?.reference ?? 'Walk-in'}</p>
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
          <p className="font-serif text-2xl font-bold text-ink-primary text-center">
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
              <span className="text-sm font-semibold text-ink-primary">Show Menu</span>
              <span className="text-[10px] text-ink-tertiary block mt-0.5">Guest wants to browse</span>
            </motion.button>
            <motion.button whileTap={{ scale: 0.97 }}
              onClick={() => setEntryChoice('order')}
              className="flex-1 py-4 rounded-2xl gradient-hero text-center text-white">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" className="mx-auto mb-1 text-ink-primary">
                <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
              <span className="text-sm font-semibold">Straight to Order</span>
              <span className="text-[10px] text-ink-primary/70 block mt-0.5">Guest knows what they want</span>
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
                ? 'text-primary-dark border-b-2 border-primary-main'
                : 'text-ink-tertiary hover:text-ink-secondary'
            }`}>
            {v === 'menu' ? `Menu${draftCount > 0 ? ` (${draftCount})` : ''}` : 'Order'}
          </button>
        ))}
      </div>

      {/* ONE set of panes.

          This was two sibling containers — a `hidden md:grid` two-pane desktop
          layout and a `md:hidden` single-pane mobile one — each rendering
          {menuPane} and {orderPane}. Both were always in the DOM, so this screen
          rendered every pane TWICE: measured at 1280px, 29 of 98 buttons were
          duplicates (every "Add <item> to order" appeared twice) plus a genuine
          duplicate DOM id, `search-input` x2. A screen reader read the whole menu
          out twice, and the duplicate id broke <label htmlFor> binding.

          The two layouts are structurally different (both panes side by side vs
          one at a time), so CSS alone can't merge them — hence the JS breakpoint. */}
      {!showEntryPrompt && (
        isDesktop ? (
          <div className="flex-1 min-h-0 grid grid-cols-[3fr_2fr] divide-x divide-cream-alt">
            <div className="overflow-hidden">{menuPane}</div>
            <div className="overflow-hidden bg-transparent">{orderPane}</div>
          </div>
        ) : (
          <div className="flex-1 min-h-0">
            {mobilePane === 'menu' ? menuPane : orderPane}
          </div>
        )
      )}

      {cancelModal}
      {receiptModal}
      </ErrorBoundary>
    </div>
  )
}
