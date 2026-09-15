import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { Modal, useToastStore, ErrorBoundary, PaymentRef, MpesaPrompt, useMpesaPrompt } from '@shared'
import { RequireRole } from '../components/AuthGate'
import api from '../lib/axios'
import { formatBandBalance } from '../lib/format'

// Gate station hub: issue wristbands + today's stats (bands issued, total fees).
// Band lookup lives on POS screens; booking check-in lives on FrontDesk.

const ENTRY_FEE = 3000  // KES — single source of truth in backend, mirrored here

interface Stats {
  issued_today: number
  inside_now: number
  total_entry_fees: string
}

interface Band { id: string; band_number: number; tab_balance: string }

// Three ways a guest pays here. Bank transfer was offered and nobody knew
// how it worked — a method staff cannot explain is a method that produces
// payments nobody can verify. Staff PAYROLL still goes by bank; that is a
// different thing and is untouched.
type Method = 'CASH' | 'MPESA' | 'CARD'

const METHODS: { value: Method; label: string }[] = [
  { value: 'CASH',          label: 'Cash'  },
  { value: 'MPESA',         label: 'M-Pesa'},
  { value: 'CARD',          label: 'Card'  },
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
    <>
      <p className="text-[10px] text-ink-tertiary mb-2">How many guests entered today</p>
      <motion.div className="grid grid-cols-3 gap-3 mb-4"
        initial="hidden" animate="visible" variants={stagger}>
        {items.map(({ label, value }) => (
          <motion.div key={label} variants={fadeIn}
            transition={{ duration: 0.35, ease: 'easeOut' }}
            className="glass-card rounded-2xl p-3 text-center">
            <p className="font-bold tabular-nums text-ink-secondary text-base">{value}</p>
            <p className="text-[10px] text-ink-tertiary uppercase tracking-wide mt-0.5">{label}</p>
          </motion.div>
        ))}
      </motion.div>
    </>
  )
}

// ── Recent bands ─────────────────────────────────────────────────────────────
// This screen and WristbandScreen (/gate/issue) both hit POST /gate/issue-band
// independently, each with its own idempotency key — nothing stops a worker
// from issuing a real second paid band for the same guest by using both
// screens in a row. Surfacing what's already been issued today, right next
// to the Issue button, gives a gate attendant a chance to notice before it
// happens instead of relying on idempotency (which only catches a retry of
// the exact same tap, not a human repeating the whole flow elsewhere).
function RecentBands() {
  const { data: bands, isLoading } = useQuery<Band[]>({
    queryKey: ['gate-active-bands'],
    queryFn: () => api.get<Band[]>('/gate/active-bands').then(r => r.data),
    refetchInterval: 30_000,
  })
  if (isLoading || !bands || bands.length === 0) return null
  return (
    <div className="glass-card rounded-2xl p-4 mb-6">
      <p className="text-[10px] font-bold tracking-[0.2em] uppercase text-ink-tertiary mb-3">
        Recent Bands — check before issuing another for the same guest
      </p>
      <div className="space-y-2">
        {bands.slice(0, 4).map(b => {
          const bal = formatBandBalance(b.tab_balance)
          return (
            <div key={b.id} className="flex items-center justify-between py-1 text-sm">
              <span className="font-semibold text-ink-primary">#{b.band_number}</span>
              <span className="text-xs tabular-nums text-ink-tertiary">
                KSh {bal.amount} {bal.owed ? 'owed' : 'credit left'}
              </span>
            </div>
          )
        })}
        {bands.length > 4 && (
          <p className="text-[10px] text-ink-tertiary text-center pt-1">+{bands.length - 4} more inside</p>
        )}
      </div>
    </div>
  )
}

// ── Issue section ─────────────────────────────────────────────────────────────

function IssueSection({ onIssued }: { onIssued: () => void }) {
  const addToast   = useToastStore(s => s.addToast)
  const [method, setMethod]       = useState<Method>('CASH')
  const [payRef, setPayRef]       = useState('')
  const [idemKey, setIdemKey]     = useState(genKey)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [lastBand, setLastBand]   = useState<number | null>(null)
  const navigate = useNavigate()
  // Can this gate push a prompt to the guest's phone? Asked before the
  // button exists, never assumed.
  const { canPrompt } = useMpesaPrompt(api)

  const mut = useMutation({
    mutationFn: () =>
      api.post<{ band_number: number; duplicate?: boolean }>('/gate/issue-band', {
        method, idempotency_key: idemKey,
        // The endpoint has always accepted these; nothing ever sent them, so
        // every gate payment reached the reconcile screen as "no reference".
        ...(method === 'MPESA' && payRef.trim() ? { mpesa_code: payRef.trim() } : {}),
        ...(method === 'CARD'  && payRef.trim() ? { card_ref:   payRef.trim() } : {}),
      }).then(r => r.data),
    onSuccess: (data) => {
      setConfirmOpen(false)
      setLastBand(data.band_number)
      setIdemKey(genKey())
      setPayRef('')
      onIssued()
      const msg = data.duplicate
        ? `Already issued — Band #${data.band_number}`
        : `Band #${data.band_number} issued · ${kes(ENTRY_FEE)} recorded`
      addToast({ type: data.duplicate ? 'warning' : 'success', message: msg })
    },
    onError: (e) => { setConfirmOpen(false); addToast({ type: 'error', message: extractErr(e) }) },
  })

  // Issue by prompt. The band is issued first because the charge endpoint
  // needs a payment to reference, and at the gate that payment is the entry
  // fee issue_band() already wrote. The guest walks in wearing the band while
  // their phone is still buzzing — which is how a gate has to work — and if
  // they decline, the payment row simply stays unreconciled and surfaces on
  // the manager's Pending Payments list, exactly where a manually typed
  // M-Pesa payment with a wrong code lands today.
  const stkMut = useMutation({
    mutationFn: async (phone: string) => {
      // Re-check at the tap: the socket can be switched off while this screen
      // sits open, and offering a prompt we cannot send is how a band once got
      // issued against money that never moved.
      if (!canPrompt) throw new Error(
        'M-Pesa prompts are not switched on yet. Ask the guest to pay the paybill and type their code instead.')
      const { data: band } = await api.post<{ band_number: number; tab_id: string; entry_payment_id: string }>(
        '/gate/issue-band', { method: 'MPESA', idempotency_key: idemKey })
      try {
        await api.post('/finance/mpesa/charge', {
          tab_id: band.tab_id,
          payment_id: band.entry_payment_id,
          amount: ENTRY_FEE,
          phone_number: phone,
        })
      } catch (e) {
        // The band is already on the guest's wrist and its entry fee is
        // already recorded — issue_band writes both in one transaction, and
        // Payments cannot be taken back. So the failure has to be SAID, with
        // the band number in it, or the attendant waves a guest through
        // against money that was never requested.
        throw new Error(
          `Band #${band.band_number} is issued but the prompt did not send (${extractErr(e)}). `
          + `Collect KSh ${ENTRY_FEE.toLocaleString()} another way and note band #${band.band_number}.`)
      }
      return band
    },
    onSuccess: (band) => {
      setLastBand(band.band_number)
      setIdemKey(genKey())
      setPayRef('')
      onIssued()
      addToast({ type: 'success',
        message: `Band #${band.band_number} issued — prompt sent, ask the guest to check their phone.` })
    },
    onError: (e) => {
      setIdemKey(genKey())   // the band was issued; a retry must not return it again as 'duplicate'
      onIssued()
      addToast({ type: 'error', message: e instanceof Error ? e.message : extractErr(e) })
    },
  })

  return (
    <section className="glass-card rounded-2xl p-5 space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-wider text-ink-tertiary">Issue Band</p>
        <p className="text-[10px] text-ink-tertiary mt-0.5">Give the guest a wristband — KSh 3,000 entry fee goes on as credit</p>
        <p className="text-sm font-bold tabular-nums text-ink-secondary">{kes(ENTRY_FEE)}</p>
      </div>

      {/* Payment method toggle */}
      <div className="grid grid-cols-3 gap-2">
        {METHODS.map(({ value, label }) => (
          <motion.button key={value} onClick={() => setMethod(value)}
            whileTap={{ scale: 0.97 }}
            className={`min-h-[44px] rounded-xl text-xs font-semibold border transition-colors ${
              method === value
                ? 'bg-ink-primary text-cream-card border-ink-primary'
                : 'border-cream-alt text-ink-secondary hover:bg-cream-alt'
            }`}>
            {label}
          </motion.button>
        ))}
      </div>

      {/* Prompting comes first when it is available — the guest approves on
          their own phone and Safaricom confirms it back, so the entry fee
          arrives already matched instead of waiting on a typed code. */}
      {method === 'MPESA' && (
        <MpesaPrompt canPrompt={canPrompt} amount={ENTRY_FEE}
          sending={stkMut.isPending} onSend={p => stkMut.mutate(p)} />
      )}

      <PaymentRef method={method} value={payRef} onChange={setPayRef} />

      {/* HERO CTA — the focal point of this screen */}
      <motion.button
        whileTap={{ scale: 0.98 }}
        onClick={() => setConfirmOpen(true)}
        disabled={mut.isPending}
        aria-label="Issue wristband"
        className="w-full py-5 rounded-2xl bg-primary-main text-white text-lg font-bold
          hover:bg-primary-dark transition-colors disabled:opacity-50
          focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-main
          shadow-lg shadow-[#fa5c29]/20"
      >
        {mut.isPending ? 'Issuing…' : 'Issue Wristband'}
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
        {/* The number only existed on this screen. The guest walked in with
            nothing in their hand and the gate had to remember it — so print it:
            the number, a barcode of it for the scanner at the exit, what was
            loaded and the terms. */}
        {lastBand !== null && (
          <motion.button
            initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            onClick={() => navigate(`/print/band/${lastBand}?print=1`)}
            className="mx-auto mt-2 block px-5 py-2.5 rounded-xl glass-card text-sm
              text-ink-secondary hover:bg-white/5 transition-colors">
            Print band #{lastBand}
          </motion.button>
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
            className="flex-1 py-3 rounded-xl bg-primary-main text-white font-semibold
              hover:bg-primary-dark transition-colors disabled:opacity-50">
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

  // Every endpoint behind this screen is GATE_LEVEL (3): issue-band,
  // today-stats, active-bands. Without this guard the screen still drew —
  // stats bar of em-dashes, an Issue button that 403s — for anyone who typed
  // the URL or was handed the tablet. A refusal rendered as an empty
  // dashboard is the worst of both: it looks broken rather than forbidden.
  return (
    <RequireRole minLevel={3}>
    <div className="min-h-screen p-4 md:p-6">
      <ErrorBoundary level="tile">
      <motion.div className="max-w-3xl mx-auto"
        initial="hidden" animate="visible" variants={stagger}>

      {/* Header */}
      <motion.div variants={fadeIn} transition={{ duration: 0.3, ease: 'easeOut' }}
        className="flex items-center justify-between mb-8">
        <div>
          <h1 className="font-serif text-3xl md:text-4xl font-bold text-ink-primary tracking-tight">Gate</h1>
          <p className="text-xs text-ink-tertiary mt-1">
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

      {/* HERO: Issue section first — the primary action */}
      <motion.div variants={fadeIn} transition={{ duration: 0.3, ease: 'easeOut' }}
        className="mb-8">
        <IssueSection onIssued={refresh} />
      </motion.div>

      <RecentBands />

      {/* Stats — secondary, below the action */}
      {!isLoading && <StatsBar stats={stats} />}
      </motion.div>
      </ErrorBoundary>
    </div>
    </RequireRole>
  )
}
