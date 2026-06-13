import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Skeleton, EmptyState, Modal, Button, useToastStore } from '@shared'
import api from '../lib/axios'

// ── Types ──────────────────────────────────────────────────────────────────────

interface JudgeAlert {
  id: string
  item_id: string | null
  item_name: string | null
  alert_type: string
  severity: string
  description: string
  status: string
  created_at: string
}

type Filter = 'open' | 'acknowledged' | 'all'

// ── Helpers ────────────────────────────────────────────────────────────────────

const extractErr = (e: unknown) =>
  (e as { response?: { data?: { error?: string } } })?.response?.data?.error ?? 'Something went wrong.'

function timeAgo(iso: string) {
  const sec = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (sec < 60) return 'just now'
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`
  if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`
  return `${Math.floor(sec / 86400)}d ago`
}

// ── Alert-type icons ───────────────────────────────────────────────────────────

function RatioIcon() {
  return <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <path d="M2 12l3-4 2.5 2.5L11 6l3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    <path d="M1 14h14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
}
function SpoilageIcon() {
  return <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <path d="M4 4h8l-1 8H5L4 4z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
    <path d="M2.5 4h11M6 2h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
    <path d="M8 7v2.5M8 11h.01" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
}
function SafeIcon() {
  return <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <rect x="2" y="3" width="12" height="10" rx="1.5" stroke="currentColor" strokeWidth="1.5"/>
    <circle cx="8" cy="8" r="2" stroke="currentColor" strokeWidth="1.5"/>
    <path d="M13 6h1M13 10h1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
  </svg>
}

function AlertTypeIcon({ type }: { type: string }) {
  if (type === 'RATIO') return <RatioIcon />
  if (type === 'SPOILAGE_SPIKE') return <SpoilageIcon />
  return <SafeIcon />
}

// ── Severity styling ───────────────────────────────────────────────────────────

const SEV_BORDER: Record<string, string> = {
  CRITICAL: 'border-l-status-failed',
  HIGH:     'border-l-status-failed',
  MEDIUM:   'border-l-status-pending',
  LOW:      'border-l-status-neutral',
}
const SEV_TEXT: Record<string, string> = {
  CRITICAL: 'text-status-failed',
  HIGH:     'text-status-failed',
  MEDIUM:   'text-status-pending',
  LOW:      'text-status-neutral',
}

const SEVERITY_ORDER = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']

// ── Component ──────────────────────────────────────────────────────────────────

export default function AlertsScreen() {
  const qc = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  const [view, setView] = useState({ filter: 'open' as Filter, ackingId: null as string | null })

  const { data: alerts = [], isLoading, isError } = useQuery<JudgeAlert[]>({
    queryKey: ['judge-alerts', view.filter],
    queryFn: () => api.get<JudgeAlert[]>(`/judge/alerts?status=${view.filter}`).then(r => r.data),
    staleTime: 2 * 60_000,
    refetchOnWindowFocus: true,
  })

  const ackMut = useMutation({
    mutationFn: (id: string) => api.post(`/judge/alerts/${id}/acknowledge`).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['judge-alerts'] })
      setView(v => ({ ...v, ackingId: null }))
      addToast({ type: 'success', message: 'Alert acknowledged.' })
    },
    onError: (e) => addToast({ type: 'error', message: extractErr(e) }),
  })

  // Group by severity in priority order
  const groups = SEVERITY_ORDER.reduce<{ severity: string; items: JudgeAlert[] }[]>((acc, sev) => {
    const items = alerts.filter(a => a.severity === sev)
    if (items.length) acc.push({ severity: sev, items })
    return acc
  }, [])

  const FILTERS: { key: Filter; label: string }[] = [
    { key: 'open', label: 'Open' },
    { key: 'acknowledged', label: 'Acknowledged' },
    { key: 'all', label: 'All' },
  ]

  const ackingAlert = view.ackingId ? alerts.find(a => a.id === view.ackingId) : null

  return (
    <div className="p-4 max-w-2xl mx-auto space-y-4">

      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-ink-primary font-serif">Judge Alerts</h1>
        {!isLoading && (
          <span className="text-xs text-ink-secondary">
            {alerts.length} {view.filter === 'all' ? 'total' : view.filter}
          </span>
        )}
      </div>

      {/* Filter chips */}
      <div className="flex gap-2">
        {FILTERS.map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setView(v => ({ ...v, filter: key }))}
            className={[
              'px-3 py-1.5 min-h-[44px] rounded-full text-xs font-semibold transition-colors',
              view.filter === key
                ? 'bg-ink-primary text-cream-card'
                : 'bg-cream-alt text-ink-secondary hover:bg-cream-deep',
            ].join(' ')}
          >
            {label}
          </button>
        ))}
      </div>

      {/* States */}
      {isLoading && (
        <div className="space-y-3">
          {[1,2,3].map(i => <Skeleton key={i} variant="row" />)}
        </div>
      )}

      {isError && (
        <p className="text-sm text-status-failed text-center py-8">
          Failed to load alerts. Check your connection.
        </p>
      )}

      {!isLoading && !isError && alerts.length === 0 && (
        <EmptyState
          icon={<svg width="40" height="40" viewBox="0 0 40 40" fill="none" aria-hidden="true">
            <circle cx="20" cy="20" r="14" stroke="currentColor" strokeWidth="1.5"/>
            <path d="M20 13v8M20 25h.01" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
          </svg>}
          title={view.filter === 'open' ? 'All clear · Hakuna shida' : 'No alerts in this view.'}
        />
      )}

      {/* Grouped alerts */}
      {groups.map(({ severity, items }) => (
        <div key={severity} className="space-y-2">
          <p className={`text-[10px] font-semibold tracking-widest uppercase ${SEV_TEXT[severity] ?? 'text-ink-secondary'}`}>
            {severity}
          </p>
          {items.map(alert => (
            <div
              key={alert.id}
              className={[
                'border-l-4 rounded-r-2xl rounded-l-sm bg-cream-card border border-cream-alt p-4',
                SEV_BORDER[alert.severity] ?? 'border-l-ink-tertiary',
                alert.status === 'ACKNOWLEDGED' ? 'opacity-50' : '',
              ].join(' ')}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  {/* Type + item */}
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`shrink-0 ${SEV_TEXT[alert.severity] ?? 'text-ink-tertiary'}`}>
                      <AlertTypeIcon type={alert.alert_type} />
                    </span>
                    <span className="text-[10px] font-bold tracking-widest uppercase text-ink-secondary font-serif">
                      {alert.alert_type.replace(/_/g, ' ')}
                    </span>
                    {alert.item_name && (
                      <span className="text-[10px] text-ink-secondary truncate">· {alert.item_name}</span>
                    )}
                  </div>
                  <p className="text-sm text-ink-primary leading-snug">{alert.description}</p>
                  <p className="text-[10px] text-ink-secondary mt-1.5">{timeAgo(alert.created_at)}</p>
                </div>
                {/* Acknowledge / done */}
                {alert.status === 'ACKNOWLEDGED' ? (
                  <span className="shrink-0 text-[10px] font-semibold text-status-paid bg-status-paid/10 px-2 py-0.5 rounded-full">
                    ✓ Done
                  </span>
                ) : (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setView(v => ({ ...v, ackingId: alert.id }))}
                  >
                    Ack
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>
      ))}

      {/* Acknowledge confirmation modal */}
      <Modal
        open={!!view.ackingId}
        onClose={() => setView(v => ({ ...v, ackingId: null }))}
        title="Acknowledge alert?"
        size="sm"
      >
        {ackingAlert && (
          <div className="space-y-4">
            <p className="text-sm text-ink-secondary">{ackingAlert.description}</p>
            <p className="text-xs text-ink-secondary">This cannot be undone.</p>
            <div className="flex gap-2 justify-end">
              <Button variant="ghost" size="sm" onClick={() => setView(v => ({ ...v, ackingId: null }))}>
                Cancel
              </Button>
              <Button
                variant="primary"
                size="sm"
                loading={ackMut.isPending}
                onClick={() => ackMut.mutate(view.ackingId!)}
              >
                Acknowledge
              </Button>
            </div>
          </div>
        )}
      </Modal>

    </div>
  )
}
