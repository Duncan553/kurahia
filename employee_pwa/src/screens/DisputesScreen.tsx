/**
 * DisputesScreen (employee) — raise a grievance, and see your own.
 *
 * This used to be the MANAGER's queue: a worker opened it and saw everyone
 * else's complaints with Claim / Resolve / Dismiss buttons the API refuses
 * them, and no way at all to file their own — the one thing this channel
 * exists for. The queue now lives with the manager and the owner; the phone
 * keeps what belongs to the person holding it.
 *
 * "Only the owner sees this" is offered because the complaint may be ABOUT the
 * manager (app/disputes/core.py filters owner-only rows out of a manager's
 * query entirely).
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { StatusBadge, EmptyState, Skeleton, useToastStore, ErrorBoundary, Icon } from '@shared'
import type { StatusValue } from '@shared'
import api from '../lib/axios'

interface Dispute {
  id: string
  category: string
  description: string
  status: 'OPEN' | 'UNDER_REVIEW' | 'RESOLVED' | 'DISMISSED'
  priority: string
  is_owner_only: boolean
  created_at: string
  resolution_notes?: string | null
}

const CATEGORIES = [
  { value: 'PERFORMANCE',       label: 'Something about my work or my pay' },
  { value: 'INTERPERSONAL',     label: 'A problem with another person here' },
  { value: 'CONDUCT_VIOLATION', label: 'Someone broke the rules' },
  { value: 'OTHER',             label: 'Something else' },
]

const BADGE: Record<Dispute['status'], StatusValue> = {
  // The same four words the manager's queue shows, so the person who filed it
  // and the person who answered it are reading the same outcome.
  OPEN: 'pending', UNDER_REVIEW: 'under-review', RESOLVED: 'resolved', DISMISSED: 'dismissed',
}

export default function DisputesScreen() {
  const qc = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  const [category, setCategory]   = useState('PERFORMANCE')
  const [description, setDesc]    = useState('')
  const [ownerOnly, setOwnerOnly] = useState(false)

  const { data: mine = [], isLoading } = useQuery<Dispute[]>({
    queryKey: ['my-disputes'],
    queryFn: () => api.get<Dispute[]>('/disputes').then(r => Array.isArray(r.data) ? r.data : []),
  })

  const file = useMutation({
    mutationFn: () => api.post('/disputes', {
      category,
      description: description.trim(),
      priority: 'MEDIUM',
      is_owner_only: ownerOnly,
      idempotency_key: crypto.randomUUID(),
    }).then(r => r.data),
    onSuccess: () => {
      addToast({ type: 'success', message: ownerOnly
        ? 'Sent to the owner. No manager can see it.'
        : 'Raised. A manager will pick it up.' })
      setDesc(''); setOwnerOnly(false)
      qc.invalidateQueries({ queryKey: ['my-disputes'] })
    },
    onError: (e: unknown) => addToast({ type: 'error',
      message: (e as { response?: { data?: { error?: string } } })?.response?.data?.error
        ?? 'Could not send that.' }),
  })

  return (
    <ErrorBoundary level="screen">
      <div className="p-4 max-w-2xl mx-auto space-y-5">
        <div>
          <h1 className="text-xl font-bold text-ink-primary">Raise something</h1>
          <p className="text-sm text-ink-tertiary">
            A formal complaint about work, pay, or how you have been treated.
          </p>
        </div>

        <div className="glass-card rounded-2xl p-4 space-y-3">
          <select
            style={{ colorScheme: 'dark' }}
            value={category}
            onChange={e => setCategory(e.target.value)}
            className="w-full rounded-xl glass-card bg-transparent px-4 py-3 text-sm
              text-ink-primary focus:outline-none focus:border-primary-main">
            {CATEGORIES.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
          </select>

          <textarea
            rows={4}
            placeholder="What happened? Dates and names help."
            value={description}
            onChange={e => setDesc(e.target.value)}
            className="w-full rounded-xl glass-card bg-transparent px-4 py-3 text-sm
              text-ink-primary focus:outline-none focus:border-primary-main resize-none"
          />

          <button
            type="button"
            onClick={() => setOwnerOnly(o => !o)}
            className={`w-full flex items-center justify-between px-4 py-3 rounded-xl border text-sm
              ${ownerOnly ? 'border-primary-main/40 bg-primary-main/5 text-primary-main'
                          : 'border-white/10 text-ink-tertiary'}`}>
            <span className="font-medium text-left">
              Only the owner sees this
              <span className="block text-[11px] font-normal opacity-80">
                Use this if the problem involves a manager.
              </span>
            </span>
            <span className={`w-5 h-5 rounded-full border-2 shrink-0 ${
              ownerOnly ? 'border-primary-main bg-primary-main' : 'border-white/20'}`} />
          </button>

          <button
            onClick={() => file.mutate()}
            disabled={!description.trim() || file.isPending}
            className="w-full min-h-[44px] rounded-xl bg-primary-main text-white text-sm
              font-semibold disabled:opacity-50">
            {file.isPending ? 'Sending…' : 'Send it'}
          </button>
        </div>

        <div className="space-y-3">
          <h2 className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary">
            What you have raised
          </h2>
          {isLoading && <Skeleton variant="text" className="w-full h-20" />}
          {!isLoading && mine.length === 0 && (
            <EmptyState icon={<Icon name="alert" size={40} />} title="Nothing raised"
              description="Anything you send shows here with what came of it." />
          )}
          {mine.map(d => (
            <div key={d.id} className="glass-card rounded-2xl p-4 space-y-1.5">
              <div className="flex items-start justify-between gap-3">
                <p className="text-sm text-ink-primary whitespace-pre-wrap">{d.description}</p>
                <StatusBadge status={BADGE[d.status]} size="sm" />
              </div>
              <p className="text-[11px] text-ink-tertiary">
                {new Date(d.created_at).toLocaleDateString('en-KE', { day: 'numeric', month: 'short' })}
                {d.is_owner_only && ' · owner only'}
              </p>
              {d.resolution_notes && (
                <p className="text-xs text-ink-secondary border-l-2 border-white/10 pl-3">
                  {d.resolution_notes}
                </p>
              )}
            </div>
          ))}
        </div>
      </div>
    </ErrorBoundary>
  )
}
