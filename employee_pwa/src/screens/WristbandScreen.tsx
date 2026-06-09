import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Select, Modal, Skeleton, useToastStore } from '@shared'
import api from '../lib/axios'
import { RequireRole } from '../components/AuthGate'

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

  return (
    <RequireRole minLevel={3}>
      <div className="p-4 max-w-md mx-auto space-y-5">

        {/* ── Header + headcount ────────────────────────────────────── */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-ink-primary">Wristband Issuance</h1>
            <p className="text-sm text-ink-tertiary">Issue entry band + open tab</p>
          </div>
          <div className="text-right">
            {isLoading ? (
              <Skeleton variant="text" className="w-12" />
            ) : (
              <span className="text-3xl font-bold tabular-nums text-ink-primary">
                {canLoad ? headcount : '—'}
              </span>
            )}
            <p className="text-[10px] text-ink-tertiary uppercase tracking-wide">inside today</p>
          </div>
        </div>

        {/* ── Last issued band (success card) ───────────────────────── */}
        {lastBand && (
          <div className="bg-sage-light/30 border border-sage-main/30 rounded-2xl p-4 text-center">
            <p className="text-xs text-ink-tertiary uppercase tracking-widest mb-1">Last issued</p>
            <p className="text-5xl font-bold tabular-nums text-sage-dark">#{lastBand.band_number}</p>
            <p className="text-sm text-ink-secondary mt-1">Tab opened · KSh {ENTRY_FEE.toLocaleString()} paid</p>
          </div>
        )}

        {/* ── Active bands list — partial state ──────────────────────── */}
        {isError && (
          <div className="rounded-xl bg-cream-alt/60 p-3 text-sm text-ink-tertiary text-center">
            Couldn't load headcount — issuance still available below.
          </div>
        )}
        {!isLoading && !isError && bands && bands.length > 0 && (
          <div className="space-y-2">
            <p className="text-xs font-medium text-ink-tertiary uppercase tracking-widest">Active bands</p>
            {bands.slice(0, 5).map((b) => (
              <div key={b.id} className="flex items-center justify-between
                bg-cream-alt/40 rounded-xl px-4 py-2.5">
                <span className="font-semibold text-ink-primary">#{b.band_number}</span>
                <span className="text-xs text-ink-tertiary">KSh {parseFloat(b.tab_balance).toLocaleString()} on tab</span>
              </div>
            ))}
            {bands.length > 5 && (
              <p className="text-xs text-ink-tertiary text-center">
                +{bands.length - 5} more inside
              </p>
            )}
          </div>
        )}

        {/* ── Issue form ─────────────────────────────────────────────── */}
        <div className="rounded-2xl bg-cream-alt/30 border border-cream-alt p-4 space-y-4">
          <p className="text-sm font-semibold text-ink-primary">New wristband</p>

          <div className="flex items-center justify-between py-2 border-b border-cream-alt">
            <span className="text-sm text-ink-secondary">Entry fee</span>
            <span className="text-base font-bold tabular-nums text-ink-primary">
              KSh {ENTRY_FEE.toLocaleString()}
            </span>
          </div>

          <Select
            label="Payment method"
            value={method}
            onChange={(e) => setMethod(e.target.value as PaymentMethod)}
            options={METHOD_OPTS}
          />

          <button
            onClick={() => setConfirmOpen(true)}
            disabled={mutation.isPending}
            className={[
              'w-full py-4 rounded-2xl text-base font-semibold transition-all',
              'bg-sage-dark text-cream-card hover:bg-sage-dark/90 active:scale-[0.99]',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sage-dark focus-visible:ring-offset-2',
              'disabled:opacity-50 disabled:cursor-not-allowed',
            ].join(' ')}
          >
            {mutation.isPending ? (
              <span className="flex items-center justify-center gap-2">
                <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
                  <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" strokeOpacity="0.3" />
                  <path d="M21 12a9 9 0 01-9 9" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                </svg>
                Issuing…
              </span>
            ) : 'Issue Band'}
          </button>
        </div>

      </div>

      {/* ── Confirmation modal (Pattern 2 — payment is irreversible) ── */}
      <Modal open={confirmOpen} onClose={() => setConfirmOpen(false)} title="Issue wristband?">
        <p className="text-base text-ink-secondary mb-1">
          This will open a new tab and record a payment of{' '}
          <strong className="text-ink-primary tabular-nums">KSh {ENTRY_FEE.toLocaleString()}</strong>{' '}
          via {METHOD_OPTS.find((o) => o.value === method)?.label}.
        </p>
        <p className="text-sm text-ink-tertiary mb-6">Payment records cannot be reversed.</p>
        <div className="flex gap-3">
          <button
            onClick={() => setConfirmOpen(false)}
            className="flex-1 py-3 rounded-xl border border-cream-alt text-ink-secondary
              font-medium hover:bg-cream-alt/50 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
            className="flex-1 py-3 rounded-xl bg-sage-dark text-cream-card font-semibold
              hover:bg-sage-dark/90 transition-colors disabled:opacity-50"
          >
            {mutation.isPending ? 'Issuing…' : 'Confirm Issue'}
          </button>
        </div>
      </Modal>

      {/* ── Error modal ─────────────────────────────────────────────── */}
      <Modal open={errorOpen} onClose={() => setErrorOpen(false)} title="Issue failed">
        <p className="text-base text-ink-secondary mb-6">{errorMsg}</p>
        <div className="flex gap-3">
          <button
            onClick={() => setErrorOpen(false)}
            className="flex-1 py-3 rounded-xl border border-cream-alt text-ink-secondary
              font-medium hover:bg-cream-alt/50 transition-colors"
          >
            Close
          </button>
          <button
            onClick={() => { setErrorOpen(false); setConfirmOpen(true) }}
            className="flex-1 py-3 rounded-xl bg-sage-dark text-cream-card font-semibold
              hover:bg-sage-dark/90 transition-colors"
          >
            Retry
          </button>
        </div>
      </Modal>
    </RequireRole>
  )
}
