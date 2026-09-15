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

/**
 * An audit line, written the way the owner would say it.
 *
 * The trail is the screen that has to survive an argument — "who voided that,
 * and when" — so it is the last place that should be written in code. It read
 * `booking.waiver.create` and `order_item.ready` with a raw row id beneath,
 * which is fine for me and useless to the person who owns the resort.
 *
 * Rule first, table second. Actions are consistently `noun.verb`, so the rule
 * handles the ninety-odd that exist and any the owner's own new roles create
 * later; the table only overrides the ones where plain de-underscoring would
 * read oddly. A code with no entry still comes out as words, never as a dot.
 */
const SAID: Record<string, string> = {
  'user.login':                 'signed in',
  'user.self_register':         'created their own account',
  'user.login.pending_pin_setup':'signed in, PIN not set yet',
  'auth.login.rate_limited':    'was blocked after too many sign-in attempts',
  'hr.clock_in':                'clocked in',
  'hr.clock_out':               'clocked out',
  'hr.roster.assign':           'put someone on a station',
  'hr.leave.create':            'requested leave',
  'order.create':               'started an order',
  'order.send':                 'sent an order to the kitchen',
  'order_item.receive':         'started cooking an item',
  'order_item.ready':           'marked an item ready',
  'order_item.serve':           'served an item',
  'order_item.cancel':          'cancelled an item',
  'tab.open':                   'opened an account',
  'tab.close':                  'closed an account',
  'payment.record':             'recorded a payment',
  'payment.stk_requested':      'sent an M-Pesa prompt to a guest',
  'payment.stk_confirmed':      'had an M-Pesa payment confirmed by Safaricom',
  'payment.mpesa_c2b':          'received an M-Pesa payment to the till',
  'gate.issue_band':            'issued a wristband',
  'gate.band.deactivate':       'closed a wristband',
  'gate.deactivate_band':       'closed a wristband',
  'gate.forfeit_day':           "closed the day's unused wristband credit",
  'booking.check_in':           'checked a guest in',
  'booking.check_out':          'checked a guest out',
  'booking.waiver.create':      'recorded a signed waiver',
  'booking.occupant.add':       'added someone to a villa',
  'menu.recipe.set':            'set a recipe',
  'inventory.purchase':         'recorded a purchase',
  'inventory.count':            'counted stock',
  'finance.cash.reconcile':     'reconciled cash',
  'incident.log':               'logged an incident',
  'incident.action':            'actioned an incident',
  'housekeeping.auto_dirty':    'marked a room for cleaning (automatic)',
  'calendar.create':            'marked a date on the calendar',
  'booking.payment':            'took a booking payment',
  'booking.create':             'made a booking',
  'booking.confirm':            'confirmed a booking',
  'booking.resource.create':    'added a villa',
  'booking.resource.disable':   'took a villa out of service',
  'feedback.create':            'left guest feedback',
  'equipment.maintenance':      'logged equipment maintenance',
  'equipment.create':           'added equipment',
  'equipment.disable':          'took equipment out of service',
  'suggestion.submit':          'sent a suggestion',
  'suggestion.review':          'answered a suggestion',
  'purchase_request.create':    'raised a purchase request',
  'purchase_request.propose':   'costed a purchase request',
  'purchase_request.approve':   'approved a purchase',
  'purchase_request.reject':    'rejected a purchase',
  'hr.leave.approve':           'approved leave',
  'hr.leave.reject':            'rejected leave',
  'hr.roster.generate':         "generated the day's roster",
  'hr.profile.set_payment':     'set a wage rate',
  'hr.profile.create':          'added a staff record',
  'hr.profile.disable':         'switched off a staff record',
  'hr.shift.create':            'scheduled a shift',
  'hr.shift.cancel':            'cancelled a shift',
  'guest.rename':               'corrected a guest name',
  'user.password_reset':        'reset a password',
  'password.lockout':           'was locked out after failed attempts',
  'upload.receipt':             'attached a receipt photo',
  'housekeeping.start':         'started cleaning a room',
  'housekeeping.assign':        'assigned a room to a cleaner',
  'housekeeping.complete':      'finished cleaning a room',
  'event_type.create':          'added an event type',
  'menu.item.create':           'added a menu item',
  'menu.item.edit':             'changed a menu item',
  'menu.item.disable':          'took a menu item off the menu',
  'inventory.item.create':      'added a stock item',
  'inventory.item.edit':        'changed a stock item',
  'inventory.item.disable':     'switched off a stock item',
  'user.create':                'created an account',
  'user.edit':                  'changed an account',
  'user.activate':              'switched an account on',
  'user.deactivate':            'switched an account off',
  'supplier.create':            'added a supplier',
  'audit.verify':               'verified the history',
}

// Guest-message rows written before the enum leak was fixed read
// "guest.notify.MessageType.BOOKING_CONFIRMED.sms". They are append-only, so
// they stay as written and are translated on the way out instead.
function guestMessage(action: string): string | null {
  const m = action.match(/^guest\.notify\.(?:MessageType\.)?([A-Za-z_]+)\.(\w+)$/)
  if (!m) return null
  const kind = m[1].toLowerCase().replace(/_/g, ' ')
  const how = { sms: 'by SMS', whatsapp: 'by WhatsApp', logged_only: 'recorded only',
                render_error: 'but the message could not be built' }[m[2]] ?? m[2]
  return `sent a guest a ${kind} message ${how}`
}

const THING: Record<string, string> = {
  user: 'account', hr: 'staff record', order_item: 'order line', gate: 'wristband',
  tab: 'account', menu: 'menu', inventory: 'stock', booking: 'booking',
  finance: 'money record', equipment: 'equipment', supplier: 'supplier',
  auth: 'sign-in', guest: 'guest message', judge: 'alert', admin: 'setting',
  suggestion: 'suggestion', conduct: 'conduct record', notification: 'notification',
}
const DID: Record<string, string> = {
  create: 'added', edit: 'changed', disable: 'switched off', enable: 'switched on',
  activate: 'switched on', deactivate: 'switched off', delete: 'removed',
  set: 'set', assign: 'assigned', cancel: 'cancelled', confirm: 'confirmed',
  record: 'recorded', close: 'closed', open: 'opened', send: 'sent',
  log: 'logged', action: 'actioned', reconcile: 'reconciled', count: 'counted',
}

function said(action: string): string {
  const exact = SAID[action]
  if (exact) return exact
  const guest = guestMessage(action)
  if (guest) return guest
  const parts = action.split('.')
  const verb = DID[parts[parts.length - 1]]
  const noun = THING[parts[0]]
  if (verb && noun) {
    const middle = parts.length > 2 ? ` ${parts[1].replace(/_/g, ' ')}` : ''
    return `${verb} a${/^[aeiou]/.test(noun) ? 'n' : ''} ${noun}${middle}`
  }
  // Never fall through to a dotted code. Words, even if clumsy ones.
  return action.replace(/[._]/g, ' ')
}

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
              {actions.map(a => <option key={a} value={a}>{said(a)}</option>)}
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
                      <span className="text-xs text-ink-primary">{said(e.action)}</span>
                      <span className="text-[10px] uppercase tracking-wide text-ink-tertiary">
                        {domainOf(e.action)}
                      </span>
                    </div>
                    {e.target && (
                      <p className="text-[10px] font-mono text-ink-tertiary mt-0.5 truncate"
                         title={e.target}>ref {e.target.slice(0, 8)}</p>
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
