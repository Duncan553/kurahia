import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { ErrorBoundary, StatusBadge, Button, Modal, useToastStore } from '@shared'
import type { StatusValue } from '@shared'
import api from '../lib/axios'

/* ── Types ──────────────────────────────────────────────────────────────────── */

interface Dispute {
  id: string
  category: string
  status: string            // OPEN | UNDER_REVIEW | RESOLVED | DISMISSED
  priority: string          // LOW | MEDIUM | HIGH
  is_owner_only: boolean
  description: string
  reporter: string | null
  subjects: string[]        // accused employee names
  assigned_to: string | null
  resolution_notes: string | null
  created_at: string        // ISO date
}

/* ── Helpers ─────────────────────────────────────────────────────────────────── */

const extractErr = (e: unknown) =>
  (e as { response?: { data?: { error?: string } } })?.response?.data?.error ?? 'Something went wrong.'

// Map dispute status to StatusBadge values
function statusBadge(s: string): StatusValue {
  if (s === 'OPEN')         return 'pending'
  if (s === 'UNDER_REVIEW') return 'active'
  if (s === 'RESOLVED')     return 'paid'
  return 'failed' // DISMISSED
}

// Priority color classes
function priorityColor(p: string): string {
  if (p === 'HIGH')   return 'text-status-failed'
  if (p === 'MEDIUM') return 'text-status-pending'
  return 'text-ink-tertiary'
}

// Format ISO date to readable string
function fmtDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString('en-KE', { day: 'numeric', month: 'short', year: 'numeric' })
}

/* ── Dispute card ────────────────────────────────────────────────────────────── */

function DisputeCard({ d, onAction }: {
  d: Dispute
  onAction: (id: string, action: 'claim' | 'resolve' | 'dismiss') => void
}) {
  const [expanded, setExpanded] = useState(false)

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.95 }}
      transition={{ duration: 0.25, ease: 'easeOut' }}
      className="glass-card rounded-2xl p-5 border border-white/10"
    >
      {/* Header row: category + status badge */}
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="min-w-0">
          <p className="text-sm font-bold text-ink-primary truncate">
            {d.category.replace(/_/g, ' ')}
          </p>
          <p className="text-[10px] text-ink-tertiary mt-0.5">
            Filed {fmtDate(d.created_at)}
            {d.reporter && <> by <span className="text-ink-tertiary">{d.reporter}</span></>}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {/* Priority dot */}
          <span className={`text-[10px] font-bold uppercase tracking-wider ${priorityColor(d.priority)}`}>
            {d.priority}
          </span>
          <StatusBadge status={statusBadge(d.status)} />
        </div>
      </div>

      {/* Accused names */}
      {d.subjects.length > 0 && (
        <p className="text-xs text-ink-tertiary mb-2">
          Accused: <span className="font-medium text-ink-primary">{d.subjects.join(', ')}</span>
        </p>
      )}

      {/* Description (truncated, expand on click) */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="text-left w-full"
      >
        <p className={`text-xs text-ink-secondary ${expanded ? '' : 'line-clamp-2'}`}>
          {d.description}
        </p>
        {d.description.length > 120 && (
          <span className="text-[10px] text-primary-main mt-1 inline-block">
            {expanded ? 'Show less' : 'Read more'}
          </span>
        )}
      </button>

      {/* Assigned to */}
      {d.assigned_to && (
        <p className="text-[10px] text-ink-tertiary mt-2">
          Assigned to: <span className="text-ink-tertiary">{d.assigned_to}</span>
        </p>
      )}

      {/* Resolution notes (if resolved/dismissed) */}
      {d.resolution_notes && (
        <div className="mt-3 p-3 rounded-xl bg-white/5 border border-white/5">
          <p className="text-[10px] font-semibold tracking-widest uppercase text-ink-tertiary mb-1">Resolution</p>
          <p className="text-xs text-ink-secondary">{d.resolution_notes}</p>
        </div>
      )}

      {/* Action buttons — only for OPEN or UNDER_REVIEW */}
      {(d.status === 'OPEN' || d.status === 'UNDER_REVIEW') && (
        <div className="flex gap-2 mt-4">
          {d.status === 'OPEN' && (
            <Button size="sm" variant="primary" className="flex-1"
              onClick={() => onAction(d.id, 'claim')}>
              Claim & Review
            </Button>
          )}
          {d.status === 'UNDER_REVIEW' && (
            <>
              <Button size="sm" variant="primary" className="flex-1"
                onClick={() => onAction(d.id, 'resolve')}>
                Resolve
              </Button>
              <Button size="sm" variant="ghost" className="flex-1"
                onClick={() => onAction(d.id, 'dismiss')}>
                Dismiss
              </Button>
            </>
          )}
        </div>
      )}

      {/* Owner-only indicator */}
      {d.is_owner_only && (
        <p className="text-[10px] text-status-pending font-medium mt-2">Owner-only</p>
      )}
    </motion.div>
  )
}

/* ── Resolve/Dismiss modal ───────────────────────────────────────────────────── */

function ActionModal({ action, onClose, onSubmit, loading }: {
  action: 'resolve' | 'dismiss'
  onClose: () => void
  onSubmit: (notes: string) => void
  loading: boolean
}) {
  const [notes, setNotes] = useState('')
  const isResolve = action === 'resolve'

  return (
    <Modal open onClose={onClose} size="sm" title={action === 'resolve' ? 'Resolve Dispute' : 'Dismiss Dispute'}>
      <div className="p-5 space-y-4">
        <p className="text-xs text-ink-tertiary">
          {isResolve
            ? 'Describe how this dispute was resolved.'
            : 'Provide a reason for dismissing this dispute.'}
        </p>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder={isResolve ? 'Resolution notes...' : 'Reason for dismissal...'}
          rows={4}
          className="w-full rounded-xl bg-white/5 border border-white/10 p-3
            text-sm text-ink-primary placeholder:text-ink-tertiary
            focus:outline-none focus:ring-2 focus:ring-[#fa5c29] resize-none"
        />
        <div className="flex gap-2">
          <Button size="sm" variant="ghost" className="flex-1" onClick={onClose}>
            Cancel
          </Button>
          <Button size="sm" variant="primary" className="flex-1"
            loading={loading}
            onClick={() => onSubmit(notes)}
            disabled={!notes.trim()}>
            {isResolve ? 'Resolve' : 'Dismiss'}
          </Button>
        </div>
      </div>
    </Modal>
  )
}

/* ── Main screen ─────────────────────────────────────────────────────────────── */

const STATUS_FILTERS = ['ALL', 'OPEN', 'UNDER_REVIEW', 'RESOLVED', 'DISMISSED'] as const

export default function DisputesScreen() {
  const qc = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  const [statusFilter, setStatusFilter] = useState<string>('ALL')
  const [modal, setModal] = useState<{ action: 'resolve' | 'dismiss'; id: string } | null>(null)

  // Fetch disputes — backend filters by role automatically
  const { data: disputes = [], isLoading, isError } = useQuery<Dispute[]>({
    queryKey: ['disputes', statusFilter],
    queryFn: () => {
      const params = statusFilter !== 'ALL' ? `?status=${statusFilter}` : ''
      return api.get<Dispute[]>(`/disputes${params}`).then(r => r.data)
    },
    staleTime: 30_000,
  })

  // Claim mutation (OPEN -> UNDER_REVIEW)
  const claimMut = useMutation({
    mutationFn: (id: string) => api.post(`/disputes/${id}/claim`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['disputes'] })
      addToast({ type: 'success', message: 'Dispute claimed. Now under review.' })
    },
    onError: (e) => addToast({ type: 'error', message: extractErr(e) }),
  })

  // Resolve mutation
  const resolveMut = useMutation({
    mutationFn: ({ id, notes }: { id: string; notes: string }) =>
      api.post(`/disputes/${id}/resolve`, { resolution_notes: notes }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['disputes'] })
      setModal(null)
      addToast({ type: 'success', message: 'Dispute resolved.' })
    },
    onError: (e) => addToast({ type: 'error', message: extractErr(e) }),
  })

  // Dismiss mutation
  const dismissMut = useMutation({
    mutationFn: ({ id, notes }: { id: string; notes: string }) =>
      api.post(`/disputes/${id}/dismiss`, { reason: notes }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['disputes'] })
      setModal(null)
      addToast({ type: 'success', message: 'Dispute dismissed.' })
    },
    onError: (e) => addToast({ type: 'error', message: extractErr(e) }),
  })

  function handleAction(id: string, action: 'claim' | 'resolve' | 'dismiss') {
    if (action === 'claim') {
      claimMut.mutate(id)
    } else {
      setModal({ action, id })
    }
  }

  function handleModalSubmit(notes: string) {
    if (!modal) return
    if (modal.action === 'resolve') {
      resolveMut.mutate({ id: modal.id, notes })
    } else {
      dismissMut.mutate({ id: modal.id, notes })
    }
  }

  return (
    <div className="min-h-screen p-4 md:p-6">
      <div className="max-w-3xl mx-auto">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-6"
        >
          <h1 className="font-serif text-2xl md:text-3xl font-bold text-ink-primary">
            Disputes
          </h1>
          <p className="text-sm text-ink-secondary mt-1">
            Manage formal complaints and dispute resolutions
          </p>
        </motion.div>

        {/* Status filter pills */}
        <div className="flex flex-wrap gap-2 mb-6">
          {STATUS_FILTERS.map(s => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={`px-4 py-2 rounded-full text-xs font-semibold border transition-colors
                ${statusFilter === s
                  ? 'border-[#f9dcd5]/40 bg-white/10 text-ink-primary'
                  : 'border-white/10 text-ink-tertiary hover:text-ink-primary hover:bg-white/5'
                }`}
            >
              {s.replace(/_/g, ' ')}
            </button>
          ))}
        </div>

        {/* Content */}
        <ErrorBoundary level="tile">
          {isLoading && (
            <div className="space-y-4">
              {[1, 2, 3].map(i => (
                <div key={i} className="h-36 rounded-2xl bg-cream-alt animate-pulse" />
              ))}
            </div>
          )}

          {isError && (
            <p className="text-sm text-status-failed text-center py-12">
              Failed to load disputes. Check your connection.
            </p>
          )}

          {!isLoading && !isError && disputes.length === 0 && (
            <div className="flex flex-col items-center justify-center py-20 gap-3">
              <span className="text-5xl text-ink-tertiary/40">&#9745;</span>
              <p className="text-ink-tertiary text-lg font-medium">No disputes found</p>
              <p className="text-xs text-ink-tertiary">
                {statusFilter !== 'ALL' ? 'Try a different filter.' : 'Nothing to review right now.'}
              </p>
            </div>
          )}

          {!isLoading && disputes.length > 0 && (
            <div className="space-y-4">
              <AnimatePresence mode="popLayout">
                {disputes.map(d => (
                  <DisputeCard key={d.id} d={d} onAction={handleAction} />
                ))}
              </AnimatePresence>
            </div>
          )}
        </ErrorBoundary>

        {/* Action modal */}
        {modal && (
          <ActionModal
            action={modal.action}
            onClose={() => setModal(null)}
            onSubmit={handleModalSubmit}
            loading={resolveMut.isPending || dismissMut.isPending}
          />
        )}
      </div>
    </div>
  )
}
