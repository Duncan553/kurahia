import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { Modal, useToastStore } from '@shared'
import api from '../lib/axios'

// Gate station hub: issue wristbands + today's stats (bands issued, total fees).
// Band lookup lives on POS screens; booking check-in lives on FrontDesk.

const ENTRY_FEE = 3000  // KES — single source of truth in backend, mirrored here

interface Stats {
  issued_today: number
  inside_now: number
  total_entry_fees: string
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

// ── Animation variants ──────────────────────────────────────────────────────

const fadeIn = { hidden: { opacity: 0, y: 12 }, visible: { opacity: 1, y: 0 } }
const stagger = { visible: { transition: { staggerChildren: 0.07 } } }

// ── Stats header ─────────────────────────────────────────────────────────────

function StatsBar({ stats }: { stats: Stats | undefined }) {
  const items = [
    { label: 'Inside Now',    value: stats?.inside_now   ?? '—' },
    { label: 'Issued Today',  value: stats?.issued_today ?? '—' },
    { label: 'Entry Revenue', value: stats ? kes(stats.total_entry_fees) : '—' },
  ]
  return (
    <motion.div className="grid grid-cols-3 gap-4 mb-6"
      initial="hidden" animate="visible" variants={stagger}>
      {items.map(({ label, value }, i) => (
        <motion.div key={label} variants={fadeIn}
          transition={{ duration: 0.35, ease: 'easeOut' }}
          className={`glass-card rounded-2xl p-4 text-center ${i === 0 ? 'col-span-2 row-span-1' : ''}`}>
          <p className={`font-bold tabular-nums text-ink-primary ${i === 0 ? 'text-3xl' : 'text-lg'}`}>{value}</p>
          <p className="text-[10px] text-ink-secondary uppercase tracking-wide mt-0.5">{label}</p>
        </motion.div>
      ))}
    </motion.div>
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
    <section className="glass-card rounded-2xl p-4 space-y-3 mb-4">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-ink-primary">Issue Band</p>
        <p className="text-sm font-bold tabular-nums text-ink-primary">{kes(ENTRY_FEE)}</p>
      </div>

      {/* Payment method toggle */}
      <div className="grid grid-cols-4 gap-1.5">
        {METHODS.map(({ value, label }) => (
          <motion.button key={value} onClick={() => setMethod(value)}
            whileTap={{ scale: 0.97 }}
            className={`min-h-[44px] rounded-xl text-xs font-semibold border transition-colors ${
              method === value
                ? 'bg-ink-primary text-white border-ink-primary'
                : 'border-cream-alt text-ink-secondary hover:bg-cream-alt'
            }`}>
            {label}
          </motion.button>
        ))}
      </div>

      <motion.button
        whileTap={{ scale: 0.98 }}
        onClick={() => setConfirmOpen(true)}
        disabled={mut.isPending}
        aria-label="Issue wristband"
        className="w-full py-4 rounded-2xl bg-[#fa5c29] text-white text-base font-semibold
          hover:bg-[#af3000] transition-colors disabled:opacity-50
          focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#fa5c29]"
      >
        {mut.isPending ? 'Issuing…' : 'Issue Band →'}
      </motion.button>

      <AnimatePresence>
        {lastBand !== null && (
          <motion.p
            initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
            className="text-center text-sm text-ink-tertiary">
            Last issued: <span className="font-bold text-ink-primary">#{lastBand}</span>
          </motion.p>
        )}
      </AnimatePresence>

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
            className="flex-1 py-3 rounded-xl bg-[#fa5c29] text-white font-semibold
              hover:bg-[#af3000] transition-colors disabled:opacity-50">
            {mut.isPending ? 'Issuing…' : 'Confirm'}
          </button>
        </div>
      </Modal>
    </section>
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
    <div className="min-h-screen p-4 md:p-6">
      <motion.div className="max-w-3xl mx-auto"
        initial="hidden" animate="visible" variants={stagger}>

      {/* Header */}
      <motion.div variants={fadeIn} transition={{ duration: 0.3, ease: 'easeOut' }}
        className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-base font-bold tracking-widest uppercase text-ink-primary">Gate</h1>
          <p className="text-xs text-ink-tertiary">
            {new Date().toLocaleDateString('en-KE', { weekday: 'long', day: 'numeric', month: 'long' })}
          </p>
        </div>
        <motion.button onClick={refresh} aria-label="Refresh gate stats"
          whileTap={{ scale: 0.95 }}
          className="min-h-[44px] min-w-[44px] flex items-center justify-center rounded-xl border border-cream-alt
            hover:bg-cream-alt transition-colors text-ink-tertiary">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path d="M13.5 8A5.5 5.5 0 112.5 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            <path d="M13.5 5v3h-3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </motion.button>
      </motion.div>

      {!isLoading && <StatsBar stats={stats} />}

      <motion.div variants={fadeIn} transition={{ duration: 0.3, ease: 'easeOut' }}
        className="mt-4 space-y-4">
        <IssueSection onIssued={refresh} />
      </motion.div>
      </motion.div>
    </div>
  )
}
