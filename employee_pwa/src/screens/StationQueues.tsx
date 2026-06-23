import { useState, useRef, useEffect, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { useToastStore, Button } from '@shared'
import { useAuthStore } from '../stores/authStore'
import api from '../lib/axios'
import { playOrderAlert, isMuted, setMuted as setAudioMuted } from '../lib/audio'
import AudioEnableSplash from '../components/AudioEnableSplash'

/* ── Types ──────────────────────────────────────────────────────────────────── */

interface QueueItem {
  order_item_id: string; order_id: string; tab_reference: string | null
  menu_item_id: string; menu_item: string | null; category: string | null
  quantity: string; status: string
  age_seconds: number; ordered_by: string | null; notes: string | null
}
interface StockItem {
  id: string; name: string; unit: string
  current_stock: string; reorder_level: string; below_reorder: boolean
}

/* An order card groups all items that share the same order_id */
interface OrderGroup {
  order_id: string
  tab_reference: string | null
  ordered_by: string | null
  age_seconds: number          // max age across items in this order
  status: 'PENDING' | 'RECEIVED' | 'READY' | 'MIXED'  // highest-priority status
  items: QueueItem[]
}

/* ── Helpers (unchanged business logic) ─────────────────────────────────────── */

const extractErr = (e: unknown) =>
  (e as { response?: { data?: { error?: string } } })?.response?.data?.error ?? 'Something went wrong.'

const ageLabel = (s: number) => s >= 60 ? `${Math.floor(s / 60)}m ago` : `${s}s ago`

/* Short order display ID: #ORD-XXXX using last 4 chars of the UUID */
const ordLabel = (id: string) => `#ORD-${id.slice(-4).toUpperCase()}`

/* Group flat queue items into order cards */
function groupByOrder(items: QueueItem[]): OrderGroup[] {
  const map = new Map<string, QueueItem[]>()
  for (const item of items) {
    const arr = map.get(item.order_id) ?? []
    arr.push(item)
    map.set(item.order_id, arr)
  }
  // Priority: RECEIVED > PENDING (active items show first)
  const statusPriority: Record<string, number> = { RECEIVED: 2, PENDING: 1, READY: 0 }
  return Array.from(map.entries()).map(([order_id, orderItems]) => {
    // Pick the "dominant" status: if ANY item is RECEIVED, show as active
    let topStatus = 'PENDING'
    let maxPri = 0
    for (const it of orderItems) {
      const p = statusPriority[it.status] ?? 0
      if (p > maxPri) { maxPri = p; topStatus = it.status }
    }
    return {
      order_id,
      tab_reference: orderItems[0].tab_reference,
      ordered_by: orderItems[0].ordered_by,
      age_seconds: Math.max(...orderItems.map(i => i.age_seconds)),
      status: topStatus as OrderGroup['status'],
      items: orderItems,
    }
  })
}

/* ── Stock Board (unchanged) ────────────────────────────────────────────────── */

function StockBoard() {
  const addToast = useToastStore(s => s.addToast)
  const dept = useAuthStore(s => s.user?.department) ?? 'Station'

  const { data: items = [], isLoading } = useQuery<StockItem[]>({
    queryKey: ['station-stock'],
    queryFn: () => api.get<StockItem[]>('/inventory/items').then(r => r.data),
    refetchInterval: 60_000,
  })

  // Alert Manager: send a suggestion with all low-stock items listed
  const alertMut = useMutation({
    mutationFn: (lowItems: StockItem[]) => {
      const itemList = lowItems.map(i =>
        `${i.name}: ${parseFloat(i.current_stock)} ${i.unit} (reorder at ${parseFloat(i.reorder_level)} ${i.unit})`
      ).join('\n')
      return api.post('/suggestions', {
        category: 'MANAGEMENT',
        subject: `Low stock alert from ${dept}`,
        body: `The following items are below reorder level:\n${itemList}`,
      })
    },
    onSuccess: () => addToast({ type: 'success', message: 'Manager has been alerted about low stock.' }),
    onError: () => addToast({ type: 'error', message: 'Could not send alert. Try again.' }),
  })

  if (isLoading) return (
    <div className="space-y-4 p-4">
      {[1,2,3].map(i => <div key={i} className="h-14 rounded-xl bg-cream-alt animate-pulse" />)}
    </div>
  )
  if (items.length === 0) return (
    <p className="text-ink-tertiary text-center py-16">
      No stock items set up for this department yet. Ask your manager.
    </p>
  )

  const low = items.filter(i => i.below_reorder)
  return (
    <div className="space-y-4">
      {low.length > 0 && (
        <div className="rounded-2xl border border-status-failed/40 bg-status-failed/10 p-3 space-y-2">
          <p className="text-status-failed text-sm font-bold">
            {low.length} item{low.length !== 1 ? 's' : ''} below reorder level
          </p>
          <Button variant="primary" size="sm" className="w-full"
            loading={alertMut.isPending}
            onClick={() => alertMut.mutate(low)}>
            Alert Manager
          </Button>
        </div>
      )}
      {items.map(it => {
        const stock   = parseFloat(it.current_stock)
        const reorder = parseFloat(it.reorder_level)
        const pct = reorder > 0 ? Math.min((stock / (reorder * 2)) * 100, 100) : stock > 0 ? 100 : 0
        return (
          <div key={it.id}>
            <div className="flex items-baseline justify-between mb-1">
              <span className="text-sm font-semibold text-ink-primary">{it.name}</span>
              <span className={`text-sm tabular-nums font-bold ${it.below_reorder ? 'text-status-failed' : 'text-ink-secondary'}`}>
                {stock} {it.unit}
              </span>
            </div>
            <div className="h-3 rounded-full bg-cream-alt overflow-hidden relative">
              <div
                className={`h-full rounded-full transition-all ${it.below_reorder ? 'bg-status-failed' : 'bg-status-paid'}`}
                style={{ width: `${pct}%` }}
              />
              {reorder > 0 && <div className="absolute inset-y-0 left-1/2 w-px bg-ink-tertiary/30" />}
            </div>
            <p className="text-[10px] text-ink-tertiary mt-0.5">reorder at {reorder} {it.unit}</p>
          </div>
        )
      })}
    </div>
  )
}

/* ── Glassmorphism Queue View (Stitch bar station design) ───────────────────── */

function GlassQueueView({ station, onCount }: { station: 'KITCHEN' | 'BAR'; onCount: (n: number) => void }) {
  const qc = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  const [activeFilter, setActiveFilter] = useState<string>('ALL')
  const endpoint = station === 'KITCHEN' ? '/kitchen/queue' : '/bar/queue'
  const prevIdsRef = useRef<Set<string>>(new Set())

  /* ── Data fetch (identical query setup) ──────────────────────────────────── */
  const { data: items = [], isLoading, isError } = useQuery<QueueItem[]>({
    queryKey: ['queue', station],
    queryFn: () => api.get<QueueItem[]>(endpoint).then(r => r.data),
    refetchInterval: 15_000,
    staleTime: 0,
    select: (data) => { onCount(data.length); return data },
  })

  /* ── Stock data for low-stock warnings ───────────────────────────────────── */
  const { data: stockItems = [] } = useQuery<StockItem[]>({
    queryKey: ['station-stock'],
    queryFn: () => api.get<StockItem[]>('/inventory/items').then(r => r.data),
    refetchInterval: 60_000,
  })
  const lowStockNames = new Set(stockItems.filter(i => i.below_reorder).map(i => i.name.toLowerCase()))

  /* ── Audio alert on new items (unchanged) ────────────────────────────────── */
  useEffect(() => {
    if (!items.length) return
    const currentIds = new Set(items.map(i => i.order_item_id))
    if (prevIdsRef.current.size > 0) {
      const hasNew = items.some(i => !prevIdsRef.current.has(i.order_item_id))
      if (hasNew) playOrderAlert(station)
    }
    prevIdsRef.current = currentIds
  }, [items, station])

  /* ── Mutations (unchanged) ───────────────────────────────────────────────── */
  const actMut = useMutation({
    mutationFn: ({ id, action }: { id: string; action: 'receive' | 'ready' }) =>
      api.post(`/order-items/${id}/${action}`),
    onSuccess: (_d, v) => {
      qc.invalidateQueries({ queryKey: ['queue', station] })
      if (v.action === 'ready') addToast({ type: 'success', message: 'Waiter has been notified.' })
    },
    onError: (e) => addToast({ type: 'error', message: extractErr(e) }),
  })

  /* ── Category pills: derive from live data ───────────────────────────────── */
  const categories = useMemo(() => {
    const catMap = new Map<string, number>()
    for (const it of items) {
      const cat = it.category ?? 'Other'
      catMap.set(cat, (catMap.get(cat) ?? 0) + 1)
    }
    // Sort by count descending
    return Array.from(catMap.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([name, count]) => ({ name, count }))
  }, [items])

  /* ── Filter items by category, then group by order ───────────────────────── */
  const filteredItems = activeFilter === 'ALL'
    ? items
    : items.filter(i => (i.category ?? 'Other') === activeFilter)

  const orderGroups = useMemo(() => groupByOrder(filteredItems), [filteredItems])

  // Sort: active (RECEIVED) orders first, then queued (PENDING), by age desc
  const sortedGroups = useMemo(() => {
    return [...orderGroups].sort((a, b) => {
      const statusOrder: Record<string, number> = { RECEIVED: 0, PENDING: 1, READY: 2 }
      const sa = statusOrder[a.status] ?? 9
      const sb = statusOrder[b.status] ?? 9
      if (sa !== sb) return sa - sb
      return b.age_seconds - a.age_seconds  // older orders first within same status
    })
  }, [orderGroups])

  /* ── Status label: "MIXING" for bar active, "COOKING" for kitchen active ─── */
  const activeVerb = station === 'BAR' ? 'MIXING' : 'COOKING'
  const startVerb  = station === 'BAR' ? 'Start Mixing' : 'Start Cooking'

  /* ── Loading state ───────────────────────────────────────────────────────── */
  if (isLoading) return (
    <div className="p-6">
      <div className="flex gap-3 mb-6">
        {[1,2,3,4].map(i => <div key={i} className="h-9 w-32 rounded-full bg-cream-alt animate-pulse" />)}
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {[1,2,3].map(i => <div key={i} className="h-56 rounded-xl bg-cream-alt animate-pulse" />)}
      </div>
    </div>
  )

  if (isError) return (
    <p className="text-status-failed text-sm text-center py-8">Failed to load queue. Check your connection.</p>
  )

  return (
    <div className="p-5">
      {/* ── Filter pills row ──────────────────────────────────────────────── */}
      <div className="flex flex-wrap gap-2 mb-5">
        {/* ALL ORDERS pill */}
        <button
          onClick={() => setActiveFilter('ALL')}
          className={`px-4 py-2 rounded-full text-sm font-semibold border transition-colors
            ${activeFilter === 'ALL'
              ? 'border-[#f9dcd5]/40 bg-white/10 text-[#f9dcd5]'
              : 'border-white/10 text-[#aa8980] hover:text-[#f9dcd5] hover:bg-white/5'
            }`}
        >
          ALL ORDERS ({items.length})
        </button>

        {/* Category pills */}
        {categories.map(cat => (
          <button
            key={cat.name}
            onClick={() => setActiveFilter(cat.name)}
            className={`px-4 py-2 rounded-full text-sm font-semibold border transition-colors
              ${activeFilter === cat.name
                ? 'border-[#f9dcd5]/40 bg-white/10 text-[#f9dcd5]'
                : 'border-white/10 text-[#aa8980] hover:text-[#f9dcd5] hover:bg-white/5'
              }`}
          >
            {cat.name.toUpperCase()} ({cat.count})
          </button>
        ))}
      </div>

      {/* ── Empty state ───────────────────────────────────────────────────── */}
      {items.length === 0 && (
        <div className="flex flex-col items-center justify-center py-20 gap-3">
          <span className="text-5xl text-ink-tertiary/40">&#10003;</span>
          <p className="text-[#aa8980] text-lg font-medium">Queue clear</p>
        </div>
      )}

      {/* ── No results for filter ─────────────────────────────────────────── */}
      {activeFilter !== 'ALL' && filteredItems.length === 0 && items.length > 0 && (
        <p className="text-sm text-[#aa8980] text-center py-8">
          No items in {activeFilter.toLowerCase()}
        </p>
      )}

      {/* ── Order cards grid ──────────────────────────────────────────────── */}
      {sortedGroups.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          <AnimatePresence mode="popLayout">
            {sortedGroups.map(group => {
              const isActive = group.status === 'RECEIVED'
              const allPending = group.items.every(i => i.status === 'PENDING')
              const allReady = group.items.every(i => i.status === 'READY')

              return (
                <motion.div
                  key={group.order_id}
                  layout
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.95, transition: { duration: 0.2 } }}
                  transition={{ type: 'spring', damping: 25, stiffness: 300 }}
                  className={`glass-card rounded-xl p-4 flex flex-col
                    ${isActive ? 'border-[#fa5c29]/30' : 'border-white/10'}`}
                >
                  {/* ── Card header: order ID + status badge ────────────── */}
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-bold text-[#f9dcd5]">
                      {ordLabel(group.order_id)}
                    </span>
                    <span className={`inline-flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full
                      ${isActive
                        ? 'bg-[#fa5c29]/20 text-[#fa5c29]'
                        : 'bg-white/5 text-[#aa8980]'
                      }`}
                    >
                      {isActive && <span className="w-1.5 h-1.5 rounded-full bg-[#fa5c29]" />}
                      {isActive ? activeVerb : allReady ? 'READY' : 'QUEUED'}
                    </span>
                  </div>

                  {/* ── Table + time ────────────────────────────────────── */}
                  <p className="text-xs text-[#aa8980] mb-3">
                    {group.tab_reference ?? 'Walk-in'}
                    <span className="mx-1.5">&middot;</span>
                    {ageLabel(group.age_seconds)}
                  </p>

                  {/* ── Items list ──────────────────────────────────────── */}
                  <div className="flex-1 space-y-2.5 mb-4">
                    {group.items.map(item => (
                      <div key={item.order_item_id}>
                        <div className="flex items-baseline gap-2">
                          <span className="text-sm font-bold tabular-nums text-[#f9dcd5] shrink-0">
                            {item.quantity}x
                          </span>
                          <span className="text-sm text-[#f9dcd5]">{item.menu_item}</span>
                        </div>

                        {/* Notes */}
                        {item.notes && (
                          <p className="text-xs italic text-[#aa8980] mt-0.5 ml-6">
                            - {item.notes}
                          </p>
                        )}

                        {/* Low stock warning */}
                        {lowStockNames.has((item.menu_item ?? '').toLowerCase()) && (
                          <p className="text-xs text-status-failed/80 mt-1 ml-6">
                            &#9888; Low stock
                          </p>
                        )}
                      </div>
                    ))}
                  </div>

                  {/* ── Action buttons ─────────────────────────────────── */}
                  <div className="flex gap-2 mt-auto">
                    {/* All items PENDING: show "Start Mixing/Cooking" for the whole group */}
                    {allPending && (
                      <motion.button whileTap={{ scale: 0.94 }}
                        onClick={() => {
                          // Receive all pending items in this order
                          for (const it of group.items) {
                            if (it.status === 'PENDING') {
                              actMut.mutate({ id: it.order_item_id, action: 'receive' })
                            }
                          }
                        }}
                        disabled={actMut.isPending}
                        aria-label={`${startVerb} order ${ordLabel(group.order_id)}`}
                        className="flex-1 py-2.5 rounded-xl text-sm font-semibold
                          bg-[#fa5c29] text-white
                          hover:bg-[#fa5c29]/90 transition-colors disabled:opacity-50
                          focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#fa5c29]"
                      >
                        {startVerb.toUpperCase()}
                      </motion.button>
                    )}

                    {/* Active (RECEIVED): show DETAILS + SERVE/COMPLETE */}
                    {isActive && (
                      <>
                        <motion.button whileTap={{ scale: 0.94 }}
                          onClick={() => {
                            // Bump / re-receive all items
                            for (const it of group.items) {
                              if (it.status === 'RECEIVED') {
                                actMut.mutate({ id: it.order_item_id, action: 'receive' })
                              }
                            }
                          }}
                          disabled={actMut.isPending}
                          aria-label={`Details for order ${ordLabel(group.order_id)}`}
                          className="flex-1 py-2.5 rounded-xl text-sm font-semibold
                            border border-white/10 text-[#aa8980]
                            hover:bg-white/5 transition-colors disabled:opacity-50
                            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#fa5c29]"
                        >
                          DETAILS
                        </motion.button>
                        <motion.button whileTap={{ scale: 0.94 }}
                          onClick={() => {
                            // Mark all received items ready
                            for (const it of group.items) {
                              if (it.status === 'RECEIVED') {
                                actMut.mutate({ id: it.order_item_id, action: 'ready' })
                              }
                            }
                          }}
                          disabled={actMut.isPending}
                          aria-label={`Serve order ${ordLabel(group.order_id)}`}
                          className="flex-1 py-2.5 rounded-xl text-sm font-semibold
                            bg-[#fa5c29] text-white
                            hover:bg-[#fa5c29]/90 transition-colors disabled:opacity-50
                            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#fa5c29]"
                        >
                          {station === 'BAR' ? 'SERVE' : 'COMPLETE'}
                        </motion.button>
                      </>
                    )}

                    {/* Mixed status: show per-item buttons (some pending, some received) */}
                    {!allPending && !isActive && !allReady && group.items.some(i => i.status === 'PENDING') && (
                      <motion.button whileTap={{ scale: 0.94 }}
                        onClick={() => {
                          for (const it of group.items) {
                            if (it.status === 'PENDING') {
                              actMut.mutate({ id: it.order_item_id, action: 'receive' })
                            }
                          }
                        }}
                        disabled={actMut.isPending}
                        className="flex-1 py-2.5 rounded-xl text-sm font-semibold
                          bg-[#fa5c29] text-white
                          hover:bg-[#fa5c29]/90 transition-colors disabled:opacity-50
                          focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#fa5c29]"
                      >
                        {startVerb.toUpperCase()}
                      </motion.button>
                    )}
                  </div>
                </motion.div>
              )
            })}
          </AnimatePresence>
        </div>
      )}
    </div>
  )
}

/* ── Mute Button (unchanged) ────────────────────────────────────────────────── */

function MuteButton() {
  const [muted, setMutedState] = useState(isMuted)
  function toggle() {
    const next = !muted
    setAudioMuted(next)
    setMutedState(next)
    localStorage.setItem('kurahia-audio-muted', next ? '1' : '0')
  }
  useEffect(() => {
    const saved = localStorage.getItem('kurahia-audio-muted')
    if (saved === '1') { setAudioMuted(true); setMutedState(true) }
  }, [])
  return (
    <button onClick={toggle}
      aria-label={muted ? 'Unmute audio alerts' : 'Mute audio alerts'}
      className="w-9 h-9 rounded-xl border border-white/10 flex items-center justify-center
        text-[#aa8980] hover:text-[#f9dcd5] hover:bg-white/5 transition-colors">
      {muted ? (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M11 5L6 9H2v6h4l5 4V5z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          <path d="M23 9l-6 6M17 9l6 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
        </svg>
      ) : (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M11 5L6 9H2v6h4l5 4V5z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          <path d="M15.54 8.46a5 5 0 010 7.07M19.07 4.93a10 10 0 010 14.14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
        </svg>
      )}
    </button>
  )
}

/* ── Station Shell (redesigned header + body) ───────────────────────────────── */

function StationBoard({ station }: { station: 'KITCHEN' | 'BAR' }) {
  const [view, setView] = useState<'queue' | 'stock'>('queue')
  const [count, setCount] = useState(0)

  // Station display name
  const stationName = station === 'KITCHEN' ? 'Kitchen Station' : 'Bar Station'

  return (
    <div className="min-h-screen text-[#f9dcd5]">
      <AudioEnableSplash station={station} />

      {/* ── Header bar (Stitch design: station name + badge + tabs) ─────── */}
      <div className="sticky top-0 z-10 glass-card border-b border-white/10 px-5 py-3">
        <div className="flex items-center justify-between">
          {/* Left: station name + active orders badge */}
          <div className="flex items-center gap-3">
            <h1 className="text-base font-bold text-[#f9dcd5]">
              {stationName}
            </h1>
            {count > 0 && (
              <span className="inline-flex items-center gap-1.5 bg-white/8 border border-white/10
                rounded-full px-3 py-1 text-xs font-semibold text-[#aa8980]">
                <span className="w-1.5 h-1.5 rounded-full bg-[#fa5c29]" />
                {count} Active Order{count !== 1 ? 's' : ''}
              </span>
            )}
          </div>

          {/* Right: tab buttons + mute */}
          <div className="flex items-center gap-3">
            {/* OVERVIEW / SCHEDULE / LOGS tabs */}
            <div className="hidden sm:flex items-center gap-1">
              {(['OVERVIEW', 'SCHEDULE', 'LOGS'] as const).map(tab => (
                <button key={tab}
                  onClick={() => {
                    if (tab === 'OVERVIEW') setView('queue')
                  }}
                  className={`px-3 py-1.5 text-xs font-bold uppercase tracking-widest transition-colors
                    ${(tab === 'OVERVIEW' && view === 'queue')
                      ? 'text-[#f9dcd5] border-b-2 border-[#f9dcd5]'
                      : 'text-[#aa8980] hover:text-[#f9dcd5]'
                    }`}
                >
                  {tab}
                </button>
              ))}
            </div>

            <MuteButton />

            {/* Inventory toggle (functional) */}
            <button
              onClick={() => setView(view === 'queue' ? 'stock' : 'queue')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold uppercase tracking-wider border transition-colors
                ${view === 'stock'
                  ? 'bg-white/10 border-white/20 text-[#f9dcd5]'
                  : 'border-white/10 text-[#aa8980] hover:text-[#f9dcd5] hover:bg-white/5'
                }`}
            >
              Inventory
            </button>
          </div>
        </div>
      </div>

      {/* ── Content ────────────────────────────────────────────────────────── */}
      {view === 'queue'
        ? <GlassQueueView station={station} onCount={setCount} />
        : <div className="p-5"><StockBoard /></div>
      }
    </div>
  )
}

export function KitchenQueueScreen() { return <StationBoard station="KITCHEN" /> }
export function BarQueueScreen()     { return <StationBoard station="BAR" /> }
