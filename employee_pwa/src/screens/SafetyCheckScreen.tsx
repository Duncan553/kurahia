import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { EmptyState, useToastStore } from '@shared'
import api from '../lib/axios'

// Equipment types that belong to the water activities station
const WATER_TYPES = new Set(['jetski', 'motorboat', 'paddle_boat', 'bicycle'])

interface Equipment {
  id: string
  name: string
  equipment_type: string
  status: string
  last_service_utc: string | null
  is_due_service: boolean
  notes: string | null
  is_active: boolean
}

interface ChecklistTemplate {
  equipment_type: string
  items: string[]
  count: number
}

interface CheckState {
  checked: boolean
  note: string
}

// "life_jackets_on_board" → "Life jackets on board"
function formatKey(k: string): string {
  return k.replace(/_/g, ' ').replace(/^./, (c) => c.toUpperCase())
}

function ServiceDueBadge() {
  return (
    <span className="text-[10px] font-semibold uppercase tracking-wide
      bg-status-failed/10 text-status-failed rounded-full px-2 py-0.5">
      Service due
    </span>
  )
}

function SpinIcon() {
  return (
    <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" strokeOpacity="0.3"/>
      <path d="M21 12a9 9 0 01-9 9" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
    </svg>
  )
}

// ── Single checklist row ────────────────────────────────────────────────────

function ChecklistItem({
  itemKey, state, hasError, onChange, onNote,
}: {
  itemKey: string
  state: CheckState
  hasError: boolean
  onChange: (checked: boolean) => void
  onNote: (note: string) => void
}) {
  return (
    <div className={[
      'rounded-xl border transition-all',
      hasError
        ? 'border-status-failed bg-status-failed/5'
        : state.checked
          ? 'border-primary-main/40 bg-primary-light/10'
          : 'border-white/10 bg-transparent',
    ].join(' ')}>

      {/* Checkbox row — full-width tap target */}
      <button
        type="button"
        onClick={() => onChange(!state.checked)}
        className="flex items-center gap-3 w-full px-4 py-3.5 text-left
          focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark focus-visible:ring-inset"
      >
        {/* Custom checkbox square */}
        <span className={[
          'flex-shrink-0 w-5 h-5 rounded flex items-center justify-center border-2 transition-colors',
          state.checked
            ? 'border-[#fa5c29] bg-[#fa5c29]'
            : hasError
              ? 'border-status-failed'
              : 'border-ink-tertiary/60',
        ].join(' ')}>
          {state.checked && (
            <svg width="10" height="8" viewBox="0 0 10 8" fill="none" aria-hidden="true">
              <path d="M1 4l3 3L9 1" stroke="white" strokeWidth="1.5"
                strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          )}
        </span>

        <span className={`flex-1 text-sm font-medium ${hasError ? 'text-status-failed' : 'text-white'}`}>
          {formatKey(itemKey)}
        </span>

        {hasError && (
          <span className="text-[10px] font-semibold uppercase tracking-wide
            bg-status-failed/10 text-status-failed rounded-full px-2 py-0.5 shrink-0">
            Required
          </span>
        )}
      </button>

      {/* Note field — only visible when checked */}
      {state.checked && (
        <div className="px-4 pb-3">
          <textarea
            rows={2}
            value={state.note}
            onChange={(e) => onNote(e.target.value)}
            placeholder="Optional note…"
            className="w-full rounded-lg border border-white/10 bg-transparent px-3 py-2
              text-sm text-white focus:outline-none focus:border-[#fa5c29]
              focus:ring-2 focus:ring-primary-dark/20 resize-none"
          />
        </div>
      )}
    </div>
  )
}

// ── Main screen ─────────────────────────────────────────────────────────────

export default function SafetyCheckScreen() {
  const addToast = useToastStore((s) => s.addToast)

  const [selectedEq,  setSelectedEq]  = useState<Equipment | null>(null)
  const [checks,      setChecks]      = useState<Record<string, CheckState>>({})
  const [errorItems,  setErrorItems]  = useState<string[]>([])
  const [submitting,  setSubmitting]  = useState(false)

  // Equipment list — stale for 5 min (doesn't change often)
  const { data: equipment, isLoading, isError } = useQuery<Equipment[]>({
    queryKey: ['equipment-list'],
    queryFn: () => api.get<Equipment[]>('/equipment').then((r) => r.data),
    staleTime: 5 * 60_000,
  })

  // Filter to water activity types client-side
  const waterEquipment = (equipment ?? []).filter(
    (e) => WATER_TYPES.has(e.equipment_type.toLowerCase())
  )

  // Fetch checklist template whenever a piece of equipment is selected
  const { data: template, isFetching: templateLoading } = useQuery<ChecklistTemplate>({
    queryKey: ['checklist-template', selectedEq?.equipment_type],
    queryFn: () =>
      api.get<ChecklistTemplate>(
        `/equipment/checklist-templates/${selectedEq!.equipment_type.toLowerCase()}`
      ).then((r) => r.data),
    enabled: !!selectedEq,
    staleTime: Infinity,   // templates don't change at runtime
  })

  // Merge template keys with current check state (default unchecked)
  const effectiveChecks: Record<string, CheckState> = template
    ? Object.fromEntries(
        template.items.map((k) => [k, checks[k] ?? { checked: false, note: '' }])
      )
    : {}

  const checkedCount = template
    ? template.items.filter((k) => effectiveChecks[k]?.checked).length
    : 0
  const allChecked = template ? checkedCount === template.items.length : false

  function selectEquipment(eq: Equipment) {
    setSelectedEq(eq)
    setChecks({})
    setErrorItems([])
  }

  function clearSelection() {
    setSelectedEq(null)
    setChecks({})
    setErrorItems([])
  }

  function toggleCheck(key: string, val: boolean) {
    setChecks((prev) => ({
      ...prev,
      [key]: { ...(prev[key] ?? { note: '' }), checked: val },
    }))
    if (val) setErrorItems((prev) => prev.filter((k) => k !== key))
  }

  function setNote(key: string, note: string) {
    setChecks((prev) => ({
      ...prev,
      [key]: { ...(prev[key] ?? { checked: false }), note },
    }))
  }

  async function handleSubmit() {
    if (!selectedEq || !template || !allChecked) return
    setSubmitting(true)
    setErrorItems([])

    // Build check_items object: { key: { checked: true, note: "" } }
    const checkItems: Record<string, { checked: boolean; note: string }> = {}
    template.items.forEach((k) => {
      checkItems[k] = { checked: true, note: effectiveChecks[k]?.note ?? '' }
    })

    try {
      const res = await api.post<{ id: string; passed: boolean; equipment_status: string }>(
        `/equipment/${selectedEq.id}/safety-check`,
        { check_items: checkItems }
      )
      addToast({
        type: 'success',
        message: `Safety check recorded for ${selectedEq.name}. Status: ${res.data.equipment_status}.`,
      })
      clearSelection()
    } catch (err: unknown) {
      const data = (err as {
        response?: { data?: { error?: string; unchecked_items?: string[] } }
      })?.response?.data

      const unchecked = data?.unchecked_items ?? []
      if (unchecked.length > 0) {
        setErrorItems(unchecked)
        addToast({
          type: 'error',
          message: 'Some items are not confirmed. Review the highlighted rows.',
        })
      } else {
        addToast({
          type: 'error',
          message: data?.error ?? 'Safety check failed. Try again.',
        })
      }
    } finally {
      setSubmitting(false)
    }
  }

  // ── Equipment selection view ───────────────────────────────────────────────
  if (!selectedEq) {
    return (
      <div className="p-4 max-w-3xl mx-auto space-y-5">
        <div>
          <h1 className="text-2xl font-bold text-white font-serif">Safety Check</h1>
          <p className="text-xs text-white/30 mt-0.5">Equipment safety inspections</p>
        </div>

        {isLoading && (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-16 rounded-xl bg-white/5/40 animate-pulse" />
            ))}
          </div>
        )}

        {isError && (
          <div className="p-4 rounded-xl bg-white/5/40 text-sm text-ink-tertiary text-center">
            Couldn't load equipment. Check connection.
          </div>
        )}

        {!isLoading && !isError && waterEquipment.length === 0 && (
          <EmptyState
            icon={
              <svg width="48" height="48" viewBox="0 0 48 48" fill="none" aria-hidden="true">
                <path d="M24 8a16 16 0 100 32A16 16 0 0024 8z"
                  stroke="currentColor" strokeWidth="2"/>
                <path d="M17 25l5 5 9-10"
                  stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            }
            title="No equipment configured for water activities."
            description="Ask the owner to add equipment records first."
          />
        )}

        {!isLoading && waterEquipment.map((eq) => (
          <button
            key={eq.id}
            onClick={() => selectEquipment(eq)}
            className="w-full flex items-center gap-4 p-4 rounded-2xl glass-card
              bg-transparent hover:bg-white/5/40 active:bg-white/5/60 transition-colors text-left
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark"
          >
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-semibold text-white">{eq.name}</span>
                {eq.is_due_service && <ServiceDueBadge />}
              </div>
              <p className="text-xs text-ink-tertiary capitalize mt-0.5">
                {eq.equipment_type.replace(/_/g, ' ')}
              </p>
            </div>
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none"
              className="text-ink-tertiary shrink-0" aria-hidden="true">
              <path d="M6 4l4 4-4 4" stroke="currentColor"
                strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          </button>
        ))}
      </div>
    )
  }

  // ── Checklist view (equipment selected) ───────────────────────────────────
  return (
    <div className="p-4 max-w-3xl mx-auto space-y-5">

      {/* Header + back button */}
      <div className="flex items-start gap-3">
        <button
          onClick={clearSelection}
          className="min-h-[44px] min-w-[44px] flex items-center justify-center rounded-lg
            hover:bg-white/5 transition-colors shrink-0
            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark"
          aria-label="Back to equipment list"
        >
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
            <path d="M11 4L6 9l5 5" stroke="currentColor"
              strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </button>
        <div>
          <h1 className="text-xl font-bold text-white">{selectedEq.name}</h1>
          <div className="flex items-center gap-2 mt-0.5">
            <span className="text-sm text-ink-tertiary capitalize">
              {selectedEq.equipment_type.replace(/_/g, ' ')}
            </span>
            {selectedEq.is_due_service && <ServiceDueBadge />}
          </div>
        </div>
      </div>

      {/* Template loading skeletons */}
      {templateLoading && (
        <div className="space-y-3">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="h-14 rounded-xl bg-white/5/40 animate-pulse" />
          ))}
        </div>
      )}

      {/* No template for this equipment type */}
      {!templateLoading && !template && (
        <div className="p-4 rounded-xl bg-white/5/40 text-sm text-ink-tertiary text-center">
          No checklist template configured for this equipment type.
        </div>
      )}

      {/* Checklist */}
      {!templateLoading && template && (
        <>
          <p className="text-xs text-ink-tertiary">
            All {template.count} items must be confirmed before equipment can be used.
          </p>

          <div className="space-y-3">
            {template.items.map((key) => (
              <ChecklistItem
                key={key}
                itemKey={key}
                state={effectiveChecks[key] ?? { checked: false, note: '' }}
                hasError={errorItems.includes(key)}
                onChange={(val) => toggleCheck(key, val)}
                onNote={(note) => setNote(key, note)}
              />
            ))}
          </div>

          {/* Progress bar */}
          <div className="flex items-center gap-3">
            <div className="flex-1 h-1.5 rounded-full bg-white/5 overflow-hidden">
              <div
                className="h-full bg-[#fa5c29] rounded-full transition-all duration-300"
                style={{ width: `${(checkedCount / template.items.length) * 100}%` }}
                aria-hidden="true"
              />
            </div>
            <span className="text-xs tabular-nums text-ink-tertiary shrink-0">
              {checkedCount}/{template.items.length}
            </span>
          </div>

          <button
            onClick={handleSubmit}
            disabled={!allChecked || submitting}
            className={[
              'w-full py-4 rounded-2xl text-base font-semibold transition-all',
              'bg-[#fa5c29] text-white hover:bg-[#af3000] active:scale-[0.99]',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark focus-visible:ring-offset-2',
              'disabled:opacity-50 disabled:cursor-not-allowed',
            ].join(' ')}
          >
            {submitting ? (
              <span className="flex items-center justify-center gap-2">
                <SpinIcon />
                Submitting…
              </span>
            ) : allChecked
              ? 'Record Safety Check'
              : `Check all ${template.count} items to continue`}
          </button>
        </>
      )}
    </div>
  )
}
