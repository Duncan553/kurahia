import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { Skeleton, EmptyState, Button, useToastStore, ErrorBoundary } from '@shared'
import { useAuthStore } from '../stores/authStore'
import api from '../lib/axios'

// ── Types ──────────────────────────────────────────────────────────────────

interface CleaningRecord {
  id: string | null
  resource_id: string
  resource_name: string | null
  status: string | null          // DIRTY | CLEANING | CLEAN | INSPECTED
  assigned_to_id: string | null
  assigned_to: string | null
  assigned_at: string | null
  completed_at: string | null
  inspected_by_id: string | null
  inspected_by: string | null
  inspected_at: string | null
  notes: string | null
  is_flagged: boolean
  flag_reason: string | null
  created_at: string | null
  updated_at: string | null
}

interface StaffUser {
  id: string
  username: string
}

// ── Status badge colours ───────────────────────────────────────────────────

const STATUS_STYLES: Record<string, { bg: string; text: string; label: string }> = {
  DIRTY:     { bg: 'bg-red-500/20',     text: 'text-red-400',     label: 'Dirty'     },
  CLEANING:  { bg: 'bg-amber-500/20',   text: 'text-amber-400',   label: 'Cleaning'  },
  CLEAN:     { bg: 'bg-emerald-500/20', text: 'text-emerald-400', label: 'Clean'     },
  INSPECTED: { bg: 'bg-blue-500/20',    text: 'text-blue-400',    label: 'Inspected' },
}

// ── Helpers ────────────────────────────────────────────────────────────────

const extractErr = (e: unknown) =>
  (e as { response?: { data?: { error?: string } } })?.response?.data?.error ?? 'Something went wrong.'

/** How long ago a date was, in a human-readable string */
function timeAgo(iso: string | null): string {
  if (!iso) return ''
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.floor(diff / 60_000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return `${days}d ago`
}

const fadeIn = { hidden: { opacity: 0, y: 12 }, visible: { opacity: 1, y: 0 } }
const stagger = { visible: { transition: { staggerChildren: 0.06 } } }

// ── Screen ─────────────────────────────────────────────────────────────────

export default function HousekeepingScreen() {
  const qc = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  const user = useAuthStore(s => s.user)
  const roleLevel = user?.role_level ?? 0
  const isManager = roleLevel >= 5

  // Track which card is expanded (for action panel)
  const [expanded, setExpanded] = useState<string | null>(null)
  // Assign dropdown state
  const [assignTarget, setAssignTarget] = useState<string>('')
  // Flag reason input
  const [flagReason, setFlagReason] = useState('')

  // ── Data fetching ──────────────────────────────────────────────────────

  const { data: records = [], isLoading } = useQuery<CleaningRecord[]>({
    queryKey: ['housekeeping', 'status'],
    queryFn: () => api.get<CleaningRecord[]>('/housekeeping/status').then(r => r.data),
    staleTime: 15_000,
    refetchOnWindowFocus: true,
    refetchInterval: 60_000,
  })

  // Fetch staff list for assignment dropdown (manager only).
  // Was hitting '/users' (404, no such route — real prefix is '/auth/users')
  // so this dropdown has always rendered empty for every manager, silently.
  const { data: staff = [] } = useQuery<StaffUser[]>({
    queryKey: ['housekeeping', 'staff'],
    queryFn: () => api.get<StaffUser[]>('/auth/users').then(r => r.data),
    enabled: isManager,
    staleTime: 120_000,
  })

  // ── Mutations ──────────────────────────────────────────────────────────

  const assignMut = useMutation({
    mutationFn: ({ cleaningId, keeperId }: { cleaningId: string; keeperId: string }) =>
      api.post('/housekeeping/assign', { cleaning_id: cleaningId, housekeeper_id: keeperId }),
    onSuccess: () => {
      addToast({ type: 'success', message: 'Housekeeper assigned.' })
      qc.invalidateQueries({ queryKey: ['housekeeping'] })
      setAssignTarget('')
    },
    onError: (e) => addToast({ type: 'error', message: extractErr(e) }),
  })

  const startMut = useMutation({
    mutationFn: (id: string) => api.post(`/housekeeping/${id}/start`),
    onSuccess: () => {
      addToast({ type: 'success', message: 'Cleaning started.' })
      qc.invalidateQueries({ queryKey: ['housekeeping'] })
    },
    onError: (e) => addToast({ type: 'error', message: extractErr(e) }),
  })

  const completeMut = useMutation({
    mutationFn: (id: string) => api.post(`/housekeeping/${id}/complete`),
    onSuccess: () => {
      addToast({ type: 'success', message: 'Cleaning complete.' })
      qc.invalidateQueries({ queryKey: ['housekeeping'] })
    },
    onError: (e) => addToast({ type: 'error', message: extractErr(e) }),
  })

  const inspectMut = useMutation({
    mutationFn: (id: string) => api.post(`/housekeeping/${id}/inspect`),
    onSuccess: () => {
      addToast({ type: 'success', message: 'Room inspected and approved.' })
      qc.invalidateQueries({ queryKey: ['housekeeping'] })
    },
    onError: (e) => addToast({ type: 'error', message: extractErr(e) }),
  })

  const flagMut = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      api.post(`/housekeeping/${id}/flag`, { reason }),
    onSuccess: () => {
      addToast({ type: 'success', message: 'Issue flagged.' })
      qc.invalidateQueries({ queryKey: ['housekeeping'] })
      setFlagReason('')
    },
    onError: (e) => addToast({ type: 'error', message: extractErr(e) }),
  })

  // ── Render helpers ─────────────────────────────────────────────────────

  function toggleCard(id: string | null) {
    setExpanded(prev => prev === id ? null : id)
    setFlagReason('')
    setAssignTarget('')
  }

  /** What actions can the current user take on this record? */
  function renderActions(rec: CleaningRecord) {
    if (!rec.id) return null // no cleaning record yet
    const isAssignedToMe = rec.assigned_to_id === user?.id

    return (
      <motion.div
        initial={{ height: 0, opacity: 0 }}
        animate={{ height: 'auto', opacity: 1 }}
        exit={{ height: 0, opacity: 0 }}
        transition={{ duration: 0.2 }}
        className="overflow-hidden border-t border-white/10"
      >
        <div className="p-4 space-y-3">

          {/* Manager: assign housekeeper (when DIRTY and unassigned or reassign) */}
          {isManager && rec.status === 'DIRTY' && (
            <div className="space-y-2">
              <label className="text-[10px] text-amber-200/40 uppercase tracking-wider">
                Assign Housekeeper
              </label>
              <select
                style={{ colorScheme: 'dark' }}
                value={assignTarget}
                onChange={e => setAssignTarget(e.target.value)}
                className="w-full rounded-lg glass-card bg-transparent px-3 py-2
                  text-xs text-ink-primary focus:outline-none focus:border-primary-main"
              >
                <option value="">Select staff...</option>
                {staff.map(s => (
                  <option key={s.id} value={s.id}>{s.username}</option>
                ))}
              </select>
              <Button
                variant="primary" size="sm" className="w-full"
                loading={assignMut.isPending}
                disabled={!assignTarget}
                onClick={() => assignMut.mutate({ cleaningId: rec.id!, keeperId: assignTarget })}
              >
                Assign
              </Button>
            </div>
          )}

          {/* Housekeeper: start cleaning (DIRTY → CLEANING) */}
          {rec.status === 'DIRTY' && (isAssignedToMe || isManager) && rec.assigned_to_id && (
            <Button
              variant="primary" size="sm" className="w-full"
              loading={startMut.isPending}
              onClick={() => startMut.mutate(rec.id!)}
            >
              Start Cleaning
            </Button>
          )}

          {/* Housekeeper: mark complete (CLEANING → CLEAN) */}
          {rec.status === 'CLEANING' && (isAssignedToMe || isManager) && (
            <Button
              variant="primary" size="sm" className="w-full"
              loading={completeMut.isPending}
              onClick={() => completeMut.mutate(rec.id!)}
            >
              Mark Complete
            </Button>
          )}

          {/* Manager: inspect (CLEAN → INSPECTED) */}
          {isManager && rec.status === 'CLEAN' && (
            <Button
              variant="primary" size="sm" className="w-full"
              loading={inspectMut.isPending}
              onClick={() => inspectMut.mutate(rec.id!)}
            >
              Inspect &amp; Approve
            </Button>
          )}

          {/* Flag issue — any authorized user */}
          <div className="space-y-2">
            <label className="text-[10px] text-amber-200/40 uppercase tracking-wider">
              Flag Issue
            </label>
            <input
              placeholder="Describe the issue..."
              value={flagReason}
              onChange={e => setFlagReason(e.target.value)}
              className="w-full rounded-lg glass-card bg-transparent px-3 py-2
                text-xs text-ink-primary placeholder:text-ink-tertiary focus:outline-none focus:border-primary-main"
            />
            <Button
              variant="secondary" size="sm" className="w-full"
              loading={flagMut.isPending}
              disabled={!flagReason.trim()}
              onClick={() => flagMut.mutate({ id: rec.id!, reason: flagReason.trim() })}
            >
              Flag Issue
            </Button>
          </div>

          {/* Notes / flag info */}
          {rec.notes && (
            <p className="text-[10px] text-amber-200/50 italic">Note: {rec.notes}</p>
          )}
          {rec.is_flagged && rec.flag_reason && (
            <p className="text-[10px] text-red-400 italic">Flagged: {rec.flag_reason}</p>
          )}
        </div>
      </motion.div>
    )
  }

  // ── Main render ────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen p-4 md:p-6">
      <ErrorBoundary level="tile">
      <motion.div className="max-w-4xl mx-auto space-y-6"
        initial="hidden" animate="visible" variants={stagger}>

        <motion.div variants={fadeIn} transition={{ duration: 0.3, ease: 'easeOut' }}>
          <h1 className="text-2xl font-bold font-serif text-ink-primary">Housekeeping</h1>
          <p className="text-xs text-amber-200/40 mt-0.5">Villa cleaning status &amp; assignments</p>
          <p className="text-[10px] text-ink-tertiary mt-0.5">Track which villas need cleaning, who's cleaning them, and inspection status</p>
        </motion.div>

        {/* Loading skeleton */}
        {isLoading && (
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            {[1, 2, 3, 4, 5, 6].map(i => <Skeleton key={i} variant="row" className="h-44" />)}
          </div>
        )}

        {/* Empty state */}
        {!isLoading && records.length === 0 && (
          <motion.div variants={fadeIn} transition={{ duration: 0.35, ease: 'easeOut' }}>
            <EmptyState
              icon={
                <svg width="40" height="40" viewBox="0 0 40 40" fill="none" aria-hidden="true">
                  <path d="M6 20L20 8l14 12v16a2 2 0 01-2 2H8a2 2 0 01-2-2V20z"
                    stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  <path d="M20 18v8M16 22h8" stroke="currentColor" strokeWidth="1.5"
                    strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              }
              title="No rooms to display."
              description="Cleaning records appear here after guest checkouts."
            />
          </motion.div>
        )}

        {/* Villa grid */}
        {!isLoading && records.length > 0 && (
          <motion.div variants={fadeIn} transition={{ duration: 0.35, ease: 'easeOut' }}
            className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {records.map(rec => {
              const st = rec.status ? STATUS_STYLES[rec.status] : null
              const cardKey = rec.id ?? rec.resource_id
              const isOpen = expanded === cardKey

              return (
                <div key={cardKey}
                  className="glass-card rounded-2xl overflow-hidden transition-shadow hover:shadow-lg">

                  {/* Card body — tap to expand */}
                  <button
                    onClick={() => rec.id ? toggleCard(cardKey) : undefined}
                    className="w-full text-left p-4 space-y-3 focus-visible:outline-none
                      focus-visible:ring-2 focus-visible:ring-primary-main rounded-t-2xl"
                    disabled={!rec.id}
                  >
                    {/* Top row: name + badge */}
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="font-semibold text-ink-primary text-sm truncate">
                          {rec.resource_name ?? 'Unknown Room'}
                        </p>
                        {rec.assigned_to && (
                          <p className="text-[10px] text-amber-200/50 mt-0.5 truncate">
                            {rec.assigned_to}
                          </p>
                        )}
                      </div>

                      {st ? (
                        <span className={`shrink-0 text-[10px] font-bold uppercase tracking-wider
                          px-2.5 py-1 rounded-full ${st.bg} ${st.text}`}>
                          {st.label}
                        </span>
                      ) : (
                        <span className="shrink-0 text-[10px] font-bold uppercase tracking-wider
                          px-2.5 py-1 rounded-full bg-white/10 text-white/40">
                          No status
                        </span>
                      )}
                    </div>

                    {/* Meta row */}
                    <div className="flex items-center justify-between text-[10px] text-amber-200/40">
                      {rec.created_at ? (
                        <span>Since checkout {timeAgo(rec.created_at)}</span>
                      ) : (
                        <span>No checkout recorded</span>
                      )}
                      {rec.is_flagged && (
                        <span className="text-red-400 font-semibold uppercase tracking-wider">
                          Flagged
                        </span>
                      )}
                    </div>

                    {/* Completed / inspected info */}
                    {rec.completed_at && (
                      <p className="text-[10px] text-emerald-400/60">
                        Cleaned {timeAgo(rec.completed_at)}
                      </p>
                    )}
                    {rec.inspected_at && rec.inspected_by && (
                      <p className="text-[10px] text-blue-400/60">
                        Inspected by {rec.inspected_by} {timeAgo(rec.inspected_at)}
                      </p>
                    )}
                  </button>

                  {/* Expandable action panel */}
                  <AnimatePresence>
                    {isOpen && renderActions(rec)}
                  </AnimatePresence>
                </div>
              )
            })}
          </motion.div>
        )}

      </motion.div>
      </ErrorBoundary>
    </div>
  )
}
