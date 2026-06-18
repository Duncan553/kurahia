import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { StatusBadge, Skeleton, EmptyState, useToastStore } from '@shared'
import type { StatusValue } from '@shared'
import api from '../lib/axios'
import { todayKey } from '../lib/format'

type LeaveType = 'SICK' | 'ANNUAL' | 'EMERGENCY' | 'UNPAID'

interface LeaveRequest {
  id: string
  leave_type: string
  start_date: string
  end_date: string
  reason: string | null
  status: string
  created_at: string
}

function statusVal(s: string): StatusValue {
  const map: Record<string, StatusValue> = {
    PENDING: 'pending', APPROVED: 'paid', REJECTED: 'cancelled', CANCELLED: 'inactive',
  }
  return map[s] ?? 'pending'
}

function genKey() { return crypto.randomUUID() }

const LEAVE_TYPES: { value: LeaveType; label: string }[] = [
  { value: 'ANNUAL',    label: 'Annual Leave' },
  { value: 'SICK',      label: 'Sick Leave' },
  { value: 'EMERGENCY', label: 'Emergency Leave' },
  { value: 'UNPAID',    label: 'Unpaid Leave' },
]

export default function LeaveRequestScreen() {
  const queryClient = useQueryClient()
  const addToast = useToastStore((s) => s.addToast)
  const today = todayKey()

  const [leaveType, setLeaveType] = useState<LeaveType>('ANNUAL')
  const [startDate, setStartDate] = useState(today)
  const [endDate,   setEndDate]   = useState(today)
  const [reason,    setReason]    = useState('')
  const [idemKey,   setIdemKey]   = useState(genKey)
  const [touched,   setTouched]   = useState(false)

  const dateErr = touched && endDate < startDate ? 'End date must be after start date.' : ''
  const isValid = !!startDate && !!endDate && endDate >= startDate

  const { data: history, isLoading } = useQuery<LeaveRequest[]>({
    queryKey: ['leave-requests'],
    queryFn: () => api.get<LeaveRequest[]>('/hr/leave-requests').then((r) => r.data),
  })

  const mutation = useMutation({
    mutationFn: () =>
      api.post('/hr/leave-requests', {
        leave_type:      leaveType,
        start_date:      startDate,
        end_date:        endDate,
        reason:          reason.trim() || undefined,
        idempotency_key: idemKey,
      }).then((r) => r.data),
    onSuccess: () => {
      addToast({ type: 'success', message: 'Leave request submitted.' })
      setStartDate(today)
      setEndDate(today)
      setReason('')
      setTouched(false)
      setIdemKey(genKey())
      queryClient.invalidateQueries({ queryKey: ['leave-requests'] })
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
        ?? 'Could not submit leave request. Try again.'
      addToast({ type: 'error', message: msg })
    },
  })

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setTouched(true)
    if (!isValid) return
    mutation.mutate()
  }

  return (
    <motion.div
      className="p-4 max-w-3xl mx-auto space-y-6"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease: 'easeOut' }}
    >

      <div>
        <h1 className="text-xl font-bold text-white">Leave Request</h1>
        <p className="text-sm text-slate-400/50">Submit a leave request — your manager will approve or reject it</p>
      </div>

      {/* ── Form ─────────────────────────────────────────────────────── */}
      <form onSubmit={handleSubmit} noValidate className="space-y-4">

        {/* Leave type */}
        <div>
          <label className="block text-sm font-medium text-slate-300/70 mb-1.5">Leave type *</label>
          <div className="grid grid-cols-2 gap-2">
            {LEAVE_TYPES.map((lt) => (
              <button
                key={lt.value}
                type="button"
                onClick={() => setLeaveType(lt.value)}
                className={[
                  'py-2.5 min-h-[44px] px-3 rounded-xl border text-sm font-medium transition-all text-left',
                  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark',
                  leaveType === lt.value
                    ? 'border-primary-dark bg-primary-dark/10 text-primary-dark'
                    : 'border-white/10 bg-transparent text-slate-300/70 hover:border-primary-main',
                ].join(' ')}
              >
                {lt.label}
              </button>
            ))}
          </div>
        </div>

        {/* Dates */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-slate-400/50 mb-1">Start date *</label>
            <input
              type="date"
              value={startDate}
              min={today}
              onChange={(e) => setStartDate(e.target.value)}
              className="w-full rounded-xl border border-white/10 bg-transparent px-3 py-2.5
                text-sm text-white focus:outline-none focus:border-primary-dark
                focus:ring-2 focus:ring-primary-dark/20"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-400/50 mb-1">End date *</label>
            <input
              type="date"
              value={endDate}
              min={startDate}
              onChange={(e) => { setEndDate(e.target.value); setTouched(true) }}
              className="w-full rounded-xl border border-white/10 bg-transparent px-3 py-2.5
                text-sm text-white focus:outline-none focus:border-primary-dark
                focus:ring-2 focus:ring-primary-dark/20"
            />
          </div>
        </div>
        {dateErr && <p className="text-sm text-status-failed -mt-2">{dateErr}</p>}

        {/* Reason */}
        <div>
          <label className="block text-sm font-medium text-slate-300/70 mb-1.5">
            Reason <span className="font-normal text-slate-400/50">(optional)</span>
          </label>
          <textarea
            rows={3}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="e.g. Family event, medical appointment…"
            className="w-full rounded-xl border border-white/10 bg-transparent px-4 py-3
              text-sm text-white focus:outline-none focus:border-primary-dark
              focus:ring-2 focus:ring-primary-dark/20 resize-none"
          />
        </div>

        <button
          type="submit"
          disabled={mutation.isPending}
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
              Submitting…
            </span>
          ) : 'Submit Request'}
        </button>
      </form>

      {/* ── History ──────────────────────────────────────────────────── */}
      <div>
        <p className="text-xs font-semibold uppercase tracking-widest text-slate-400/50 mb-3">
          My requests
        </p>

        {isLoading && (
          <div className="space-y-2">
            {[1,2,3].map((i) => <Skeleton key={i} variant="row" />)}
          </div>
        )}

        {!isLoading && history?.length === 0 && (
          <EmptyState
            icon={
              <svg width="40" height="40" viewBox="0 0 40 40" fill="none" aria-hidden="true">
                <rect x="6" y="4" width="28" height="33" rx="3" stroke="currentColor" strokeWidth="1.5"/>
                <path d="M13 13h14M13 20h10M13 27h8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
              </svg>
            }
            title="No leave requests yet."
            description="Submit one above — your manager will review it."
          />
        )}

        {history && history.length > 0 && (
          <motion.div
            className="space-y-2"
            initial="hidden"
            animate="visible"
            variants={{ visible: { transition: { staggerChildren: 0.06 } } }}
          >
            {history.map((r) => (
              <motion.div
                key={r.id}
                variants={{ hidden: { opacity: 0, y: 8 }, visible: { opacity: 1, y: 0 } }}
                transition={{ duration: 0.22, ease: 'easeOut' }}
                className="flex items-start justify-between gap-3 rounded-xl
                  bg-white/5/30 border border-white/10 px-4 py-3"
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium text-white capitalize">
                    {r.leave_type.charAt(0) + r.leave_type.slice(1).toLowerCase()} Leave
                  </p>
                  <p className="text-xs text-slate-400/50 tabular-nums mt-0.5">
                    {r.start_date} → {r.end_date}
                  </p>
                  {r.reason && (
                    <p className="text-xs text-slate-400/50 mt-0.5 truncate">{r.reason}</p>
                  )}
                </div>
                <StatusBadge status={statusVal(r.status)} size="sm" />
              </motion.div>
            ))}
          </motion.div>
        )}
      </div>
    </motion.div>
  )
}
