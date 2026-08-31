/**
 * ReconcileScreen — match the day's digital takings against the statement.
 *
 * Cash reconciliation had a screen. M-Pesa, bank transfer and card did not —
 * /finance/mpesa/pending, /finance/bank/pending, /finance/card/summary and both
 * reconcile endpoints have existed since Phase A with no caller anywhere. In
 * Kenya that is most of the money: the one payment method with a screen was the
 * one least used.
 *
 * The job is the same for each: here is what the system thinks it received, tick
 * off what the statement agrees with, flag what it does not. Tabs rather than
 * three screens, because a manager does all of them in one sitting at close.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Button, useToastStore, ErrorBoundary, EmptyState, Input } from '@shared'
import { RequireRole } from '../components/AuthGate'
import { todayKey } from '../lib/format'
import api from '../lib/axios'
import CashReconScreen from './CashReconScreen'

// Cash is reconciled per STAFF MEMBER (a handover), the other two per DAY (a
// statement). Different shape, same job and same sitting — so it is a tab here
// and CashReconScreen renders inside it rather than being a separate errand.
type Method = 'mpesa' | 'bank' | 'cash'

interface Payment {
  payment_id: string
  amount: string
  mpesa_code?: string | null
  reference?: string | null
  received_by: string | null
  created_at: string
}

const extractErr = (e: unknown) =>
  (e as { response?: { data?: { error?: string } } })?.response?.data?.error
  ?? 'Something went wrong. Try again.'

const TABS: { id: Method; label: string }[] = [
  { id: 'cash',  label: 'Cash' },
  { id: 'mpesa', label: 'M-Pesa' },
  { id: 'bank',  label: 'Bank' },
]

export default function ReconcileScreen() {
  const qc = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  const [tab, setTab] = useState<Method>('cash')
  const [date, setDate] = useState(todayKey)
  // payment_id -> what the manager decided. Held locally and submitted as one
  // batch, because the endpoint takes an entries[] array and a half-finished
  // reconciliation should not be written a row at a time.
  const [marks, setMarks] = useState<Record<string, 'MATCH' | 'FLAG'>>({})
  const [refs, setRefs] = useState<Record<string, string>>({})

  const { data, isLoading, isError } = useQuery<{ count: number; payments: Payment[] }>({
    queryKey: ['recon-pending', tab, date],
    queryFn: () => api.get(`/finance/${tab}/pending`, { params: { date } }).then(r => r.data),
    staleTime: 30_000,
    enabled: tab !== 'cash',   // cash loads per staff member, inside its own screen
  })
  const payments = data?.payments ?? []

  const submit = useMutation({
    mutationFn: () => {
      const entries = Object.entries(marks).map(([payment_id, action]) => ({
        payment_id, action,
        statement_ref: refs[payment_id]?.trim() || null,
      }))
      if (entries.length === 0) throw new Error('Tick at least one payment first.')
      return api.post(`/finance/${tab}/reconcile`, { entries })
    },
    onSuccess: () => {
      const n = Object.keys(marks).length
      addToast({ type: 'success', message: `${n} payment${n === 1 ? '' : 's'} reconciled.` })
      setMarks({}); setRefs({})
      qc.invalidateQueries({ queryKey: ['recon-pending'] })
    },
    onError: (e) => addToast({ type: 'error', message: e instanceof Error ? e.message : extractErr(e) }),
  })

  const mark = (id: string, action: 'MATCH' | 'FLAG') =>
    setMarks(m => (m[id] === action ? (({ [id]: _drop, ...rest }) => rest)(m) : { ...m, [id]: action }))

  const total = payments.reduce((s, p) => s + parseFloat(p.amount || '0'), 0)
  const markedTotal = payments
    .filter(p => marks[p.payment_id] === 'MATCH')
    .reduce((s, p) => s + parseFloat(p.amount || '0'), 0)

  return (
    <RequireRole minLevel={5}>
      <ErrorBoundary level="tile">
        <div className="p-4 md:p-6 max-w-4xl mx-auto">
          <header className="mb-5">
            <p className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary">Close of day</p>
            <h1 className="text-3xl md:text-4xl font-bold font-serif text-ink-primary">Reconcile</h1>
            <p className="text-sm text-ink-secondary mt-1">
              What the system recorded, against what actually landed.
            </p>
          </header>

          <div className="flex flex-wrap items-center gap-3 mb-5">
            <div className="flex rounded-xl glass-surface p-1" role="tablist">
              {TABS.map(t => (
                <button key={t.id} role="tab" aria-selected={tab === t.id}
                  onClick={() => { setTab(t.id); setMarks({}); setRefs({}) }}
                  className={`px-4 py-2 rounded-lg text-sm font-semibold transition-colors
                    ${tab === t.id ? 'bg-primary-main text-white' : 'text-ink-tertiary hover:text-ink-primary'}`}>
                  {t.label}
                </button>
              ))}
            </div>
            {tab !== 'cash' && (
              <Input type="date" aria-label="Date" value={date}
                onChange={e => { setDate(e.target.value); setMarks({}); setRefs({}) }}
                className="w-auto" />
            )}
          </div>

          {tab === 'cash' ? (
            <CashReconScreen embedded />
          ) : isLoading ? (
            <div className="py-16 flex justify-center">
              <div className="w-7 h-7 rounded-full border-2 border-primary-main border-t-transparent animate-spin" />
            </div>
          ) : isError ? (
            <EmptyState
              icon={<svg width="40" height="40" viewBox="0 0 40 40" fill="none" aria-hidden="true">
                <circle cx="20" cy="20" r="14" stroke="currentColor" strokeWidth="1.5"/>
                <path d="M20 13v9M20 26v.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
              </svg>}
              title="Could not load that day"
              description="Check the date and try again." />
          ) : payments.length === 0 ? (
            <EmptyState
              icon={<svg width="40" height="40" viewBox="0 0 40 40" fill="none" aria-hidden="true">
                <path d="M9 20l7 7 15-15" stroke="currentColor" strokeWidth="1.5"
                  strokeLinecap="round" strokeLinejoin="round"/>
              </svg>}
              title="Nothing outstanding"
              description={`No unreconciled ${TABS.find(t => t.id === tab)?.label} payments on ${date}.`} />
          ) : (
            <>
              <div className="glass-card rounded-2xl p-4 mb-4 flex items-baseline justify-between">
                <span className="text-xs text-ink-tertiary">
                  {payments.length} outstanding · {Object.keys(marks).length} ticked
                </span>
                <span className="text-sm font-semibold text-ink-primary tabular-nums">
                  KSh {markedTotal.toLocaleString()} <span className="text-ink-tertiary font-normal">
                    of {total.toLocaleString()}</span>
                </span>
              </div>

              <div className="flex flex-col gap-2">
                {payments.map(p => {
                  const m = marks[p.payment_id]
                  return (
                    <div key={p.payment_id}
                      className={`glass-card rounded-xl p-3 flex flex-wrap items-center gap-3
                        ${m === 'MATCH' ? 'border-status-paid' : m === 'FLAG' ? 'border-status-failed' : ''}`}>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-semibold text-ink-primary tabular-nums">
                          KSh {parseFloat(p.amount).toLocaleString()}
                        </p>
                        <p className="text-[11px] text-ink-tertiary truncate">
                          {p.mpesa_code || p.reference || 'no reference'}
                          {p.received_by ? ` · ${p.received_by}` : ''}
                        </p>
                      </div>

                      {/* Statement reference is what makes a match auditable later —
                          "we matched it" with no line to point at is not a match. */}
                      {m === 'MATCH' && (
                        <Input aria-label="Statement reference" placeholder="Statement ref"
                          value={refs[p.payment_id] ?? ''}
                          onChange={e => setRefs(r => ({ ...r, [p.payment_id]: e.target.value }))}
                          className="w-36" />
                      )}

                      <div className="flex gap-1.5 shrink-0">
                        <button onClick={() => mark(p.payment_id, 'MATCH')}
                          aria-pressed={m === 'MATCH'}
                          className={`px-3 py-1.5 rounded-lg text-xs font-semibold border
                            ${m === 'MATCH'
                              ? 'bg-status-paid text-white border-status-paid'
                              : 'border-white/15 text-ink-secondary hover:text-ink-primary'}`}>
                          Matches
                        </button>
                        <button onClick={() => mark(p.payment_id, 'FLAG')}
                          aria-pressed={m === 'FLAG'}
                          className={`px-3 py-1.5 rounded-lg text-xs font-semibold border
                            ${m === 'FLAG'
                              ? 'bg-status-failed text-white border-status-failed'
                              : 'border-white/15 text-ink-secondary hover:text-ink-primary'}`}>
                          Flag
                        </button>
                      </div>
                    </div>
                  )
                })}
              </div>

              <div className="mt-5">
                <Button onClick={() => submit.mutate()}
                  disabled={Object.keys(marks).length === 0} loading={submit.isPending}>
                  Reconcile {Object.keys(marks).length || ''} payment{Object.keys(marks).length === 1 ? '' : 's'}
                </Button>
              </div>
            </>
          )}
        </div>
      </ErrorBoundary>
    </RequireRole>
  )
}
