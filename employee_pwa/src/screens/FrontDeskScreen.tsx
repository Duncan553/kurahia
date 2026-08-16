import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { Skeleton, EmptyState, StatusBadge, Button, useToastStore, ErrorBoundary } from '@shared'
import { RequireRole } from '../components/AuthGate'
import api from '../lib/axios'
import { formatTime } from '../lib/format'

interface ArrivalRow {
  booking_id: string
  guest_name: string
  resource: string | null
  status: string
  deposit_paid: string
  deposit_required: string
}

interface DepartureRow {
  booking_id: string
  guest_name: string
  resource: string | null
  tab_balance: string
}

interface OccupancyRow {
  booking_id: string
  guest_name: string
  resource: string | null
  tab_id: string | null
  tab_balance: string
}

interface PendingWaiver {
  booking_id: string
  guest_name: string
  resource: string
  check_in: string
}

interface FrontDeskData {
  date: string
  arrivals: ArrivalRow[]
  departures: DepartureRow[]
  occupancy: OccupancyRow[]
  pending_waivers: PendingWaiver[]
}

type Tab = 'arrivals' | 'departures' | 'occupancy'

function ksh(amount: string): string {
  const n = parseFloat(amount)
  return isNaN(n) ? '—' : `KSh ${n.toLocaleString()}`
}

function depositStatus(paid: string, required: string): 'paid' | 'pending' {
  return parseFloat(paid) >= parseFloat(required) ? 'paid' : 'pending'
}

const fadeIn = { hidden: { opacity: 0, y: 12 }, visible: { opacity: 1, y: 0 } }
const stagger = { visible: { transition: { staggerChildren: 0.06 } } }

const extractErr = (e: unknown) =>
  (e as { response?: { data?: { error?: string } } })?.response?.data?.error ?? 'Something went wrong.'

export default function FrontDeskScreen() {
  const [tab, setTab] = useState<Tab>('arrivals')
  const [band, setBand] = useState('')
  const navigate = useNavigate()
  const addToast = useToastStore(s => s.addToast)

  // Wristband lookup: find a guest's band tab and navigate to charge against it
  const bandMut = useMutation({
    mutationFn: (num: string) =>
      api.get<{ tab_id: string; status: string }>(`/gate/bands/${num.trim()}`).then(r => r.data),
    onSuccess: (data) => {
      if (data.status !== 'ACTIVE') {
        addToast({ type: 'error', message: 'That band is not active.' })
        return
      }
      navigate(`/pos/tabs/${data.tab_id}`)
    },
    onError: (e) => addToast({ type: 'error', message: extractErr(e) }),
  })

  const { data, isLoading, isError, dataUpdatedAt } = useQuery<FrontDeskData>({
    queryKey: ['front-desk-today'],
    queryFn: () => api.get<FrontDeskData>('/front-desk/today').then((r) => r.data),
    staleTime: 2 * 60_000,
    refetchInterval: 5 * 60_000,
  })

  const counts = {
    arrivals:   data?.arrivals.length   ?? 0,
    departures: data?.departures.length ?? 0,
    occupancy:  data?.occupancy.length  ?? 0,
  }

  const lastUpdated = dataUpdatedAt
    ? new Date(dataUpdatedAt).toLocaleTimeString('en-KE', {
        timeZone: 'Africa/Nairobi',
        hour: '2-digit',
        minute: '2-digit',
      })
    : null

  return (
    <RequireRole minLevel={5}>
      <ErrorBoundary level="tile">
      <div className="min-h-screen p-4 md:p-6">
        <motion.div className="max-w-6xl mx-auto"
          initial="hidden" animate="visible" variants={stagger}>

        {/* Header + hero stats */}
        <motion.div variants={fadeIn} transition={{ duration: 0.3, ease: 'easeOut' }}
          className="flex flex-col md:flex-row md:items-end md:justify-between gap-4 mb-8">
          <div>
            <h1 className="text-3xl font-bold text-ink-primary font-serif">Front Desk</h1>
            <p className="text-sm text-ink-tertiary mt-1">
              {data?.date ?? 'Today'}
              {lastUpdated ? ` · updated ${lastUpdated}` : ''}
            </p>
          </div>
          <div className="flex gap-4">
            <div className="glass-card px-5 py-3 text-center">
              <p className="text-2xl font-bold tabular-nums text-ink-primary">{counts.arrivals}</p>
              <p className="text-[10px] uppercase tracking-widest text-ink-tertiary">Arrivals</p>
            </div>
            <div className="glass-card px-5 py-3 text-center">
              <p className="text-2xl font-bold tabular-nums text-ink-primary">{counts.departures}</p>
              <p className="text-[10px] uppercase tracking-widest text-ink-tertiary">Departures</p>
            </div>
            <div className="glass-card px-5 py-3 text-center">
              <p className="text-2xl font-bold tabular-nums text-[#fa5c29]">{counts.occupancy}</p>
              <p className="text-[10px] uppercase tracking-widest text-ink-tertiary">In-House</p>
            </div>
          </div>
        </motion.div>

        {/* Wristband lookup — look up guest tab by band number */}
        <motion.div variants={fadeIn} transition={{ duration: 0.3, ease: 'easeOut' }}
          className="flex gap-2">
          <input
            type="number" min="1" inputMode="numeric"
            aria-label="Wristband number"
            placeholder="Wristband # — look up guest tab"
            value={band}
            onChange={e => setBand(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && band && bandMut.mutate(band)}
            className="flex-1 rounded-xl glass-card bg-transparent px-4 py-2.5
              text-sm text-ink-primary placeholder:text-ink-tertiary
              focus:outline-none focus:border-primary-main focus-visible:ring-2 focus-visible:ring-primary-main"
          />
          <Button variant="ghost" size="sm" loading={bandMut.isPending}
            onClick={() => band && bandMut.mutate(band)}>
            Open Band
          </Button>
        </motion.div>

        {/* Pending waivers warning banner */}
        <AnimatePresence>
          {(data?.pending_waivers.length ?? 0) > 0 && (
            <motion.div
              initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }}
              transition={{ duration: 0.3, ease: 'easeOut' }}
              className="rounded-xl bg-status-failed/5 border border-status-failed/20 p-4">
              <p className="text-sm font-semibold text-status-failed">
                {data!.pending_waivers.length} water activity booking
                {data!.pending_waivers.length !== 1 ? 's' : ''} missing waiver
              </p>
              <div className="mt-1.5 space-y-1">
                {data!.pending_waivers.map((w) => (
                  <p key={w.booking_id} className="text-xs text-ink-secondary">
                    {w.guest_name} · {w.resource} · check-in {formatTime(w.check_in)}
                  </p>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Tabs with live counts */}
        <motion.div variants={fadeIn} transition={{ duration: 0.3, ease: 'easeOut' }}
          className="flex gap-1 bg-cream-alt/50 rounded-xl p-1">
          {(['arrivals', 'departures', 'occupancy'] as Tab[]).map((t) => (
            <motion.button
              key={t}
              onClick={() => setTab(t)}
              whileTap={{ scale: 0.97 }}
              className={[
                'flex-1 py-2 min-h-[44px] rounded-lg text-xs font-medium capitalize transition-all',
                tab === t ? 'bg-white/8 shadow-sm text-ink-primary' : 'text-ink-tertiary hover:text-ink-secondary',
              ].join(' ')}
            >
              {t.charAt(0).toUpperCase() + t.slice(1)}
              {!isLoading && (
                <span className={[
                  'ml-1 text-[10px] font-bold',
                  tab === t ? 'text-ink-primary' : 'text-ink-tertiary',
                ].join(' ')}>
                  ({counts[t]})
                </span>
              )}
            </motion.button>
          ))}
        </motion.div>

        {isLoading && (
          <div className="space-y-3">
            {[1,2,3].map((i) => <Skeleton key={i} variant="row" />)}
          </div>
        )}

        {isError && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            transition={{ duration: 0.25 }}
            className="p-4 rounded-xl bg-cream-alt/40 text-sm text-ink-tertiary text-center">
            Couldn't load front desk data. Check connection.
          </motion.div>
        )}

        {/* Arrivals */}
        <AnimatePresence mode="wait">
          {tab === 'arrivals' && !isLoading && (
            <motion.div key="arrivals"
              initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
              transition={{ duration: 0.25, ease: 'easeOut' }}>
              {counts.arrivals === 0 ? (
                <EmptyState
                  icon={
                    <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
                      <path d="M24 8L8 24h8v14h16V24h8L24 8z" stroke="currentColor" strokeWidth="1.5"
                        strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  }
                  title="No arrivals expected today."
                />
              ) : (
                <div className="space-y-2">
                  {data!.arrivals.map((a) => {
                    const depStatus = depositStatus(a.deposit_paid, a.deposit_required)
                    return (
                      <div key={a.booking_id}
                        className="glass-card rounded-2xl px-4 py-3 space-y-1.5">
                        <div className="flex items-start justify-between gap-2">
                          <p className="text-sm font-semibold text-ink-primary">{a.guest_name}</p>
                          <StatusBadge status={depStatus} />
                        </div>
                        {a.resource && (
                          <p className="text-xs text-ink-tertiary">{a.resource}</p>
                        )}
                        <div className="flex gap-4 text-xs text-ink-tertiary">
                          <span>Deposit paid: <span className={`font-medium ${depStatus === 'paid' ? 'text-status-paid' : 'text-status-pending'}`}>
                            {ksh(a.deposit_paid)}
                          </span></span>
                          <span>Required: <span className="font-medium text-ink-primary">{ksh(a.deposit_required)}</span></span>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </motion.div>
          )}

          {/* Departures */}
          {tab === 'departures' && !isLoading && (
            <motion.div key="departures"
              initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
              transition={{ duration: 0.25, ease: 'easeOut' }}>
              {counts.departures === 0 ? (
                <EmptyState
                  icon={
                    <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
                      <path d="M24 40L8 24h8V10h16v14h8L24 40z" stroke="currentColor" strokeWidth="1.5"
                        strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  }
                  title="No departures expected today."
                />
              ) : (
                <div className="space-y-2">
                  {data!.departures.map((d) => {
                    const bal = parseFloat(d.tab_balance)
                    const hasBalance = !isNaN(bal) && bal > 0
                    return (
                      <div key={d.booking_id}
                        className={[
                          'rounded-2xl px-4 py-3 space-y-1.5',
                          hasBalance
                            ? 'border border-status-pending/30 bg-status-pending/5'
                            : 'glass-card',
                        ].join(' ')}>
                        <div className="flex items-start justify-between gap-2">
                          <p className="text-sm font-semibold text-ink-primary">{d.guest_name}</p>
                          {hasBalance && (
                            <span className="text-xs font-semibold text-status-pending">
                              Outstanding
                            </span>
                          )}
                        </div>
                        {d.resource && (
                          <p className="text-xs text-ink-tertiary">{d.resource}</p>
                        )}
                        <p className="text-xs text-ink-tertiary">
                          Tab balance:{' '}
                          <span className={`font-semibold ${hasBalance ? 'text-status-pending' : 'text-status-paid'}`}>
                            {ksh(d.tab_balance)}
                          </span>
                        </p>
                      </div>
                    )
                  })}
                </div>
              )}
            </motion.div>
          )}

          {/* Occupancy */}
          {tab === 'occupancy' && !isLoading && (
            <motion.div key="occupancy"
              initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
              transition={{ duration: 0.25, ease: 'easeOut' }}>
              {counts.occupancy === 0 ? (
                <EmptyState
                  icon={
                    <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
                      <rect x="8" y="14" width="32" height="26" rx="3" stroke="currentColor" strokeWidth="1.5"/>
                      <path d="M16 14V10a8 8 0 0116 0v4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                      <circle cx="24" cy="27" r="3" stroke="currentColor" strokeWidth="1.5"/>
                      <path d="M24 30v4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                    </svg>
                  }
                  title="No guests checked in."
                />
              ) : (
                <div className="space-y-2">
                  {data!.occupancy.map((o) => {
                    const bal = parseFloat(o.tab_balance)
                    const hasBalance = !isNaN(bal) && bal > 0
                    const clickable = !!o.tab_id
                    return (
                      <motion.div
                        key={o.booking_id}
                        whileTap={clickable ? { scale: 0.98 } : undefined}
                        onClick={() => o.tab_id && navigate(`/pos/tabs/${o.tab_id}`)}
                        className={[
                          'glass-card rounded-2xl px-4 py-3 space-y-1.5',
                          clickable ? 'cursor-pointer hover:bg-cream-alt/60 transition-colors' : '',
                        ].join(' ')}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <p className="text-sm font-semibold text-ink-primary">{o.guest_name}</p>
                          {clickable && (
                            <span className="text-[10px] text-ink-tertiary">View tab →</span>
                          )}
                        </div>
                        {o.resource && (
                          <p className="text-xs text-ink-tertiary">{o.resource}</p>
                        )}
                        <p className="text-xs text-ink-tertiary">
                          Running tab:{' '}
                          <span className={`font-semibold ${hasBalance ? 'text-ink-primary' : 'text-ink-tertiary'}`}>
                            {ksh(o.tab_balance)}
                          </span>
                        </p>
                      </motion.div>
                    )
                  })}
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
      </div>
      </ErrorBoundary>
    </RequireRole>
  )
}
