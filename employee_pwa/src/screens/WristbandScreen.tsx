import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Modal, Skeleton, useToastStore, ErrorBoundary } from '@shared'
import api from '../lib/axios'
import { RequireRole } from '../components/AuthGate'
import { formatBandBalance } from '../lib/format'

type PaymentMethod = 'CASH' | 'MPESA' | 'CARD' | 'BANK_TRANSFER'

interface Band {
  id: string
  band_number: number
  issue_date: string
  status: string
  tab_id: string | null
  notes: string | null
  issued_by: string | null
  issued_at: string
  tab_balance: string
}

interface IssueResponse extends Band {
  duplicate?: boolean
}

const ENTRY_FEE = 3000  // KES — owner configures later in F-19

const METHOD_OPTS = [
  { value: 'CASH',          label: 'Cash' },
  { value: 'MPESA',         label: 'M-Pesa' },
  { value: 'CARD',          label: 'Card' },
  { value: 'BANK_TRANSFER', label: 'Bank Transfer' },
]

function genKey() { return crypto.randomUUID() }

export default function WristbandScreen() {
  const queryClient = useQueryClient()
  const addToast    = useToastStore((s) => s.addToast)

  const [method,      setMethod]      = useState<PaymentMethod>('CASH')
  const [idemKey,     setIdemKey]     = useState(genKey)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [errorOpen,   setErrorOpen]   = useState(false)
  const [errorMsg,    setErrorMsg]    = useState('')
  const [lastBand,    setLastBand]    = useState<Band | null>(null)

  const { data: bands, isLoading, isError } = useQuery<Band[]>({
    queryKey: ['gate-active-bands'],
    queryFn: () => api.get<Band[]>('/gate/active-bands').then((r) => r.data),
    refetchInterval: 60_000,
  })

  const headcount  = bands?.length ?? null
  const canLoad    = !isLoading && !isError

  const mutation = useMutation({
    mutationFn: () =>
      api.post<IssueResponse>('/gate/issue-band', {
        method,
        idempotency_key: idemKey,
      }).then((r) => r.data),

    onSuccess: (data) => {
      setConfirmOpen(false)
      setLastBand(data)
      setIdemKey(genKey())  // fresh key for next issue

      if (data.duplicate) {
        addToast({ type: 'warning', message: `Band already issued — showing existing record (Band #${data.band_number}).` })
      } else {
        addToast({ type: 'success', message: `Band #${data.band_number} issued. Payment KSh ${ENTRY_FEE.toLocaleString()} recorded.` })
      }
      queryClient.invalidateQueries({ queryKey: ['gate-active-bands'] })
    },

    onError: (err: unknown) => {
      setConfirmOpen(false)
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
        ?? 'Failed to issue band. Please try again.'
      setErrorMsg(msg)
      setErrorOpen(true)
    },
  })

  /* Revenue estimate from active bands */
  const revenue = headcount !== null ? headcount * ENTRY_FEE : null

  return (
    <RequireRole minLevel={3}>
      <ErrorBoundary level="tile">
      <div className="min-h-screen p-4 md:p-6">
        <div className="max-w-6xl mx-auto grid grid-cols-1 md:grid-cols-3 gap-6">

          {/* ── Left column: Issue form (spans 2 cols on desktop) ───── */}
          <div className="md:col-span-2 space-y-5">

            {/* Header */}
            <div>
              <h1 className="font-serif text-2xl md:text-3xl font-bold text-ink-primary tracking-tight">
                Issue Day Wristband
              </h1>
              <p className="text-sm text-ink-tertiary mt-1">
                Register a new day guest and collect entry fee.
              </p>
            </div>

            {/* Issue card */}
            <div className="glass-card rounded-2xl p-5 space-y-5">

              {/* Payment method selection */}
              <div>
                <p className="text-[10px] font-bold tracking-[0.2em] uppercase text-ink-tertiary mb-3">
                  Select Payment Method
                </p>
                <div className="grid grid-cols-4 gap-4">
                  {METHOD_OPTS.map(({ value, label }) => (
                    <button key={value} onClick={() => setMethod(value as PaymentMethod)}
                      className={`min-h-[44px] rounded-xl text-sm font-semibold border transition-colors ${
                        method === value
                          ? 'bg-primary-main text-white border-primary-main'
                          : 'border-white/10 text-ink-tertiary hover:bg-white/5'
                      }`}>
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Entry fee display */}
              <div className="flex items-center justify-between py-3 border-t border-b border-white/10">
                <div>
                  <p className="text-[10px] font-bold tracking-[0.2em] uppercase text-ink-tertiary">
                    Entry Fee Amount
                  </p>
                  <p className="text-2xl font-bold tabular-nums text-ink-primary mt-1">
                    KSh {ENTRY_FEE.toLocaleString()}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-[10px] font-bold tracking-[0.2em] uppercase text-ink-tertiary">
                    Valid For
                  </p>
                  <p className="text-sm font-semibold text-ink-primary mt-1">Today Only</p>
                </div>
              </div>

              {/* Issue button */}
              <button
                onClick={() => setConfirmOpen(true)}
                disabled={mutation.isPending}
                className="w-full py-4 rounded-2xl text-base font-semibold transition-all
                  bg-primary-main text-white hover:bg-primary-main/90 active:scale-[0.99]
                  focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-main focus-visible:ring-offset-2
                  disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {mutation.isPending ? (
                  <span className="flex items-center justify-center gap-2">
                    <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
                      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" strokeOpacity="0.3" />
                      <path d="M21 12a9 9 0 01-9 9" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                    </svg>
                    Issuing...
                  </span>
                ) : (
                  <>Confirm &amp; Issue Wristband &rarr;</>
                )}
              </button>
            </div>

            {/* Day pass info note */}
            <div className="flex items-start gap-2 px-3 py-2 rounded-lg bg-primary-main/5">
              <span className="text-[#fa5c29] text-sm mt-0.5">&#9888;</span>
              <p className="text-xs text-ink-tertiary">
                Day passes grant access to the pool, gardens, and restaurant area.
                Ensure the wristband is securely fastened and the serial number is
                logged to the ledger if the scanner is offline.
              </p>
            </div>
          </div>

          {/* ── Right column: Running total + last issued ───────────── */}
          <div className="space-y-4">

            {/* Today's running total */}
            <div className="glass-card rounded-2xl p-5">
              <p className="text-[10px] font-bold tracking-[0.2em] uppercase text-ink-tertiary mb-4">
                Today&apos;s Running Total
              </p>

              <div className="space-y-4">
                <div>
                  <p className="text-[10px] font-bold tracking-[0.15em] uppercase text-ink-tertiary">
                    Active Wristbands
                  </p>
                  {isLoading ? (
                    <Skeleton variant="text" className="w-16 h-8" />
                  ) : (
                    <p className="text-3xl font-bold tabular-nums text-ink-primary">
                      {canLoad ? headcount : '—'}
                    </p>
                  )}
                </div>

                <div className="border-t border-white/10 pt-3">
                  <p className="text-[10px] font-bold tracking-[0.15em] uppercase text-ink-tertiary">
                    Revenue
                  </p>
                  <p className="text-lg font-bold tabular-nums text-ink-primary">
                    {revenue !== null
                      ? `KSh ${revenue.toLocaleString('en-KE')}`
                      : '—'}
                  </p>
                </div>
              </div>
            </div>

            {/* Last issued band receipt card */}
            {lastBand && (
              <div className="glass-card rounded-2xl p-5">
                <div className="flex items-center justify-between mb-3">
                  <p className="text-[10px] font-bold tracking-[0.2em] uppercase text-ink-tertiary">
                    Sample Receipt
                  </p>
                  <p className="text-sm font-bold tabular-nums text-ink-primary">
                    KV-{String(lastBand.band_number).padStart(4, '0')}
                  </p>
                </div>
                <div>
                  <p className="text-sm font-semibold text-ink-primary">Day Visitor Walk-in</p>
                  <p className="text-xs text-ink-tertiary mt-1">
                    {new Date(lastBand.issued_at).toLocaleTimeString('en-KE', {
                      hour: '2-digit', minute: '2-digit', hour12: true
                    })}
                    {lastBand.issued_by && ` · ${lastBand.issued_by}`}
                  </p>
                  <p className="text-xs text-ink-tertiary mt-0.5">
                    KSh {ENTRY_FEE.toLocaleString()} paid via {METHOD_OPTS.find(o => o.value === method)?.label}
                  </p>
                </div>
              </div>
            )}

            {/* Active bands list (compact) */}
            {!isLoading && !isError && bands && bands.length > 0 && (
              <div className="glass-card rounded-2xl p-5">
                <p className="text-[10px] font-bold tracking-[0.2em] uppercase text-ink-tertiary mb-3">
                  Recent Bands
                </p>
                <div className="space-y-2">
                  {bands.slice(0, 4).map((b) => {
                    const bal = formatBandBalance(b.tab_balance)
                    return (
                      <div key={b.id} className="flex items-center justify-between py-1.5
                        border-b border-white/5 last:border-0">
                        <span className="text-sm font-semibold text-ink-primary">#{b.band_number}</span>
                        <span className="text-xs tabular-nums text-ink-tertiary">
                          KSh {bal.amount} {bal.owed ? 'owed' : 'credit left'}
                        </span>
                      </div>
                    )
                  })}
                  {bands.length > 4 && (
                    <p className="text-[10px] text-ink-tertiary text-center pt-1">
                      +{bands.length - 4} more inside
                    </p>
                  )}
                </div>
              </div>
            )}

            {isError && (
              <div className="rounded-xl bg-white/5 p-3 text-sm text-ink-tertiary text-center">
                Couldn&apos;t load headcount — issuance still available.
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Confirmation modal ─────────────────────────────────────── */}
      <Modal open={confirmOpen} onClose={() => setConfirmOpen(false)} title="Issue wristband?">
        <p className="text-base text-ink-tertiary mb-1">
          This will open a new tab and record a payment of{' '}
          <strong className="text-ink-primary tabular-nums">KSh {ENTRY_FEE.toLocaleString()}</strong>{' '}
          via {METHOD_OPTS.find((o) => o.value === method)?.label}.
        </p>
        <p className="text-sm text-ink-tertiary/70 mb-6">Payment records cannot be reversed.</p>
        <div className="flex gap-3">
          <button
            onClick={() => setConfirmOpen(false)}
            className="flex-1 py-3 rounded-xl glass-card text-ink-tertiary
              font-medium hover:bg-white/5 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
            className="flex-1 py-3 rounded-xl bg-primary-main text-white font-semibold
              hover:bg-primary-main/90 transition-colors disabled:opacity-50"
          >
            {mutation.isPending ? 'Issuing...' : 'Confirm Issue'}
          </button>
        </div>
      </Modal>

      {/* ── Error modal ────────────────────────────────────────────── */}
      <Modal open={errorOpen} onClose={() => setErrorOpen(false)} title="Issue failed">
        <p className="text-base text-ink-tertiary mb-6">{errorMsg}</p>
        <div className="flex gap-3">
          <button
            onClick={() => setErrorOpen(false)}
            className="flex-1 py-3 rounded-xl glass-card text-ink-tertiary
              font-medium hover:bg-white/5 transition-colors"
          >
            Close
          </button>
          <button
            onClick={() => { setErrorOpen(false); setConfirmOpen(true) }}
            className="flex-1 py-3 rounded-xl bg-primary-main text-white font-semibold
              hover:bg-primary-main/90 transition-colors"
          >
            Retry
          </button>
        </div>
      </Modal>
      </ErrorBoundary>
    </RequireRole>
  )
}
