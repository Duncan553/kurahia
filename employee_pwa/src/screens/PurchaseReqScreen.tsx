import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Drawer, Modal, Skeleton, EmptyState, StatusBadge, useToastStore } from '@shared'
import type { StatusValue } from '@shared'
import { RequireRole } from '../components/AuthGate'
import api from '../lib/axios'

interface PurchaseRequest {
  id: string
  item_name: string | null
  quantity: string
  status: string
  created_at: string
  requested_by: string | null
  notes: string | null
  estimated_cost: string | null
}

type Filter = 'PENDING' | 'PROPOSED' | 'APPROVED' | 'REJECTED' | 'FULFILLED'
const FILTERS: Filter[] = ['PENDING', 'PROPOSED', 'APPROVED', 'REJECTED', 'FULFILLED']

function statusValue(s: string): StatusValue {
  const map: Record<string, StatusValue> = {
    PENDING:   'pending',
    PROPOSED:  'pending',
    APPROVED:  'paid',
    REJECTED:  'cancelled',
    FULFILLED: 'checked-out',
  }
  return map[s] ?? 'pending'
}

function genKey() { return crypto.randomUUID() }

export default function PurchaseReqScreen() {
  const addToast    = useToastStore((s) => s.addToast)
  const queryClient = useQueryClient()

  const [filter,     setFilter]     = useState<Filter>('PENDING')
  const [selected,   setSelected]   = useState<PurchaseRequest | null>(null)
  const [cost,       setCost]       = useState('')
  const [propNotes,  setPropNotes]  = useState('')
  const [idemKey,    setIdemKey]    = useState(genKey)
  const [confirmId,  setConfirmId]  = useState<string | null>(null)

  const { data: requests, isLoading, isError } = useQuery<PurchaseRequest[]>({
    queryKey: ['purchase-requests-manager'],
    queryFn: () => api.get<PurchaseRequest[]>('/inventory/purchase-requests').then((r) => r.data),
    staleTime: 30_000,
  })

  const filtered = (requests ?? []).filter((r) => r.status === filter)
  const pendingCount = (requests ?? []).filter((r) => r.status === 'PENDING').length

  const proposeMutation = useMutation({
    mutationFn: ({ id }: { id: string }) =>
      api.post(`/inventory/purchase-requests/${id}/propose`, {
        estimated_cost:  parseFloat(cost),
        notes:           propNotes.trim() || undefined,
        idempotency_key: idemKey,
      }).then((r) => r.data),
    onSuccess: (_, { id }) => {
      const req = requests?.find((r) => r.id === id)
      addToast({ type: 'success', message: `Budget proposed for ${req?.item_name ?? 'request'}.` })
      queryClient.invalidateQueries({ queryKey: ['purchase-requests-manager'] })
      setSelected(null)
      setCost('')
      setPropNotes('')
      setIdemKey(genKey())
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
        ?? 'Proposal failed. Try again.'
      addToast({ type: 'error', message: msg })
    },
  })

  const costValid = !!cost && parseFloat(cost) > 0

  function openPropose(req: PurchaseRequest) {
    setSelected(req)
    setCost(req.estimated_cost ?? '')
    setPropNotes(req.notes ?? '')
  }

  return (
    <RequireRole minLevel={5}>
      <div className="p-4 max-w-lg mx-auto space-y-4">

        <div>
          <h1 className="text-xl font-bold text-ink-primary">Purchase Requests</h1>
          <p className="text-sm text-ink-tertiary">Add estimated costs — owner approves final purchase</p>
        </div>

        {/* Filter tabs */}
        <div className="flex gap-1 bg-cream-alt/50 rounded-xl p-1 overflow-x-auto">
          {FILTERS.map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={[
                'flex-1 py-2 px-2 rounded-lg text-xs font-medium whitespace-nowrap transition-all',
                filter === f
                  ? 'bg-cream-card shadow-sm text-ink-primary'
                  : 'text-ink-tertiary hover:text-ink-secondary',
              ].join(' ')}
            >
              {f.charAt(0) + f.slice(1).toLowerCase()}
              {f === 'PENDING' && pendingCount > 0 && (
                <span className="ml-1 inline-flex items-center justify-center w-4 h-4
                  rounded-full bg-status-failed text-cream-card text-[10px] font-bold">
                  {pendingCount}
                </span>
              )}
            </button>
          ))}
        </div>

        {isLoading && (
          <div className="space-y-3">
            {[1,2,3].map((i) => <Skeleton key={i} variant="row" />)}
          </div>
        )}

        {isError && (
          <div className="p-4 rounded-xl bg-cream-alt/40 text-sm text-ink-tertiary text-center">
            Couldn't load requests. Check connection.
          </div>
        )}

        {!isLoading && filtered.length === 0 && (
          <EmptyState
            icon={
              <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
                <path d="M6 8h5l4 20h22l4-14H14" stroke="currentColor" strokeWidth="2"
                  strokeLinecap="round" strokeLinejoin="round"/>
                <circle cx="20" cy="36" r="3" stroke="currentColor" strokeWidth="2"/>
                <circle cx="32" cy="36" r="3" stroke="currentColor" strokeWidth="2"/>
              </svg>
            }
            title={`No ${filter.toLowerCase()} requests.`}
            description={filter === 'PENDING' ? 'All caught up.' : ''}
          />
        )}

        {!isLoading && filtered.map((req) => {
          const dim = req.status !== 'PENDING'
          return (
            <div
              key={req.id}
              className={[
                'rounded-2xl border p-4 space-y-2',
                dim ? 'border-cream-alt bg-cream-alt/20' : 'border-cream-alt bg-cream-card',
              ].join(' ')}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className={`text-sm font-semibold text-ink-primary ${dim ? 'opacity-70' : ''}`}>
                    {req.item_name ?? 'Unknown item'}
                  </p>
                  <p className="text-xs text-ink-tertiary mt-0.5">
                    Qty: {parseFloat(req.quantity).toLocaleString()}
                    {req.requested_by ? ` · by ${req.requested_by}` : ''}
                  </p>
                </div>
                <StatusBadge status={statusValue(req.status)} />
              </div>

              {req.notes && (
                <p className="text-xs text-ink-secondary italic">"{req.notes}"</p>
              )}

              {req.estimated_cost && (
                <p className="text-xs text-ink-tertiary">
                  Estimated cost:{' '}
                  <span className="font-semibold text-ink-primary">
                    KSh {parseFloat(req.estimated_cost).toLocaleString()}
                  </span>
                </p>
              )}

              {/* Only PENDING can be proposed */}
              {req.status === 'PENDING' && (
                <button
                  onClick={() => openPropose(req)}
                  className="w-full mt-1 py-2.5 rounded-xl bg-primary-dark text-cream-card text-sm font-semibold
                    hover:bg-primary-dark/90 transition-colors
                    focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark"
                >
                  Propose budget
                </button>
              )}

              {/* PROPOSED: show re-propose option */}
              {req.status === 'PROPOSED' && (
                <button
                  onClick={() => openPropose(req)}
                  className="w-full mt-1 py-2 rounded-xl border border-primary-dark/30 text-primary-dark
                    text-sm font-medium hover:bg-primary-dark/5 transition-colors"
                >
                  Update estimate
                </button>
              )}
            </div>
          )
        })}
      </div>

      {/* Propose budget drawer */}
      <Drawer
        open={!!selected}
        onClose={() => setSelected(null)}
        title={`Propose budget — ${selected?.item_name ?? ''}`}
      >
        {selected && (
          <form
            onSubmit={(e) => {
              e.preventDefault()
              if (costValid) setConfirmId(selected.id)
            }}
            className="space-y-4"
          >
            <div className="rounded-xl bg-cream-alt/40 px-4 py-3 text-sm space-y-0.5">
              <p className="text-ink-tertiary">
                Item: <span className="text-ink-primary font-medium">{selected.item_name}</span>
              </p>
              <p className="text-ink-tertiary">
                Qty: <span className="text-ink-primary font-medium">
                  {parseFloat(selected.quantity).toLocaleString()}
                </span>
              </p>
              {selected.requested_by && (
                <p className="text-ink-tertiary">
                  Requested by: <span className="text-ink-primary font-medium">{selected.requested_by}</span>
                </p>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-ink-secondary mb-1.5">
                Estimated cost (KSh) *
              </label>
              <input
                type="number"
                min="1"
                step="0.01"
                inputMode="decimal"
                value={cost}
                onChange={(e) => setCost(e.target.value)}
                placeholder="0.00"
                autoFocus
                className="w-full rounded-xl border border-cream-alt bg-white px-4 py-3 text-base
                  text-ink-primary focus:outline-none focus:border-primary-dark focus:ring-2 focus:ring-primary-dark/20"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-ink-secondary mb-1.5">
                Manager notes (optional)
              </label>
              <textarea
                rows={3}
                value={propNotes}
                onChange={(e) => setPropNotes(e.target.value)}
                placeholder="Supplier name, urgency, any caveats…"
                className="w-full rounded-xl border border-cream-alt bg-white px-4 py-3 text-sm
                  text-ink-primary focus:outline-none focus:border-primary-dark
                  focus:ring-2 focus:ring-primary-dark/20 resize-none"
              />
            </div>

            <p className="text-xs text-ink-tertiary">
              This sends the estimated cost to the owner for final approval. You cannot approve purchases.
            </p>

            <button
              type="submit"
              disabled={!costValid}
              className={[
                'w-full py-4 rounded-2xl text-base font-semibold transition-all',
                'bg-primary-dark text-cream-card hover:bg-primary-dark/90 active:scale-[0.99]',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark focus-visible:ring-offset-2',
                'disabled:opacity-50 disabled:cursor-not-allowed',
              ].join(' ')}
            >
              Submit estimate to owner
            </button>
          </form>
        )}
      </Drawer>

      {/* Confirm modal */}
      <Modal
        open={!!confirmId}
        onClose={() => setConfirmId(null)}
        title="Submit budget estimate?"
        size="sm"
      >
        {confirmId && (() => {
          const req = requests?.find((r) => r.id === confirmId)
          return (
            <div className="space-y-4">
              <p className="text-sm text-ink-secondary">
                Submit <strong>KSh {parseFloat(cost).toLocaleString()}</strong> as estimated cost for{' '}
                <strong>{req?.item_name}</strong>? The owner will be notified to approve.
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => setConfirmId(null)}
                  className="flex-1 py-3 rounded-xl border border-cream-alt text-sm font-medium
                    text-ink-secondary hover:bg-cream-alt/40 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={() => {
                    setConfirmId(null)
                    proposeMutation.mutate({ id: confirmId })
                  }}
                  disabled={proposeMutation.isPending}
                  className="flex-1 py-3 rounded-xl bg-primary-dark text-cream-card text-sm font-semibold
                    hover:bg-primary-dark/90 disabled:opacity-50 transition-colors"
                >
                  {proposeMutation.isPending ? 'Submitting…' : 'Confirm'}
                </button>
              </div>
            </div>
          )
        })()}
      </Modal>
    </RequireRole>
  )
}
