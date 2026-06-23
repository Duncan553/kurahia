import { useState, useRef, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { useToastStore, SearchInput } from '@shared'
import api from '../lib/axios'
import { playOrderAlert, isMuted, setMuted as setAudioMuted } from '../lib/audio'
import AudioEnableSplash from '../components/AudioEnableSplash'

interface QueueItem {
  order_item_id: string; order_id: string; tab_reference: string | null
  menu_item_id: string; menu_item: string | null; quantity: string; status: string
  age_seconds: number; ordered_by: string | null; notes: string | null
}
interface StockItem {
  id: string; name: string; unit: string
  current_stock: string; reorder_level: string; below_reorder: boolean
}

const extractErr = (e: unknown) =>
  (e as { response?: { data?: { error?: string } } })?.response?.data?.error ?? 'Something went wrong.'

function ageCls(s: number) {
  if (s < 480) return 'text-status-paid'
  if (s < 900) return 'text-status-pending'
  return 'text-status-failed'
}
const ageLabel = (s: number) => s >= 60 ? `${Math.floor(s / 60)}m` : `${s}s`

function currentTime() {
  return new Date().toLocaleTimeString('en-KE', { hour: '2-digit', minute: '2-digit' })
}
function currentDate() {
  return new Date().toLocaleDateString('en-KE', { weekday: 'long', day: 'numeric', month: 'long' })
}

// ── Stock view ────────────────────────────────────────────────────────────────

function StockBoard() {
  const { data: items = [], isLoading } = useQuery<StockItem[]>({
    queryKey: ['station-stock'],
    queryFn: () => api.get<StockItem[]>('/inventory/items').then(r => r.data),
    refetchInterval: 60_000,
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
        <div className="rounded-2xl border border-status-failed/40 bg-status-failed/10 p-3">
          <p className="text-status-failed text-sm font-bold">
            {low.length} item{low.length !== 1 ? 's' : ''} below reorder level
          </p>
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

// ── 3-column Kanban queue view ───────────────────────────────────────────────

function KanbanView({ station, onCount }: { station: 'KITCHEN' | 'BAR'; onCount: (n: number) => void }) {
  const qc = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  const [searchQ, setSearchQ] = useState('')
  const endpoint = station === 'KITCHEN' ? '/kitchen/queue' : '/bar/queue'
  const prevIdsRef = useRef<Set<string>>(new Set())

  const { data: items = [], isLoading, isError } = useQuery<QueueItem[]>({
    queryKey: ['queue', station],
    queryFn: () => api.get<QueueItem[]>(endpoint).then(r => r.data),
    refetchInterval: 15_000,
    staleTime: 0,
    select: (data) => { onCount(data.length); return data },
  })

  // Stock data for low-stock warnings on queued items
  const { data: stockItems = [] } = useQuery<StockItem[]>({
    queryKey: ['station-stock'],
    queryFn: () => api.get<StockItem[]>('/inventory/items').then(r => r.data),
    refetchInterval: 60_000,
  })
  const lowStockNames = new Set(stockItems.filter(i => i.below_reorder).map(i => i.name.toLowerCase()))

  useEffect(() => {
    if (!items.length) return
    const currentIds = new Set(items.map(i => i.order_item_id))
    if (prevIdsRef.current.size > 0) {
      const hasNew = items.some(i => !prevIdsRef.current.has(i.order_item_id))
      if (hasNew) playOrderAlert(station)
    }
    prevIdsRef.current = currentIds
  }, [items, station])

  const actMut = useMutation({
    mutationFn: ({ id, action }: { id: string; action: 'receive' | 'ready' }) =>
      api.post(`/order-items/${id}/${action}`),
    onSuccess: (_d, v) => {
      qc.invalidateQueries({ queryKey: ['queue', station] })
      if (v.action === 'ready') addToast({ type: 'success', message: 'Waiter has been notified.' })
    },
    onError: (e) => addToast({ type: 'error', message: extractErr(e) }),
  })

  const filteredItems = searchQ
    ? items.filter(i => {
        const q = searchQ.toLowerCase()
        return (i.menu_item ?? '').toLowerCase().includes(q) ||
               (i.tab_reference ?? '').toLowerCase().includes(q) ||
               (i.ordered_by ?? '').toLowerCase().includes(q)
      })
    : items

  if (isLoading) return (
    <div className="grid grid-cols-3 gap-4">
      {[1,2,3].map(c => (
        <div key={c} className="space-y-3">
          <div className="h-8 rounded-lg bg-cream-alt animate-pulse" />
          <div className="h-32 rounded-xl bg-cream-alt animate-pulse" />
        </div>
      ))}
    </div>
  )
  if (isError) return (
    <p className="text-status-failed text-sm text-center py-8">Failed to load queue. Check your connection.</p>
  )

  /* Split items into 3 kanban columns by status */
  const sent    = filteredItems.filter(i => i.status === 'PENDING')
  const cooking = filteredItems.filter(i => i.status === 'RECEIVED')
  const ready   = filteredItems.filter(i => i.status === 'READY')

  const columns = [
    { key: 'sent',    title: 'Sent',    items: sent,    accent: 'border-primary-main' },
    { key: 'cooking', title: 'Cooking', items: cooking, accent: 'border-status-pending' },
    { key: 'ready',   title: 'Ready',   items: ready,   accent: 'border-status-paid' },
  ]

  return (
    <div className="space-y-3">
      {/* Search bar */}
      <SearchInput value={searchQ} onChange={setSearchQ} placeholder="Search orders..." label="Search orders" />

      {items.length === 0 && (
        <div className="flex flex-col items-center justify-center py-20 gap-3">
          <span className="text-5xl text-ink-tertiary/40">&#10003;</span>
          <p className="text-ink-secondary text-lg font-medium">Queue clear</p>
        </div>
      )}

      {searchQ && filteredItems.length === 0 && items.length > 0 && (
        <p className="text-sm text-ink-tertiary text-center py-8">
          No results for '{searchQ}'
        </p>
      )}

      {/* 3-column kanban */}
      {(items.length > 0 || searchQ) && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {columns.map(col => (
            <div key={col.key} className="min-h-[200px]">
              {/* Column header */}
              <div className={`flex items-center justify-between mb-3 pb-2 border-b-2 ${col.accent}`}>
                <h3 className="text-sm font-bold text-ink-primary uppercase tracking-widest">{col.title}</h3>
                <span className="text-xs font-bold tabular-nums text-ink-tertiary bg-cream-alt px-2 py-0.5 rounded-full">
                  {col.items.length}
                </span>
              </div>

              {/* Cards in column */}
              <div className="space-y-3">
                <AnimatePresence mode="popLayout">
                  {col.items.map(item => (
                    <motion.div
                      key={item.order_item_id}
                      layout
                      initial={{ opacity: 0, y: -12 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, height: 0, marginBottom: 0, overflow: 'hidden' }}
                      transition={{ type: 'spring', damping: 25, stiffness: 300 }}
                      className="glass-card rounded-xl p-4 border border-white/10"
                    >
                      {/* Ticket header: order ID + age */}
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary">
                          {item.order_id.slice(0, 6)}
                        </span>
                        <span className={`text-xs font-bold tabular-nums ${ageCls(item.age_seconds)}`}>
                          {ageLabel(item.age_seconds)}
                        </span>
                      </div>

                      {/* Table reference — large */}
                      <p className="text-xl font-bold text-ink-primary leading-tight mb-1">
                        {item.tab_reference ?? 'Walk-in'}
                      </p>
                      {item.ordered_by && (
                        <p className="text-[10px] text-ink-tertiary mb-2">by {item.ordered_by}</p>
                      )}

                      {/* Item name + quantity */}
                      <div className="flex items-baseline justify-between gap-2 mb-1">
                        <span className="text-sm font-semibold text-ink-primary">{item.menu_item}</span>
                        <span className="text-sm font-bold tabular-nums text-ink-tertiary shrink-0">x{item.quantity}</span>
                      </div>

                      {/* Notes */}
                      {item.notes && (
                        <p className="text-xs italic text-status-pending mt-1 pl-2 border-l-2 border-status-pending/30">
                          {item.notes}
                        </p>
                      )}

                      {/* Stock warning */}
                      {lowStockNames.has((item.menu_item ?? '').toLowerCase()) && (
                        <p className="text-xs text-status-failed/80 mt-2">
                          &#9888; Low stock — verify before prep
                        </p>
                      )}

                      {/* Action buttons per column */}
                      <div className="flex gap-2 mt-3">
                        {item.status === 'PENDING' && (
                          <motion.button whileTap={{ scale: 0.94 }}
                            onClick={() => actMut.mutate({ id: item.order_item_id, action: 'receive' })}
                            disabled={actMut.isPending}
                            aria-label={`Start cooking ${item.menu_item ?? 'item'}`}
                            className="flex-1 py-2.5 rounded-xl text-sm font-semibold
                              bg-primary-main text-white
                              hover:bg-primary-main/90 transition-colors disabled:opacity-50
                              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#fa5c29]">
                            Start Cooking
                          </motion.button>
                        )}
                        {item.status === 'RECEIVED' && (
                          <>
                            <motion.button whileTap={{ scale: 0.94 }}
                              onClick={() => actMut.mutate({ id: item.order_item_id, action: 'receive' })}
                              disabled={actMut.isPending}
                              aria-label={`Bump ${item.menu_item ?? 'item'}`}
                              className="flex-1 py-2.5 rounded-xl text-sm font-semibold
                                border border-white/10 text-ink-secondary
                                hover:bg-white/5 transition-colors disabled:opacity-50
                                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#fa5c29]">
                              Bump
                            </motion.button>
                            <motion.button whileTap={{ scale: 0.94 }}
                              onClick={() => actMut.mutate({ id: item.order_item_id, action: 'ready' })}
                              disabled={actMut.isPending}
                              aria-label={`Mark ${item.menu_item ?? 'item'} ready`}
                              className="flex-1 py-2.5 rounded-xl text-sm font-semibold
                                bg-primary-main text-white
                                hover:bg-primary-main/90 transition-colors disabled:opacity-50
                                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#fa5c29]">
                              &#10003; Mark Ready
                            </motion.button>
                          </>
                        )}
                      </div>
                    </motion.div>
                  ))}
                </AnimatePresence>

                {col.items.length === 0 && (
                  <p className="text-xs text-ink-tertiary text-center py-6">Empty</p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Mute button ──────────────────────────────────────────────────────────────

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
        text-ink-secondary hover:bg-white/5 transition-colors">
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

// ── Station shell ─────────────────────────────────────────────────────────────

function StationBoard({ station }: { station: 'KITCHEN' | 'BAR' }) {
  const [view, setView] = useState<'queue' | 'stock'>('queue')
  const [count, setCount] = useState(0)
  const [time, setTime] = useState(currentTime)

  useEffect(() => {
    const id = setInterval(() => setTime(currentTime()), 1_000)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="min-h-screen bg-cream-card text-ink-primary">
      <AudioEnableSplash station={station} />

      {/* Header — sticky top bar */}
      <div className="sticky top-0 z-10 glass-card border-b border-white/10 px-4 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div>
              <h1 className="text-base font-bold tracking-widest uppercase text-ink-primary">
                {station === 'KITCHEN' ? 'Grill Station' : 'Bar'}
              </h1>
              <p className="text-[10px] text-ink-tertiary">{currentDate()}</p>
            </div>
            <div className="glass-card-sage rounded-xl px-3 py-1.5">
              <span className="font-serif text-2xl font-bold tabular-nums text-ink-primary">{time}</span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <MuteButton />
            <div className="flex rounded-xl overflow-hidden border border-white/10">
              {(['queue', 'stock'] as const).map(v => (
                <button key={v} onClick={() => setView(v)}
                  className={`px-4 py-2 text-sm font-semibold capitalize transition-colors ${
                    view === v
                      ? 'bg-ink-primary text-cream-card'
                      : 'text-ink-secondary hover:bg-white/5'
                  }`}>
                  {v === 'queue' ? `Queue${count ? ` (${count})` : ''}` : 'Inventory'}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="p-4">
        {view === 'queue'
          ? <KanbanView station={station} onCount={setCount} />
          : <StockBoard />
        }
      </div>
    </div>
  )
}

export function KitchenQueueScreen() { return <StationBoard station="KITCHEN" /> }
export function BarQueueScreen()     { return <StationBoard station="BAR" /> }
