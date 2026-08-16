import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { ErrorBoundary, Skeleton } from '@shared'
import api from '../lib/axios'

/* ── Types ──────────────────────────────────────────────────────────────────── */

interface FeedbackSummary {
  count: number
  average_score: string | null
  recent: {
    id: string
    score: number
    guest_name: string
    comments: string | null
    created_at: string
  }[]
}

interface StaffFeedback {
  employee_id: string
  employee_name: string | null
  count: number
  average_score: string | null
  recent_comments: string[]
}

interface EmployeeProfile {
  id: string
  full_name: string
  department: string | null
  is_active: boolean
}

/* ── Helpers ─────────────────────────────────────────────────────────────────── */

// Star display: filled stars + empty stars
function Stars({ score }: { score: number }) {
  return (
    <span className="inline-flex gap-0.5" aria-label={`${score} out of 5 stars`}>
      {[1, 2, 3, 4, 5].map(i => (
        <span key={i} className={`text-sm ${i <= score ? 'text-[#fa5c29]' : 'text-white/15'}`}>
          &#9733;
        </span>
      ))}
    </span>
  )
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-KE', {
    day: 'numeric', month: 'short', year: 'numeric',
  })
}

function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('en-KE', {
    hour: '2-digit', minute: '2-digit',
  })
}

function scoreColor(avg: string | null): string {
  if (!avg) return 'text-ink-tertiary'
  const n = parseFloat(avg)
  if (n >= 4) return 'text-status-paid'
  if (n >= 3) return 'text-status-pending'
  return 'text-status-failed'
}

/* ── Feedback card ───────────────────────────────────────────────────────────── */

function FeedbackCard({ fb }: {
  fb: { id: string; score: number; guest_name: string; comments: string | null; created_at: string }
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card rounded-2xl p-4 border border-white/10"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-ink-primary">{fb.guest_name}</p>
          <p className="text-[10px] text-ink-tertiary mt-0.5">
            {fmtDate(fb.created_at)} at {fmtTime(fb.created_at)}
          </p>
        </div>
        <Stars score={fb.score} />
      </div>
      {fb.comments && (
        <p className="text-xs text-ink-secondary mt-3 leading-relaxed">
          &ldquo;{fb.comments}&rdquo;
        </p>
      )}
    </motion.div>
  )
}

/* ── Staff performance breakdown ─────────────────────────────────────────────── */

function StaffFeedbackSection() {
  const [selectedStaff, setSelectedStaff] = useState<string | null>(null)

  // Fetch all active employees to list them
  const { data: profiles = [], isLoading: profLoading } = useQuery<EmployeeProfile[]>({
    queryKey: ['hr-profiles'],
    queryFn: () => api.get<EmployeeProfile[]>('/hr/profiles').then(r => r.data),
    staleTime: 5 * 60_000,
  })
  const active = useMemo(() => profiles.filter(p => p.is_active), [profiles])

  // Fetch selected staff's feedback
  const { data: staffFb, isLoading: fbLoading } = useQuery<StaffFeedback>({
    queryKey: ['staff-feedback', selectedStaff],
    queryFn: () => api.get<StaffFeedback>(`/feedback/staff/${selectedStaff}`).then(r => r.data),
    enabled: !!selectedStaff,
    staleTime: 60_000,
  })

  return (
    <div className="space-y-4">
      <h2 className="font-serif text-lg font-bold text-ink-primary">By Staff</h2>
      <p className="text-xs text-ink-tertiary">
        Select an employee to see their guest feedback breakdown.
      </p>

      {profLoading ? (
        <div className="flex gap-2 overflow-x-auto pb-2">
          {[1, 2, 3].map(i => <Skeleton key={i} variant="text" className="w-24 h-8 rounded-full shrink-0" />)}
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          {active.map(p => (
            <button
              key={p.id}
              onClick={() => setSelectedStaff(selectedStaff === p.id ? null : p.id)}
              className={`px-3 py-1.5 rounded-full text-xs font-semibold border transition-colors
                ${selectedStaff === p.id
                  ? 'border-[#f9dcd5]/40 bg-white/10 text-ink-primary'
                  : 'border-white/10 text-ink-tertiary hover:text-ink-primary hover:bg-white/5'
                }`}
            >
              {p.full_name}
            </button>
          ))}
        </div>
      )}

      {/* Staff feedback detail */}
      {selectedStaff && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          className="glass-card rounded-2xl p-4 border border-white/10"
        >
          {fbLoading ? (
            <div className="space-y-2">
              <Skeleton variant="text" className="w-32 h-6" />
              <Skeleton variant="text" className="w-48 h-4" />
            </div>
          ) : staffFb ? (
            <>
              <div className="flex items-baseline justify-between mb-3">
                <p className="text-sm font-semibold text-ink-primary">
                  {staffFb.employee_name ?? 'Staff'}
                </p>
                <div className="flex items-baseline gap-1">
                  <span className={`text-2xl font-bold tabular-nums ${scoreColor(staffFb.average_score)}`}>
                    {staffFb.average_score ? parseFloat(staffFb.average_score).toFixed(1) : '--'}
                  </span>
                  <span className="text-xs text-ink-tertiary">/ 5</span>
                </div>
              </div>
              <p className="text-xs text-ink-tertiary mb-3">
                {staffFb.count} total review{staffFb.count !== 1 ? 's' : ''}
              </p>
              {staffFb.recent_comments.length > 0 ? (
                <div className="space-y-2">
                  {staffFb.recent_comments.map((c, i) => (
                    <p key={i} className="text-xs text-ink-secondary leading-relaxed">
                      &ldquo;{c}&rdquo;
                    </p>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-ink-tertiary">No comments for this staff member.</p>
              )}
            </>
          ) : null}
        </motion.div>
      )}
    </div>
  )
}

/* ── Main screen ─────────────────────────────────────────────────────────────── */

export default function FeedbackScreen() {
  const [tab, setTab] = useState<'recent' | 'staff'>('recent')

  // Fetch overall feedback summary from the feedback endpoint
  const { data, isLoading, isError } = useQuery<FeedbackSummary>({
    queryKey: ['feedback-list'],
    queryFn: () => api.get<FeedbackSummary>('/feedback').then(r => r.data),
    staleTime: 30_000,
  })

  const avg = data?.average_score ? parseFloat(data.average_score).toFixed(1) : null

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
            Guest Feedback
          </h1>
          <p className="text-sm text-ink-secondary mt-1">
            Reviews and ratings from guests
          </p>
        </motion.div>

        {/* Summary bar */}
        <ErrorBoundary level="tile">
          {!isLoading && data && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="glass-card rounded-2xl p-5 border border-white/10 mb-6"
            >
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-[10px] font-semibold tracking-widest uppercase text-ink-tertiary mb-1">
                    Overall Rating
                  </p>
                  <div className="flex items-baseline gap-1.5">
                    <span className={`text-4xl font-bold tabular-nums ${scoreColor(data.average_score)}`}>
                      {avg ?? '--'}
                    </span>
                    <span className="text-sm text-ink-tertiary">/ 5</span>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-3xl font-bold tabular-nums text-ink-primary">{data.count}</p>
                  <p className="text-xs text-ink-tertiary">total reviews</p>
                </div>
              </div>
            </motion.div>
          )}

          {/* Tab toggle */}
          <div className="flex rounded-xl overflow-hidden border border-white/10 mb-6 w-fit">
            {(['recent', 'staff'] as const).map(t => (
              <button key={t} onClick={() => setTab(t)}
                className={`px-5 py-2 text-xs font-bold tracking-widest uppercase transition-colors
                  ${tab === t
                    ? 'bg-white/10 text-ink-primary'
                    : 'text-ink-tertiary hover:text-ink-secondary'
                  }`}>
                {t === 'recent' ? 'Recent' : 'By Staff'}
              </button>
            ))}
          </div>

          {/* Recent feedback list */}
          {tab === 'recent' && (
            <>
              {isLoading && (
                <div className="space-y-4">
                  {[1, 2, 3].map(i => (
                    <div key={i} className="h-24 rounded-2xl bg-cream-alt animate-pulse" />
                  ))}
                </div>
              )}

              {isError && (
                <p className="text-sm text-status-failed text-center py-12">
                  Failed to load feedback. Check your connection.
                </p>
              )}

              {!isLoading && !isError && data && data.recent.length === 0 && (
                <div className="flex flex-col items-center justify-center py-20 gap-3">
                  <span className="text-5xl text-ink-tertiary/40">&#9733;</span>
                  <p className="text-ink-tertiary text-lg font-medium">No feedback yet</p>
                  <p className="text-xs text-ink-tertiary">
                    Guest feedback will appear here once submitted.
                  </p>
                </div>
              )}

              {!isLoading && data && data.recent.length > 0 && (
                <div className="space-y-3">
                  {data.recent.map(fb => (
                    <FeedbackCard key={fb.id} fb={fb} />
                  ))}
                </div>
              )}

              {/* Note about response capability */}
              <div className="mt-6 glass-card rounded-xl p-4 border border-white/10">
                <p className="text-xs text-ink-tertiary">
                  Guest response feature is not yet available. Guest feedback is recorded at
                  the front desk and feeds into staff performance scores automatically.
                </p>
              </div>
            </>
          )}

          {/* Staff breakdown tab */}
          {tab === 'staff' && <StaffFeedbackSection />}
        </ErrorBoundary>
      </div>
    </div>
  )
}
