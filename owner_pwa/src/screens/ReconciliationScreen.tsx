import { useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Skeleton, Modal, Button, useToastStore } from '@shared'
import api from '../lib/axios'

// ── Types ──────────────────────────────────────────────────────────────────────

interface ReconData {
  date: string
  receipts: { cash: string; card: string; mpesa: string; total: string }
  cash_reconciliation: {
    total_collected: string
    total_expected: string
    total_handed_in: string
    difference: string
    shortfalls: { staff: string; expected: string; actual: string; difference: string }[]
    pending_staff: string[]
  }
  stock: {
    open_alerts_count: number
    alerts: { type: string; severity: string; description: string }[]
  }
  period_closed: boolean
  balanced: boolean
  gaps: string[]
}

// ── Helpers ────────────────────────────────────────────────────────────────────

const _tz = 'Africa/Nairobi'
const todayNairobi = () => new Intl.DateTimeFormat('en-CA', { timeZone: _tz }).format(new Date())

const kes = (v: string | number) =>
  `KSh ${parseFloat(String(v)).toLocaleString('en-KE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

const extractErr = (e: unknown) =>
  (e as { response?: { data?: { error?: string } } })?.response?.data?.error ?? 'Something went wrong.'

function diffColor(v: string) {
  const n = parseFloat(v)
  if (n < 0) return 'text-status-failed'
  if (n > 0) return 'text-status-pending'
  return 'text-status-paid'
}

// ── Component ──────────────────────────────────────────────────────────────────

export default function ReconciliationScreen() {
  const qc = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  const holdTimerRef    = useRef<ReturnType<typeof setTimeout> | null>(null)
  const holdIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const [view, setView] = useState({
    date:           todayNairobi(),
    holdProgress:   0,
    showCloseModal: false,
    safeCount:      '',
    idemKey:        crypto.randomUUID(),
  })

  const { data, isLoading, isError } = useQuery<ReconData>({
    queryKey: ['reconciliation', view.date],
    queryFn: () =>
      api.get<ReconData>(`/finance/reconciliation?date=${view.date}`).then(r => r.data),
    staleTime: 60_000,
    enabled: !!view.date,
  })

  const closeMut = useMutation({
    mutationFn: (body: { date: string; safe_count: string; idempotency_key: string }) =>
      api.post('/finance/close-period', body).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['reconciliation', view.date] })
      setView(v => ({ ...v, showCloseModal: false, safeCount: '', idemKey: crypto.randomUUID() }))
      addToast({ type: 'success', message: 'Period closed successfully.' })
    },
    onError: (e) => addToast({ type: 'error', message: extractErr(e) }),
  })

  // Hold-to-confirm handlers
  function startHold() {
    const start = Date.now()
    holdIntervalRef.current = setInterval(() => {
      setView(v => ({ ...v, holdProgress: Math.min(((Date.now() - start) / 2000) * 100, 100) }))
    }, 50)
    holdTimerRef.current = setTimeout(() => {
      cancelHold()
      setView(v => ({ ...v, showCloseModal: true, idemKey: crypto.randomUUID() }))
    }, 2000)
  }
  function cancelHold() {
    if (holdTimerRef.current)    clearTimeout(holdTimerRef.current)
    if (holdIntervalRef.current) clearInterval(holdIntervalRef.current)
    setView(v => ({ ...v, holdProgress: 0 }))
  }

  function submitClose() {
    const sc = parseFloat(view.safeCount)
    if (isNaN(sc) || sc < 0) {
      addToast({ type: 'error', message: 'Enter a valid safe count (0 or above).' })
      return
    }
    closeMut.mutate({ date: view.date, safe_count: view.safeCount, idempotency_key: view.idemKey })
  }

  const Row = ({ label, value, valueClass = '' }: { label: string; value: string; valueClass?: string }) => (
    <div className="flex items-center justify-between py-1.5 border-b border-cream-alt last:border-0">
      <span className="text-xs text-ink-secondary">{label}</span>
      <span className={`text-sm font-semibold tabular-nums ${valueClass}`}>{value}</span>
    </div>
  )

  return (
    <div className="p-4 max-w-4xl mx-auto space-y-4">

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold text-ink-primary font-serif">Three-Way Reconciliation</h1>
          <p className="text-xs text-ink-secondary mt-0.5">Receipts · Cash · Stock</p>
        </div>
        {/* Date picker */}
        <input
          type="date"
          value={view.date}
          max={todayNairobi()}
          onChange={e => setView(v => ({ ...v, date: e.target.value }))}
          className="rounded-xl border border-cream-alt bg-cream-card px-3 py-2
            text-sm text-ink-primary focus:outline-none focus:border-primary-dark"
        />
      </div>

      {/* Balanced badge */}
      {data && (
        <div className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold ${
          data.balanced ? 'bg-status-paid/10 text-status-paid' : 'bg-status-failed/10 text-status-failed'
        }`}>
          {data.balanced ? '✓ Balanced' : '✗ Imbalanced'}
          {data.period_closed && <span className="ml-1 opacity-60">(period closed)</span>}
        </div>
      )}

      {isLoading && (
        <div className="grid sm:grid-cols-3 gap-4">
          {[1,2,3].map(i => <Skeleton key={i} variant="card" />)}
        </div>
      )}

      {isError && (
        <p className="text-sm text-status-failed text-center py-8">
          Failed to load reconciliation. Select a date that has data.
        </p>
      )}

      {/* Three columns */}
      {data && !isLoading && (
        <>
          <div className="grid sm:grid-cols-3 gap-4">

            {/* Corner 1: Receipts */}
            <div className="rounded-2xl border border-cream-alt bg-cream-card p-4 space-y-1">
              <p className="text-[10px] font-bold tracking-widest uppercase text-ink-secondary mb-3">Receipts</p>
              <Row label="Cash"   value={kes(data.receipts.cash)} />
              <Row label="Card"   value={kes(data.receipts.card)} />
              <Row label="M-Pesa" value={kes(data.receipts.mpesa)} />
              <div className="mt-2 pt-2 border-t border-cream-alt flex justify-between">
                <span className="text-xs font-semibold text-ink-primary">Total</span>
                <span className="text-sm font-bold tabular-nums text-ink-primary">{kes(data.receipts.total)}</span>
              </div>
            </div>

            {/* Corner 2: Cash Reconciliation */}
            <div className="rounded-2xl border border-cream-alt bg-cream-card p-4 space-y-1">
              <p className="text-[10px] font-bold tracking-widest uppercase text-ink-secondary mb-3">Cash Reconciliation</p>
              <Row label="Collected" value={kes(data.cash_reconciliation.total_collected)} />
              <Row label="Expected"  value={kes(data.cash_reconciliation.total_expected)} />
              <Row label="Handed in" value={kes(data.cash_reconciliation.total_handed_in)} />
              <Row
                label="Difference"
                value={kes(data.cash_reconciliation.difference)}
                valueClass={diffColor(data.cash_reconciliation.difference)}
              />
              {data.cash_reconciliation.shortfalls.length > 0 && (
                <div className="pt-2 space-y-1">
                  <p className="text-[10px] text-status-failed font-semibold">Shortfalls</p>
                  {data.cash_reconciliation.shortfalls.map((s, i) => (
                    <p key={i} className="text-[11px] text-ink-secondary">
                      {s.staff}: {kes(s.difference)}
                    </p>
                  ))}
                </div>
              )}
              {data.cash_reconciliation.pending_staff.length > 0 && (
                <div className="pt-1">
                  <p className="text-[10px] text-status-pending font-semibold">Unreconciled</p>
                  <p className="text-[11px] text-ink-secondary">
                    {data.cash_reconciliation.pending_staff.join(', ')}
                  </p>
                </div>
              )}
            </div>

            {/* Corner 3: Stock / Judge */}
            <div className="rounded-2xl border border-cream-alt bg-cream-card p-4">
              <p className="text-[10px] font-bold tracking-widest uppercase text-ink-secondary mb-3">Stock Alerts</p>
              <p className="text-2xl font-bold text-ink-primary tabular-nums">
                {data.stock.open_alerts_count}
              </p>
              <p className="text-xs text-ink-secondary mb-3">open alert{data.stock.open_alerts_count !== 1 ? 's' : ''}</p>
              {data.stock.alerts.map((a, i) => (
                <div key={i} className="py-1.5 border-b border-cream-alt last:border-0">
                  <div className="flex items-center gap-1.5">
                    <span className={`text-[9px] font-bold uppercase px-1.5 py-0.5 rounded ${
                      a.severity === 'HIGH' ? 'bg-status-failed/10 text-status-failed' : 'bg-status-pending/10 text-status-pending'
                    }`}>{a.severity}</span>
                    <span className="text-[10px] text-ink-secondary">{a.type.replace(/_/g,' ')}</span>
                  </div>
                  <p className="text-[11px] text-ink-secondary mt-0.5 line-clamp-2">{a.description}</p>
                </div>
              ))}
            </div>

          </div>

          {/* Gaps banner */}
          {data.gaps.length > 0 && (
            <div className="rounded-2xl border border-status-failed/30 bg-status-failed/5 p-4 space-y-1">
              <p className="text-xs font-bold text-status-failed uppercase tracking-widest mb-2">
                ⚠ Gaps detected
              </p>
              {data.gaps.map((g, i) => (
                <p key={i} className="text-sm text-ink-primary leading-snug">• {g}</p>
              ))}
            </div>
          )}

          {/* Close Period */}
          {!data.period_closed && (
            <div className="pt-2">
              <p className="text-xs text-ink-secondary mb-2">
                Hold the button for 2 seconds to close this period.
              </p>
              <div className="relative overflow-hidden rounded-2xl">
                {/* Hold progress fill */}
                <div
                  className="absolute inset-y-0 left-0 bg-primary-dark/20 transition-none pointer-events-none"
                  style={{ width: `${view.holdProgress}%` }}
                />
                <button
                  onMouseDown={startHold}
                  onMouseUp={cancelHold}
                  onMouseLeave={cancelHold}
                  onTouchStart={startHold}
                  onTouchEnd={cancelHold}
                  onKeyDown={(e) => { if (e.key === ' ' && !e.repeat) { e.preventDefault(); startHold() } }}
                  onKeyUp={(e) => { if (e.key === ' ') { e.preventDefault(); cancelHold() } }}
                  aria-label="Close Period. Hold Space for 2 seconds to confirm."
                  className="relative w-full py-4 bg-primary-dark text-cream-card rounded-2xl
                    text-base font-semibold select-none cursor-grab active:cursor-grabbing
                    focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark"
                >
                  {view.holdProgress > 0
                    ? `Hold… ${Math.floor(view.holdProgress)}%`
                    : 'Close Period'}
                </button>
              </div>
            </div>
          )}

          {data.period_closed && (
            <p className="text-xs text-status-paid font-semibold text-center py-2">
              ✓ Period closed
            </p>
          )}
        </>
      )}

      {/* Close Period modal — safe count entry */}
      <Modal
        open={view.showCloseModal}
        onClose={() => setView(v => ({ ...v, showCloseModal: false }))}
        title="Close period — enter safe count"
        size="sm"
        preventClose={closeMut.isPending}
      >
        <div className="space-y-4">
          <p className="text-sm text-ink-secondary">
            Count the physical cash in the safe for <strong>{view.date}</strong> and enter the total.
          </p>
          <div>
            <label className="block text-[10px] tracking-widest uppercase text-ink-secondary mb-1">
              Safe count (KSh)
            </label>
            <input
              type="number"
              min="0"
              step="0.01"
              inputMode="decimal"
              placeholder="0.00"
              value={view.safeCount}
              onChange={e => setView(v => ({ ...v, safeCount: e.target.value }))}
              className="w-full rounded-xl border border-cream-alt bg-cream-card px-4 py-3
                text-base text-ink-primary focus:outline-none focus:border-primary-dark"
            />
          </div>
          <div className="flex gap-2 justify-end">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setView(v => ({ ...v, showCloseModal: false }))}
              disabled={closeMut.isPending}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              loading={closeMut.isPending}
              onClick={submitClose}
            >
              Confirm &amp; Close
            </Button>
          </div>
        </div>
      </Modal>

    </div>
  )
}
