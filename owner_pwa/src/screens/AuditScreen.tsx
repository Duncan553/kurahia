import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Skeleton, EmptyState, SearchInput, Button, Icon, resortToday } from '@shared'
import api from '../lib/axios'

/**
 * Owner-only view of the hash-chained audit trail.
 *
 * The trail was reachable only through `flask audit verify-chain`, so the
 * question it exists to answer — "who voided that order at 9pm?" — needed an
 * SSH session. This is that question, answerable.
 *
 * Owner-only is deliberate: the log records what managers did, so a manager
 * reading their own trail is not a control. The server enforces it; this screen
 * simply is not in the manager's navigation.
 */

interface Entry {
  id: string
  actor: string
  action: string
  target: string | null
  details: string | null
  timestamp: string
}
interface LogPage {
  total: number
  limit: number
  offset: number
  entries: Entry[]
}
interface Verification {
  intact: boolean
  detail: string
  entries_checked: number
}

const PAGE = 50

/** Group a verb like "menu.item.edit" by its first segment, for colouring. */
function domainOf(action: string) {
  return action.split('.')[0]
}

// Actions worth spotting at a glance in a wall of rows. Money leaving, history
// being changed, or access being granted — the three things an owner scans for.
const NOTABLE = /(cancel|refund|reversal|void|delete|deactivate|disable|price|role|rate_limited)/i

function timeOf(iso: string) {
  const d = new Date(iso)
  return d.toLocaleString('en-KE', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
  })
}

export default function AuditScreen() {
  const [actor, setActor] = useState('')
  const [action, setAction] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [offset, setOffset] = useState(0)

  const params = new URLSearchParams()
  if (actor) params.set('actor', actor)
  if (action) params.set('action', action)
  if (from) params.set('from', from)
  if (to) params.set('to', to)
  params.set('limit', String(PAGE))
  params.set('offset', String(offset))

  const { data, isLoading, isError } = useQuery<LogPage>({
    queryKey: ['audit-logs', actor, action, from, to, offset],
    queryFn: () => api.get<LogPage>(`/audit/logs?${params}`).then(r => r.data),
    staleTime: 30_000,
  })

  // The distinct verbs actually present, so the filter offers real options
  // rather than asking the owner to guess what the system calls things.
  const { data: actions = [] } = useQuery<string[]>({
    queryKey: ['audit-actions'],
    queryFn: () => api.get<string[]>('/audit/actions').then(r => r.data),
    staleTime: 5 * 60_000,
  })

  // Verification is opt-in: it re-walks every entry, which is not something to
  // run on every page load.
  const [checkNow, setCheckNow] = useState(false)
  const { data: check, isFetching: checking } = useQuery<Verification>({
    queryKey: ['audit-verify'],
    queryFn: () => api.get<Verification>('/audit/verify').then(r => r.data),
    enabled: checkNow,
    staleTime: 60_000,
  })

  // `data?.entries.length` would still throw if `entries` were missing —
  // optional chaining stops at `data`. That is exactly what happened when
  // /audit was absent from vite.config's PROXIED_PATHS: Vite answered with
  // index.html, axios handed back an HTML STRING, and the screen crashed
  // instead of showing that the request had failed.
  const total = data?.total ?? 0
  const entries = Array.isArray(data?.entries) ? data.entries : []
  const shown = entries.length

  return (
    <div className="p-4 md:p-6 max-w-5xl mx-auto space-y-4">

      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-ink-primary font-serif">Audit Trail</h1>
          <p className="text-xs text-ink-secondary mt-0.5">
            Every write, hash-chained. Editing or deleting history breaks the chain.
          </p>
        </div>
        <Button variant="ghost" size="sm" loading={checking}
          onClick={() => setCheckNow(true)}>
          Verify history
        </Button>
      </div>

      {/* Chain state — the part that makes the trail evidence rather than a list */}
      {check && (
        <div className={`glass-card rounded-2xl p-4 flex items-start gap-3 border-l-4 ${
          check.intact ? 'border-l-status-paid' : 'border-l-status-failed'
        }`}>
          <Icon name={check.intact ? 'check' : 'alert'} size={20}
            className={check.intact ? 'text-status-paid' : 'text-status-failed'} />
          <div className="min-w-0">
            <p className={`text-sm font-semibold ${
              check.intact ? 'text-status-paid' : 'text-status-failed'}`}>
              {check.intact ? 'History intact' : 'Chain broken'}
            </p>
            <p className="text-xs text-ink-secondary mt-0.5">{check.detail}</p>
            <p className="text-[11px] text-ink-tertiary mt-1 tabular-nums">
              {check.entries_checked.toLocaleString()} entries checked
            </p>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="glass-card rounded-2xl p-4 space-y-3">
        <SearchInput
          value={actor}
          onChange={v => { setActor(v); setOffset(0) }}
          placeholder="Who — e.g. joyce"
        />
        <div className="grid sm:grid-cols-3 gap-3">
          <div>
            <label htmlFor="audit-action"
              className="block text-[10px] tracking-widest uppercase text-ink-secondary mb-1">
              Action
            </label>
            <select
              id="audit-action"
              value={action}
              onChange={e => { setAction(e.target.value); setOffset(0) }}
              style={{ colorScheme: 'dark' }}
              className="w-full min-h-[44px] rounded-xl glass-card bg-transparent px-3 py-2
                text-sm text-ink-primary focus:outline-none focus:border-primary-main"
            >
              <option value="">Everything</option>
              {actions.map(a => <option key={a} value={a}>{a}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="audit-from"
              className="block text-[10px] tracking-widest uppercase text-ink-secondary mb-1">
              From
            </label>
            <input id="audit-from" type="date" max={resortToday()}
              value={from} onChange={e => { setFrom(e.target.value); setOffset(0) }}
              style={{ colorScheme: 'dark' }}
              className="w-full min-h-[44px] rounded-xl glass-card bg-transparent px-3 py-2
                text-sm text-ink-primary focus:outline-none focus:border-primary-main" />
          </div>
          <div>
            <label htmlFor="audit-to"
              className="block text-[10px] tracking-widest uppercase text-ink-secondary mb-1">
              To
            </label>
            <input id="audit-to" type="date" max={resortToday()}
              value={to} onChange={e => { setTo(e.target.value); setOffset(0) }}
              style={{ colorScheme: 'dark' }}
              className="w-full min-h-[44px] rounded-xl glass-card bg-transparent px-3 py-2
                text-sm text-ink-primary focus:outline-none focus:border-primary-main" />
          </div>
        </div>
      </div>

      {isLoading && <div className="space-y-2">{[1,2,3,4].map(i => <Skeleton key={i} variant="row" />)}</div>}

      {isError && (
        <p className="text-sm text-status-failed text-center py-8">
          Could not load the trail. Only the owner can read it.
        </p>
      )}

      {data && shown === 0 && (
        <EmptyState
          icon={<Icon name="alert" size={40} />}
          title="Nothing matches"
          description="No entries for those filters. Try widening the dates or clearing the action."
        />
      )}

      {data && shown > 0 && (
        <>
          <p className="text-xs text-ink-tertiary tabular-nums">
            {offset + 1}–{offset + shown} of {total.toLocaleString()}
          </p>

          <div className="space-y-1.5">
            {entries.map(e => {
              const notable = NOTABLE.test(e.action)
              return (
                <div key={e.id}
                  className={`glass-card rounded-xl px-4 py-3 flex items-start gap-3 ${
                    notable ? 'border-l-2 border-l-status-pending' : ''}`}>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-semibold text-ink-primary">{e.actor}</span>
                      <span className="text-xs font-mono text-primary-light">{e.action}</span>
                      <span className="text-[10px] uppercase tracking-wide text-ink-tertiary">
                        {domainOf(e.action)}
                      </span>
                    </div>
                    {e.target && (
                      <p className="text-xs text-ink-secondary mt-0.5 truncate">on {e.target}</p>
                    )}
                    {/* The details carry the answer — "price 1800 -> 900" is the
                        whole reason to open this screen. */}
                    {e.details && (
                      <p className="text-xs text-ink-primary mt-1 font-mono break-words">{e.details}</p>
                    )}
                  </div>
                  <span className="text-[11px] text-ink-tertiary tabular-nums shrink-0">
                    {timeOf(e.timestamp)}
                  </span>
                </div>
              )
            })}
          </div>

          <div className="flex items-center justify-between gap-2 pt-2">
            <Button variant="ghost" size="sm"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE))}>
              Newer
            </Button>
            <Button variant="ghost" size="sm"
              disabled={offset + shown >= total}
              onClick={() => setOffset(offset + PAGE)}>
              Older
            </Button>
          </div>
        </>
      )}
    </div>
  )
}
