import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Skeleton, EmptyState, Icon, resortToday, resortDatePlus } from '@shared'
import api from '../lib/axios'

/**
 * Menu engineering — the Kasavana-Smith matrix.
 *
 * Two axes measured against THIS MENU'S OWN AVERAGES: how often a dish sells,
 * and how many shillings it contributes each time it does.
 *
 * The axis is contribution margin, not food-cost percentage. A dish at 20% cost
 * sounds better than one at 40%, but if the first sells for 300 and the second
 * for 1,800 the second puts far more in the till. Percentage describes a dish;
 * contribution margin describes the business.
 */

interface Item {
  id: string
  name: string
  category: string | null
  prep_station: string
  price: string
  units_sold: string
  food_cost?: string
  contribution_margin?: string
  total_contribution?: string
  food_cost_pct?: string | null
  classification?: string
  action?: string
  reason?: string
}
interface Matrix {
  thresholds: { avg_units_sold: string; avg_contribution_margin: string }
  items: Record<string, Item[]>
  counts: Record<string, number>
  unclassified: { count: number; items: Item[]; note: string }
}

// Order matters: the owner should meet their best dishes first and their worst
// last, because the list doubles as a to-do.
const ORDER = ['STAR', 'PLOWHORSE', 'PUZZLE', 'DOG'] as const

const STYLE: Record<string, { label: string; ring: string; text: string; blurb: string }> = {
  STAR:      { label: 'Stars',      ring: 'border-l-status-paid',    text: 'text-status-paid',
               blurb: 'Selling well and earning well. Protect these.' },
  PLOWHORSE: { label: 'Plowhorses', ring: 'border-l-status-pending', text: 'text-status-pending',
               blurb: 'Popular but thin. People already want them — cut the cost or lift the price.' },
  PUZZLE:    { label: 'Puzzles',    ring: 'border-l-primary-main',   text: 'text-primary-main',
               blurb: 'Good money, few takers. Promote, rename, or move up the menu.' },
  DOG:       { label: 'Dogs',       ring: 'border-l-status-failed',  text: 'text-status-failed',
               blurb: 'Neither selling nor earning. Remove unless they exist for a reason.' },
}

const kes = (v: string | number) =>
  `KSh ${parseFloat(String(v)).toLocaleString('en-KE', { maximumFractionDigits: 0 })}`

export default function MenuProfitScreen() {
  // Default to the last 30 days: long enough for popularity to mean something,
  // short enough that a menu change from last quarter is not still counted.
  const [from, setFrom] = useState(resortDatePlus(-30))
  const [to, setTo] = useState(resortToday())

  const { data, isLoading, isError } = useQuery<Matrix>({
    queryKey: ['menu-engineering', from, to],
    queryFn: () => api.get<Matrix>(`/finance/menu-engineering?from=${from}&to=${to}`)
      .then(r => r.data),
    staleTime: 60_000,
  })

  const anyClassified = data && Object.values(data.counts ?? {}).some(n => n > 0)

  return (
    <div className="p-4 md:p-6 max-w-5xl mx-auto space-y-4">

      <div>
        <h1 className="text-2xl font-bold text-ink-primary font-serif">Menu Profit</h1>
        <p className="text-xs text-ink-secondary mt-0.5">
          Every dish by how often it sells and what it earns — measured against your own menu.
        </p>
      </div>

      <div className="glass-card rounded-2xl p-4 grid sm:grid-cols-2 gap-3">
        <div>
          <label htmlFor="mp-from" className="block text-[10px] tracking-widest uppercase text-ink-secondary mb-1">From</label>
          <input id="mp-from" type="date" value={from} max={to}
            onChange={e => setFrom(e.target.value)} style={{ colorScheme: 'dark' }}
            className="w-full min-h-[44px] rounded-xl glass-card bg-transparent px-3 py-2
              text-sm text-ink-primary focus:outline-none focus:border-primary-main" />
        </div>
        <div>
          <label htmlFor="mp-to" className="block text-[10px] tracking-widest uppercase text-ink-secondary mb-1">To</label>
          <input id="mp-to" type="date" value={to} max={resortToday()}
            onChange={e => setTo(e.target.value)} style={{ colorScheme: 'dark' }}
            className="w-full min-h-[44px] rounded-xl glass-card bg-transparent px-3 py-2
              text-sm text-ink-primary focus:outline-none focus:border-primary-main" />
        </div>
      </div>

      {isLoading && <div className="space-y-2">{[1,2,3].map(i => <Skeleton key={i} variant="card" />)}</div>}

      {isError && (
        <p className="text-sm text-status-failed text-center py-8">
          Could not load. Manager or owner access required.
        </p>
      )}

      {data && (
        <>
          <p className="text-[11px] text-ink-tertiary tabular-nums">
            Averages for this period — {parseFloat(data.thresholds.avg_units_sold).toFixed(1)} sold,
            {' '}{kes(data.thresholds.avg_contribution_margin)} margin. A dish is above or below
            {' '}<em>these</em>, not an industry benchmark.
          </p>

          {!anyClassified && (
            <EmptyState
              icon={<Icon name="alert" size={40} />}
              title="Nothing can be measured yet"
              description="A dish needs a recipe and priced ingredients before its profit can be worked out. Record a purchase so ingredients learn their cost, then add recipes."
            />
          )}

          {ORDER.map(kind => {
            const rows = data.items?.[kind] ?? []
            if (!rows.length) return null
            const s = STYLE[kind]
            return (
              <section key={kind} className="space-y-2">
                <div className="flex items-baseline gap-2 flex-wrap">
                  <h2 className={`text-lg font-bold font-serif ${s.text}`}>{s.label}</h2>
                  <span className="text-xs text-ink-tertiary tabular-nums">{rows.length}</span>
                  <p className="text-xs text-ink-secondary">{s.blurb}</p>
                </div>
                {rows.map(r => (
                  <div key={r.id} className={`glass-card rounded-xl px-4 py-3 border-l-4 ${s.ring}`}>
                    <div className="flex items-start justify-between gap-3 flex-wrap">
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-ink-primary">{r.name}</p>
                        <p className="text-xs text-ink-tertiary">
                          {r.category ?? 'Uncategorised'} · {r.units_sold} sold
                        </p>
                      </div>
                      <div className="text-right shrink-0">
                        {/* Total contribution first: one dish earning 200 x 50
                            times matters more than one earning 1,600 once. */}
                        <p className="text-sm font-bold text-ink-primary tabular-nums">
                          {kes(r.total_contribution ?? 0)}
                        </p>
                        <p className="text-[11px] text-ink-tertiary tabular-nums">
                          {kes(r.contribution_margin ?? 0)} each · {kes(r.price)} price
                          {r.food_cost_pct ? ` · ${parseFloat(r.food_cost_pct).toFixed(0)}% cost` : ''}
                        </p>
                      </div>
                    </div>
                    {r.action && (
                      <p className="text-xs text-ink-secondary mt-2">{r.action}</p>
                    )}
                  </div>
                ))}
              </section>
            )
          })}

          {/* Not a footnote. On this menu it is most of the list, and it is the
              actual work: a dish with no recipe cannot be measured, and guessing
              its cost would drive a real decision to keep or drop it. */}
          {data.unclassified?.count > 0 && (
            <section className="space-y-2 pt-2">
              <div className="flex items-baseline gap-2 flex-wrap">
                <h2 className="text-lg font-bold font-serif text-ink-secondary">Cannot be measured</h2>
                <span className="text-xs text-ink-tertiary tabular-nums">{data.unclassified.count}</span>
              </div>
              <p className="text-xs text-ink-secondary">{data.unclassified.note}</p>
              <div className="glass-card rounded-xl p-3 flex flex-wrap gap-x-4 gap-y-1">
                {data.unclassified.items.map(r => (
                  <span key={r.id} className="text-xs text-ink-tertiary">
                    {r.name} <span className="text-ink-tertiary/70">· {kes(r.price)}</span>
                  </span>
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  )
}
