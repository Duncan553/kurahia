import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { Drawer, Skeleton, EmptyState } from '@shared'
import { RequireRole } from '../components/AuthGate'
import api from '../lib/axios'
import { formatTime, formatDateTime, todayKey } from '../lib/format'

interface AttendanceRow {
  employee_id: string
  employee_name: string | null
  shift_id: string
  shift_start: string
  shift_end: string
  status: string
  late: boolean | null
}

interface ClockEvent {
  id: string
  event_type: string
  occurred_at: string
  shift_id: string | null
  is_manual_override: boolean
}

interface EmployeeDetail {
  employee_id: string
  employee_name: string
  date: string
  hours_worked: string
  events: ClockEvent[]
}

interface SummaryRow {
  employee_id: string
  employee_name: string
  shifts_scheduled: number
  shifts_attended: number
  absent_with_notice: number
  absent_no_notice: number
  hours_worked: string
}

interface AbsenceNotice {
  id: string
  employee_name: string | null
  reason: string | null
  sent_at: string
}

type Tab = 'today' | 'week'

const STATUS_LABELS: Record<string, { label: string; color: string }> = {
  clocked_in:          { label: 'In',             color: 'text-status-paid' },
  approved_leave:      { label: 'On leave',       color: 'text-primary-light' },
  absent_with_notice:  { label: 'Absent (notice)',color: 'text-status-pending' },
  absent_no_notice:    { label: 'Absent',          color: 'text-status-failed' },
}

function StatusChip({ status }: { status: string }) {
  const { label, color } = STATUS_LABELS[status] ?? { label: status, color: 'text-ink-tertiary' }
  return <span className={`text-xs font-semibold ${color}`}>{label}</span>
}

export default function AttendanceScreen() {
  const today = todayKey()

  const [tab,          setTab]          = useState<Tab>('today')
  const [selectedEmp,  setSelectedEmp]  = useState<AttendanceRow | null>(null)

  // Stagger animation variants for lists
  const containerVariants = { hidden: {}, visible: { transition: { staggerChildren: 0.06 } } }
  const itemVariants = { hidden: { opacity: 0, y: 12 }, visible: { opacity: 1, y: 0, transition: { type: 'spring' as const, damping: 25, stiffness: 300 } } }

  const { data: todayRows, isLoading: todayLoading, isError: todayError } = useQuery<AttendanceRow[]>({
    queryKey: ['attendance-today'],
    queryFn: () => api.get<AttendanceRow[]>('/hr/attendance/today').then((r) => r.data),
    staleTime: 2 * 60_000,
    refetchInterval: 5 * 60_000,
  })

  const { data: summary, isLoading: summaryLoading } = useQuery<SummaryRow[]>({
    queryKey: ['attendance-summary', today],
    queryFn: () =>
      api.get<SummaryRow[]>(`/hr/attendance/summary?start_date=${today.slice(0, 8)}01&end_date=${today}`)
        .then((r) => r.data),
    enabled: tab === 'week',
    staleTime: 5 * 60_000,
  })

  const { data: absences } = useQuery<AbsenceNotice[]>({
    queryKey: ['absence-notices', today],
    queryFn: () =>
      api.get<AbsenceNotice[]>(`/hr/absence-notices?date=${today}`).then((r) => r.data),
    staleTime: 2 * 60_000,
  })

  const { data: empDetail } = useQuery<EmployeeDetail>({
    queryKey: ['attendance-employee', selectedEmp?.employee_id, today],
    queryFn: () =>
      api.get<EmployeeDetail>(
        `/hr/attendance/employee/${selectedEmp!.employee_id}?date=${today}`
      ).then((r) => r.data),
    enabled: !!selectedEmp,
    staleTime: 60_000,
  })

  // Group today rows by status
  const groups: Record<string, AttendanceRow[]> = {}
  ;(todayRows ?? []).forEach((r) => {
    ;(groups[r.status] ??= []).push(r)
  })
  const groupOrder = ['clocked_in', 'absent_no_notice', 'absent_with_notice', 'approved_leave']

  return (
    <RequireRole minLevel={5}>
      <motion.div
        className="p-4 max-w-3xl mx-auto space-y-4"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ type: 'spring', damping: 25, stiffness: 300 }}
      >

        <div>
          <h1 className="text-2xl font-bold text-white font-serif">Attendance</h1>
          <p className="text-xs text-ink-tertiary mt-0.5">Today's clock-in roster</p>
        </div>

        {/* Absence notices banner */}
        {(absences ?? []).length > 0 && (
          <div className="rounded-xl bg-status-pending/5 border border-status-pending/20 p-3">
            <p className="text-sm font-medium text-status-pending">
              {absences!.length} absence notice{absences!.length !== 1 ? 's' : ''} today
            </p>
            <div className="mt-1 space-y-0.5">
              {absences!.map((a) => (
                <p key={a.id} className="text-xs text-ink-secondary">
                  {a.employee_name} — {a.reason ?? 'No reason given'} · {formatDateTime(a.sent_at)}
                </p>
              ))}
            </div>
          </div>
        )}

        {/* Tabs */}
        <div className="flex gap-1 bg-white/6 rounded-xl p-1">
          {(['today', 'week'] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={[
                'flex-1 py-2 min-h-[44px] rounded-lg text-xs font-medium capitalize transition-all',
                tab === t ? 'bg-transparent shadow-sm text-white' : 'text-ink-tertiary hover:text-ink-secondary',
              ].join(' ')}
            >
              {t === 'today' ? 'Today' : 'Month summary'}
            </button>
          ))}
        </div>

        {/* Today tab */}
        {tab === 'today' && (
          <>
            {todayLoading && (
              <div className="space-y-3">
                {[1,2,3,4].map((i) => <Skeleton key={i} variant="row" />)}
              </div>
            )}
            {todayError && (
              <div className="p-4 rounded-xl bg-white/5 text-sm text-ink-tertiary text-center">
                Couldn't load attendance. Check connection.
              </div>
            )}
            {!todayLoading && (todayRows ?? []).length === 0 && (
              <EmptyState
                icon={
                  <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
                    <circle cx="24" cy="16" r="8" stroke="currentColor" strokeWidth="2"/>
                    <path d="M8 40c0-8.8 7.2-16 16-16s16 7.2 16 16"
                      stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                  </svg>
                }
                title="No shifts scheduled today."
                description="Create shifts in the Shifts screen."
              />
            )}
            {!todayLoading && groupOrder.map((status) => {
              const rows = groups[status]
              if (!rows?.length) return null
              const { label } = STATUS_LABELS[status] ?? { label: status }
              return (
                <div key={status}>
                  <p className="text-xs font-semibold uppercase tracking-wider text-ink-tertiary mb-2">
                    {label} ({rows.length})
                  </p>
                  <motion.div
                    initial="hidden"
                    animate="visible"
                    variants={containerVariants}
                    className="space-y-2"
                  >
                    {rows.map((row) => (
                      <motion.button
                        key={row.shift_id}
                        variants={itemVariants}
                        whileTap={{ scale: 0.97 }}
                        whileHover={{ y: -2 }}
                        onClick={() => setSelectedEmp(row)}
                        className="w-full flex items-center gap-3 px-4 py-3 rounded-xl glass-card
                          bg-transparent hover:bg-white/5 transition-colors text-left
                          focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark"
                      >
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-semibold text-white">
                              {row.employee_name ?? 'Unknown'}
                            </span>
                            {row.late && (
                              <span className="text-[10px] font-semibold uppercase tracking-wide
                                bg-status-pending/10 text-status-pending rounded-full px-1.5 py-0.5">
                                Late
                              </span>
                            )}
                          </div>
                          <p className="text-xs text-ink-tertiary mt-0.5">
                            {formatTime(row.shift_start)} – {formatTime(row.shift_end)}
                          </p>
                        </div>
                        <StatusChip status={row.status} />
                      </motion.button>
                    ))}
                  </motion.div>
                </div>
              )
            })}
          </>
        )}

        {/* Week / month tab */}
        {tab === 'week' && (
          <>
            {summaryLoading && (
              <div className="space-y-3">
                {[1,2,3].map((i) => <Skeleton key={i} variant="row" />)}
              </div>
            )}
            {!summaryLoading && (summary ?? []).length === 0 && (
              <EmptyState
                icon={
                  <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
                    <rect x="8" y="8" width="32" height="34" rx="3" stroke="currentColor" strokeWidth="2"/>
                    <path d="M16 8V5M32 8V5M8 20h32" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                  </svg>
                }
                title="No attendance data for this month."
              />
            )}
            {!summaryLoading && (summary ?? []).length > 0 && (
              <motion.div
                initial="hidden"
                animate="visible"
                variants={containerVariants}
                className="space-y-4"
              >
                {summary!.map((row) => (
                  <motion.div
                    key={row.employee_id}
                    variants={itemVariants}
                    whileHover={{ y: -2 }}
                    className="rounded-xl glass-card bg-transparent px-4 py-3"
                  >
                    <p className="text-sm font-semibold text-white">{row.employee_name}</p>
                    <div className="grid grid-cols-3 gap-2 mt-2">
                      {[
                        { label: 'Hours', value: parseFloat(row.hours_worked).toFixed(1) },
                        { label: 'Attended', value: `${row.shifts_attended}/${row.shifts_scheduled}` },
                        { label: 'Absences', value: row.absent_no_notice, danger: row.absent_no_notice > 0 },
                      ].map(({ label, value, danger }) => (
                        <div key={label} className="text-center">
                          <p className={`text-lg font-bold tabular-nums ${danger ? 'text-status-failed' : 'text-white'}`}>
                            {value}
                          </p>
                          <p className="text-[10px] text-ink-tertiary">{label}</p>
                        </div>
                      ))}
                    </div>
                  </motion.div>
                ))}
              </motion.div>
            )}
          </>
        )}
      </motion.div>

      {/* Employee detail drawer */}
      <Drawer
        open={!!selectedEmp}
        onClose={() => setSelectedEmp(null)}
        title={selectedEmp?.employee_name ?? 'Employee'}
      >
        {selectedEmp && (
          <div className="space-y-4">
            <div className="rounded-xl bg-white/5 px-4 py-3 text-sm space-y-0.5">
              <p className="text-ink-tertiary">
                Shift: <span className="text-white font-medium">
                  {formatTime(selectedEmp.shift_start)} – {formatTime(selectedEmp.shift_end)}
                </span>
              </p>
              <p className="text-ink-tertiary">
                Status: <StatusChip status={selectedEmp.status} />
              </p>
              {empDetail && (
                <p className="text-ink-tertiary">
                  Hours worked: <span className="text-white font-medium">
                    {parseFloat(empDetail.hours_worked).toFixed(1)}h
                  </span>
                </p>
              )}
            </div>

            {empDetail && empDetail.events.length > 0 ? (
              <div className="space-y-2">
                <p className="text-xs font-semibold uppercase tracking-wider text-ink-tertiary">
                  Clock events today
                </p>
                {empDetail.events.map((ev) => (
                  <div key={ev.id}
                    className="flex items-center justify-between rounded-xl glass-card px-4 py-2.5">
                    <div>
                      <p className="text-sm font-medium text-white capitalize">
                        {ev.event_type.replace('_', ' ').toLowerCase()}
                      </p>
                      {ev.is_manual_override && (
                        <p className="text-[10px] text-status-pending">Manual override</p>
                      )}
                    </div>
                    <span className="text-sm tabular-nums text-ink-tertiary">
                      {formatTime(ev.occurred_at)}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-ink-tertiary text-center py-4">
                No clock events recorded today.
              </p>
            )}
          </div>
        )}
      </Drawer>
    </RequireRole>
  )
}
