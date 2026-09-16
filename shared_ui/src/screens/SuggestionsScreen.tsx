/**
 * SuggestionsScreen — what staff sent upstairs, and the owner-private channel.
 *
 * The dashboard has counted suggestions for a long time ("Owner-private: 1 ·
 * Management: 0") with nowhere to open one. A staff member who takes the
 * trouble to write "the gate float keeps coming up short — managers cannot see
 * this" became a number on a tile, and the one person allowed to read it
 * could not.
 *
 * Owner-private rows are structurally invisible to managers (the query filters
 * them out server-side, app/suggestions/core.py), so this screen is the only
 * place they can ever be read.
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Skeleton } from '../components/Skeleton'
import { EmptyState } from '../components/EmptyState'
import { Icon } from '../components/Icon'
import { useToastStore } from '../stores/toastStore'
import { ErrorBoundary } from '../components/ErrorBoundary'
import { StatusBadge } from '../components/StatusBadge'
import type { StatusValue } from '../components/StatusBadge'
import api from '../lib/axios'

interface Suggestion {
  id: string
  category: 'MANAGEMENT' | 'OWNER_PRIVATE'
  subject: string
  body: string
  status: 'NEW' | 'UNDER_REVIEW' | 'ACTIONED' | 'DISMISSED'
  submitted_by: string
  reviewed_by: string | null
  response: string | null
  created_at: string
}

const STATUS_BADGE: Record<Suggestion['status'], StatusValue> = {
  NEW: 'pending', UNDER_REVIEW: 'info', ACTIONED: 'actioned', DISMISSED: 'inactive',
}

const extractErr = (e: unknown) =>
  (e as { response?: { data?: { error?: string } } })?.response?.data?.error
  ?? 'Something went wrong.'

export default function SuggestionsScreen() {
  const qc = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  const [open, setOpen] = useState<string | null>(null)
  const [reply, setReply] = useState('')

  const { data: items = [], isLoading, isError } = useQuery<Suggestion[]>({
    queryKey: ['suggestions'],
    queryFn: () => api.get<Suggestion[]>('/suggestions').then(r => Array.isArray(r.data) ? r.data : []),
    staleTime: 30_000,
  })

  const review = useMutation({
    mutationFn: ({ id, status }: { id: string; status: Suggestion['status'] }) =>
      api.post(`/suggestions/${id}/review`, {
        status, response: reply.trim() || undefined,
      }).then(r => r.data),
    onSuccess: (_d, { status }) => {
      addToast({ type: 'success',
        message: status === 'ACTIONED' ? 'Marked as actioned.'
               : status === 'DISMISSED' ? 'Closed.' : 'Marked as being looked at.' })
      setReply(''); setOpen(null)
      qc.invalidateQueries({ queryKey: ['suggestions'] })
      qc.invalidateQueries({ queryKey: ['dash-suggestions'] })
    },
    onError: (e) => addToast({ type: 'error', message: extractErr(e) }),
  })

  const priv = items.filter(s => s.category === 'OWNER_PRIVATE')
  const mgmt = items.filter(s => s.category === 'MANAGEMENT')

  const Card = ({ s }: { s: Suggestion }) => (
    <div className="glass-card rounded-2xl p-4 space-y-2">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-semibold text-ink-primary">{s.subject}</p>
          <p className="text-[11px] text-ink-tertiary mt-0.5">
            {s.submitted_by} · {new Date(s.created_at).toLocaleString('en-KE', {
              day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
            {s.reviewed_by && ` · seen by ${s.reviewed_by}`}
          </p>
        </div>
        <StatusBadge status={STATUS_BADGE[s.status]} size="sm" />
      </div>

      <p className="text-sm text-ink-secondary whitespace-pre-wrap">{s.body}</p>

      {s.response && (
        <p className="text-xs text-ink-tertiary border-l-2 border-white/10 pl-3">
          Replied: {s.response}
        </p>
      )}

      {s.status === 'NEW' || s.status === 'UNDER_REVIEW' ? (
        open === s.id ? (
          <div className="space-y-2 pt-1">
            <textarea
              rows={2}
              placeholder="Reply to them (optional) — they see this on their phone"
              value={reply}
              onChange={e => setReply(e.target.value)}
              className="w-full rounded-xl glass-card bg-transparent px-4 py-3 text-sm
                text-ink-primary focus:outline-none focus:border-primary-main resize-none"
            />
            <div className="flex gap-2 flex-wrap">
              <button onClick={() => review.mutate({ id: s.id, status: 'ACTIONED' })}
                disabled={review.isPending}
                className="flex-1 min-h-[44px] px-4 rounded-xl bg-primary-main text-white
                  text-sm font-semibold disabled:opacity-50">
                Done — acted on it
              </button>
              <button onClick={() => review.mutate({ id: s.id, status: 'UNDER_REVIEW' })}
                disabled={review.isPending}
                className="min-h-[44px] px-4 rounded-xl glass-card text-sm text-ink-secondary">
                Looking into it
              </button>
              <button onClick={() => review.mutate({ id: s.id, status: 'DISMISSED' })}
                disabled={review.isPending}
                className="min-h-[44px] px-4 rounded-xl border border-status-failed/40
                  text-status-failed text-sm font-semibold">
                Close
              </button>
            </div>
          </div>
        ) : (
          <button onClick={() => { setOpen(s.id); setReply('') }}
            className="text-xs font-semibold text-ink-tertiary hover:text-ink-primary">
            Respond
          </button>
        )
      ) : null}
    </div>
  )

  return (
    <ErrorBoundary level="screen">
      <div className="p-4 max-w-3xl mx-auto">
        <div className="mb-5">
          <h1 className="text-2xl font-bold text-ink-primary font-serif">Suggestions</h1>
          <p className="text-xs text-ink-tertiary mt-0.5">
            What staff sent up. A note marked for the owner only never appears on a
            manager's screen — not here, not anywhere.
          </p>
        </div>

        {isLoading && <div className="space-y-3">{[1,2].map(i => <Skeleton key={i} variant="text" className="w-full h-24" />)}</div>}
        {isError && <p className="text-sm text-ink-tertiary">Couldn&apos;t load these. Check the connection.</p>}

        {!isLoading && !isError && items.length === 0 && (
          <EmptyState icon={<Icon name="bell" size={40} />} title="Nothing yet"
            description="Staff can write to you from the phone app, privately if they choose." />
        )}

        {priv.length > 0 && (
          <section className="mb-6 space-y-3">
            <h2 className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary">
              For you only
            </h2>
            {priv.map(s => <Card key={s.id} s={s} />)}
          </section>
        )}

        {mgmt.length > 0 && (
          <section className="space-y-3">
            <h2 className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary">
              To management
            </h2>
            {mgmt.map(s => <Card key={s.id} s={s} />)}
          </section>
        )}
      </div>
    </ErrorBoundary>
  )
}
