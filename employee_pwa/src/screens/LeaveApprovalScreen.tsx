import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { Modal, Skeleton, EmptyState, StatusBadge, useToastStore } from '@shared'
import { RequireRole } from '../components/AuthGate'
import api from '../lib/axios'

interface LeaveRequest {
  id: string
  employee: string | null
  leave_type: string
  start_date: string
  end_date: string
  status: string
  reason: string | null
}

type Filter = 'PENDING' | 'APPROVED' | 'REJECTED' | 'CANCELLED'

const FILTERS: Filter[] = ['PENDING', 'APPROVED', 'REJECTED', 'CANCELLED']

const TYPE_LABELS: Record<string, string> = {
  ANNUAL: 'Annual Leave',
  SICK: 'Sick Leave',
  EMERGENCY: 'Emergency Leave',
  UNPAID: 'Unpaid Leave',
}

function statusToValue(s: string): 'paid' | 'pending' | 'cancelled' {
  if (s === 'APPROVED') return 'paid'
  if (s === 'PENDING')  return 'pending'
  return 'cancelled'
}

function daysBetween(start: string, end: string): number {
  const s = new Date(start).getTime()
  const e = new Date(end).getTime()
  return Math.ceil((e - s) / (1000 * 60 * 60 * 24)) + 1
}

export default function LeaveApprovalScreen() {
  const addToast    = useToastStore((s) => s.addToast)
  const queryClient = useQueryClient()

  const [filter,      setFilter]      = useState<Filter>('PENDING')
  const [approveId,   setApproveId]   = useState<string | null>(null)
  const [rejectId,    setRejectId]    = useState<string | null>(null)
  const [rejectNotes, setRejectNotes] = useState('')

  const containerVariants = { hidden: {}, visible: { transition: { staggerChildren: 0.06 } } }
  const itemVariants = { hidden: { opacity: 0, y: 12 }, visible: { opacity: 1, y: 0, transition: { type: 'spring' as const, damping: 25, stiffness: 300 } } }

  const { data: requests, isLoading, isError } = useQuery<LeaveRequest[]>({
    queryKey: ['leave-requests'],
    queryFn: () => api.get<LeaveRequest[]>('/hr/leave-requests').then((r) => r.data),
    staleTime: 30_000,
  })

  const filtered = (requests ?? []).filter((r) => r.status === filter)

  const approveMutation = useMutation({
    mutationFn: (id: string) =>
      api.post(`/hr/leave-requests/${id}/approve`).then((r) => r.data),
    onSuccess: (_, id) => {
      const emp = requests?.find((r) => r.id === id)?.employee ?? 'Employee'
      addToast({ type: 'success', message: `Leave approved for ${emp}.` })
      queryClient.invalidateQueries({ queryKey: ['leave-requests'] })
      setApproveId(null)
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
        ?? 'Approval failed. Try again.'
      addToast({ type: 'error', message: msg })
    },
  })

  const rejectMutation = useMutation({
    mutationFn: ({ id, notes }: { id: string; notes: string }) =>
      api.post(`/hr/leave-requests/${id}/reject`, { notes }).then((r) => r.data),
    onSuccess: (_, { id }) => {
      const emp = requests?.find((r) => r.id === id)?.employee ?? 'Employee'
      addToast({ type: 'warning', message: `Leave rejected for ${emp}.` })
      queryClient.invalidateQueries({ queryKey: ['leave-requests'] })
      setRejectId(null)
      setRejectNotes('')
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
        ?? 'Rejection failed. Try again.'
      addToast({ type: 'error', message: msg })
    },
  })

  const rejectNotesValid = rejectNotes.trim().length >= 10

  return (
    <RequireRole minLevel={5}>
      <motion.div
        className="p-4 max-w-3xl mx-auto space-y-4"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ type: 'spring', damping: 25, stiffness: 300 }}
      >

        <div>
          <h1 className="text-2xl font-bold text-white font-serif">Leave Requests</h1>
          <p className="text-xs text-white/30 mt-0.5">Review staff leave requests</p>
        </div>

        {/* Status filter tabs */}
        <div className="flex gap-1 bg-white/5/50 rounded-xl p-1 overflow-x-auto">
          {FILTERS.map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={[
                'flex-1 py-2 min-h-[44px] px-3 rounded-lg text-xs font-medium whitespace-nowrap transition-all',
                filter === f
                  ? 'bg-transparent shadow-sm text-white'
                  : 'text-slate-400/50 hover:text-slate-300/70',
              ].join(' ')}
            >
              {f.charAt(0) + f.slice(1).toLowerCase()}
              {f === 'PENDING' && (requests ?? []).filter(r => r.status === 'PENDING').length > 0 && (
                <span className="ml-1.5 inline-flex items-center justify-center w-4 h-4
                  rounded-full bg-status-failed text-white text-[10px] font-bold">
                  {(requests ?? []).filter(r => r.status === 'PENDING').length}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* List */}
        {isLoading && (
          <div className="space-y-3">
            {[1,2,3].map((i) => <Skeleton key={i} variant="row" />)}
          </div>
        )}

        {isError && (
          <div className="p-4 rounded-xl bg-white/5/40 text-sm text-slate-400/50 text-center">
            Couldn't load leave requests. Check connection.
          </div>
        )}

        {!isLoading && filtered.length === 0 && (
          <EmptyState
            icon={
              <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
                <rect x="8" y="8" width="32" height="34" rx="3" stroke="currentColor" strokeWidth="2"/>
                <path d="M16 8V5M32 8V5M8 20h32" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                <path d="M16 28l4 4 10-10" stroke="currentColor" strokeWidth="2"
                  strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            }
            title={`No ${filter.toLowerCase()} leave requests.`}
            description="All clear here."
          />
        )}

        {!isLoading && filtered.length > 0 && (
          <motion.div initial="hidden" animate="visible" variants={containerVariants} className="space-y-4">
            {filtered.map((lr) => {
              const days = daysBetween(lr.start_date, lr.end_date)
              const isCancelled = lr.status !== 'PENDING'
              return (
                <motion.div
                  key={lr.id}
                  variants={itemVariants}
                  whileHover={{ y: -2 }}
                  className={[
                    'rounded-2xl border p-4 space-y-3',
                    isCancelled ? 'glass-card bg-white/5/20 opacity-80' : 'glass-card bg-transparent',
                  ].join(' ')}
                >
                  {/* Header row */}
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className={`font-semibold text-sm text-white ${isCancelled ? 'line-through opacity-60' : ''}`}>
                        {lr.employee ?? 'Unknown'}
                      </p>
                      <p className="text-xs text-slate-400/50 mt-0.5">
                        {TYPE_LABELS[lr.leave_type] ?? lr.leave_type}
                        {' · '}{days} day{days !== 1 ? 's' : ''}
                      </p>
                    </div>
                    <StatusBadge status={statusToValue(lr.status)} />
                  </div>

                  {/* Date range */}
                  <div className="flex gap-2 text-xs text-slate-400/50">
                    <span>{lr.start_date}</span>
                    <span aria-hidden="true">{'→'}</span>
                    <span>{lr.end_date}</span>
                  </div>

                  {/* Reason */}
                  {lr.reason && (
                    <p className="text-xs text-slate-300/70 italic">"{lr.reason}"</p>
                  )}

                  {/* Actions — only for PENDING */}
                  {lr.status === 'PENDING' && (
                    <div className="flex gap-2 pt-1">
                      <motion.button
                        whileTap={{ scale: 0.97 }}
                        onClick={() => setApproveId(lr.id)}
                        className="flex-1 py-2.5 min-h-[44px] rounded-xl bg-primary-dark text-white text-sm font-semibold
                          hover:bg-primary-dark/90 transition-colors
                          focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark"
                      >
                        Approve
                      </motion.button>
                      <motion.button
                        whileTap={{ scale: 0.97 }}
                        onClick={() => { setRejectId(lr.id); setRejectNotes('') }}
                        className="flex-1 py-2.5 min-h-[44px] rounded-xl bg-status-failed text-white
                          text-sm font-semibold hover:bg-status-failed/90 transition-colors
                          focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-status-failed"
                      >
                        Reject
                      </motion.button>
                    </div>
                  )}
                </motion.div>
              )
            })}
          </motion.div>
        )}
      </motion.div>

      {/* Approve modal */}
      <Modal
        open={!!approveId}
        onClose={() => setApproveId(null)}
        title="Approve leave?"
        size="sm"
      >
        {approveId && (() => {
          const lr = requests?.find((r) => r.id === approveId)
          return (
            <div className="space-y-4">
              <p className="text-sm text-slate-300/70">
                Approve <strong>{TYPE_LABELS[lr?.leave_type ?? ''] ?? lr?.leave_type}</strong> for{' '}
                <strong>{lr?.employee}</strong>?
                The employee will be notified.
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => setApproveId(null)}
                  className="flex-1 py-3 rounded-xl border border-white/10 text-sm font-medium
                    text-slate-300/70 hover:bg-white/5/40 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={() => approveMutation.mutate(approveId)}
                  disabled={approveMutation.isPending}
                  className="flex-1 py-3 rounded-xl bg-primary-dark text-white text-sm font-semibold
                    hover:bg-primary-dark/90 disabled:opacity-50 transition-colors"
                >
                  {approveMutation.isPending ? 'Approving…' : 'Approve'}
                </button>
              </div>
            </div>
          )
        })()}
      </Modal>

      {/* Reject modal — requires reason */}
      <Modal
        open={!!rejectId}
        onClose={() => setRejectId(null)}
        title="Reject leave"
        size="sm"
      >
        {rejectId && (() => {
          const lr = requests?.find((r) => r.id === rejectId)
          return (
            <div className="space-y-4">
              <p className="text-sm text-slate-300/70">
                Reject <strong>{TYPE_LABELS[lr?.leave_type ?? ''] ?? lr?.leave_type}</strong> for{' '}
                <strong>{lr?.employee}</strong>? A reason is required — the employee will be notified.
              </p>
              <div>
                <label className="block text-sm font-medium text-slate-300/70 mb-1.5">
                  Reason for rejection *
                </label>
                <textarea
                  rows={3}
                  value={rejectNotes}
                  onChange={(e) => setRejectNotes(e.target.value)}
                  placeholder="Explain why this leave cannot be approved… (min 10 chars)"
                  autoFocus
                  className="w-full rounded-xl border border-white/10 bg-transparent px-4 py-3 text-sm
                    text-white focus:outline-none focus:border-primary-dark
                    focus:ring-2 focus:ring-primary-dark/20 resize-none"
                />
                {rejectNotes.length > 0 && !rejectNotesValid && (
                  <p className="text-xs text-status-failed mt-1">
                    Must be at least 10 characters ({rejectNotes.trim().length}/10).
                  </p>
                )}
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => setRejectId(null)}
                  className="flex-1 py-3 rounded-xl border border-white/10 text-sm font-medium
                    text-slate-300/70 hover:bg-white/5/40 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={() => rejectMutation.mutate({ id: rejectId, notes: rejectNotes.trim() })}
                  disabled={!rejectNotesValid || rejectMutation.isPending}
                  className="flex-1 py-3 rounded-xl bg-status-failed text-white text-sm font-semibold
                    hover:bg-status-failed/90 disabled:opacity-50 transition-colors"
                >
                  {rejectMutation.isPending ? 'Rejecting…' : 'Reject'}
                </button>
              </div>
            </div>
          )
        })()}
      </Modal>
    </RequireRole>
  )
}
