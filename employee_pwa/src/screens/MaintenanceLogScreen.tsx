import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Drawer, EmptyState, useToastStore } from '@shared'
import { RequireRole } from '../components/AuthGate'
import api from '../lib/axios'

const WATER_TYPES = new Set(['jetski', 'motorboat', 'paddle_boat', 'bicycle'])

interface Equipment {
  id: string
  name: string
  equipment_type: string
  status: string
  last_service_utc: string | null
  service_interval_days: number | null
  is_due_service: boolean
  notes: string | null
  is_active: boolean
}

type Filter = 'all' | 'water' | 'other'

const FILTERS: { key: Filter; label: string }[] = [
  { key: 'all',   label: 'All' },
  { key: 'water', label: 'Water Activities' },
  { key: 'other', label: 'Other' },
]

function formatDateNairobi(iso: string | null): string {
  if (!iso) return 'Never'
  return new Date(iso).toLocaleDateString('en-KE', {
    year: 'numeric', month: 'short', day: 'numeric',
    timeZone: 'Africa/Nairobi',
  })
}

// Returns YYYY-MM-DDTHH:mm in the device's local timezone — suitable for datetime-local input
function localNow(): string {
  const now = new Date()
  const offset = now.getTimezoneOffset() * 60_000
  return new Date(now.getTime() - offset).toISOString().slice(0, 16)
}

export default function MaintenanceLogScreen() {
  const addToast = useToastStore((s) => s.addToast)
  const queryClient = useQueryClient()

  const [filter,      setFilter]      = useState<Filter>('all')
  const [selectedEq,  setSelectedEq]  = useState<Equipment | null>(null)
  const [performedAt, setPerformedAt] = useState('')
  const [notes,       setNotes]       = useState('')
  const [cost,        setCost]        = useState('')
  const [touched,     setTouched]     = useState(false)
  const [submitting,  setSubmitting]  = useState(false)

  const { data: equipment, isLoading, isError } = useQuery<Equipment[]>({
    queryKey: ['equipment-list'],
    queryFn: () => api.get<Equipment[]>('/equipment').then((r) => r.data),
    staleTime: 5 * 60_000,
  })

  const notesErr = touched && notes.trim().length < 5
    ? 'Notes must be at least 5 characters.'
    : ''

  function openDrawer(eq: Equipment) {
    setSelectedEq(eq)
    setPerformedAt(localNow())
    setNotes('')
    setCost('')
    setTouched(false)
  }

  function closeDrawer() { setSelectedEq(null) }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setTouched(true)
    if (notes.trim().length < 5) return
    setSubmitting(true)

    try {
      await api.post(`/equipment/${selectedEq!.id}/maintenance`, {
        performed_at_utc: new Date(performedAt).toISOString(),
        notes:            notes.trim(),
        cost:             cost ? parseFloat(cost) : null,
      })
      addToast({ type: 'success', message: `Maintenance logged for ${selectedEq!.name}.` })
      // Invalidate so the equipment list refreshes is_due_service + last_service_utc
      queryClient.invalidateQueries({ queryKey: ['equipment-list'] })
      closeDrawer()
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
        ?? 'Failed to log maintenance. Try again.'
      addToast({ type: 'error', message: msg })
    } finally {
      setSubmitting(false)
    }
  }

  const all = equipment ?? []
  const filtered = filter === 'all' ? all
    : filter === 'water'
      ? all.filter((e) => WATER_TYPES.has(e.equipment_type.toLowerCase()))
      : all.filter((e) => !WATER_TYPES.has(e.equipment_type.toLowerCase()))

  return (
    <RequireRole minLevel={5}>
      <div className="p-4 max-w-lg mx-auto space-y-4">

        <div>
          <h1 className="text-xl font-bold text-ink-primary">Equipment Service</h1>
          <p className="text-sm text-ink-tertiary">Log maintenance — tap any row to record a service</p>
        </div>

        {/* Filter chips */}
        <div className="flex gap-2 overflow-x-auto pb-1">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={[
                'px-3 py-1.5 min-h-[44px] rounded-full text-xs font-medium whitespace-nowrap transition-colors shrink-0',
                filter === f.key
                  ? 'bg-primary-dark text-cream-card'
                  : 'bg-cream-alt text-ink-secondary hover:bg-cream-alt/60',
              ].join(' ')}
            >
              {f.label}
            </button>
          ))}
        </div>

        {/* Loading skeletons */}
        {isLoading && (
          <div className="space-y-3">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="h-16 rounded-xl bg-cream-alt/40 animate-pulse" />
            ))}
          </div>
        )}

        {isError && (
          <div className="p-4 rounded-xl bg-cream-alt/40 text-sm text-ink-tertiary text-center">
            Couldn't load equipment. Check connection.
          </div>
        )}

        {!isLoading && !isError && filtered.length === 0 && (
          <EmptyState
            icon={
              <svg width="48" height="48" viewBox="0 0 48 48" fill="none" aria-hidden="true">
                <path d="M28 8l-4 4-4-4-4 4 4 4 4-4 4 4 4-4-4-4z" stroke="currentColor" strokeWidth="2"
                  strokeLinejoin="round"/>
                <path d="M24 16v16M16 32h16" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                <circle cx="24" cy="24" r="14" stroke="currentColor" strokeWidth="2"/>
              </svg>
            }
            title="No equipment records."
            description={filter !== 'all'
              ? "Try 'All' to see all equipment."
              : 'Ask the owner to add equipment first.'}
          />
        )}

        {/* Equipment rows */}
        {!isLoading && filtered.map((eq) => (
          <button
            key={eq.id}
            onClick={() => openDrawer(eq)}
            className={[
              'w-full flex items-center gap-4 p-4 rounded-2xl border text-left transition-colors',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark',
              eq.is_due_service
                ? 'border-status-failed/30 bg-status-failed/5 hover:bg-status-failed/10'
                : 'border-cream-alt bg-cream-card hover:bg-cream-alt/40',
            ].join(' ')}
          >
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-semibold text-ink-primary">{eq.name}</span>
                {eq.is_due_service && (
                  <span className="text-[10px] font-semibold uppercase tracking-wide
                    bg-status-failed/10 text-status-failed rounded-full px-2 py-0.5">
                    Service due
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2 mt-0.5">
                <span className="text-xs text-ink-tertiary capitalize">
                  {eq.equipment_type.replace(/_/g, ' ')}
                </span>
                <span className="text-xs text-ink-tertiary" aria-hidden="true">·</span>
                <span className="text-xs text-ink-tertiary">
                  Last: {formatDateNairobi(eq.last_service_utc)}
                </span>
              </div>
            </div>
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none"
              className="text-ink-tertiary shrink-0" aria-hidden="true">
              <path d="M6 4l4 4-4 4" stroke="currentColor"
                strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </button>
        ))}
      </div>

      {/* Maintenance form drawer */}
      <Drawer
        open={!!selectedEq}
        onClose={closeDrawer}
        title={selectedEq ? `Log Service — ${selectedEq.name}` : ''}
      >
        {selectedEq && (
          <div className="space-y-4">

            {/* Equipment summary */}
            <div className="rounded-xl bg-cream-alt/40 px-4 py-3 space-y-0.5 text-sm">
              <p className="text-ink-tertiary">
                Last service:{' '}
                <span className="text-ink-primary font-medium">
                  {formatDateNairobi(selectedEq.last_service_utc)}
                </span>
              </p>
              {selectedEq.service_interval_days && (
                <p className="text-ink-tertiary">
                  Interval:{' '}
                  <span className="text-ink-primary font-medium">
                    every {selectedEq.service_interval_days} days
                  </span>
                </p>
              )}
            </div>

            {/* History placeholder — endpoint not yet implemented */}
            <div className="rounded-xl bg-cream-alt/20 border border-cream-alt px-4 py-3">
              <p className="text-xs text-ink-tertiary italic">
                History will load when the history endpoint ships.
              </p>
            </div>

            {/* Log service form */}
            <form onSubmit={handleSubmit} noValidate className="space-y-4">

              <div>
                <label className="block text-sm font-medium text-ink-secondary mb-1.5">
                  Performed at
                </label>
                <input
                  type="datetime-local"
                  value={performedAt}
                  onChange={(e) => setPerformedAt(e.target.value)}
                  className="w-full rounded-xl border border-cream-alt bg-cream-card px-4 py-3
                    text-sm text-ink-primary focus:outline-none focus:border-primary-dark
                    focus:ring-2 focus:ring-primary-dark/20"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-ink-secondary mb-1.5">
                  Notes *
                </label>
                <textarea
                  rows={3}
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Describe the work performed…"
                  className={[
                    'w-full rounded-xl border bg-cream-card px-4 py-3',
                    'text-sm text-ink-primary focus:outline-none focus:ring-2 focus:ring-primary-dark/20 resize-none',
                    notesErr
                      ? 'border-status-failed focus:border-status-failed'
                      : 'border-cream-alt focus:border-primary-dark',
                  ].join(' ')}
                />
                {notesErr && (
                  <p className="text-sm text-status-failed mt-1">{notesErr}</p>
                )}
              </div>

              <div>
                <label className="block text-sm font-medium text-ink-secondary mb-1.5">
                  Cost (KES, optional)
                </label>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  inputMode="decimal"
                  value={cost}
                  onChange={(e) => setCost(e.target.value)}
                  placeholder="0.00"
                  className="w-full rounded-xl border border-cream-alt bg-cream-card px-4 py-3
                    text-sm text-ink-primary focus:outline-none focus:border-primary-dark
                    focus:ring-2 focus:ring-primary-dark/20"
                />
              </div>

              <button
                type="submit"
                disabled={submitting}
                className={[
                  'w-full py-4 rounded-2xl text-base font-semibold transition-all',
                  'bg-primary-dark text-cream-card hover:bg-primary-dark/90 active:scale-[0.99]',
                  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark focus-visible:ring-offset-2',
                  'disabled:opacity-50 disabled:cursor-not-allowed',
                ].join(' ')}
              >
                {submitting ? (
                  <span className="flex items-center justify-center gap-2">
                    <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
                      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" strokeOpacity="0.3"/>
                      <path d="M21 12a9 9 0 01-9 9" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                    </svg>
                    Saving…
                  </span>
                ) : 'Log Service'}
              </button>
            </form>
          </div>
        )}
      </Drawer>
    </RequireRole>
  )
}
