/**
 * LostFoundScreen — the box behind the front desk, written down.
 *
 * The API for this (app/lost_found/) has existed the whole time with no screen
 * anywhere in any of the three apps: a guest left a jacket by the pool and
 * there was nowhere to put that fact. Same shape as the equipment register and
 * the conduct rules before them — an endpoint with no door.
 *
 * Who can do what follows the API, and the split is deliberate:
 *   log an item     — anyone on shift, because anyone can find a phone
 *   read the list   — front desk and above, because that is who gets asked
 *   hand it back    — manager and above, because "yes, that iPhone is mine"
 *                     is where the risk lives and it needs a signature
 */
import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Button, Input, Drawer, StatusBadge, EmptyState, Skeleton, Icon,
  useToastStore, ErrorBoundary,
} from '@shared'
import type { StatusValue } from '@shared'
import { useAuthStore } from '../stores/authStore'
import api from '../lib/axios'

interface Item {
  id: string
  description: string
  found_location: string
  found_by_name: string | null
  found_at: string | null
  status: 'UNCLAIMED' | 'CLAIMED' | 'DISPOSED'
  claimed_by_name: string | null
  claimed_at: string | null
  notes: string | null
}

const BADGE: Record<Item['status'], StatusValue> = {
  UNCLAIMED: 'pending', CLAIMED: 'resolved', DISPOSED: 'inactive',
}

const extractErr = (e: unknown) =>
  (e as { response?: { data?: { error?: string } } })?.response?.data?.error
  ?? 'Something went wrong.'

// "16 Sept, 14:20" — the two things you need to judge how long it has sat.
function when(iso: string | null) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
    + ', ' + d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
}

function LostFound() {
  const qc = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  const level = useAuthStore(s => s.user?.role_level ?? 0)
  const canRelease = level >= 5          // PATCH is manager+ on the API too

  const [logging, setLogging] = useState(false)
  const [desc, setDesc] = useState('')
  const [place, setPlace] = useState('')
  const [notes, setNotes] = useState('')

  const [claiming, setClaiming] = useState<Item | null>(null)
  const [claimant, setClaimant] = useState('')

  const [filter, setFilter] = useState<'UNCLAIMED' | 'ALL'>('UNCLAIMED')

  const { data: items = [], isLoading, isError } = useQuery<Item[]>({
    queryKey: ['lost-found'],
    queryFn: () => api.get<Item[]>('/lost-found').then(r => Array.isArray(r.data) ? r.data : []),
    staleTime: 30_000,
  })

  const shown = filter === 'ALL' ? items : items.filter(i => i.status === 'UNCLAIMED')

  const log = useMutation({
    mutationFn: () => api.post('/lost-found', {
      description: desc.trim(),
      found_location: place.trim(),
      notes: notes.trim() || undefined,
    }),
    onSuccess: () => {
      addToast({ message: 'Logged. It is in the book now.', type: 'success' })
      setDesc(''); setPlace(''); setNotes(''); setLogging(false)
      qc.invalidateQueries({ queryKey: ['lost-found'] })
    },
    onError: (e) => addToast({ message: extractErr(e), type: 'error' }),
  })

  const release = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      api.patch(`/lost-found/${id}`, { status: 'CLAIMED', claimed_by_name: name.trim() }),
    onSuccess: () => {
      addToast({ message: 'Marked as returned.', type: 'success' })
      setClaiming(null); setClaimant('')
      qc.invalidateQueries({ queryKey: ['lost-found'] })
    },
    onError: (e) => addToast({ message: extractErr(e), type: 'error' }),
  })

  const dispose = useMutation({
    mutationFn: (id: string) => api.patch(`/lost-found/${id}`, { status: 'DISPOSED' }),
    onSuccess: () => {
      addToast({ message: 'Written off.', type: 'success' })
      qc.invalidateQueries({ queryKey: ['lost-found'] })
    },
    onError: (e) => addToast({ message: extractErr(e), type: 'error' }),
  })

  const unclaimed = items.filter(i => i.status === 'UNCLAIMED').length

  return (
    <div className="p-4 sm:p-6 max-w-3xl mx-auto space-y-4">

      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-serif text-ink-primary">Lost &amp; Found</h1>
          <p className="text-sm text-ink-tertiary">
            {unclaimed === 0
              ? 'Nothing waiting to be claimed.'
              : `${unclaimed} item${unclaimed === 1 ? '' : 's'} waiting to be claimed.`}
          </p>
        </div>
        <Button onClick={() => setLogging(true)}>Log an item</Button>
      </div>

      {/* Two tabs, not five: what is still here, and everything ever. */}
      <div className="flex gap-2">
        {(['UNCLAIMED', 'ALL'] as const).map(f => (
          <button key={f} onClick={() => setFilter(f)}
            className={[
              'px-3 py-1.5 rounded-full text-xs font-medium min-h-[36px]',
              filter === f
                ? 'bg-ink-primary/10 text-ink-primary'
                : 'text-ink-tertiary hover:text-ink-secondary',
            ].join(' ')}>
            {f === 'UNCLAIMED' ? 'Still here' : 'Everything'}
          </button>
        ))}
      </div>

      {isLoading && <Skeleton variant="text" className="w-full h-24" />}
      {isError && <p className="text-sm text-ink-tertiary">Couldn&apos;t load this.</p>}

      {!isLoading && !isError && shown.length === 0 && (
        <EmptyState
          icon={<Icon name="circle" size={40} />}
          title={filter === 'UNCLAIMED' ? 'Nothing in the box' : 'Nothing logged yet'}
          description="When a guest leaves something behind, log it here so the next person on the desk can answer for it."
        />
      )}

      {shown.map(i => (
        <div key={i.id} className="glass-card rounded-2xl p-4 space-y-2">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-sm text-ink-primary font-medium">{i.description}</p>
              <p className="text-xs text-ink-tertiary">
                {i.found_location}
                {i.found_at && ` · ${when(i.found_at)}`}
                {i.found_by_name && ` · handed in by ${i.found_by_name}`}
              </p>
            </div>
            <StatusBadge status={BADGE[i.status]} size="sm" />
          </div>

          {i.notes && <p className="text-xs text-ink-secondary">{i.notes}</p>}

          {i.status === 'CLAIMED' && i.claimed_by_name && (
            <p className="text-xs text-ink-tertiary">
              Returned to {i.claimed_by_name}{i.claimed_at && ` on ${when(i.claimed_at)}`}
            </p>
          )}

          {i.status === 'UNCLAIMED' && canRelease && (
            <div className="flex gap-2 pt-1">
              <Button size="sm" onClick={() => { setClaiming(i); setClaimant('') }}>
                Someone claimed it
              </Button>
              <Button size="sm" variant="ghost" onClick={() => dispose.mutate(i.id)}>
                Write off
              </Button>
            </div>
          )}
          {i.status === 'UNCLAIMED' && !canRelease && (
            // Said out loud rather than shown as a button that answers "not
            // yours" — the mistake the Cash tile made for front desk.
            <p className="text-xs text-ink-tertiary">A manager hands this back.</p>
          )}
        </div>
      ))}

      {/* ── Log a found item ─────────────────────────────────────────── */}
      <Drawer open={logging} onClose={() => setLogging(false)} title="Log a found item">
        <div className="space-y-3">
          <Input label="What is it?" value={desc} onChange={e => setDesc(e.target.value)}
            placeholder="Blue denim jacket, size M" />
          <Input label="Where was it found?" value={place} onChange={e => setPlace(e.target.value)}
            placeholder="Pool deck, by the far loungers" />
          <Input label="Anything else? (optional)" value={notes} onChange={e => setNotes(e.target.value)}
            placeholder="Car key in the pocket" />
          <Button className="w-full"
            disabled={!desc.trim() || !place.trim() || log.isPending}
            onClick={() => log.mutate()}>
            {log.isPending ? 'Saving…' : 'Log it'}
          </Button>
        </div>
      </Drawer>

      {/* ── Hand it back ─────────────────────────────────────────────── */}
      <Drawer open={!!claiming} onClose={() => setClaiming(null)} title="Who is taking it?">
        <div className="space-y-3">
          <p className="text-sm text-ink-secondary">{claiming?.description}</p>
          <Input label="Name of the person" value={claimant}
            onChange={e => setClaimant(e.target.value)}
            placeholder="As it appears on their ID" />
          <p className="text-xs text-ink-tertiary">
            The name is kept against the item, with the time and who released it.
          </p>
          <Button className="w-full"
            disabled={!claimant.trim() || release.isPending}
            onClick={() => claiming && release.mutate({ id: claiming.id, name: claimant })}>
            {release.isPending ? 'Saving…' : 'Hand it back'}
          </Button>
        </div>
      </Drawer>
    </div>
  )
}

export default function LostFoundScreen() {
  return <ErrorBoundary><LostFound /></ErrorBoundary>
}
