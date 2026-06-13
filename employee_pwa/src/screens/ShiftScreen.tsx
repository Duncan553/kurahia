import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Drawer, Modal, Skeleton, EmptyState, useToastStore } from '@shared'
import { RequireRole } from '../components/AuthGate'
import api from '../lib/axios'
import { formatTime, formatDayLabel, todayKey, toDateKey } from '../lib/format'

interface Shift {
  id: string
  employee_id: string
  employee_name: string | null
  start: string
  end: string
  role: string | null
  status: string
}

interface Profile {
  id: string
  full_name: string
}

type Tab = 'today' | 'upcoming'

function genKey() { return crypto.randomUUID() }

function localNow() {
  const now = new Date()
  return new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 16)
}

// Converts a datetime-local string (no tz) to UTC ISO string
function toUtcISO(localDT: string) {
  return new Date(localDT).toISOString()
}

function StatusDot({ status }: { status: string }) {
  const isCancelled = status === 'CANCELLED'
  return (
    <>
      <span aria-hidden="true" className={`inline-block w-2 h-2 rounded-full mr-1 ${isCancelled ? 'bg-status-failed/60' : 'bg-status-paid'}`} />
      <span className="mr-1.5">{isCancelled ? 'Cancelled' : 'Scheduled'}</span>
    </>
  )
}

export default function ShiftScreen() {
  const addToast    = useToastStore((s) => s.addToast)
  const queryClient = useQueryClient()
  const today       = todayKey()

  const [tab,         setTab]         = useState<Tab>('today')
  const [drawerOpen,  setDrawerOpen]  = useState(false)
  const [cancelId,    setCancelId]    = useState<string | null>(null)

  // Create form state
  const [empId,    setEmpId]    = useState('')
  const [startDT,  setStartDT]  = useState(() => localNow())
  const [endDT,    setEndDT]    = useState(() => {
    const d = new Date()
    d.setHours(d.getHours() + 8)
    return new Date(d.getTime() - d.getTimezoneOffset() * 60_000).toISOString().slice(0, 16)
  })
  const [role,     setRole]     = useState('')
  const [idemKey,  setIdemKey]  = useState(genKey)

  const { data: shifts, isLoading, isError } = useQuery<Shift[]>({
    queryKey: ['shifts'],
    queryFn: () => api.get<Shift[]>('/hr/shifts').then((r) => r.data),
    staleTime: 60_000,
  })

  const { data: profiles } = useQuery<Profile[]>({
    queryKey: ['hr-profiles'],
    queryFn: () => api.get<Profile[]>('/hr/profiles').then((r) => r.data),
    staleTime: 5 * 60_000,
  })

  // Split shifts into today vs future
  const todayShifts    = (shifts ?? []).filter((s) => toDateKey(s.start) === today)
  const upcomingShifts = (shifts ?? []).filter((s) => toDateKey(s.start) > today)

  // Group upcoming by day label
  const byDay = upcomingShifts.reduce<Record<string, Shift[]>>((acc, s) => {
    const key = toDateKey(s.start)
    ;(acc[key] ??= []).push(s)
    return acc
  }, {})

  const createMutation = useMutation({
    mutationFn: () =>
      api.post<{ id: string }>('/hr/shifts', {
        employee_id:          empId,
        scheduled_start_utc:  toUtcISO(startDT),
        scheduled_end_utc:    toUtcISO(endDT),
        role_on_shift:        role.trim() || undefined,
        idempotency_key:      idemKey,
      }).then((r) => r.data),
    onSuccess: () => {
      addToast({ type: 'success', message: 'Shift created.' })
      queryClient.invalidateQueries({ queryKey: ['shifts'] })
      setDrawerOpen(false)
      setIdemKey(genKey())
      setRole('')
      setEmpId('')
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
        ?? 'Failed to create shift.'
      addToast({ type: 'error', message: msg })
    },
  })

  const cancelMutation = useMutation({
    mutationFn: (id: string) =>
      api.post(`/hr/shifts/${id}/cancel`).then((r) => r.data),
    onSuccess: () => {
      addToast({ type: 'warning', message: 'Shift cancelled.' })
      queryClient.invalidateQueries({ queryKey: ['shifts'] })
      setCancelId(null)
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
        ?? 'Cancellation failed.'
      addToast({ type: 'error', message: msg })
    },
  })

  const createValid = !!empId && !!startDT && !!endDT && new Date(endDT) > new Date(startDT)

  function ShiftCard({ shift }: { shift: Shift }) {
    const cancelled = shift.status === 'CANCELLED'
    return (
      <div className={[
        'rounded-xl border px-4 py-3 flex items-center gap-3',
        cancelled ? 'border-cream-alt bg-cream-alt/20 opacity-70' : 'border-cream-alt bg-cream-card',
      ].join(' ')}>
        <div className="flex-1 min-w-0">
          <p className={`text-sm font-semibold text-ink-primary ${cancelled ? 'line-through' : ''}`}>
            {shift.employee_name ?? 'Unknown'}
          </p>
          <p className="text-xs text-ink-tertiary mt-0.5 flex items-center">
            <StatusDot status={shift.status} />
            {formatTime(shift.start)} – {formatTime(shift.end)}
            {shift.role ? ` · ${shift.role}` : ''}
          </p>
        </div>
        {!cancelled && (
          <button
            onClick={() => setCancelId(shift.id)}
            className="shrink-0 min-h-[44px] text-xs text-status-failed hover:text-status-failed/80
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-status-failed
              px-3 flex items-center rounded-lg transition-colors"
          >
            Cancel
          </button>
        )}
      </div>
    )
  }

  return (
    <RequireRole minLevel={5}>
      <div className="p-4 max-w-lg mx-auto space-y-4">

        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-ink-primary">Shifts</h1>
            <p className="text-sm text-ink-tertiary">Schedule and manage the roster</p>
          </div>
          <button
            onClick={() => setDrawerOpen(true)}
            className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-primary-dark text-cream-card
              text-sm font-semibold hover:bg-primary-dark/90 transition-colors
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M7 2v10M2 7h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
            Add
          </button>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 bg-cream-alt/50 rounded-xl p-1">
          {(['today', 'upcoming'] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={[
                'flex-1 py-2 min-h-[44px] rounded-lg text-xs font-medium capitalize transition-all',
                tab === t ? 'bg-cream-card shadow-sm text-ink-primary' : 'text-ink-tertiary hover:text-ink-secondary',
              ].join(' ')}
            >
              {t === 'today' ? `Today (${todayShifts.length})` : `Upcoming (${upcomingShifts.length})`}
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
            Couldn't load shifts. Check connection.
          </div>
        )}

        {/* Today tab */}
        {tab === 'today' && !isLoading && (
          <>
            {todayShifts.length === 0 ? (
              <EmptyState
                icon={
                  <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
                    <rect x="8" y="8" width="32" height="34" rx="3" stroke="currentColor" strokeWidth="2"/>
                    <path d="M16 8V5M32 8V5M8 20h32" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                    <path d="M18 30h12M18 25h8" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                  </svg>
                }
                title="No shifts scheduled today."
                description="Tap + Add to create one."
              />
            ) : (
              <div className="space-y-2">
                {todayShifts.map((s) => <ShiftCard key={s.id} shift={s} />)}
              </div>
            )}
          </>
        )}

        {/* Upcoming tab */}
        {tab === 'upcoming' && !isLoading && (
          <>
            {upcomingShifts.length === 0 ? (
              <EmptyState
                icon={
                  <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
                    <rect x="8" y="8" width="32" height="34" rx="3" stroke="currentColor" strokeWidth="2"/>
                    <path d="M16 8V5M32 8V5M8 20h32" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                    <path d="M18 30h12M18 25h8" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                  </svg>
                }
                title="No upcoming shifts."
                description="Schedule shifts with the + Add button."
              />
            ) : (
              <div className="space-y-4">
                {Object.entries(byDay).sort(([a], [b]) => a.localeCompare(b)).map(([dateKey, dayShifts]) => (
                  <div key={dateKey}>
                    <p className="text-xs font-semibold text-ink-tertiary uppercase tracking-wider mb-2">
                      {formatDayLabel(dayShifts[0].start)}
                    </p>
                    <div className="space-y-2">
                      {dayShifts.map((s) => <ShiftCard key={s.id} shift={s} />)}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>

      {/* Create shift drawer */}
      <Drawer open={drawerOpen} onClose={() => setDrawerOpen(false)} title="Add Shift">
        <form
          onSubmit={(e) => { e.preventDefault(); if (createValid) createMutation.mutate() }}
          className="space-y-4"
        >
          <div>
            <label className="block text-sm font-medium text-ink-secondary mb-1.5">
              Employee *
            </label>
            <select
              value={empId}
              onChange={(e) => setEmpId(e.target.value)}
              className="w-full rounded-xl border border-cream-alt bg-cream-card px-4 py-3 text-sm
                text-ink-primary focus:outline-none focus:border-primary-dark focus:ring-2 focus:ring-primary-dark/20"
            >
              <option value="">Choose employee…</option>
              {(profiles ?? []).map((p) => (
                <option key={p.id} value={p.id}>{p.full_name}</option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-ink-secondary mb-1.5">Start *</label>
              <input
                type="datetime-local"
                value={startDT}
                onChange={(e) => setStartDT(e.target.value)}
                className="w-full rounded-xl border border-cream-alt bg-cream-card px-3 py-2.5 text-sm
                  text-ink-primary focus:outline-none focus:border-primary-dark focus:ring-2 focus:ring-primary-dark/20"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink-secondary mb-1.5">End *</label>
              <input
                type="datetime-local"
                value={endDT}
                onChange={(e) => setEndDT(e.target.value)}
                className="w-full rounded-xl border border-cream-alt bg-cream-card px-3 py-2.5 text-sm
                  text-ink-primary focus:outline-none focus:border-primary-dark focus:ring-2 focus:ring-primary-dark/20"
              />
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-ink-secondary mb-1.5">
              Role / position (optional)
            </label>
            <input
              type="text"
              value={role}
              onChange={(e) => setRole(e.target.value)}
              placeholder="e.g. Front gate, Kitchen…"
              className="w-full rounded-xl border border-cream-alt bg-cream-card px-4 py-3 text-sm
                text-ink-primary focus:outline-none focus:border-primary-dark focus:ring-2 focus:ring-primary-dark/20"
            />
          </div>

          <button
            type="submit"
            disabled={!createValid || createMutation.isPending}
            className={[
              'w-full py-4 rounded-2xl text-base font-semibold transition-all',
              'bg-primary-dark text-cream-card hover:bg-primary-dark/90 active:scale-[0.99]',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark focus-visible:ring-offset-2',
              'disabled:opacity-50 disabled:cursor-not-allowed',
            ].join(' ')}
          >
            {createMutation.isPending ? 'Creating…' : 'Create Shift'}
          </button>
        </form>
      </Drawer>

      {/* Cancel confirmation modal */}
      <Modal
        open={!!cancelId}
        onClose={() => setCancelId(null)}
        title="Cancel shift?"
        size="sm"
      >
        <div className="space-y-4">
          <p className="text-sm text-ink-secondary">
            This will cancel the shift permanently. The employee will not receive an automatic notification — notify them manually.
          </p>
          <div className="flex gap-2">
            <button
              onClick={() => setCancelId(null)}
              className="flex-1 py-3 rounded-xl border border-cream-alt text-sm font-medium
                text-ink-secondary hover:bg-cream-alt/40 transition-colors"
            >
              Keep shift
            </button>
            <button
              onClick={() => cancelId && cancelMutation.mutate(cancelId)}
              disabled={cancelMutation.isPending}
              className="flex-1 py-3 rounded-xl bg-status-failed text-cream-card text-sm font-semibold
                hover:bg-status-failed/90 disabled:opacity-50 transition-colors"
            >
              {cancelMutation.isPending ? 'Cancelling…' : 'Cancel shift'}
            </button>
          </div>
        </div>
      </Modal>
    </RequireRole>
  )
}
