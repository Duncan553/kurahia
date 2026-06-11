import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useToastStore } from '@shared'
import api from '../lib/axios'

interface QueueItem {
  order_item_id: string; order_id: string; tab_reference: string | null
  menu_item: string | null; quantity: string; status: string; age_seconds: number
}

const extractErr = (e: unknown) =>
  (e as { response?: { data?: { error?: string } } })?.response?.data?.error ?? 'Something went wrong.'

function ageCls(s: number) {
  if (s < 480) return 'text-status-paid'     // < 8 min: green
  if (s < 900) return 'text-status-pending'  // 8-15 min: amber
  return 'text-status-failed'                // > 15 min: red
}

function ageLabel(s: number) {
  const m = Math.floor(s / 60), sec = s % 60
  return m > 0 ? `${m}m ${sec}s` : `${sec}s`
}

function QueueBoard({ station }: { station: 'KITCHEN' | 'BAR' }) {
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
    onSuccess: () => qc.invalidateQueries({ queryKey: ['queue', station] }),
    onError: (e) => addToast({ type: 'error', message: extractErr(e) }),
  })

  return (
    <div className="min-h-screen bg-ink-primary text-cream-card p-4">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-lg font-bold tracking-widest uppercase">
          {station === 'KITCHEN' ? 'Kitchen Queue' : 'Bar Queue'}
        </h1>
        <span className="text-xs text-cream-card/50 tabular-nums">
          {items.length} item{items.length !== 1 ? 's' : ''}
        </span>
      </div>

      {isLoading && (
        <div className="space-y-3">
          {[1,2,3].map(i => (
            <div key={i} className="h-20 rounded-2xl bg-cream-card/10 animate-pulse" />
          ))}
        </div>
      )}

      {isError && (
        <p className="text-status-failed text-sm text-center py-8">
          Failed to load queue. Check your connection.
        </p>
      )}

      {!isLoading && !isError && items.length === 0 && (
        <p className="text-cream-card/40 text-center py-20 text-xl">Queue is clear ✓</p>
      )}

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
                </div>
                <p className="text-xs text-cream-card/50 mt-1">
                  {item.tab_reference ?? 'Walk-in'}
                  {' · '}
                  <span className={ageCls(item.age_seconds)}>{ageLabel(item.age_seconds)}</span>
                </p>
              </div>
              <div className="shrink-0">
                {item.status === 'PENDING' && (
                  <button
                    onClick={() => actMut.mutate({ id: item.order_item_id, action: 'receive' })}
                    disabled={actMut.isPending}
                    className="px-4 py-2 rounded-xl text-sm font-semibold
                      bg-status-pending/20 text-status-pending border border-status-pending/40
                      disabled:opacity-50">
                    Receive
                  </button>
                )}
                {item.status === 'RECEIVED' && (
                  <button
                    onClick={() => actMut.mutate({ id: item.order_item_id, action: 'ready' })}
                    disabled={actMut.isPending}
                    className="px-4 py-2 rounded-xl text-sm font-semibold
                      bg-status-paid/20 text-status-paid border border-status-paid/40
                      disabled:opacity-50">
                    Ready ✓
                  </button>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export function KitchenQueueScreen() { return <QueueBoard station="KITCHEN" /> }
export function BarQueueScreen()     { return <QueueBoard station="BAR" /> }
