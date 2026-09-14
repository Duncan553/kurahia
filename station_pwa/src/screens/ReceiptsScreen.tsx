/**
 * ReceiptsScreen — every bill the resort raised, searchable.
 *
 * GET /receipts (the LIST) has existed since Phase A with no caller anywhere in
 * the three PWAs — the same gap FolioScreen was built to close for the single
 * bill. So the only way to reach a bill was to already know whose it was and
 * open their folio from check-in. "Show me all of today's receipts" had no
 * answer on any screen, and the question front desk is asked most often is
 * exactly that.
 *
 * The endpoint requires FRONT_DESK_LEVEL (3), so this screen is gated to match
 * it. The tile that opens it is gated the same way — a tile that offers what
 * the screen refuses is the bug scripts/pwa_contract.py now checks for.
 *
 * Dates go through the resort's own business day on the server (06:00->06:00),
 * so "today" here means today's TRADING day, not midnight to midnight.
 */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { ErrorBoundary, EmptyState, Input, Icon } from '@shared'
import { RequireRole } from '../components/AuthGate'
import { formatDateTime } from '../lib/format'
import api from '../lib/axios'

interface Receipt {
  tab_id: string
  reference: string | null
  tab_type: string
  status: string
  opened_at: string
  opened_by: string | null
  balance: string
}

const ksh = (v: string) =>
  'KSh ' + parseFloat(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })

// Today in the browser's own date, used only to seed the picker. The SERVER
// decides what that date means (business_day_bounds) — this never computes a
// day boundary itself, because the resort's day is not the calendar's.
const todayISO = () => new Date().toISOString().slice(0, 10)

const TYPE_LABEL: Record<string, string> = {
  WALK_IN: 'Table', VILLA: 'Villa', BAND: 'Wristband', EVENT: 'Event',
}

export default function ReceiptsScreen() {
  const navigate = useNavigate()
  const [date, setDate] = useState(todayISO())
  const [q, setQ] = useState('')

  const { data: receipts = [], isLoading, isError, error } = useQuery<Receipt[]>({
    queryKey: ['receipts', date, q],
    queryFn: () => api
      .get<Receipt[]>('/receipts', { params: { date, ...(q ? { q } : {}) } })
      .then(r => r.data),
  })

  // A tab has THREE states, not two. balance = charges - payments, so:
  //   > 0  the guest owes the resort
  //   = 0  square
  //   < 0  the RESORT holds the guest's money — a wristband topped up at the
  //        gate and not yet spent down. Calling that "settled" (the first
  //        version of this screen did) hides money the resort is holding and
  //        will forfeit at exit, which is exactly the figure the gate needs.
  const owing  = receipts.filter(r => parseFloat(r.balance) > 0)
  const credit = receipts.filter(r => parseFloat(r.balance) < 0)
  const owedTotal   = owing.reduce((sum, r) => sum + parseFloat(r.balance), 0)
  const creditTotal = credit.reduce((sum, r) => sum - parseFloat(r.balance), 0)

  return (
    <RequireRole minLevel={3}>
      <ErrorBoundary level="tile">
        <div className="p-4 md:p-6 max-w-5xl mx-auto">
          <header className="mb-5">
            <h1 className="font-serif text-2xl md:text-3xl font-bold text-ink-primary">Receipts</h1>
            <p className="text-sm text-ink-tertiary mt-1">
              Every bill raised on the resort&rsquo;s trading day. Open one to see each
              line, what was paid, and who took it.
            </p>
          </header>

          <div className="flex flex-col sm:flex-row gap-3 mb-5">
            <div className="sm:w-48">
              <label htmlFor="receipt-date" className="block text-[11px] uppercase tracking-wider text-ink-tertiary mb-1">
                Trading day
              </label>
              <Input id="receipt-date" type="date" value={date}
                     onChange={e => setDate(e.target.value)} />
            </div>
            <div className="flex-1">
              <label htmlFor="receipt-q" className="block text-[11px] uppercase tracking-wider text-ink-tertiary mb-1">
                Find by reference
              </label>
              <Input id="receipt-q" type="search" placeholder="Villa 4, Band #12, a guest name&hellip;"
                     value={q} onChange={e => setQ(e.target.value)} />
            </div>
          </div>

          {/* The two numbers the desk actually needs, before the list itself. */}
          {!isLoading && !isError && receipts.length > 0 && (
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-5">
              <div className="glass-surface p-4">
                <p className="text-[11px] uppercase tracking-wider text-ink-tertiary">Bills raised</p>
                <p className="text-2xl font-bold text-ink-primary tabular-nums mt-1">{receipts.length}</p>
              </div>
              <div className="glass-surface p-4">
                <p className="text-[11px] uppercase tracking-wider text-ink-tertiary">Still owing</p>
                <p className="text-2xl font-bold tabular-nums mt-1"
                   style={{ color: owing.length ? 'var(--color-tea-brown)' : undefined }}>
                  {owing.length}
                </p>
                {owing.length > 0 && (
                  <p className="text-xs text-ink-tertiary mt-1">{ksh(String(owedTotal))} outstanding</p>
                )}
              </div>
              <div className="glass-surface p-4">
                <p className="text-[11px] uppercase tracking-wider text-ink-tertiary">Credit held</p>
                <p className="text-2xl font-bold tabular-nums mt-1"
                   style={{ color: credit.length ? 'var(--color-leaf-green)' : undefined }}>
                  {credit.length}
                </p>
                {credit.length > 0 && (
                  <p className="text-xs text-ink-tertiary mt-1">{ksh(String(creditTotal))} unspent</p>
                )}
              </div>
            </div>
          )}

          {isLoading && <p className="text-sm text-ink-tertiary">Loading receipts&hellip;</p>}

          {/* The server's own sentence, shown as written. A 403 here means the
              account is below front desk, and saying so beats a blank list. */}
          {isError && (
            <EmptyState
              icon={<Icon name="alert" size={40} />}
              title="Could not load receipts"
              description={
                (error as { response?: { data?: { error?: string } } })?.response?.data?.error
                ?? 'Something went wrong reaching the server.'
              }
            />
          )}

          {!isLoading && !isError && receipts.length === 0 && (
            <EmptyState
              icon={<Icon name="circle" size={40} />}
              title="No bills on this day"
              description="Nothing was opened on the trading day selected. Try another date, or clear the search."
            />
          )}

          {receipts.length > 0 && (
            <div className="flex flex-col gap-2">
              {receipts.map(r => {
                const bal = parseFloat(r.balance)
                return (
                  <button
                    key={r.tab_id}
                    onClick={() => navigate(`/folio/${r.tab_id}`)}
                    className="glass-card p-4 text-left w-full hover:brightness-110 transition
                               focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-main"
                  >
                    <div className="flex items-start justify-between gap-4 flex-wrap">
                      <div className="min-w-0">
                        <p className="font-semibold text-ink-primary truncate">
                          {r.reference || 'Walk-in'}
                        </p>
                        <p className="text-xs text-ink-tertiary mt-0.5">
                          {TYPE_LABEL[r.tab_type] ?? r.tab_type}
                          {' · '}{formatDateTime(r.opened_at)}
                          {r.opened_by && <> · opened by {r.opened_by}</>}
                        </p>
                      </div>
                      <div className="text-right shrink-0">
                        {/* The magnitude is what a person reads out loud, so the
                            sign is carried by the WORD under it, not by a minus. */}
                        <p className="font-bold tabular-nums text-ink-primary">
                          {ksh(String(Math.abs(bal)))}
                        </p>
                        <p className="text-[11px] uppercase tracking-wider mt-0.5"
                           style={{ color: bal > 0 ? 'var(--color-tea-brown)'
                                         : bal < 0 ? 'var(--color-leaf-green)'
                                         : 'var(--color-ink-tertiary)' }}>
                          {bal > 0 ? 'Owing' : bal < 0 ? 'Credit left' : 'Settled'}
                        </p>
                      </div>
                    </div>
                  </button>
                )
              })}
            </div>
          )}
        </div>
      </ErrorBoundary>
    </RequireRole>
  )
}
