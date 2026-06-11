import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { useToastStore } from '@shared'
import api from '../lib/axios'

// Station dashboard for kitchen + bar tablets: live order queue + own-dept
// stock levels. No clock/alerts chrome — this is a fixed station screen.

interface QueueItem {
  order_item_id: string; order_id: string; tab_reference: string | null
  menu_item: string | null; quantity: string; status: string; age_seconds: number
}
interface StockItem {
  id: string; name: string; unit: string
  current_stock: string; reorder_level: string; below_reorder: boolean
}

const extractErr = (e: unknown) =>
  (e as { response?: { data?: { error?: string } } })?.response?.data?.error ?? 'Something went wrong.'

function ageCls(s: number) {
  if (s < 480) return 'text-status-paid'     // < 8 min
  if (s < 900) return 'text-status-pending'  // 8–15 min
  return 'text-status-failed'                // > 15 min
}
const ageLabel = (s: number) => s >= 60 ? `${Math.floor(s / 60)}m ${s % 60}s` : `${s}s`

// ── Stock view — horizontal bars scaled against 2× reorder level ─────────────

function StockBoard() {
  // Backend auto-scopes /inventory/items to the caller's department
  const { data: items = [], isLoading } = useQuery<StockItem[]>({
    queryKey: ['station-stock'],
    queryFn: () => api.get<StockItem[]>('/inventory/items').then(r => r.data),
    refetchInterval: 60_000,
  })

  if (isLoading) return <p className="text-cream-card/40 text-center py-16">Loading stock…</p>
  if (items.length === 0) return (
    <p className="text-cream-card/40 text-center py-16">
      No stock items set up for this department yet. Ask your manager.
    </p>
  )

  const low = items.filter(i => i.below_reorder)
  return (
    <div className="space-y-4">
      {low.length > 0 && (
        <div className="rounded-2xl border border-status-failed/40 bg-status-failed/10 p-3">
          <p className="text-status-failed text-sm font-bold">
            ⚠ {low.length} item{low.length !== 1 ? 's' : ''} below reorder level
          </p>
        </div>
      )}
      {items.map(it => {
        const stock = parseFloat(it.current_stock)
        const reorder = parseFloat(it.reorder_level)
        // Bar fills relative to 2× reorder level (a sensible "healthy" ceiling)
        const pct = reorder > 0 ? Math.min((stock / (reorder * 2)) * 100, 100) : stock > 0 ? 100 : 0
        return (
          <div key={it.id}>
            <div className="flex items-baseline justify-between mb-1">
              <span className="text-sm font-semibold">{it.name}</span>
              <span className={`text-sm tabular-nums font-bold ${it.below_reorder ? 'text-status-failed' : 'text-cream-card/70'}`}>
                {stock} {it.unit}
              </span>
            </div>
            <div className="h-3 rounded-full bg-cream-card/10 overflow-hidden relative">
              <div
                className={`h-full rounded-full ${it.below_reorder ? 'bg-status-failed' : 'bg-status-paid'}`}
                style={{ width: `${pct}%` }}
              />
              {/* Reorder threshold tick at the 50% mark (reorder = half of ceiling) */}
              {reorder > 0 && <div className="absolute inset-y-0 left-1/2 w-px bg-cream-card/40" />}
            </div>
            <p className="text-[10px] text-cream-card/40 mt-0.5">reorder at {reorder} {it.unit}</p>
          </div>
        )
      })}
    </div>
  )
}

// ── Queue view ────────────────────────────────────────────────────────────────

function QueueView({ station }: { station: 'KITCHEN' | 'BAR' }) {
  const qc = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  const endpoint = station === 'KITCHEN' ? '/kitchen/queue' : '/bar/queue'

  const { data: items = [], isLoading, isError } = useQuery<QueueItem[]>({
    queryKey: ['queue', station],
    queryFn: () => api.get<QueueItem[]>(endpoint).then(r => r.data),
    refetchInterval: 15_000,
    staleTime: 0,
  })

  const actMut = useMutation({
    mutationFn: ({ id, action }: { id: string; action: 'receive' | 'ready' }) =>
      api.post(`/order-items/${id}/${action}`),
    onSuccess: (_d, v) => {
      qc.invalidateQueries({ queryKey: ['queue', station] })
      if (v.action === 'ready') addToast({ type: 'success', message: 'Waiter has been notified.' })
    },
    onError: (e) => addToast({ type: 'error', message: extractErr(e) }),
  })

  if (isLoading) return (
    <div className="space-y-3">{[1,2,3].map(i =>
      <div key={i} className="h-20 rounded-2xl bg-cream-card/10 animate-pulse" />)}</div>
  )
  if (isError) return (
    <p className="text-status-failed text-sm text-center py-8">Failed to load queue. Check your connection.</p>
  )
  if (items.length === 0) return (
    <p className="text-cream-card/40 text-center py-20 text-xl">Queue is clear ✓</p>
  )

  return (
    <div className="space-y-3">
      {items.map(item => (
        <div key={item.order_item_id}
          className={`rounded-2xl border p-4 ${
            item.status === 'RECEIVED'
              ? 'border-status-pending/40 bg-status-pending/10'
              : 'border-cream-card/15 bg-cream-card/5'
          }`}>
          <div className="flex items-center justify-between gap-3">
            <div className="flex-1 min-w-0">
              <div className="flex items-baseline gap-2 flex-wrap">
                <span className="font-bold text-base leading-snug">{item.menu_item}</span>
                <span className="text-cream-card/50 text-sm">×{item.quantity}</span>
                {item.status === 'RECEIVED' && (
                  <span className="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded
                    bg-status-pending/20 text-status-pending">preparing</span>
                )}
              </div>
              <p className="text-xs text-cream-card/50 mt-1">
                {item.tab_reference ?? 'Walk-in'}
                {' · '}
                <span className={ageCls(item.age_seconds)}>{ageLabel(item.age_seconds)}</span>
              </p>
            </div>
            <div className="shrink-0">
              {item.status === 'PENDING' && (
                <motion.button whileTap={{ scale: 0.94 }}
                  onClick={() => actMut.mutate({ id: item.order_item_id, action: 'receive' })}
                  disabled={actMut.isPending}
                  className="px-4 py-3 rounded-xl text-sm font-semibold
                    bg-status-pending/20 text-status-pending border border-status-pending/40
                    disabled:opacity-50">
                  Start Preparing
                </motion.button>
              )}
              {item.status === 'RECEIVED' && (
                <motion.button whileTap={{ scale: 0.94 }}
                  onClick={() => actMut.mutate({ id: item.order_item_id, action: 'ready' })}
                  disabled={actMut.isPending}
                  className="px-4 py-3 rounded-xl text-sm font-semibold
                    bg-status-paid/20 text-status-paid border border-status-paid/40
                    disabled:opacity-50">
                  Ready — notify waiter ✓
                </motion.button>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Station shell ─────────────────────────────────────────────────────────────

function StationBoard({ station }: { station: 'KITCHEN' | 'BAR' }) {
  const [view, setView] = useState<'queue' | 'stock'>('queue')
  const { data: queue = [] } = useQuery<QueueItem[]>({ queryKey: ['queue', station] })

  return (
    <div className="min-h-screen bg-ink-primary text-cream-card p-4">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-lg font-bold tracking-widest uppercase">
          {station === 'KITCHEN' ? 'Kitchen' : 'Bar'}
        </h1>
        <div className="flex rounded-xl overflow-hidden border border-cream-card/20">
          {(['queue', 'stock'] as const).map(v => (
            <button key={v} onClick={() => setView(v)}
              className={`px-4 py-2 text-sm font-semibold capitalize transition-colors ${
                view === v ? 'bg-cream-card text-ink-primary' : 'text-cream-card/60'
              }`}>
              {v === 'queue' ? `Orders${queue.length ? ` (${queue.length})` : ''}` : 'Stock'}
            </button>
          ))}
        </div>
      </div>
      {view === 'queue' ? <QueueView station={station} /> : <StockBoard />}
    </div>
  )
}

export function KitchenQueueScreen() { return <StationBoard station="KITCHEN" /> }
export function BarQueueScreen()     { return <StationBoard station="BAR" /> }
