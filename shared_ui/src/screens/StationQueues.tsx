import { useState, useMemo, useEffect, useRef } from 'react'
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import api from '../lib/axios'
import { useToastStore, Icon } from '../index'
import { playOrderAlert, isMuted, setMuted as setAudioMuted } from '../lib/audio'

const MUTE_STORAGE_KEY = 'kurahia-audio-muted'

type Station = 'KITCHEN' | 'BAR'

interface QueueItem {
  order_item_id: string
  order_id: string
  tab_reference: string | null
  menu_item_id: string
  menu_item: string
  category: string | null
  quantity: string
  status: 'PENDING' | 'RECEIVED' | 'READY'
  created_at: string
  age_seconds: number
  ordered_by: string | null
  notes: string | null
  allergens: string | null
  dietary_flags: string | null
}

interface OrderGroup {
  order_id: string
  tab_reference: string | null
  status: 'PENDING' | 'RECEIVED' | 'READY' | 'MIXED'
  items: QueueItem[]
  age_seconds: number
  ordered_by: string | null
}

/* ── Utilities ─────────────────────────────────────────────────── */
function groupByOrder(items: QueueItem[]): OrderGroup[] {
  const map = new Map<string, QueueItem[]>()
  for (const it of items) {
    const arr = map.get(it.order_id) ?? []
    arr.push(it)
    map.set(it.order_id, arr)
  }
  return Array.from(map.entries()).map(([order_id, items]) => {
    const statuses = new Set(items.map(i => i.status))
    let status: OrderGroup['status'] = 'MIXED'
    if (statuses.size === 1) status = items[0].status
    const maxAge = Math.max(...items.map(i => i.age_seconds))
    return {
      order_id,
      tab_reference: items[0].tab_reference,
      status,
      items,
      age_seconds: maxAge,
      ordered_by: items[0].ordered_by,
    }
  })
}

function ordLabel(id: string) { return `#${id.slice(0, 6).toUpperCase()}` }

function formatTimer(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
}

function timerColor(seconds: number): string {
  if (seconds < 300) return 'text-status-paid'      // < 5 min: green
  if (seconds < 600) return 'text-status-pending'  // < 10 min: yellow
  return 'text-status-failed'                        // >= 10 min: red
}

/* ── Order Ticket Card (KDS Style) ─────────────────────────────── */
function OrderTicket({
  group,
  station,
  onAction,
  isPending,
}: {
  group: OrderGroup
  station: Station
  onAction: (id: string, action: 'receive' | 'ready') => void
  isPending: boolean
}) {
  const [tick, setTick] = useState(0)

  // Live timer update every second
  useEffect(() => {
    const id = setInterval(() => setTick(t => t + 1), 1000)
    return () => clearInterval(id)
  }, [])

  const liveSeconds = group.age_seconds + tick
  const isUrgent = liveSeconds >= 600

  // Color-coded header based on status
  const headerColors = {
    PENDING: 'bg-gradient-to-r from-status-failed/20 to-status-failed/5 border-status-failed/30',
    RECEIVED: 'bg-gradient-to-r from-status-pending/20 to-status-pending/5 border-status-pending/30',
    READY: 'bg-gradient-to-r from-status-paid/20 to-status-paid/5 border-status-paid/30',
    MIXED: 'bg-gradient-to-r from-status-pending/20 to-status-pending/5 border-status-pending/30',
  }

  const allPending = group.status === 'PENDING'
  const allReceived = group.status === 'RECEIVED'
  const allReady = group.status === 'READY'

  return (
    <motion.div
      layout
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.9 }}
      className="glass-card overflow-hidden flex flex-col"
    >
      {/* ── Color-coded header band ─────────────────────────────── */}
      <div className={`px-4 py-3 border-b ${headerColors[group.status]} flex items-center justify-between`}>
        <div className="flex items-center gap-3">
          <span className="text-lg font-bold font-mono text-ink-primary">{ordLabel(group.order_id)}</span>
          <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-white/10 text-ink-secondary">
            {group.tab_reference ?? 'Walk-in'}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-2xl font-mono font-bold tabular-nums ${timerColor(liveSeconds)}`}>
            {formatTimer(liveSeconds)}
          </span>
          {isUrgent && (
            <span className="animate-pulse w-2 h-2 rounded-full bg-status-failed" />
          )}
        </div>
      </div>

      {/* ── Ordered by ──────────────────────────────────────────── */}
      <div className="px-4 py-1.5 bg-white/[0.02] border-b border-white/[0.06]">
        <span className="text-[11px] uppercase tracking-wider text-ink-tertiary">
          Ordered by {group.ordered_by ?? 'Unknown'} · {group.items.length} item{group.items.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* ── Item list ───────────────────────────────────────────── */}
      <div className="flex-1 p-4 space-y-3">
        {group.items.map(item => (
          <div key={item.order_item_id} className="flex items-start gap-3">
            <span className="text-lg font-bold text-primary-main min-w-[2rem]">{item.quantity}×</span>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-ink-primary leading-tight">{item.menu_item}</p>
              {item.notes && (
                <p className="text-xs text-ink-tertiary mt-0.5">— {item.notes}</p>
              )}
              {item.allergens && (
                <span className="inline-flex items-center gap-1 mt-1 px-1.5 py-0.5 rounded bg-status-failed/15 text-status-failed text-[10px] font-bold border border-status-failed/25">
                  <Icon name="alert" size={11} strokeWidth={2} /> ALLERGENS: {item.allergens}
                </span>
              )}
              {item.dietary_flags && (
                <span className="inline-flex items-center gap-1 mt-1 px-1.5 py-0.5 rounded bg-status-pending/15 text-status-pending text-[10px] font-bold border border-status-pending/25">
                  {item.dietary_flags}
                </span>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* ── Action bar ──────────────────────────────────────────── */}
      <div className="px-4 py-3 bg-white/[0.02] border-t border-white/[0.06] flex gap-2">
        {allPending && (
          <button
            onClick={() => group.items.forEach(it => onAction(it.order_item_id, 'receive'))}
            disabled={isPending}
            className="flex-1 py-3 rounded-xl text-sm font-bold uppercase tracking-wider
                       gradient-hero text-white disabled:opacity-50
                       focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-main"
          >
            {station === 'BAR' ? 'Start Mixing' : 'Start Cooking'}
          </button>
        )}

        {allReceived && (
          <>
            <button
              onClick={() => group.items.forEach(it => onAction(it.order_item_id, 'ready'))}
              disabled={isPending}
              className="flex-1 py-3 rounded-xl text-sm font-bold uppercase tracking-wider
                         gradient-hero text-white disabled:opacity-50
                         focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-main"
            >
              {/* This fires the RECEIVED→READY transition (marks it ready at the pass) —
                  a separate /order-items/:id/serve endpoint exists for the waiter to
                  call once it actually reaches the guest. "Serve" here read as if that
                  had already happened, and disagreed with Kitchen's "Complete" for the
                  identical state change. */}
              Ready for Pickup
            </button>
          </>
        )}

        {group.status === 'MIXED' && (
          <>
            <button
              onClick={() => group.items.filter(it => it.status === 'PENDING').forEach(it => onAction(it.order_item_id, 'receive'))}
              disabled={isPending}
              className="flex-1 py-3 rounded-xl text-sm font-bold uppercase tracking-wider
                         bg-white/8 text-ink-primary border border-white/15
                         hover:bg-white/12 disabled:opacity-50"
            >
              Start Remaining
            </button>
            <button
              onClick={() => group.items.filter(it => it.status === 'RECEIVED').forEach(it => onAction(it.order_item_id, 'ready'))}
              disabled={isPending}
              className="flex-1 py-3 rounded-xl text-sm font-bold uppercase tracking-wider
                         gradient-hero text-white disabled:opacity-50"
            >
              Finish
            </button>
          </>
        )}

        {allReady && (
          <span className="flex-1 flex items-center justify-center gap-1.5 py-3 rounded-xl text-sm font-bold uppercase tracking-wider
                           bg-status-paid/15 text-status-paid border border-status-paid/25">
            <Icon name="check" size={16} strokeWidth={2.5} /> Ready for Pickup
          </span>
        )}
      </div>
    </motion.div>
  )
}

/* ── Station Shell ─────────────────────────────────────────────── */
function StationBoard({ station }: { station: Station }) {
  const qc = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  // Was useState(isMuted) with a same-named local setMuted — it only ever
  // updated this component's own UI state, never called lib/audio.ts's real
  // setMuted(), so playOrderAlert()'s internal `muted` check never changed:
  // the mute button toggled its icon but never actually muted anything.
  const [muted, setLocalMuted] = useState(() => {
    const stored = localStorage.getItem(MUTE_STORAGE_KEY)
    return stored !== null ? stored === '1' : isMuted()
  })
  const prevIdsRef = useRef<Set<string>>(new Set())

  const endpoint = station === 'KITCHEN' ? '/kitchen/queue' : '/bar/queue'
  const stationName = station === 'KITCHEN' ? 'Kitchen Station' : 'Bar Station'

  // The generic on api.get is what types `items` — without it the response is
  // `any`, and every `.map(i => ...)` below silently loses its typing too.
  const { data: items = [], isLoading, isError } = useQuery<QueueItem[]>({
    queryKey: ['queue', station],
    queryFn: () => api.get<QueueItem[]>(endpoint).then(r => r.data),
    refetchInterval: 15_000,
    staleTime: 0,
  })

  // lib/audio.ts's `muted` module variable starts false regardless of what
  // was persisted last session — sync it once on mount so a previously-muted
  // tablet doesn't start alerting again until someone re-taps the button.
  useEffect(() => { setAudioMuted(muted) }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  // Audio alert on new items
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
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: ['queue', station] })
      if (v.action === 'ready') addToast({ type: 'success', message: 'Waiter has been notified.' })
    },
    onError: (e: any) => addToast({ type: 'error', message: e?.response?.data?.error ?? 'Action failed' }),
  })

  const orderGroups = useMemo(() => groupByOrder(items), [items])

  // Sort: RECEIVED first (active cooking), then PENDING (new), then READY
  const sortedGroups = useMemo(() => {
    const statusOrder = { RECEIVED: 0, MIXED: 1, PENDING: 2, READY: 3 }
    return [...orderGroups].sort((a, b) => {
      const sa = statusOrder[a.status] ?? 9
      const sb = statusOrder[b.status] ?? 9
      if (sa !== sb) return sa - sb
      return b.age_seconds - a.age_seconds
    })
  }, [orderGroups])

  // Stats
  const pendingCount = items.filter(i => i.status === 'PENDING').length
  const receivedCount = items.filter(i => i.status === 'RECEIVED').length
  const urgentCount = items.filter(i => i.age_seconds >= 600 && i.status !== 'READY').length

  return (
    <div className="h-full flex flex-col">
      {/* ── Header ──────────────────────────────────────────────── */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-white/[0.08]">
        <div className="flex items-center gap-4">
          <h1 className="text-2xl font-bold text-ink-primary">{stationName}</h1>
          <div className="flex items-center gap-2">
            {pendingCount > 0 && (
              <span className="px-3 py-1 rounded-full bg-status-failed/15 text-status-failed text-sm font-bold border border-status-failed/25">
                {pendingCount} New
              </span>
            )}
            {receivedCount > 0 && (
              <span className="px-3 py-1 rounded-full bg-status-pending/15 text-status-pending text-sm font-bold border border-status-pending/25">
                {receivedCount} Active
              </span>
            )}
            {urgentCount > 0 && (
              <span className="px-3 py-1 rounded-full bg-status-failed/15 text-status-failed text-sm font-bold border border-status-failed/25 animate-pulse">
                <span className="inline-flex items-center gap-1">
                  <Icon name="alert" size={14} strokeWidth={2} /> {urgentCount} Urgent
                </span>
              </span>
            )}
          </div>
        </div>
        <button
          onClick={() => {
            const next = !muted
            setLocalMuted(next)
            setAudioMuted(next)  // the call that was missing — this is what playOrderAlert() actually checks
            localStorage.setItem(MUTE_STORAGE_KEY, next ? '1' : '0')
          }}
          className="p-2 rounded-lg glass-surface text-ink-tertiary hover:text-ink-primary"
          aria-label={muted ? 'Unmute alerts' : 'Mute alerts'}
        >
          {/* aria-label already lives on the button, so the icon stays decorative */}
          <Icon name={muted ? 'bellOff' : 'bell'} size={20} />
        </button>
      </div>

      {/* ── Content ─────────────────────────────────────────────── */}
      <div className="flex-1 overflow-auto p-6 glass-scroll">
        {isLoading && (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {[1, 2, 3].map(i => (
              <div key={i} className="glass-card h-64 animate-pulse" />
            ))}
          </div>
        )}

        {isError && (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <p className="text-ink-secondary text-lg">Failed to load queue</p>
            <p className="text-ink-tertiary text-sm mt-1">Check your connection and try again</p>
          </div>
        )}

        {!isLoading && !isError && items.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <Icon name="check" size={64} strokeWidth={1.5} className="mb-4 text-status-paid" />
            <p className="text-2xl font-bold text-ink-primary">Queue Clear</p>
            <p className="text-ink-tertiary mt-1">All orders have been prepared</p>
          </div>
        )}

        {!isLoading && !isError && sortedGroups.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            <AnimatePresence mode="popLayout">
              {sortedGroups.map(group => (
                <OrderTicket
                  key={group.order_id}
                  group={group}
                  station={station}
                  onAction={(id, action) => actMut.mutate({ id, action })}
                  isPending={actMut.isPending}
                />
              ))}
            </AnimatePresence>
          </div>
        )}
      </div>
    </div>
  )
}

export function KitchenQueueScreen() { return <StationBoard station="KITCHEN" /> }
export function BarQueueScreen() { return <StationBoard station="BAR" /> }
