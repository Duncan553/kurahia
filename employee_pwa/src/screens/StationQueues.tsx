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
function ageBg(s: number) {
  if (s < 480) return 'bg-status-paid/10 border-status-paid/30'
  if (s < 900) return 'bg-status-pending/10 border-status-pending/30'
  return 'bg-status-failed/10 border-status-failed/30'
}
const ageLabel = (s: number) => s >= 60 ? `${Math.floor(s / 60)}m ${s % 60}s` : `${s}s`
function ageBadge(s: number): { icon: string; text: string } {
  if (s < 480) return { icon: '○', text: 'Fresh' }
  if (s < 900) return { icon: '◐', text: 'Aging' }
  return { icon: '●', text: 'Overdue' }
}

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

// ── Queue view ────────────────────────────────────────────────────────────────

function QueueView({ station, onCount }: { station: 'KITCHEN' | 'BAR'; onCount: (n: number) => void }) {
  const qc = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  const [searchQ, setSearchQ] = useState('')
  const [compact, setCompact] = useState(() => localStorage.getItem('kurahia-compact-queue') === '1')
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

  function toggleCompact() {
    const next = !compact
    setCompact(next)
    localStorage.setItem('kurahia-compact-queue', next ? '1' : '0')
  }

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
    <div className="space-y-4">
      {[1,2,3,4].map(i => <div key={i} className={`rounded-2xl bg-cream-alt animate-pulse ${compact ? 'h-20' : 'h-32'}`} />)}
    </div>
  )
  if (isError) return (
    <p className="text-status-failed text-sm text-center py-8">Failed to load queue. Check your connection.</p>
  )

  return (
    <div className="space-y-3">
      {/* Search + compact toggle */}
      <div className="flex gap-2 items-start">
        <div className="flex-1">
          <SearchInput value={searchQ} onChange={setSearchQ} placeholder="Search orders..." label="Search orders" />
        </div>
        <button onClick={toggleCompact}
          aria-label={compact ? 'Expand cards' : 'Compact cards'}
          className="shrink-0 w-9 h-9 rounded-xl border border-cream-alt flex items-center justify-center
            text-ink-secondary hover:bg-cream-alt/40 transition-colors mt-0.5">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            {compact ? (
              <path d="M2 3h12M2 8h12M2 13h12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            ) : (
              <path d="M2 4h12M2 8h12M2 12h12" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            )}
          </svg>
        </button>
      </div>

      {/* Empty states */}
      {items.length === 0 && (
        <div className="flex flex-col items-center justify-center py-20 gap-3">
          <span className="text-5xl text-ink-tertiary/40">✓</span>
          <p className="text-ink-secondary text-lg font-medium">Queue clear &middot; Pole pole</p>
        </div>
      )}

      {searchQ && filteredItems.length === 0 && items.length > 0 && (
        <p className="text-sm text-ink-tertiary text-center py-8">
          No results for &lsquo;{searchQ}&rsquo; &middot; Hakuna kitu
        </p>
      )}

      {/* Order cards */}
      <AnimatePresence mode="popLayout">
        {filteredItems.map(item => {
          const badge = ageBadge(item.age_seconds)
          return (
            <motion.div
              key={item.order_item_id}
              layout
              initial={{ opacity: 0, y: -12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, height: 0, marginBottom: 0, overflow: 'hidden' }}
              transition={{ type: 'spring', damping: 25, stiffness: 300 }}
              aria-label={`${item.menu_item} × ${item.quantity} for ${item.tab_reference ?? 'walk-in'}, ${badge.text}`}
              className={`rounded-xl shadow-md overflow-hidden ${
                item.status === 'RECEIVED'
                  ? 'bg-status-pending/5 border-l-4 border-l-status-pending'
                  : 'bg-ticket-paper border-l-4 border-l-primary-main'
              } ${compact ? 'p-3' : 'p-5'}`}
              style={{ fontFamily: "'JetBrains Mono', monospace" }}
            >
              {/* Receipt header */}
              <div className="flex items-start justify-between gap-3 mb-1">
                <div>
                  <span className={`font-bold tabular-nums text-ticket-ink ${compact ? 'text-lg' : 'text-3xl'} tracking-tight`}>
                    {item.tab_reference ?? 'WALK-IN'}
                  </span>
                  {item.status === 'RECEIVED' && (
                    <span className="ml-2 text-[10px] font-bold uppercase px-1.5 py-0.5 rounded
                      bg-status-pending/20 text-status-pending tracking-wide align-middle">
                      PREP
                    </span>
                  )}
                </div>
                <span className={`text-xs font-bold tabular-nums px-2 py-1 rounded border ${ageBg(item.age_seconds)} ${ageCls(item.age_seconds)}`}>
                  {badge.icon} {ageLabel(item.age_seconds)}
                </span>
              </div>

              {/* Dotted divider */}
              {!compact && <div className="border-b border-dashed border-ticket-ink/20 my-2" />}

              {/* Waiter */}
              {item.ordered_by && !compact && (
                <p className="text-[10px] text-ticket-ink/50 uppercase tracking-wider mb-2">
                  WAITER: {item.ordered_by}
                </p>
              )}

              {/* Item — receipt style */}
              <div className={`flex items-baseline justify-between gap-3 ${compact ? '' : 'mb-2'}`}>
                <span className={`font-bold text-ticket-ink ${compact ? 'text-sm' : 'text-xl'} leading-snug`}
                  style={{ fontFamily: "'Hanken Grotesk', sans-serif" }}>
                  {item.menu_item}
                </span>
                <span className={`tabular-nums font-bold text-ticket-ink/70 shrink-0 ${compact ? 'text-sm' : 'text-xl'}`}>
                  ×{item.quantity}
                </span>
              </div>

              {/* Notes */}
              {item.notes && !compact && (
                <p className="text-xs italic text-status-pending mb-3 pl-1 border-l-2 border-status-pending/30">
                  {item.notes}
                </p>
              )}
              {item.notes && compact && (
                <p className="text-[10px] italic text-status-pending truncate mt-1">{item.notes}</p>
              )}

              {/* Stock warning */}
              {lowStockNames.has((item.menu_item ?? '').toLowerCase()) && !compact && (
                <p className="text-xs text-status-failed/80 mb-3">
                  &#9888; {item.menu_item}: stock low &mdash; verify before prep
                </p>
              )}

              {/* Actions */}
              {!compact && (
                <div className="flex gap-2 mt-1">
                  {item.status === 'PENDING' && (
                    <motion.button whileTap={{ scale: 0.94 }}
                      onClick={() => actMut.mutate({ id: item.order_item_id, action: 'receive' })}
                      disabled={actMut.isPending}
                      className="flex-1 min-h-[56px] rounded-xl text-sm font-semibold
                        bg-status-pending/15 text-status-pending border border-status-pending/40
                        hover:bg-status-pending/25 transition-colors disabled:opacity-50">
                      Start Preparing
                    </motion.button>
                  )}
                  {item.status === 'RECEIVED' && (
                    <motion.button whileTap={{ scale: 0.94 }}
                      onClick={() => actMut.mutate({ id: item.order_item_id, action: 'ready' })}
                      disabled={actMut.isPending}
                      className="flex-1 min-h-[56px] rounded-xl text-sm font-semibold
                        bg-primary-dark text-cream-card
                        hover:bg-primary-dark/90 transition-colors disabled:opacity-50">
                      Ready ✓
                    </motion.button>
                  )}
                </div>
              )}
              {compact && (
                <div className="flex gap-2 mt-2">
                  {item.status === 'PENDING' && (
                    <motion.button whileTap={{ scale: 0.94 }}
                      onClick={() => actMut.mutate({ id: item.order_item_id, action: 'receive' })}
                      disabled={actMut.isPending}
                      className="px-4 py-2 rounded-lg text-xs font-semibold
                        bg-status-pending/15 text-status-pending border border-status-pending/40 disabled:opacity-50">
                      Receive
                    </motion.button>
                  )}
                  {item.status === 'RECEIVED' && (
                    <motion.button whileTap={{ scale: 0.94 }}
                      onClick={() => actMut.mutate({ id: item.order_item_id, action: 'ready' })}
                      disabled={actMut.isPending}
                      className="px-4 py-2 rounded-lg text-xs font-semibold
                        bg-primary-dark text-cream-card disabled:opacity-50">
                      Ready ✓
                    </motion.button>
                  )}
                </div>
              )}
            </motion.div>
          )
        })}
      </AnimatePresence>
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
      className="w-9 h-9 rounded-xl border border-cream-alt flex items-center justify-center
        text-ink-secondary hover:bg-cream-alt/40 transition-colors">
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
    const id = setInterval(() => setTime(currentTime()), 30_000)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="min-h-screen bg-cream-card text-ink-primary">
      <AudioEnableSplash station={station} />

      {/* Header */}
      <div className="sticky top-0 z-10 bg-cream-card border-b border-cream-alt px-4 py-3">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-base font-bold tracking-widest uppercase text-ink-primary">
              {station === 'KITCHEN' ? 'Kitchen' : 'Bar'}
            </h1>
            <p className="text-xs text-ink-tertiary">
              {currentDate()} &middot; <span className="font-serif">{time}</span>
            </p>
          </div>

          <div className="flex items-center gap-2">
            <MuteButton />
            <div className="flex rounded-xl overflow-hidden border border-cream-alt">
              {(['queue', 'stock'] as const).map(v => (
                <button key={v} onClick={() => setView(v)}
                  className={`px-4 py-2 text-sm font-semibold capitalize transition-colors ${
                    view === v
                      ? 'bg-ink-primary text-cream-card'
                      : 'text-ink-secondary hover:bg-cream-alt'
                  }`}>
                  {v === 'queue' ? `Orders${count ? ` (${count})` : ''}` : 'Stock'}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="p-4">
        {view === 'queue'
          ? <QueueView station={station} onCount={setCount} />
          : <StockBoard />
        }
      </div>
    </div>
  )
}

export function KitchenQueueScreen() { return <StationBoard station="KITCHEN" /> }
export function BarQueueScreen()     { return <StationBoard station="BAR" /> }
