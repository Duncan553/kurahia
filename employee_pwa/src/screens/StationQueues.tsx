import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { useToastStore } from '@shared'
import api from '../lib/axios'

// Station dashboard for kitchen + bar tablets: live order queue + own-dept
// stock levels. No clock/alerts chrome — this is a shared station screen.

interface QueueItem {
  order_item_id: string; order_id: string; tab_reference: string | null
  menu_item: string | null; quantity: string; status: string
  age_seconds: number; ordered_by: string | null
}
interface StockItem {
  id: string; name: string; unit: string
  current_stock: string; reorder_level: string; below_reorder: boolean
}

const extractErr = (e: unknown) =>
  (e as { response?: { data?: { error?: string } } })?.response?.data?.error ?? 'Something went wrong.'

function ageCls(s: number) {
  if (s < 480) return 'text-status-paid'     // < 8 min — green
  if (s < 900) return 'text-status-pending'  // 8–15 min — amber
  return 'text-status-failed'                // > 15 min — red
}
const ageLabel = (s: number) => s >= 60 ? `${Math.floor(s / 60)}m ${s % 60}s` : `${s}s`

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
            ⚠ {low.length} item{low.length !== 1 ? 's' : ''} below reorder level
          </p>
        </div>
      )}
      {items.map(it => {
        const stock   = parseFloat(it.current_stock)
        const reorder = parseFloat(it.reorder_level)
        // Bar fills relative to 2× reorder level ("healthy" ceiling)
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
              {/* Reorder threshold tick at 50% — reorder = half of 2× ceiling */}
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
  const endpoint = station === 'KITCHEN' ? '/kitchen/queue' : '/bar/queue'

  const { data: items = [], isLoading, isError } = useQuery<QueueItem[]>({
    queryKey: ['queue', station],
    queryFn: () => api.get<QueueItem[]>(endpoint).then(r => r.data),
    refetchInterval: 15_000,
    staleTime: 0,
    select: (data) => { onCount(data.length); return data },
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
    <div className="space-y-3">
      {[1,2,3].map(i => <div key={i} className="h-24 rounded-2xl bg-cream-alt animate-pulse" />)}
    </div>
  )
  if (isError) return (
    <p className="text-status-failed text-sm text-center py-8">Failed to load queue. Check your connection.</p>
  )
  if (items.length === 0) return (
    <div className="flex flex-col items-center justify-center py-24 gap-2">
      <span className="text-4xl">✓</span>
      <p className="text-ink-tertiary text-lg font-medium">Queue is clear</p>
    </div>
  )

  return (
    <div className="space-y-3">
      {items.map(item => (
        <motion.div
          key={item.order_item_id}
          layout
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          className={`rounded-2xl border p-4 ${
            item.status === 'RECEIVED'
              ? 'border-status-pending/40 bg-status-pending/8'
              : 'border-cream-alt bg-cream-card'
          }`}
        >
          <div className="flex items-start justify-between gap-3">
            <div className="flex-1 min-w-0">
              {/* Item name + qty */}
              <div className="flex items-baseline gap-2 flex-wrap">
                <span className="font-bold text-lg text-ink-primary leading-snug">{item.menu_item}</span>
                <span className="text-ink-tertiary text-sm font-medium">×{item.quantity}</span>
                {item.status === 'RECEIVED' && (
                  <span className="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded-md
                    bg-status-pending/20 text-status-pending tracking-wide">
                    preparing
                  </span>
                )}
              </div>
              {/* Tab + waiter + age */}
              <div className="flex items-center gap-2 mt-1 flex-wrap text-xs text-ink-secondary">
                <span className="font-medium">{item.tab_reference ?? 'Walk-in'}</span>
                {item.ordered_by && (
                  <>
                    <span className="text-ink-tertiary">·</span>
                    <span>{item.ordered_by}</span>
                  </>
                )}
                <span className="text-ink-tertiary">·</span>
                <span className={`font-semibold tabular-nums ${ageCls(item.age_seconds)}`}>
                  {ageLabel(item.age_seconds)}
                </span>
              </div>
            </div>

            {/* Action button */}
            <div className="shrink-0">
              {item.status === 'PENDING' && (
                <motion.button whileTap={{ scale: 0.94 }}
                  onClick={() => actMut.mutate({ id: item.order_item_id, action: 'receive' })}
                  disabled={actMut.isPending}
                  className="px-4 py-2.5 rounded-xl text-sm font-semibold
                    bg-status-pending/15 text-status-pending border border-status-pending/40
                    hover:bg-status-pending/25 transition-colors disabled:opacity-50">
                  Start Preparing
                </motion.button>
              )}
              {item.status === 'RECEIVED' && (
                <motion.button whileTap={{ scale: 0.94 }}
                  onClick={() => actMut.mutate({ id: item.order_item_id, action: 'ready' })}
                  disabled={actMut.isPending}
                  className="px-4 py-2.5 rounded-xl text-sm font-semibold
                    bg-primary-dark text-cream-card
                    hover:bg-primary-dark/90 transition-colors disabled:opacity-50">
                  Ready ✓
                </motion.button>
              )}
            </div>
          </div>
        </motion.div>
      ))}
    </div>
  )
}

// ── Station shell ─────────────────────────────────────────────────────────────

function StationBoard({ station }: { station: 'KITCHEN' | 'BAR' }) {
  const [view, setView]   = useState<'queue' | 'stock'>('queue')
  const [count, setCount] = useState(0)

  return (
    // 60% cream background, 30% ink content, 10% terracotta highlights
    <div className="min-h-screen bg-cream-card text-ink-primary">

      {/* Header */}
      <div className="sticky top-0 z-10 bg-cream-card border-b border-cream-alt px-4 py-3
        flex items-center justify-between">
        <h1 className="text-base font-bold tracking-widest uppercase text-ink-primary">
          {station === 'KITCHEN' ? 'Kitchen' : 'Bar'}
        </h1>

        {/* Tab switcher */}
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
