/**
 * FolioScreen — the guest's bill for their whole stay.
 *
 * GET /receipts/:tab_id has existed since Phase A with no caller in any of the
 * three PWAs. So a guest checking out after four nights was told a total and
 * nothing else, and front desk could not answer "what is this KSh 18,400 for?"
 * without opening the database.
 *
 * Every line here is already stored — charges carry unit_price_snapshot frozen
 * at the time of sale (invariant 3), so a bill printed today for a stay last
 * month shows the price that was actually charged, not today's menu.
 *
 * The balance is DERIVED (charges - payments, invariant 2), never stored, so
 * this screen cannot disagree with the tab it is describing.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useParams, useNavigate } from 'react-router-dom'
import { ErrorBoundary, EmptyState, Modal, Button, Input, Select, FormField, useToastStore } from '@shared'
import { formatDateTime } from '../lib/format'
import api from '../lib/axios'

interface Line { description: string; amount: string; created_at: string }
interface Pay {
  method: string; amount: string; received_by: string | null
  mpesa_code: string | null; card_ref: string | null; created_at: string
}
interface Folio {
  tab_id: string; reference: string | null; tab_type: string
  opened_at: string; closed_at: string | null; opened_by: string | null
  charges: Line[]; payments: Pay[]
  total_charges: string; total_payments: string; balance: string; status: string
}

const ksh = (v: string | number) =>
  'KSh ' + parseFloat(String(v)).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })

const METHODS = [
  { value: 'CASH',          label: 'Cash' },
  { value: 'MPESA',         label: 'M-Pesa' },
  { value: 'CARD',          label: 'Card' },
  { value: 'BANK_TRANSFER', label: 'Bank transfer' },
]

const extractErr = (e: unknown) =>
  (e as { response?: { data?: { error?: string } } })?.response?.data?.error
  ?? 'Could not record that payment. Try again.'

export default function FolioScreen() {
  const { tabId } = useParams<{ tabId: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const addToast = useToastStore(s => s.addToast)

  // Settling the bill lives HERE because front desk had nowhere else to do it.
  // Check-out refuses while a balance stands (services/tab.py is_tab_closable),
  // CheckInScreen never called /tabs/:id/payments, and front desk has no Tables
  // tile (AppLayout gates it to restaurant/F&B departments) — so a guest with
  // KSh 18,400 on the villa could not be checked out by anyone at the desk.
  // The guest is already looking at the bill; take the money on the same screen.
  const [paying, setPaying] = useState(false)
  const [method, setMethod] = useState('CASH')
  const [amount, setAmount] = useState('')
  const [ref, setRef] = useState('')
  const [idem, setIdem] = useState(() => crypto.randomUUID())

  const { data, isLoading, isError } = useQuery<Folio>({
    queryKey: ['folio', tabId],
    queryFn: () => api.get<Folio>(`/receipts/${tabId}`).then(r => r.data),
    enabled: !!tabId,
  })

  const payMut = useMutation({
    mutationFn: () => api.post(`/tabs/${tabId}/payments`, {
      method,
      amount,
      // The reference is what makes a payment checkable at reconciliation.
      // Sent under the key the backend reads for each method.
      ...(method === 'MPESA' ? { mpesa_code: ref.trim() || null } : {}),
      ...(method === 'CARD' ? { card_ref: ref.trim() || null } : {}),
      ...(method === 'BANK_TRANSFER' ? { bank_ref: ref.trim() || null } : {}),
      idempotency_key: idem,
    }),
    onSuccess: () => {
      addToast({ type: 'success', message: 'Payment recorded.' })
      setPaying(false); setAmount(''); setRef(''); setIdem(crypto.randomUUID())
      qc.invalidateQueries({ queryKey: ['folio', tabId] })
      // The departures list shows the outstanding balance — keep it honest.
      qc.invalidateQueries({ queryKey: ['front-desk-today'] })
    },
    onError: (e) => addToast({ type: 'error', message: extractErr(e) }),
  })

  if (isLoading) {
    return (
      <div className="py-24 flex justify-center">
        <div className="w-7 h-7 rounded-full border-2 border-primary-main border-t-transparent animate-spin" />
      </div>
    )
  }

  if (isError || !data) {
    return (
      <EmptyState
        icon={<svg width="40" height="40" viewBox="0 0 40 40" fill="none" aria-hidden="true">
          <circle cx="20" cy="20" r="14" stroke="currentColor" strokeWidth="1.5"/>
          <path d="M20 13v9M20 26v.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
        </svg>}
        title="Could not load this bill"
        description="The tab may have been removed, or the connection dropped. Go back and try again." />
    )
  }

  const owes = parseFloat(data.balance) > 0
  // A refund/reversal is a negative charge (invariant: corrections are new rows,
  // never edits). Showing it as its own line is the point — the guest can see
  // the thing that was taken off, not just a total that quietly shrank.
  const isReversal = (l: Line) => parseFloat(l.amount) < 0

  // NOT gated to level 3 here. GET /receipts/:tab_id checks only that the
  // caller is an active user, and a waiter closing their own table needs the
  // bill as much as front desk does. Gating the SCREEN stricter than the
  // ENDPOINT would not add security — the API is reachable either way — it
  // would just hide a legitimate tool from the people who use it most.
  // If villa folios should be restricted, that belongs in receipts.py.
  return (
      <ErrorBoundary level="tile">
        <div className="p-4 md:p-6 max-w-2xl mx-auto">

          <button onClick={() => navigate(-1)}
            className="text-xs text-ink-tertiary hover:text-ink-primary mb-4">
            ← Back
          </button>

          <div className="glass-card rounded-2xl overflow-hidden">
            {/* ── Header ─────────────────────────────────────────── */}
            <div className="p-5 border-b border-white/10">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary">
                    {data.tab_type === 'VILLA' ? 'Villa account'
                      : data.tab_type === 'BAND' ? 'Wristband account' : 'Table'}
                  </p>
                  <h1 className="text-2xl font-bold font-serif text-ink-primary truncate">
                    {data.reference ?? 'Walk-in'}
                  </h1>
                </div>
                <span className={`text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full
                  shrink-0 ${data.status === 'CLOSED'
                    ? 'bg-status-paid/20 text-status-paid' : 'bg-status-pending/20 text-status-pending'}`}>
                  {data.status === 'CLOSED' ? 'Settled' : 'Open'}
                </span>
              </div>
              <p className="text-[11px] text-ink-tertiary mt-2">
                Opened {formatDateTime(data.opened_at)}
                {data.closed_at ? ` · Closed ${formatDateTime(data.closed_at)}` : ''}
                {data.opened_by ? ` · by ${data.opened_by}` : ''}
              </p>
            </div>

            {/* ── Charges ────────────────────────────────────────── */}
            <div className="p-5 border-b border-white/10">
              <p className="text-[11px] font-semibold tracking-wider uppercase text-ink-tertiary mb-3">
                Charges
              </p>
              {data.charges.length === 0 ? (
                <p className="text-sm text-ink-tertiary">Nothing charged to this account.</p>
              ) : (
                <ul className="flex flex-col gap-2">
                  {data.charges.map((l, i) => (
                    <li key={i} className="flex items-baseline justify-between gap-3 text-sm">
                      <span className={`min-w-0 ${isReversal(l) ? 'text-status-paid' : 'text-ink-secondary'}`}>
                        {l.description}
                        <span className="block text-[10px] text-ink-tertiary">
                          {formatDateTime(l.created_at)}
                        </span>
                      </span>
                      <span className={`tabular-nums shrink-0 font-medium
                        ${isReversal(l) ? 'text-status-paid' : 'text-ink-primary'}`}>
                        {ksh(l.amount)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              <div className="flex items-baseline justify-between mt-4 pt-3 border-t border-white/10">
                <span className="text-sm font-semibold text-ink-primary">Total charges</span>
                <span className="text-sm font-bold text-ink-primary tabular-nums">
                  {ksh(data.total_charges)}
                </span>
              </div>
            </div>

            {/* ── Payments ───────────────────────────────────────── */}
            <div className="p-5 border-b border-white/10">
              <p className="text-[11px] font-semibold tracking-wider uppercase text-ink-tertiary mb-3">
                Paid
              </p>
              {data.payments.length === 0 ? (
                <p className="text-sm text-ink-tertiary">No payment received yet.</p>
              ) : (
                <ul className="flex flex-col gap-2">
                  {data.payments.map((p, i) => (
                    <li key={i} className="flex items-baseline justify-between gap-3 text-sm">
                      <span className="min-w-0 text-ink-secondary">
                        {p.method}
                        {/* The reference is what makes a payment checkable later. */}
                        {(p.mpesa_code || p.card_ref) && (
                          <span className="text-ink-tertiary"> · {p.mpesa_code ?? p.card_ref}</span>
                        )}
                        <span className="block text-[10px] text-ink-tertiary">
                          {formatDateTime(p.created_at)}{p.received_by ? ` · ${p.received_by}` : ''}
                        </span>
                      </span>
                      <span className="tabular-nums shrink-0 font-medium text-ink-primary">
                        {ksh(p.amount)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              <div className="flex items-baseline justify-between mt-4 pt-3 border-t border-white/10">
                <span className="text-sm font-semibold text-ink-primary">Total paid</span>
                <span className="text-sm font-bold text-ink-primary tabular-nums">
                  {ksh(data.total_payments)}
                </span>
              </div>
            </div>

            {/* ── Balance: the number the guest is actually asking about ── */}
            <div className={`p-5 flex items-baseline justify-between
              ${owes ? 'bg-status-pending/10' : 'bg-status-paid/10'}`}>
              <span className="text-base font-semibold text-ink-primary">
                {owes ? 'Still to pay' : 'Balance'}
              </span>
              <span className={`text-2xl font-bold tabular-nums font-serif
                ${owes ? 'text-status-pending' : 'text-status-paid'}`}>
                {ksh(data.balance)}
              </span>
            </div>
          </div>

          {owes && data.status !== 'CLOSED' && (
            <div className="mt-4 flex flex-col gap-2">
              <Button onClick={() => { setAmount(data.balance); setPaying(true) }}>
                Take payment
              </Button>
              <p className="text-xs text-ink-tertiary text-center">
                Check-out is blocked until this is settled.
              </p>
            </div>
          )}

          <Modal open={paying} onClose={() => setPaying(false)} title="Take payment" size="sm">
            <form onSubmit={e => { e.preventDefault(); payMut.mutate() }} className="flex flex-col gap-4">
              <FormField label="How are they paying?" htmlFor="pay-method" required>
                <Select id="pay-method" required value={method}
                  onChange={e => { setMethod(e.target.value); setRef('') }}
                  options={METHODS} />
              </FormField>

              <FormField label="Amount (KSh)" htmlFor="pay-amount" required>
                <Input id="pay-amount" required type="number" min="0" step="0.01"
                  inputMode="decimal" value={amount}
                  onChange={e => setAmount(e.target.value)} />
              </FormField>

              {/* Part-payments are allowed — the backend just reduces the
                  balance — so this is prefilled with the full amount but not
                  locked to it. */}
              {parseFloat(amount || '0') < parseFloat(data.balance) && (
                <p className="text-xs text-status-pending">
                  This is a part payment. {ksh(parseFloat(data.balance) - parseFloat(amount || '0'))} will
                  still be owing, and check-out stays blocked.
                </p>
              )}

              {method !== 'CASH' && (
                <FormField
                  label={method === 'MPESA' ? 'M-Pesa code' : method === 'CARD' ? 'Card reference' : 'Bank reference'}
                  htmlFor="pay-ref">
                  <Input id="pay-ref" value={ref} onChange={e => setRef(e.target.value)}
                    placeholder="So it can be matched at reconciliation" />
                </FormField>
              )}

              <Button type="submit" loading={payMut.isPending}
                disabled={!amount || parseFloat(amount) <= 0}>
                Record {ksh(amount || 0)}
              </Button>
            </form>
          </Modal>
        </div>
      </ErrorBoundary>
  )
}
