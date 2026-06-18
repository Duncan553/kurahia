import { useEffect, useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Skeleton, EmptyState, StatusBadge, useToastStore } from '@shared'
import { RequireRole } from '../components/AuthGate'
import api from '../lib/axios'
import { timeAgo } from '../lib/format'

interface Profile {
  id: string           // EmployeeProfile.id
  user_id: string      // User.id — cash pending uses this
  full_name: string
}

interface Payment {
  payment_id: string
  amount: string
  tab_id: string
  created_at: string
}

interface PendingCash {
  staff_id: string
  staff_name: string
  expected_total: string
  payment_count: number
  payments: Payment[]
}

interface ReconResult {
  id: string
  expected_amount: string
  actual_amount: string
  difference: string
  status: string
  payments_swept: number
}

const SHORT_THRESHOLD = 500   // KSh — above this, hold-to-confirm required

function genKey() { return crypto.randomUUID() }

// ── Hold-to-Confirm (2 s press) ─────────────────────────────────────────────

function HoldToConfirm({
  onConfirm, label, disabled,
}: {
  onConfirm: () => void
  label: string
  disabled?: boolean
}) {
  const [progress, setProgress] = useState(0)
  const intervalRef  = useRef<ReturnType<typeof setInterval> | null>(null)
  const confirmedRef = useRef(false)

  function startHold() {
    if (disabled) return
    confirmedRef.current = false
    intervalRef.current = setInterval(() => {
      setProgress((prev) => {
        const next = prev + 5
        if (next >= 100) {
          clearInterval(intervalRef.current!)
          if (!confirmedRef.current) { confirmedRef.current = true; onConfirm() }
          return 100
        }
        return next
      })
    }, 100)
  }
  function stopHold() {
    if (intervalRef.current) clearInterval(intervalRef.current)
    intervalRef.current = null
    if (!confirmedRef.current) setProgress(0)
  }
  useEffect(() => () => { if (intervalRef.current) clearInterval(intervalRef.current) }, [])

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === ' ' && !e.repeat) { e.preventDefault(); startHold() }
  }
  function handleKeyUp(e: React.KeyboardEvent) {
    if (e.key === ' ') { e.preventDefault(); stopHold() }
  }

  return (
    <button
      onMouseDown={startHold}
      onMouseUp={stopHold}
      onMouseLeave={stopHold}
      onPointerDown={startHold}
      onPointerUp={stopHold}
      onPointerLeave={stopHold}
      onKeyDown={handleKeyDown}
      onKeyUp={handleKeyUp}
      disabled={disabled}
      aria-label={`${label}. Hold Space for 2 seconds to confirm.`}
      className={[
        'relative w-full py-4 rounded-2xl overflow-hidden',
        'bg-status-failed text-white font-semibold text-base select-none',
        'disabled:opacity-50 disabled:cursor-not-allowed transition-all',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-status-failed',
      ].join(' ')}
    >
      {progress > 0 && (
        <div
          aria-hidden="true"
          className="absolute inset-0 bg-white/20 transition-none"
          style={{ width: `${progress}%` }}
        />
      )}
      <span className="relative">
        {progress > 0 ? `Hold to confirm… ${Math.round(progress)}%` : label}
      </span>
    </button>
  )
}

// ── Reconcile form ───────────────────────────────────────────────────────────

function ReconForm({
  pending,
  onClose,
}: {
  pending: PendingCash
  onClose: () => void
}) {
  const addToast = useToastStore((s) => s.addToast)
  const queryClient = useQueryClient()
  const [actualRaw, setActualRaw] = useState('')
  const [notes,     setNotes]     = useState('')
  const [idemKey]                 = useState(genKey)
  const [result,    setResult]    = useState<ReconResult | null>(null)
  const [expanded,  setExpanded]  = useState(false)

  const expected = parseFloat(pending.expected_total)
  const actual   = parseFloat(actualRaw || '0')
  const diff     = actual - expected
  const isShort  = diff < 0 && Math.abs(diff) > SHORT_THRESHOLD

  const mutation = useMutation({
    mutationFn: () =>
      api.post<ReconResult>('/finance/cash/reconcile', {
        staff_id:        pending.staff_id,
        actual_amount:   parseFloat(actualRaw),
        notes:           notes.trim() || undefined,
        idempotency_key: idemKey,
      }).then((r) => r.data),
    onSuccess: (data) => {
      setResult(data)
      queryClient.invalidateQueries({ queryKey: ['cash-pending'] })
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
        ?? 'Reconciliation failed. Try again.'
      addToast({ type: 'error', message: msg })
    },
  })

  if (result) {
    const diff = parseFloat(result.difference)
    return (
      <div className="space-y-5">
        <div className={[
          'rounded-xl p-5 text-center space-y-1',
          result.status === 'BALANCED' ? 'bg-primary-light/20 border border-primary-main/30' :
          result.status === 'SHORT'    ? 'bg-status-failed/10 border border-status-failed/30' :
                                         'bg-blue-50 border border-blue-200',
        ].join(' ')}>
          <p className="text-2xl font-bold tabular-nums text-white">
            KSh {Math.abs(diff).toLocaleString('en-KE', { minimumFractionDigits: 2 })}
          </p>
          <StatusBadge status={result.status.toLowerCase() as 'paid' | 'pending' | 'cancelled'} />
          {result.status === 'SHORT' && (
            <p className="text-sm text-status-failed mt-1">
              {pending.staff_name} is KSh {Math.abs(diff).toLocaleString('en-KE')} short.
            </p>
          )}
          {result.status === 'OVER' && (
            <p className="text-sm text-slate-300/70 mt-1">
              KSh {diff.toLocaleString('en-KE')} over — note any discrepancy.
            </p>
          )}
        </div>
        <p className="text-xs text-slate-400/50 text-center">
          {result.payments_swept} payment{result.payments_swept !== 1 ? 's' : ''} swept into this reconciliation.
        </p>
        <button
          onClick={onClose}
          className="w-full py-3 rounded-xl bg-primary-dark text-white font-semibold
            hover:bg-primary-dark/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark"
        >
          Done
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-5">
      {/* Staff summary */}
      <div className="rounded-xl bg-white/5/40 px-4 py-3">
        <p className="text-sm text-slate-400/50">Expected cash from {pending.staff_name}</p>
        <p className="text-3xl font-bold tabular-nums text-white mt-0.5">
          KSh {parseFloat(pending.expected_total).toLocaleString('en-KE', { minimumFractionDigits: 2 })}
        </p>
        <p className="text-xs text-slate-400/50 mt-1">
          {pending.payment_count} payment{pending.payment_count !== 1 ? 's' : ''}
        </p>
      </div>

      {/* Payment breakdown (collapsible) */}
      {pending.payments.length > 0 && (
        <div>
          <button
            onClick={() => setExpanded((e) => !e)}
            className="w-full min-h-[44px] flex items-center justify-between text-sm text-slate-300/70
              hover:text-white transition-colors
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark rounded"
          >
            <span>Payment breakdown</span>
            <svg
              width="16" height="16" viewBox="0 0 16 16" fill="none"
              className={`transition-transform ${expanded ? 'rotate-180' : ''}`}
            >
              <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
          </button>
          {expanded && (
            <div className="space-y-1.5 mt-2">
              {pending.payments.map((p) => (
                <div key={p.payment_id}
                  className="flex justify-between text-sm px-3 py-2 rounded-lg bg-white/5/30">
                  <span className="text-slate-400/50">{timeAgo(p.created_at)}</span>
                  <span className="font-medium tabular-nums text-white">
                    KSh {parseFloat(p.amount).toLocaleString('en-KE', { minimumFractionDigits: 2 })}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Actual amount input */}
      <div>
        <label className="block text-sm font-medium text-slate-300/70 mb-1.5">
          Actual cash received (KSh) *
        </label>
        <input
          type="number"
          min="0"
          step="0.01"
          inputMode="decimal"
          autoFocus
          value={actualRaw}
          onChange={(e) => setActualRaw(e.target.value)}
          placeholder="0.00"
          className="w-full rounded-xl border border-white/10 bg-transparent px-4 py-3
            text-2xl font-bold tabular-nums text-white
            focus:outline-none focus:border-primary-dark focus:ring-2 focus:ring-primary-dark/20"
        />
        {actualRaw && (
          <p className={`text-sm mt-1.5 tabular-nums font-medium ${
            diff === 0 ? 'text-status-paid' :
            diff < 0   ? 'text-status-failed' : 'text-blue-600'
          }`}>
            {diff === 0 ? 'Balanced'
              : diff < 0  ? `KSh ${Math.abs(diff).toFixed(2)} short`
                          : `KSh ${diff.toFixed(2)} over`}
          </p>
        )}
      </div>

      {/* Notes */}
      <div>
        <label className="block text-sm font-medium text-slate-300/70 mb-1.5">
          Notes (optional)
        </label>
        <textarea
          rows={2}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Any discrepancy reason…"
          className="w-full rounded-xl border border-white/10 bg-transparent px-4 py-3
            text-sm text-white focus:outline-none focus:border-primary-dark
            focus:ring-2 focus:ring-primary-dark/20 resize-none"
        />
      </div>

      {/* Submit — hold if short beyond threshold */}
      {isShort ? (
        <>
          <p className="text-xs text-status-failed text-center">
            This is a significant shortfall (KSh {Math.abs(diff).toFixed(2)}).
            Hold the button to confirm.
          </p>
          <HoldToConfirm
            label={`Confirm SHORT — KSh ${Math.abs(diff).toFixed(2)}`}
            disabled={!actualRaw || mutation.isPending}
            onConfirm={() => mutation.mutate()}
          />
        </>
      ) : (
        <button
          onClick={() => mutation.mutate()}
          disabled={!actualRaw || mutation.isPending}
          className={[
            'w-full py-4 rounded-2xl text-base font-semibold transition-all',
            'bg-primary-dark text-white hover:bg-primary-dark/90 active:scale-[0.99]',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark focus-visible:ring-offset-2',
            'disabled:opacity-50 disabled:cursor-not-allowed',
          ].join(' ')}
        >
          {mutation.isPending ? (
            <span className="flex items-center justify-center gap-2">
              <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" strokeOpacity="0.3"/>
                <path d="M21 12a9 9 0 01-9 9" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
              </svg>
              Reconciling…
            </span>
          ) : 'Reconcile'}
        </button>
      )}
    </div>
  )
}

// ── Main screen ──────────────────────────────────────────────────────────────

export default function CashReconScreen() {
  const [selectedProfile, setSelectedProfile] = useState<Profile | null>(null)
  const [pendingOpen, setPendingOpen]         = useState(false)

  const { data: profiles, isLoading: profilesLoading } = useQuery<Profile[]>({
    queryKey: ['hr-profiles'],
    queryFn: () => api.get<Profile[]>('/hr/profiles').then((r) => r.data),
    staleTime: 2 * 60_000,
  })

  const {
    data: pending,
    isLoading: pendingLoading,
    isError: pendingError,
    refetch: refetchPending,
  } = useQuery<PendingCash>({
    queryKey: ['cash-pending', selectedProfile?.user_id],
    queryFn: () =>
      api.get<PendingCash>(`/finance/cash/pending?staff_id=${selectedProfile!.user_id}`)
        .then((r) => r.data),
    enabled: !!selectedProfile,
    staleTime: 0,   // always fresh — money data
  })

  function selectProfile(p: Profile) {
    setSelectedProfile(p)
    setPendingOpen(false)
  }

  return (
    <RequireRole minLevel={5}>
      <div className="p-4 max-w-md mx-auto space-y-5">

        <div>
          <h1 className="text-xl font-bold text-white">Cash Reconciliation</h1>
          <p className="text-sm text-slate-400/50">Reconcile end-of-shift cash handover per staff member</p>
        </div>

        {/* Staff selector */}
        <div>
          <label className="block text-sm font-medium text-slate-300/70 mb-2">
            Select staff member
          </label>
          {profilesLoading ? (
            <Skeleton variant="button" className="w-full h-12" />
          ) : (
            <div className="relative">
              <button
                onClick={() => setPendingOpen((o) => !o)}
                className="w-full flex items-center justify-between px-4 py-3 rounded-xl
                  border border-white/10 bg-transparent text-left
                  focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark"
              >
                <span className={selectedProfile ? 'text-white font-medium' : 'text-slate-400/50'}>
                  {selectedProfile ? selectedProfile.full_name : 'Choose a staff member…'}
                </span>
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className={`transition-transform ${pendingOpen ? 'rotate-180' : ''}`}>
                  <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                </svg>
              </button>
              {pendingOpen && (
                <div className="absolute z-10 mt-1 w-full rounded-xl bg-transparent border border-white/10 shadow-lg overflow-hidden">
                  {(profiles ?? []).length === 0 ? (
                    <p className="px-4 py-3 text-sm text-slate-400/50">No staff profiles found.</p>
                  ) : (profiles ?? []).map((p) => (
                    <button
                      key={p.id}
                      onClick={() => { selectProfile(p); setPendingOpen(false) }}
                      className="w-full text-left px-4 py-3 text-sm text-white
                        hover:bg-white/5/60 transition-colors border-b border-white/10 last:border-0"
                    >
                      {p.full_name}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Pending cash panel */}
        {selectedProfile && (
          <>
            {pendingLoading && (
              <div className="space-y-3">
                <Skeleton variant="text" className="w-48" />
                <Skeleton variant="button" className="w-full h-16" />
              </div>
            )}

            {pendingError && (
              <div className="p-4 rounded-xl bg-white/5/40 text-sm text-slate-400/50 text-center space-y-2">
                <p>Couldn't load cash data for {selectedProfile.full_name}.</p>
                <button
                  onClick={() => refetchPending()}
                  className="min-h-[44px] inline-flex items-center text-primary-dark underline text-xs
                    hover:text-primary-main transition-colors
                    focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark rounded"
                >
                  Retry
                </button>
              </div>
            )}

            {!pendingLoading && pending && pending.payment_count === 0 && (
              <EmptyState
                icon={
                  <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
                    <rect x="6" y="14" width="36" height="22" rx="3" stroke="currentColor" strokeWidth="2"/>
                    <circle cx="24" cy="25" r="5" stroke="currentColor" strokeWidth="2"/>
                    <path d="M12 25h0M36 25h0" stroke="currentColor" strokeWidth="3" strokeLinecap="round"/>
                  </svg>
                }
                title="No cash handovers pending."
                description={`${selectedProfile.full_name} has no unreconciled cash payments.`}
              />
            )}

            {!pendingLoading && pending && pending.payment_count > 0 && (
              <ReconForm
                pending={pending}
                onClose={() => setSelectedProfile(null)}
              />
            )}
          </>
        )}

        {!selectedProfile && !profilesLoading && (
          <p className="text-sm text-slate-400/50 text-center py-6">
            Select a staff member above to load their pending cash.
          </p>
        )}
      </div>
    </RequireRole>
  )
}
