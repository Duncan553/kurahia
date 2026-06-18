import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Skeleton, EmptyState, StatusBadge } from '@shared'
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

export default function FrontDeskScreen() {
  const [tab, setTab] = useState<Tab>('arrivals')
  const navigate = useNavigate()

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
      <div className="min-h-screen p-4 md:p-6">
        <div className="max-w-2xl mx-auto space-y-4">

        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-xl font-bold text-white font-serif">Front Desk</h1>
            <p className="text-sm text-blue-200/40">
              {data?.date ?? 'Today'} · read-only
              {lastUpdated ? ` · updated ${lastUpdated}` : ''}
            </p>
          </div>
        </div>

        {/* Pending waivers warning banner */}
        {(data?.pending_waivers.length ?? 0) > 0 && (
          <div className="rounded-xl bg-status-failed/5 border border-status-failed/20 p-3">
            <p className="text-sm font-semibold text-status-failed">
              {data!.pending_waivers.length} water activity booking
              {data!.pending_waivers.length !== 1 ? 's' : ''} missing waiver
            </p>
            <div className="mt-1.5 space-y-1">
              {data!.pending_waivers.map((w) => (
                <p key={w.booking_id} className="text-xs text-blue-200/60">
                  {w.guest_name} · {w.resource} · check-in {formatTime(w.check_in)}
                </p>
              ))}
            </div>
          </div>
        )}

        {/* Tabs with live counts */}
        <div className="flex gap-1 bg-cream-alt/50 rounded-xl p-1">
          {(['arrivals', 'departures', 'occupancy'] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={[
                'flex-1 py-2 min-h-[44px] rounded-lg text-xs font-medium capitalize transition-all',
                tab === t ? 'bg-cream-card shadow-sm text-white' : 'text-blue-200/40 hover:text-blue-200/60',
              ].join(' ')}
            >
              {t.charAt(0).toUpperCase() + t.slice(1)}
              {!isLoading && (
                <span className={[
                  'ml-1 text-[10px] font-bold',
                  tab === t ? 'text-white' : 'text-blue-200/40',
                ].join(' ')}>
                  ({counts[t]})
                </span>
              )}
            </button>
          ))}
        </div>

        {isLoading && (
          <div className="space-y-3">
            {[1,2,3].map((i) => <Skeleton key={i} variant="row" />)}
          </div>
        )}

        {isError && (
          <div className="p-4 rounded-xl bg-cream-alt/40 text-sm text-blue-200/40 text-center">
            Couldn't load front desk data. Check connection.
          </div>
        )}

        {/* Arrivals */}
        {tab === 'arrivals' && !isLoading && (
          <>
            {counts.arrivals === 0 ? (
              <EmptyState
                icon={
                  <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
                    <path d="M24 8L8 24h8v14h16V24h8L24 8z" stroke="currentColor" strokeWidth="2"
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
                      className="rounded-2xl border border-white/10 px-4 py-3 space-y-1.5">
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-sm font-semibold text-white">{a.guest_name}</p>
                        <StatusBadge status={depStatus} />
                      </div>
                      {a.resource && (
                        <p className="text-xs text-blue-200/40">{a.resource}</p>
                      )}
                      <div className="flex gap-4 text-xs text-blue-200/40">
                        <span>Deposit paid: <span className={`font-medium ${depStatus === 'paid' ? 'text-status-paid' : 'text-status-pending'}`}>
                          {ksh(a.deposit_paid)}
                        </span></span>
                        <span>Required: <span className="font-medium text-white">{ksh(a.deposit_required)}</span></span>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </>
        )}

        {/* Departures */}
        {tab === 'departures' && !isLoading && (
          <>
            {counts.departures === 0 ? (
              <EmptyState
                icon={
                  <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
                    <path d="M24 40L8 24h8V10h16v14h8L24 40z" stroke="currentColor" strokeWidth="2"
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
                        'rounded-2xl border px-4 py-3 space-y-1.5',
                        hasBalance
                          ? 'border-status-pending/30 bg-status-pending/5'
                          : 'border border-white/10',
                      ].join(' ')}>
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-sm font-semibold text-white">{d.guest_name}</p>
                        {hasBalance && (
                          <span className="text-xs font-semibold text-status-pending">
                            Outstanding
                          </span>
                        )}
                      </div>
                      {d.resource && (
                        <p className="text-xs text-blue-200/40">{d.resource}</p>
                      )}
                      <p className="text-xs text-blue-200/40">
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
          </>
        )}

        {/* Occupancy */}
        {tab === 'occupancy' && !isLoading && (
          <>
            {counts.occupancy === 0 ? (
              <EmptyState
                icon={
                  <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
                    <rect x="8" y="14" width="32" height="26" rx="3" stroke="currentColor" strokeWidth="2"/>
                    <path d="M16 14V10a8 8 0 0116 0v4" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
                    <circle cx="24" cy="27" r="3" stroke="currentColor" strokeWidth="2"/>
                    <path d="M24 30v4" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
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
                    <div
                      key={o.booking_id}
                      onClick={() => o.tab_id && navigate(`/pos/tabs/${o.tab_id}`)}
                      className={[
                        'rounded-2xl border border-white/10 px-4 py-3 space-y-1.5',
                        clickable ? 'cursor-pointer hover:bg-cream-alt/60 transition-colors' : '',
                      ].join(' ')}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-sm font-semibold text-white">{o.guest_name}</p>
                        {clickable && (
                          <span className="text-[10px] text-blue-200/40">View tab →</span>
                        )}
                      </div>
                      {o.resource && (
                        <p className="text-xs text-blue-200/40">{o.resource}</p>
                      )}
                      <p className="text-xs text-blue-200/40">
                        Running tab:{' '}
                        <span className={`font-semibold ${hasBalance ? 'text-white' : 'text-blue-200/40'}`}>
                          {ksh(o.tab_balance)}
                        </span>
                      </p>
                    </div>
                  )
                })}
              </div>
            )}
          </>
        )}
      </div>
      </div>
    </RequireRole>
  )
}
