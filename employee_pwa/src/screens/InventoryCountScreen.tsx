import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Skeleton, EmptyState, useToastStore } from '@shared'
import api from '../lib/axios'
import { RequireRole } from '../components/AuthGate'
import { todayKey } from '../lib/format'

interface InventoryItem {
  id: string
  name: string
  unit: string
  department_id: string
  is_active: boolean
  current_stock: string
  reorder_level: string
  below_reorder: boolean
  is_watch_list: boolean
  is_staff_food: boolean
}

interface CountResult {
  id: string
  item: string
  counted: string
  prior_stock: string
  adjustment: string
  duplicate?: boolean
}

interface VarianceItem {
  item_id: string
  item_name: string
  no_closing_count?: boolean
  flagged?: boolean
  variance_pct?: string
  opening_stock?: string
  closing_stock?: string
  adjustment?: string
}

interface VarianceReport {
  period_start: string
  period_end: string
  items: VarianceItem[]
  flagged_count: number
}

type Tab = 'count' | 'variance'

function genKey() { return crypto.randomUUID() }

function VarianceBadge({ adj, watchList }: { adj: string; watchList: boolean }) {
  const val = parseFloat(adj)
  if (val === 0) return null
  if (val > 0) return (
    <span className="text-xs font-medium tabular-nums text-blue-600">+{val}</span>
  )
  if (watchList) return (
    <span className="flex items-center gap-1 text-xs font-medium tabular-nums text-status-failed">
      <svg width="10" height="10" viewBox="0 0 10 10" fill="currentColor" aria-hidden="true"><circle cx="5" cy="5" r="4"/></svg>
      {val}
    </span>
  )
  return <span className="text-xs font-medium tabular-nums text-status-pending">{val}</span>
}

export default function InventoryCountScreen() {
  const addToast = useToastStore((s) => s.addToast)
  const [tab, setTab] = useState<Tab>('count')

  // Per-item input values and submission state
  const [inputs,  setInputs]  = useState<Record<string, string>>({})
  const [keys,    setKeys]    = useState<Record<string, string>>({})
  const [results, setResults] = useState<Record<string, CountResult>>({})
  const [pending, setPending] = useState<Set<string>>(new Set())

  // Variance date range — default to today
  const today = todayKey()
  const [fromDate, setFromDate] = useState(today)
  const [toDate,   setToDate]   = useState(today)
  const [varTriggered, setVarTriggered] = useState(false)

  const { data: items, isLoading, isError } = useQuery<InventoryItem[]>({
    queryKey: ['inventory-items'],
    queryFn: () => api.get<InventoryItem[]>('/inventory/items').then((r) => r.data),
  })

  const { data: variance, isFetching: varFetching, refetch: refetchVariance } = useQuery<VarianceReport>({
    queryKey: ['inventory-variance', fromDate, toDate],
    queryFn: () => api.get<VarianceReport>(
      `/inventory/variance?from=${fromDate}T00:00:00&to=${toDate}T23:59:59`
    ).then((r) => r.data),
    enabled: varTriggered,
  })

  function getKey(itemId: string) {
    if (!keys[itemId]) {
      const k = genKey()
      setKeys((prev) => ({ ...prev, [itemId]: k }))
      return k
    }
    return keys[itemId]
  }

  function submitCount(item: InventoryItem) {
    const raw = inputs[item.id]?.trim()
    if (!raw || isNaN(parseFloat(raw))) {
      addToast({ type: 'error', message: `Enter a valid number for ${item.name}.` })
      return
    }
    const idemKey = getKey(item.id)
    setPending((prev) => new Set(prev).add(item.id))

    api.post<CountResult>('/inventory/counts', {
      item_id:         item.id,
      counted_amount:  parseFloat(raw),
      idempotency_key: idemKey,
    })
      .then((r) => {
        const data = r.data
        setResults((prev) => ({ ...prev, [item.id]: data }))
        // Fresh key so retry = new submission
        setKeys((prev) => ({ ...prev, [item.id]: genKey() }))
        if (data.duplicate) {
          addToast({ type: 'warning', message: `Count already submitted for ${data.item}.` })
        } else {
          const adj = parseFloat(data.adjustment)
          const sign = adj >= 0 ? '+' : ''
          addToast({ type: 'success', message: `Count saved for ${data.item}. Variance: ${sign}${adj} ${item.unit}.` })
        }
      })
      .catch((err) => {
        const msg = err?.response?.data?.error ?? 'Count submission failed.'
        addToast({ type: 'error', message: msg })
      })
      .finally(() => {
        setPending((prev) => { const s = new Set(prev); s.delete(item.id); return s })
      })
  }

  // Non-staff-food items for counting
  const countItems = useMemo(() => (items ?? []).filter((i) => !i.is_staff_food), [items])

  return (
    <RequireRole minLevel={5}>
      <div className="p-4 max-w-lg mx-auto space-y-4">

        <div>
          <h1 className="text-xl font-bold text-ink-primary">Inventory Count</h1>
          <p className="text-sm text-ink-tertiary">Physical count per item — each saves independently</p>
        </div>

        {/* ── Tab bar ─────────────────────────────────────────────── */}
        <div className="flex gap-1 bg-cream-alt/50 rounded-xl p-1">
          {(['count', 'variance'] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={[
                'flex-1 py-2 rounded-lg text-xs font-medium capitalize transition-all',
                tab === t
                  ? 'bg-cream-card shadow-sm text-ink-primary'
                  : 'text-ink-tertiary hover:text-ink-secondary',
              ].join(' ')}
            >
              {t === 'count' ? 'Count' : 'Variance Report'}
            </button>
          ))}
        </div>

        {/* ── COUNT TAB ────────────────────────────────────────────── */}
        {tab === 'count' && (
          <>
            {isLoading && (
              <div className="space-y-3">
                {[1,2,3,4].map((i) => (
                  <div key={i} className="rounded-xl bg-cream-alt/40 p-3 flex items-center justify-between gap-3">
                    <Skeleton variant="text" className="w-32" />
                    <Skeleton variant="button" className="w-24 h-9" />
                  </div>
                ))}
              </div>
            )}

            {isError && (
              <div className="p-4 rounded-xl bg-cream-alt/40 text-sm text-ink-tertiary text-center">
                Couldn't load items. Check connection.
              </div>
            )}

            {!isLoading && !isError && countItems.length === 0 && (
              <EmptyState
                icon={<svg width="48" height="48" viewBox="0 0 48 48" fill="none" aria-hidden="true">
                  <rect x="8" y="12" width="32" height="28" rx="3" stroke="currentColor" strokeWidth="2"/>
                  <path d="M16 12V8a4 4 0 018 0v4M32 12V8a4 4 0 018 0v4" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                  <path d="M16 24h16M16 30h10" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                </svg>}
                title="No inventory items configured yet."
                description="Ask the owner to add items first."
              />
            )}

            {!isLoading && countItems.map((item) => {
              const result = results[item.id]
              const submitted = !!result && !result.duplicate
              const adj = result ? parseFloat(result.adjustment) : null

              return (
                <div
                  key={item.id}
                  className={[
                    'rounded-xl border p-3 space-y-2 transition-colors',
                    submitted ? 'bg-primary-light/20 border-primary-main/30' : 'bg-cream-alt/30 border-cream-alt',
                  ].join(' ')}
                >
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-ink-primary">{item.name}</span>
                    <span className="text-xs text-ink-tertiary">{item.unit}</span>
                    {item.below_reorder && (
                      <span className="text-[10px] font-semibold uppercase tracking-wide
                        bg-status-pending/10 text-status-pending rounded-full px-2 py-0.5">
                        Reorder
                      </span>
                    )}
                    {item.is_watch_list && (
                      <span className="text-[10px] font-semibold uppercase tracking-wide
                        bg-status-failed/10 text-status-failed rounded-full px-2 py-0.5">
                        Watch
                      </span>
                    )}
                    {submitted && (
                      <span className="ml-auto text-primary-dark">
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
                          <circle cx="8" cy="8" r="8" opacity="0.2"/>
                          <path d="M4.5 8l2.5 2.5L11.5 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
                        </svg>
                      </span>
                    )}
                  </div>

                  <div className="flex items-center gap-2">
                    <span className="text-xs text-ink-tertiary tabular-nums shrink-0">
                      System: {item.current_stock} {item.unit}
                    </span>
                    {adj !== null && <VarianceBadge adj={result!.adjustment} watchList={item.is_watch_list} />}
                  </div>

                  <div className="flex gap-2">
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      inputMode="decimal"
                      placeholder="Counted qty"
                      value={inputs[item.id] ?? ''}
                      onChange={(e) => setInputs((prev) => ({ ...prev, [item.id]: e.target.value }))}
                      disabled={pending.has(item.id)}
                      className="flex-1 rounded-xl border border-cream-alt bg-white px-3 py-2
                        text-sm text-ink-primary focus:outline-none focus:border-primary-dark
                        focus:ring-2 focus:ring-primary-dark/20 disabled:opacity-50"
                    />
                    <button
                      onClick={() => submitCount(item)}
                      disabled={pending.has(item.id) || !inputs[item.id]?.trim()}
                      className={[
                        'px-4 py-2 rounded-xl text-sm font-semibold transition-all shrink-0',
                        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark',
                        'disabled:opacity-40 disabled:cursor-not-allowed',
                        submitted
                          ? 'bg-primary-main/20 text-primary-dark hover:bg-primary-main/30'
                          : 'bg-primary-dark text-cream-card hover:bg-primary-dark/90',
                      ].join(' ')}
                    >
                      {pending.has(item.id) ? (
                        <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
                          <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" strokeOpacity="0.3"/>
                          <path d="M21 12a9 9 0 01-9 9" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                        </svg>
                      ) : submitted ? 'Re-count' : 'Save'}
                    </button>
                  </div>
                </div>
              )
            })}
          </>
        )}

        {/* ── VARIANCE TAB ─────────────────────────────────────────── */}
        {tab === 'variance' && (
          <div className="space-y-4">
            <div className="flex gap-2 items-end">
              <div className="flex-1">
                <label className="block text-xs font-medium text-ink-tertiary mb-1">From</label>
                <input
                  type="date"
                  value={fromDate}
                  onChange={(e) => setFromDate(e.target.value)}
                  className="w-full rounded-xl border border-cream-alt bg-white px-3 py-2.5
                    text-sm text-ink-primary focus:outline-none focus:border-primary-dark
                    focus:ring-2 focus:ring-primary-dark/20"
                />
              </div>
              <div className="flex-1">
                <label className="block text-xs font-medium text-ink-tertiary mb-1">To</label>
                <input
                  type="date"
                  value={toDate}
                  onChange={(e) => setToDate(e.target.value)}
                  className="w-full rounded-xl border border-cream-alt bg-white px-3 py-2.5
                    text-sm text-ink-primary focus:outline-none focus:border-primary-dark
                    focus:ring-2 focus:ring-primary-dark/20"
                />
              </div>
              <button
                onClick={() => { setVarTriggered(true); refetchVariance() }}
                disabled={varFetching}
                className="px-4 py-2.5 rounded-xl bg-primary-dark text-cream-card text-sm font-semibold
                  hover:bg-primary-dark/90 disabled:opacity-50 transition-all shrink-0"
              >
                {varFetching ? '…' : 'Run'}
              </button>
            </div>

            {varFetching && (
              <div className="space-y-2">
                {[1,2,3].map((i) => <Skeleton key={i} variant="row" />)}
              </div>
            )}

            {!varFetching && variance && (
              <>
                {variance.flagged_count > 0 && (
                  <div className="rounded-xl bg-status-failed/5 border border-status-failed/20 p-3">
                    <p className="text-sm text-status-failed font-medium">
                      {variance.flagged_count} item{variance.flagged_count > 1 ? 's' : ''} flagged for review
                    </p>
                  </div>
                )}
                <div className="space-y-2">
                  {variance.items.map((v) => (
                    <div
                      key={v.item_id}
                      className={[
                        'rounded-xl border px-4 py-3',
                        v.flagged
                          ? 'border-status-failed/40 bg-status-failed/5'
                          : 'border-cream-alt bg-cream-alt/30',
                      ].join(' ')}
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-medium text-ink-primary text-sm">{v.item_name}</span>
                        {v.no_closing_count ? (
                          <span className="text-xs text-ink-tertiary italic">Not yet counted</span>
                        ) : (
                          <div className="flex items-center gap-2">
                            <span className="text-xs tabular-nums text-ink-tertiary">
                              {v.opening_stock} → {v.closing_stock}
                            </span>
                            {v.adjustment && (
                              <VarianceBadge adj={v.adjustment} watchList={false} />
                            )}
                          </div>
                        )}
                      </div>
                      {v.variance_pct && !v.no_closing_count && (
                        <p className={`text-[11px] mt-0.5 ${v.flagged ? 'text-status-failed' : 'text-ink-tertiary'}`}>
                          {parseFloat(v.variance_pct) > 0 ? '+' : ''}{v.variance_pct}% variance
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </>
            )}

            {!varFetching && !variance && (
              <p className="text-center text-sm text-ink-tertiary py-6">
                Select a date range and tap Run.
              </p>
            )}
          </div>
        )}
      </div>
    </RequireRole>
  )
}
