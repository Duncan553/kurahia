import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { Modal, useToastStore } from '@shared'
import api from '../lib/axios'

// Gate station hub: today's stats + quick issue + inline lookup + waiver alert.
// One screen replaces three separate navigations for gate staff.

const ENTRY_FEE = 3000  // KES — single source of truth in backend, mirrored here

interface Stats {
  issued_today: number
  inside_now: number
  total_entry_fees: string
}

interface BandResult {
  band_number: number
  status: string
  tab_balance: string
  issued_by: string | null
}

interface FrontDeskData {
  pending_waivers: { booking_id: string; guest_name: string; resource: string }[]
}

type Method = 'CASH' | 'MPESA' | 'CARD' | 'BANK_TRANSFER'

const METHODS: { value: Method; label: string }[] = [
  { value: 'CASH',          label: 'Cash'  },
  { value: 'MPESA',         label: 'M-Pesa'},
  { value: 'CARD',          label: 'Card'  },
  { value: 'BANK_TRANSFER', label: 'Bank'  },
]

const kes = (v: string | number) =>
  `KSh ${parseFloat(String(v)).toLocaleString('en-KE', { minimumFractionDigits: 0 })}`

const extractErr = (e: unknown) =>
  (e as { response?: { data?: { error?: string } } })?.response?.data?.error ?? 'Something went wrong.'

function genKey() { return crypto.randomUUID() }

// ── Stats header ─────────────────────────────────────────────────────────────

function StatsBar({ stats }: { stats: Stats | undefined }) {
  const items = [
    { label: 'Inside Now',    value: stats?.inside_now   ?? '—' },
    { label: 'Issued Today',  value: stats?.issued_today ?? '—' },
    { label: 'Entry Revenue', value: stats ? kes(stats.total_entry_fees) : '—' },
  ]
  return (
    <div className="grid grid-cols-3 gap-2 mb-5">
      {items.map(({ label, value }) => (
        <div key={label} className="rounded-2xl border border-cream-alt bg-cream-card p-3 text-center">
          <p className="text-lg font-bold tabular-nums text-ink-primary">{value}</p>
          <p className="text-[10px] text-ink-tertiary uppercase tracking-wide mt-0.5">{label}</p>
        </div>
      ))}
    </div>
  )
}

// ── Issue section ─────────────────────────────────────────────────────────────

function IssueSection({ onIssued }: { onIssued: () => void }) {
  const addToast   = useToastStore(s => s.addToast)
  const [method, setMethod]       = useState<Method>('CASH')
  const [idemKey, setIdemKey]     = useState(genKey)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [lastBand, setLastBand]   = useState<number | null>(null)

  const mut = useMutation({
    mutationFn: () =>
      api.post<{ band_number: number; duplicate?: boolean }>('/gate/issue-band', {
        method, idempotency_key: idemKey,
      }).then(r => r.data),
    onSuccess: (data) => {
      setConfirmOpen(false)
      setLastBand(data.band_number)
      setIdemKey(genKey())
      onIssued()
      const msg = data.duplicate
        ? `Already issued — Band #${data.band_number}`
        : `Band #${data.band_number} issued · ${kes(ENTRY_FEE)} recorded`
      addToast({ type: data.duplicate ? 'warning' : 'success', message: msg })
    },
    onError: (e) => { setConfirmOpen(false); addToast({ type: 'error', message: extractErr(e) }) },
  })

  return (
    <section className="rounded-2xl border border-cream-alt bg-cream-card p-4 space-y-3 mb-4">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-ink-primary">Issue Band</p>
        <p className="text-sm font-bold tabular-nums text-ink-primary">{kes(ENTRY_FEE)}</p>
      </div>

      {/* Payment method toggle */}
      <div className="grid grid-cols-4 gap-1.5">
        {METHODS.map(({ value, label }) => (
          <button key={value} onClick={() => setMethod(value)}
            className={`py-2 rounded-xl text-xs font-semibold border transition-colors ${
              method === value
                ? 'bg-ink-primary text-cream-card border-ink-primary'
                : 'border-cream-alt text-ink-secondary hover:bg-cream-alt'
            }`}>
            {label}
          </button>
        ))}
      </div>

      <motion.button
        whileTap={{ scale: 0.98 }}
        onClick={() => setConfirmOpen(true)}
        disabled={mut.isPending}
        className="w-full py-4 rounded-2xl bg-primary-dark text-cream-card text-base font-semibold
          hover:bg-primary-dark/90 transition-colors disabled:opacity-50"
      >
        {mut.isPending ? 'Issuing…' : 'Issue Band →'}
      </motion.button>

      {lastBand !== null && (
        <p className="text-center text-sm text-ink-tertiary">
          Last issued: <span className="font-bold text-ink-primary">#{lastBand}</span>
        </p>
      )}

      <Modal open={confirmOpen} onClose={() => setConfirmOpen(false)} title="Issue wristband?">
        <p className="text-base text-ink-secondary mb-1">
          Opens a new tab and records{' '}
          <strong className="text-ink-primary">{kes(ENTRY_FEE)}</strong>{' '}
          via {METHODS.find(m => m.value === method)?.label}.
        </p>
        <p className="text-sm text-ink-tertiary mb-6">Payment cannot be reversed.</p>
        <div className="flex gap-3">
          <button onClick={() => setConfirmOpen(false)}
            className="flex-1 py-3 rounded-xl border border-cream-alt text-ink-secondary
              font-medium hover:bg-cream-alt/50 transition-colors">
            Cancel
          </button>
          <button onClick={() => mut.mutate()} disabled={mut.isPending}
            className="flex-1 py-3 rounded-xl bg-primary-dark text-cream-card font-semibold
              hover:bg-primary-dark/90 transition-colors disabled:opacity-50">
            {mut.isPending ? 'Issuing…' : 'Confirm'}
          </button>
        </div>
      </Modal>
    </section>
  )
}

// ── Band lookup section ───────────────────────────────────────────────────────

function LookupSection() {
  const [input, setInput]   = useState('')
  const [query, setQuery]   = useState<number | null>(null)

  const { data, isFetching, isError } = useQuery<BandResult>({
    queryKey: ['gate-lookup', query],
    queryFn: () => api.get<BandResult>(`/gate/bands/${query}`).then(r => r.data),
    enabled: query !== null,
    retry: false,
    staleTime: 10_000,
  })

  function lookup() {
    const n = parseInt(input.trim())
    if (!n || n < 1) return
    setQuery(n)
  }

  const statusColor = (s: string) =>
    s === 'ACTIVE' ? 'text-status-paid' : 'text-ink-tertiary'

  return (
    <section className="rounded-2xl border border-cream-alt bg-cream-card p-4 space-y-3 mb-4">
      <p className="text-sm font-semibold text-ink-primary">Look Up Band</p>
      <div className="flex gap-2">
        <input
          type="number" min="1" inputMode="numeric"
          placeholder="Band number"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && lookup()}
          className="flex-1 rounded-xl border border-cream-alt bg-cream-card px-4 py-2.5
            text-base text-ink-primary focus:outline-none focus:border-primary-dark"
        />
        <button onClick={lookup} disabled={isFetching}
          className="px-5 py-2.5 rounded-xl bg-ink-primary text-cream-card text-sm font-semibold
            hover:bg-ink-primary/90 transition-colors disabled:opacity-50">
          {isFetching ? '…' : 'Look up'}
        </button>
      </div>

      {data && (
        <div className="flex items-center justify-between px-3 py-2 rounded-xl bg-cream-alt/50">
          <div>
            <span className="font-bold text-ink-primary">#{data.band_number}</span>
            <span className={`ml-2 text-sm font-semibold ${statusColor(data.status)}`}>
              {data.status}
            </span>
          </div>
          <div className="text-right">
            <p className="text-sm font-bold tabular-nums text-ink-primary">
              {kes(data.tab_balance)} credit
            </p>
            {data.issued_by && (
              <p className="text-[10px] text-ink-tertiary">by {data.issued_by}</p>
            )}
          </div>
        </div>
      )}

      {isError && query !== null && (
        <p className="text-sm text-status-failed text-center">
          Band #{query} not found for today.
        </p>
      )}
    </section>
  )
}

// ── Waiver alert section ──────────────────────────────────────────────────────

function WaiverAlert() {
  const navigate = useNavigate()
  const { data } = useQuery<FrontDeskData>({
    queryKey: ['front-desk-today'],
    queryFn: () => api.get<FrontDeskData>('/front-desk/today').then(r => r.data),
    staleTime: 2 * 60_000,
    refetchInterval: 5 * 60_000,
  })

  const count = data?.pending_waivers.length ?? 0
  if (count === 0) return null

  return (
    <button
      onClick={() => navigate('/gate/waiver')}
      className="w-full rounded-2xl border border-status-pending/40 bg-status-pending/8
        p-4 text-left flex items-center justify-between gap-3 hover:bg-status-pending/12 transition-colors"
    >
      <div>
        <p className="text-sm font-semibold text-status-pending">
          ⚠ {count} water booking{count !== 1 ? 's' : ''} missing waiver today
        </p>
        <p className="text-xs text-ink-secondary mt-0.5">
          Guests cannot participate until signed.
        </p>
      </div>
      <span className="text-ink-tertiary text-sm shrink-0">Sign →</span>
    </button>
  )
}

// ── Gate hub ──────────────────────────────────────────────────────────────────

export default function GateHubScreen() {
  const qc = useQueryClient()

  const { data: stats, isLoading } = useQuery<Stats>({
    queryKey: ['gate-today-stats'],
    queryFn: () => api.get<Stats>('/gate/today-stats').then(r => r.data),
    staleTime: 30_000,
    refetchInterval: 60_000,
  })

  function refresh() {
    qc.invalidateQueries({ queryKey: ['gate-today-stats'] })
    qc.invalidateQueries({ queryKey: ['gate-active-bands'] })
  }

  return (
    <div className="p-4 max-w-lg mx-auto">

      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-base font-bold tracking-widest uppercase text-ink-primary">Gate</h1>
          <p className="text-xs text-ink-tertiary">
            {new Date().toLocaleDateString('en-KE', { weekday: 'long', day: 'numeric', month: 'long' })}
          </p>
        </div>
        <button onClick={refresh} aria-label="Refresh gate stats"
          className="w-9 h-9 flex items-center justify-center rounded-xl border border-cream-alt
            hover:bg-cream-alt transition-colors text-ink-tertiary">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path d="M13.5 8A5.5 5.5 0 112.5 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            <path d="M13.5 5v3h-3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </button>
      </div>

      {!isLoading && <StatsBar stats={stats} />}

      <WaiverAlert />

      <div className="mt-4">
        <IssueSection onIssued={refresh} />
        <LookupSection />
      </div>
    </div>
  )
}
