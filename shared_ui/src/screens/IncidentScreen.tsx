import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { Button, useToastStore, ErrorBoundary, Icon } from '../index'
import { useAuthStore } from '../stores/authStore'
import api from '../lib/axios'

type Severity = 'LOW' | 'MEDIUM' | 'HIGH'

interface Incident {
  id: string
  description: string
  location: string
  severity: Severity
  involved_guest: string | null
  actioned: boolean
  actioned_by: string | null
  actioned_at: string | null
  reported_by: string | null
  created_at: string | null
}

const SEVERITIES: { value: Severity; label: string; color: string }[] = [
  { value: 'LOW',    label: 'Low',    color: 'bg-blue-500/20 text-blue-300 border-blue-500/30' },
  { value: 'MEDIUM', label: 'Medium', color: 'bg-amber-500/20 text-amber-300 border-amber-500/30' },
  { value: 'HIGH',   label: 'High',   color: 'bg-red-500/20 text-red-300 border-red-500/30' },
]

function SeverityBadge({ severity }: { severity: Severity }) {
  const s = SEVERITIES.find(x => x.value === severity)
  return (
    <span className={`text-[10px] font-bold tracking-widest uppercase px-2 py-0.5 rounded-full border ${s?.color}`}>
      {s?.label ?? severity}
    </span>
  )
}

function fmtDate(iso: string | null) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('en-KE', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}

/* ── Log form (all staff) ─────────────────────────────────────────────────── */

function LogForm() {
  const { addToast } = useToastStore()
  const [description, setDescription] = useState('')
  const [location, setLocation]       = useState('')
  const [severity, setSeverity]       = useState<Severity>('MEDIUM')
  const [guest, setGuest]             = useState('')

  const mut = useMutation({
    mutationFn: () => api.post<Incident>('/incidents', {
      description, location, severity,
      involved_guest: guest || undefined,
      idempotency_key: crypto.randomUUID(),
    }).then(r => r.data),
    onSuccess: () => {
      addToast({ type: 'success', message: 'Incident logged.' })
      setDescription(''); setLocation(''); setSeverity('MEDIUM'); setGuest('')
    },
    onError: (e: unknown) => {
      const msg = (e as { response?: { data?: { error?: string } } })?.response?.data?.error
      addToast({ type: 'error', message: msg ?? 'Failed to log incident.' })
    },
  })

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
      className="glass-card rounded-2xl p-5 border border-white/10 space-y-4">
      <h2 className="font-serif text-lg font-bold text-ink-primary">Log Incident</h2>

      <div className="space-y-1">
        <label className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary">Severity</label>
        <div className="flex gap-2">
          {SEVERITIES.map(s => (
            // Severity chips were 30px tall. min-h-[44px] + inline-flex gives a
            // proper touch box without changing the pill's width or type scale —
            // this form gets filled in a hurry, often with one hand.
            <button key={s.value} onClick={() => setSeverity(s.value)}
              className={`px-4 inline-flex items-center justify-center min-h-[44px] min-w-[44px]
                rounded-full text-xs font-bold border transition-colors
                ${severity === s.value ? s.color : 'border-white/10 text-ink-tertiary'}`}>
              {s.label}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-1">
        <label className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary">Location *</label>
        <input value={location} onChange={e => setLocation(e.target.value)}
          placeholder="e.g. Pool area, Jet ski dock, Villa 6"
          className="w-full rounded-xl glass-card bg-transparent px-4 py-3 text-sm text-ink-primary
            placeholder:text-ink-tertiary focus:outline-none focus:ring-2 focus:ring-[#fa5c29]/40" />
      </div>

      <div className="space-y-1">
        <label className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary">What happened *</label>
        <textarea value={description} onChange={e => setDescription(e.target.value)}
          rows={3} placeholder="Describe what happened clearly and factually."
          className="w-full rounded-xl glass-card bg-transparent px-4 py-3 text-sm text-ink-primary
            placeholder:text-ink-tertiary focus:outline-none focus:ring-2 focus:ring-[#fa5c29]/40 resize-none" />
      </div>

      <div className="space-y-1">
        <label className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary">Guest involved (optional)</label>
        <input value={guest} onChange={e => setGuest(e.target.value)}
          placeholder="Guest name if applicable"
          className="w-full rounded-xl glass-card bg-transparent px-4 py-3 text-sm text-ink-primary
            placeholder:text-ink-tertiary focus:outline-none focus:ring-2 focus:ring-[#fa5c29]/40" />
      </div>

      <Button variant="primary" size="lg" className="w-full"
        loading={mut.isPending}
        onClick={() => {
          if (!description.trim() || !location.trim()) {
            addToast({ type: 'error', message: 'Location and description are required.' })
            return
          }
          mut.mutate()
        }}>
        Submit Incident Report
      </Button>
    </motion.div>
  )
}

/* ── History list (manager+ only) ─────────────────────────────────────────── */

function IncidentHistory() {
  const qc = useQueryClient()
  const { addToast } = useToastStore()

  const { data: incidents = [], isLoading } = useQuery<Incident[]>({
    queryKey: ['incidents'],
    queryFn: () => api.get<Incident[]>('/incidents?limit=50').then(r => r.data),
    staleTime: 30_000,
  })

  const actionMut = useMutation({
    mutationFn: (id: string) => api.patch(`/incidents/${id}/action`).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['incidents'] })
      addToast({ type: 'success', message: 'Incident acknowledged.' })
    },
  })

  if (isLoading) return (
    <div className="space-y-3">
      {[1,2,3].map(i => <div key={i} className="h-24 rounded-2xl bg-white/5 animate-pulse" />)}
    </div>
  )

  if (incidents.length === 0) return (
    <div className="text-center py-12 text-ink-tertiary text-sm">No incidents recorded.</div>
  )

  return (
    <div className="space-y-3">
      {incidents.map(inc => (
        <motion.div key={inc.id}
          initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
          className="glass-card rounded-2xl p-4 border border-white/10 space-y-2">
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-2 flex-wrap">
              <SeverityBadge severity={inc.severity} />
              {!inc.actioned && (
                <span className="text-[10px] font-bold tracking-widest uppercase px-2 py-0.5
                  rounded-full bg-primary-main/20 text-[#fa5c29] border border-primary-main/30">
                  Needs attention
                </span>
              )}
            </div>
            <p className="text-[10px] text-ink-tertiary shrink-0">{fmtDate(inc.created_at)}</p>
          </div>

          <p className="text-sm text-ink-primary leading-relaxed">{inc.description}</p>

          <div className="flex items-center gap-4 text-[10px] text-ink-tertiary">
            {/* label= is set because the icon alone carries the meaning here (no visible "Location:" text) */}
            <span className="inline-flex items-center gap-1">
              <Icon name="pin" size={12} label="Location" /> {inc.location}
            </span>
            {inc.involved_guest && (
              <span className="inline-flex items-center gap-1">
                <Icon name="user" size={12} label="Guest involved" /> {inc.involved_guest}
              </span>
            )}
            <span>Reported by {inc.reported_by}</span>
          </div>

          {inc.actioned ? (
            <p className="text-[10px] text-ink-tertiary">
              Acknowledged by {inc.actioned_by} · {fmtDate(inc.actioned_at)}
            </p>
          ) : (
            <Button variant="ghost" size="sm"
              loading={actionMut.isPending}
              onClick={() => actionMut.mutate(inc.id)}>
              Acknowledge
            </Button>
          )}
        </motion.div>
      ))}
    </div>
  )
}

/* ── Main screen ──────────────────────────────────────────────────────────── */

export default function IncidentScreen() {
  const user = useAuthStore(s => s.user)
  const isManager = (user?.role_level ?? 0) >= 5

  return (
    <div className="min-h-screen p-4 md:p-6">
      <div className="max-w-2xl mx-auto space-y-6">
        <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
          <h1 className="font-serif text-2xl font-bold text-ink-primary">Incident Report</h1>
          <p className="text-sm text-ink-secondary mt-1">
            Log any accident, injury, or safety concern immediately.
          </p>
        </motion.div>

        <ErrorBoundary level="tile">
          <LogForm />
        </ErrorBoundary>

        {isManager && (
          <ErrorBoundary level="tile">
            <div className="space-y-3">
              <h2 className="font-serif text-lg font-bold text-ink-primary">All Incidents</h2>
              <IncidentHistory />
            </div>
          </ErrorBoundary>
        )}
      </div>
    </div>
  )
}
