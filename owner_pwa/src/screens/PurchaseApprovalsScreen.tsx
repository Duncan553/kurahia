import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Drawer, Button, useToastStore, EmptyState, Skeleton, StatusBadge, SearchInput } from '@shared'
import api from '../lib/axios'

// ── Types ─────────────────────────────────────────────────────────────────────

interface PurchaseRequest {
  id: string
  item_name: string
  item_id: string | null
  quantity: string
  status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'FULFILLED'
  created_at: string
  requested_by: string
  department: string
  notes: string | null
  estimated_cost: string | null
}

type TabFilter = 'pending' | 'approved' | 'rejected' | 'all'

// ── Helpers ───────────────────────────────────────────────────────────────────

const formatKsh = (v: string | number | null | undefined) => {
  if (!v) return null
  const n = parseFloat(String(v))
  if (isNaN(n)) return null
  return `KSh ${n.toLocaleString('en-KE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

const extractErr = (e: unknown) =>
  (e as { response?: { data?: { error?: string } } })?.response?.data?.error ?? 'Something went wrong.'

function timeAgo(iso: string) {
  const sec = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`
  if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`
  return `${Math.floor(sec / 86400)}d ago`
}

function statusBadge(s: string): import('@shared').StatusValue {
  if (s === 'APPROVED' || s === 'FULFILLED') return 'confirmed'
  if (s === 'REJECTED') return 'failed'
  return 'pending'
}

// ── Approval drawer ───────────────────────────────────────────────────────────

function ApprovalDrawer({
  request,
  onClose,
}: {
  request: PurchaseRequest
  onClose: () => void
}) {
  const qc = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  const [notes, setNotes] = useState('')
  const [confirmReject, setConfirmReject] = useState(false)

  const approveMut = useMutation({
    mutationFn: (action: 'approve' | 'reject') =>
      api.post(`/inventory/purchase-requests/${request.id}/approve`, { action, notes: notes || undefined }),
    onSuccess: (_, action) => {
      qc.invalidateQueries({ queryKey: ['purchase-requests'] })
      addToast({ type: 'success', message: action === 'approve' ? 'Purchase approved.' : 'Purchase rejected.' })
      onClose()
    },
    onError: e => addToast({ type: 'error', message: extractErr(e) }),
  })

  const isPending = request.status === 'PENDING'

  return (
    <div className="space-y-5">
      {/* Summary */}
      <div className="rounded-xl bg-cream-alt p-4 space-y-2">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="font-semibold text-ink-primary text-base">{request.item_name}</p>
            <p className="text-xs text-ink-secondary mt-0.5">
              Qty: <span className="font-medium">{request.quantity}</span>
            </p>
          </div>
          <StatusBadge status={statusBadge(request.status)} />
        </div>
        <div className="text-xs text-ink-secondary space-y-1 pt-1 border-t border-cream-deep">
          <p>By: <span className="font-medium text-ink-primary">{request.requested_by}</span></p>
          <p>Dept: <span className="font-medium text-ink-primary">{request.department}</span></p>
          <p>Submitted: {timeAgo(request.created_at)}</p>
          {request.notes && <p className="italic">"{request.notes}"</p>}
        </div>
      </div>

      {/* Estimated cost */}
      {request.estimated_cost ? (
        <div className="rounded-xl border border-cream-alt p-4">
          <p className="text-[10px] font-semibold tracking-widest uppercase text-ink-secondary mb-1">
            Manager's Estimate
          </p>
          <p className="text-2xl font-bold tabular-nums text-ink-primary">
            {formatKsh(request.estimated_cost) ?? request.estimated_cost}
          </p>
          <p className="text-xs text-ink-tertiary mt-0.5">Proposed by manager</p>
        </div>
      ) : (
        <div className="rounded-xl border border-cream-alt p-3">
          <p className="text-xs text-ink-tertiary">
            No cost estimate yet — manager hasn't proposed a cost for this request.
          </p>
        </div>
      )}

      {/* Notes field (only if pending) */}
      {isPending && (
        <div>
          <label className="block text-xs font-semibold text-ink-secondary mb-1.5">
            Notes (optional)
          </label>
          <textarea
            rows={2}
            value={notes}
            onChange={e => setNotes(e.target.value)}
            placeholder="Add a note for your records…"
            className="w-full rounded-lg border border-cream-alt bg-cream-card px-3 py-2 text-sm
              text-ink-primary placeholder:text-ink-tertiary resize-none
              focus:outline-none focus:ring-2 focus:ring-primary-main"
          />
        </div>
      )}

      {/* Action buttons */}
      {isPending && (
        <div className="space-y-2">
          {!confirmReject ? (
            <>
              <Button
                variant="primary"
                className="w-full"
                disabled={approveMut.isPending}
                onClick={() => approveMut.mutate('approve')}
              >
                {approveMut.isPending ? 'Approving…' : 'Approve Purchase'}
              </Button>
              <Button
                variant="ghost"
                className="w-full"
                disabled={approveMut.isPending}
                onClick={() => setConfirmReject(true)}
              >
                Reject
              </Button>
            </>
          ) : (
            <>
              <p className="text-sm text-status-failed font-medium text-center">
                Confirm rejection?
              </p>
              <Button
                variant="primary"
                className="w-full !bg-status-failed"
                disabled={approveMut.isPending}
                onClick={() => approveMut.mutate('reject')}
              >
                {approveMut.isPending ? 'Rejecting…' : 'Yes, reject'}
              </Button>
              <Button
                variant="ghost"
                className="w-full"
                disabled={approveMut.isPending}
                onClick={() => setConfirmReject(false)}
              >
                Cancel
              </Button>
            </>
          )}
        </div>
      )}

      {!isPending && (
        <p className="text-xs text-ink-tertiary text-center">
          This request is {request.status.toLowerCase()} — no further action available.
        </p>
      )}
    </div>
  )
}

// ── Row card ──────────────────────────────────────────────────────────────────

function RequestCard({
  req,
  onSelect,
}: {
  req: PurchaseRequest
  onSelect: () => void
}) {
  const isPending = req.status === 'PENDING'
  const hasCost = req.estimated_cost !== null

  return (
    <button
      onClick={onSelect}
      className="w-full text-left rounded-xl border border-cream-alt bg-cream-card p-4
        hover:border-primary-light/50 hover:shadow-sm transition-all
        focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-main"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-ink-primary text-sm truncate">{req.item_name}</p>
          <p className="text-xs text-ink-secondary mt-0.5">
            {req.department} · by {req.requested_by} · {timeAgo(req.created_at)}
          </p>
        </div>
        <StatusBadge status={statusBadge(req.status)} size="sm" />
      </div>

      {isPending && hasCost && (
        <div className="mt-2 flex items-center gap-2">
          <span className="text-xs text-ink-tertiary">Manager estimate:</span>
          <span className="text-sm font-semibold tabular-nums text-status-pending">
            {formatKsh(req.estimated_cost) ?? req.estimated_cost}
          </span>
        </div>
      )}

      {isPending && !hasCost && (
        <p className="mt-2 text-xs text-ink-secondary italic">Awaiting manager cost estimate</p>
      )}
    </button>
  )
}

// ── Main screen ───────────────────────────────────────────────────────────────

const TAB_LABELS: { key: TabFilter; label: string }[] = [
  { key: 'pending',  label: 'Pending' },
  { key: 'approved', label: 'Approved' },
  { key: 'rejected', label: 'Rejected' },
  { key: 'all',      label: 'All' },
]

export default function PurchaseApprovalsScreen() {
  const [searchQ, setSearchQ] = useState('')
  const [tab, setTab] = useState<TabFilter>('pending')
  const [selected, setSelected] = useState<PurchaseRequest | null>(null)

  const { data, isLoading, isError } = useQuery<PurchaseRequest[]>({
    queryKey: ['purchase-requests', searchQ],
    queryFn: () => api.get<PurchaseRequest[]>(`/inventory/purchase-requests${searchQ ? `?q=${encodeURIComponent(searchQ)}` : ''}`).then(r => r.data),
    staleTime: 60_000,
  })

  const filtered = (data ?? []).filter(r => {
    if (tab === 'all') return true
    return r.status.toLowerCase() === tab
  })

  const pendingCount = (data ?? []).filter(r => r.status === 'PENDING').length

  return (
    <div className="p-4 max-w-2xl mx-auto">
      <div className="mb-5">
        <h1 className="font-serif text-2xl text-ink-primary">Purchase Approvals</h1>
        {pendingCount > 0 && (
          <p className="text-xs text-status-pending font-semibold mt-0.5">
            {pendingCount} request{pendingCount !== 1 ? 's' : ''} awaiting your decision
          </p>
        )}
      </div>

      {/* Filter tabs */}
      <div className="flex gap-1 bg-cream-alt rounded-xl p-1 mb-4" role="tablist">
        {TAB_LABELS.map(({ key, label }) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={[
              'flex-1 py-2 rounded-lg text-xs font-semibold transition-colors',
              tab === key
                ? 'bg-cream-card text-ink-primary shadow-sm'
                : 'text-ink-secondary hover:text-ink-primary',
            ].join(' ')}
          >
            {label}
            {key === 'pending' && pendingCount > 0 && (
              <span className="ml-1 inline-flex items-center justify-center w-5 h-5 rounded-full
                bg-status-pending text-xs font-bold text-cream-card">
                {pendingCount}
              </span>
            )}
          </button>
        ))}
      </div>

      <SearchInput value={searchQ} onChange={setSearchQ} placeholder="Search requests..." label="Search requests" />

      {searchQ && filtered.length === 0 && !isLoading && (
        <p className="text-sm text-ink-tertiary text-center py-8">No results for &lsquo;{searchQ}&rsquo; &middot; Hakuna kitu</p>
      )}

      {/* List */}
      {isLoading && (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="rounded-xl border border-cream-alt bg-cream-card p-4 space-y-2">
              <Skeleton variant="text" className="w-40 h-4" />
              <Skeleton variant="text" className="w-56 h-3" />
            </div>
          ))}
        </div>
      )}

      {isError && (
        <div className="rounded-xl border border-status-failed/30 bg-status-failed/5 p-4 text-center">
          <p className="text-sm text-status-failed">Couldn't load purchase requests.</p>
        </div>
      )}

      {!isLoading && !isError && filtered.length === 0 && (
        <EmptyState
          icon={<svg width="32" height="32" viewBox="0 0 32 32" fill="none" aria-hidden="true"><rect x="6" y="4" width="20" height="24" rx="3" stroke="currentColor" strokeWidth="1.5"/><path d="M11 12h10M11 17h7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/></svg>}
          title={tab === 'pending' ? 'No pending approvals' : `No ${tab} requests`}
          description={tab === 'pending' ? 'All caught up. Nothing waiting for your decision.' : undefined}
        />
      )}

      {!isLoading && !isError && filtered.length > 0 && (
        <div className="space-y-2">
          {filtered.map(req => (
            <RequestCard key={req.id} req={req} onSelect={() => setSelected(req)} />
          ))}
        </div>
      )}

      {/* Detail drawer */}
      <Drawer
        open={selected !== null}
        onClose={() => setSelected(null)}
        title={selected?.item_name ?? ''}
      >
        {selected && (
          <ApprovalDrawer request={selected} onClose={() => setSelected(null)} />
        )}
      </Drawer>
    </div>
  )
}
