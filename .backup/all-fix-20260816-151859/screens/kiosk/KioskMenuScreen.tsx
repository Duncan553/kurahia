import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import api from '../../lib/axios'
import { useKioskStore } from '../../stores/kioskStore'
import { useKioskIdle } from '../../hooks/useKioskIdle'
import { useToastStore } from '@shared'

// ── Types ─────────────────────────────────────────────────────────────────────

interface MenuItem {
  id: string
  name: string
  price: string           // string Decimal from backend
  category: string | null
  prep_station: 'KITCHEN' | 'BAR' | 'NONE'
  department_id: string
  is_active: boolean
  in_stock: boolean | null  // null = no recipe configured; false = stock depleted
}

interface PinLoginResponse {
  access_token: string
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatKsh(price: string): string {
  const num = parseFloat(price)
  if (isNaN(num)) return price
  return `KSh ${num.toLocaleString('en-KE', { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`
}

// Group items by category, "Other" always last
function groupByCategory(items: MenuItem[]): [string, MenuItem[]][] {
  const map = new Map<string, MenuItem[]>()

  for (const item of items) {
    const key = item.category?.trim() || 'Other'
    if (!map.has(key)) map.set(key, [])
    map.get(key)!.push(item)
  }

  // Sort each group by name
  for (const [, group] of map) {
    group.sort((a, b) => a.name.localeCompare(b.name))
  }

  // Sort categories alphabetically, "Other" last
  const entries = [...map.entries()]
  entries.sort(([a], [b]) => {
    if (a === 'Other') return 1
    if (b === 'Other') return -1
    return a.localeCompare(b)
  })

  return entries
}

// ── Category section ──────────────────────────────────────────────────────────

function CategorySection({ name, items }: { name: string; items: MenuItem[] }) {
  const [open, setOpen] = useState(true)

  return (
    <div className="mb-1">
      {/* Header with horizontal rules */}
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-4 py-4 px-6 text-left
          focus-visible:outline-none"
        aria-expanded={open}
      >
        <div className="flex-1 border-t border-tea-brown/30" />
        <span className="font-serif text-3xl font-bold text-tea-brown tracking-widest shrink-0">
          {name}
        </span>
        <div className="flex-1 border-t border-tea-brown/30" />
      </button>

      {/* Items */}
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: 'easeInOut' }}
            className="overflow-hidden px-6"
          >
            {items.map((item, i) => {
              const soldOut = item.in_stock === false
              return (
                <div
                  key={item.id}
                  className={[
                    'flex items-center justify-between py-3',
                    i < items.length - 1 ? 'border-b border-dashed border-tea-brown/25' : '',
                    soldOut ? 'opacity-40' : '',
                  ].join(' ')}
                >
                  <span className={`text-lg text-ticket-ink ${soldOut ? 'line-through' : ''}`}>
                    {item.name}
                    {soldOut && (
                      <span className="text-sm font-normal not-italic ml-2 no-underline">
                        — Sold out
                      </span>
                    )}
                  </span>
                  <span className="text-lg font-bold text-ticket-ink tabular-nums ml-6 shrink-0">
                    {soldOut ? '—' : formatKsh(item.price)}
                  </span>
                </div>
              )
            })}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ── PIN exit modal ─────────────────────────────────────────────────────────────

const KEYPAD = ['1','2','3','4','5','6','7','8','9','','0','⌫'] as const

function PinExitModal({
  username,
  onClose,
  onSuccess,
}: {
  username: string
  onClose: () => void
  onSuccess: () => void
}) {
  const [digits, setDigits]   = useState<string[]>([])
  const [error, setError]     = useState('')
  const addToast              = useToastStore((s) => s.addToast)

  const mutation = useMutation<PinLoginResponse, { response?: { data?: { error?: string } } }>({
    mutationFn: () =>
      api.post<PinLoginResponse>('/auth/pin-login', {
        username,
        pin: digits.join(''),
      }).then((r) => r.data),
    onSuccess: () => {
      addToast({ type: 'success', message: 'Kiosk mode deactivated.' })
      onSuccess()
    },
    onError: (err) => {
      const msg = err.response?.data?.error ?? 'Incorrect PIN.'
      setError(msg)
      setDigits([])
    },
  })

  function handleKey(key: string) {
    if (mutation.isPending) return
    setError('')
    if (key === '⌫') {
      setDigits((d) => d.slice(0, -1))
    } else if (digits.length < 4) {
      const next = [...digits, key]
      setDigits(next)
    }
  }

  const ready = digits.length === 4

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-tea-brown/60 backdrop-blur-sm p-6">
      <div className="w-full max-w-xs bg-ticket-paper rounded-2xl p-6 space-y-5 border border-tea-brown/30">
        <div className="text-center">
          <h2 className="font-serif text-2xl font-bold text-tea-brown tracking-wide">Exit Kiosk</h2>
          <p className="text-sm text-ticket-ink/60 mt-1">Enter your staff PIN to return to the staff app</p>
        </div>

        {/* PIN dots */}
        <div className="flex justify-center gap-4">
          {[0,1,2,3].map((i) => (
            <div
              key={i}
              className={[
                'w-4 h-4 rounded-full border-2 transition-colors',
                i < digits.length
                  ? 'bg-tea-brown border-tea-brown'
                  : 'border-tea-brown/30 bg-transparent',
              ].join(' ')}
            />
          ))}
        </div>

        {error && (
          <p className="text-sm text-stamp-red text-center font-medium">{error}</p>
        )}

        {/* Keypad */}
        <div className="grid grid-cols-3 gap-2">
          {KEYPAD.map((key, i) => (
            key === '' ? <div key={i} /> : (
              <button
                key={i}
                type="button"
                onClick={() => handleKey(key)}
                disabled={mutation.isPending}
                className={[
                  'min-h-[56px] w-full rounded-xl font-semibold text-xl',
                  'flex items-center justify-center select-none transition-all',
                  'disabled:opacity-40',
                  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tea-brown',
                  key === '⌫'
                    ? 'bg-transparent text-ticket-ink/50 active:text-ticket-ink active:scale-95'
                    : 'bg-ticket-alt border border-tea-brown/20 text-ticket-ink active:bg-tea-brown/20 active:scale-95',
                ].join(' ')}
              >
                {key === '⌫' ? (
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <path d="M21 7H9.5L3 12l6.5 5H21V7z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
                    <path d="M15 10l-4 4M11 10l4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                  </svg>
                ) : key}
              </button>
            )
          ))}
        </div>

        {/* Actions */}
        <div className="flex gap-3">
          <button
            onClick={onClose}
            disabled={mutation.isPending}
            className="flex-1 min-h-[44px] rounded-xl border border-tea-brown/30
              text-ticket-ink/60 text-sm font-medium hover:bg-ticket-alt transition-colors
              focus-visible:outline-none disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={() => mutation.mutate()}
            disabled={!ready || mutation.isPending}
            className="flex-1 min-h-[44px] rounded-xl bg-tea-brown text-ticket-paper
              text-sm font-semibold hover:bg-tea-brown/90 transition-colors
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tea-brown
              disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {mutation.isPending ? 'Verifying…' : 'Exit Kiosk'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Main screen ───────────────────────────────────────────────────────────────

export default function KioskMenuScreen() {
  const navigate        = useNavigate()
  const kioskMode       = useKioskStore((s) => s.kioskMode)
  const kioskUser       = useKioskStore((s) => s.kioskUser)
  const deactivateKiosk = useKioskStore((s) => s.deactivateKiosk)
  const [pinOpen, setPinOpen] = useState(false)
  const tapCount   = useRef(0)  // rapid-tap counter for hidden exit target
  const tapTimer   = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  // Arm inactivity timer
  useKioskIdle()

  // Guard — kiosk store cleared means user exited, bounce to staff home
  useEffect(() => {
    if (!kioskMode) navigate('/', { replace: true })
  }, [kioskMode, navigate])

  // Disable back navigation
  useEffect(() => {
    window.history.pushState(null, '', window.location.href)
    const handler = () => window.history.pushState(null, '', window.location.href)
    window.addEventListener('popstate', handler)
    return () => window.removeEventListener('popstate', handler)
  }, [])

  const { data: items = [], isLoading, isError } = useQuery<MenuItem[]>({
    queryKey: ['kiosk-menu-items'],
    queryFn: () => api.get<MenuItem[]>('/menu/items').then((r) => r.data),
    // Refresh every 30s so sold-out items disappear promptly; pauses when tab is hidden
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
    retry: 2,
  })

  const groups = groupByCategory(items)

  function handlePinSuccess() {
    deactivateKiosk()
    navigate('/', { replace: true })
  }

  // Hidden corner tap target: 3 rapid taps in 1.5s opens the exit modal
  function handleCornerTap() {
    tapCount.current += 1
    clearTimeout(tapTimer.current)
    if (tapCount.current >= 3) {
      tapCount.current = 0
      setPinOpen(true)
    } else {
      tapTimer.current = setTimeout(() => { tapCount.current = 0 }, 1500)
    }
  }

  return (
    <div
      className="min-h-screen bg-ticket-paper flex flex-col"
      onContextMenu={(e) => e.preventDefault()}
      style={{ touchAction: 'pan-y', overscrollBehavior: 'none' }}
    >
      {/* ── Header ──────────────────────────────────────────────────────── */}
      <header className="shrink-0 text-center pt-8 pb-4 px-6 border-b border-tea-brown/20">
        <p className="font-serif text-sm tracking-[0.4em] text-tea-brown/60 uppercase mb-1">
          Waterfront Kurahia
        </p>
        <h1 className="font-serif text-5xl font-bold text-tea-brown tracking-widest leading-tight">
          MENU
        </h1>
      </header>

      {/* ── Scrollable menu content ──────────────────────────────────────── */}
      <main className="flex-1 overflow-y-auto py-4">
        {isLoading && (
          <div className="p-8 text-center">
            <p className="font-serif text-xl text-tea-brown/60 tracking-wide">Loading menu…</p>
          </div>
        )}

        {isError && (
          <div className="p-8 text-center space-y-2">
            <p className="font-serif text-xl text-stamp-red/80">Unable to load menu</p>
            <p className="text-sm text-ticket-ink/50">Please ask a staff member for a printed menu</p>
          </div>
        )}

        {!isLoading && !isError && items.length === 0 && (
          <div className="p-8 text-center">
            <p className="font-serif text-xl text-tea-brown/60 tracking-wide">Menu unavailable — please ask a staff member for assistance.</p>
          </div>
        )}

        {groups.map(([category, categoryItems]) => (
          <CategorySection key={category} name={category} items={categoryItems} />
        ))}
      </main>

      {/* ── Footer ──────────────────────────────────────────────────────── */}
      <footer className="shrink-0 text-center py-4 px-6 border-t border-tea-brown/20">
        <p className="text-xs text-ticket-ink/40 tracking-widest uppercase">
          Karibu · Asante kwa kuja
        </p>
      </footer>

      {/* ── Hidden staff exit target (bottom-right, 60×60px, invisible) ── */}
      <button
        onClick={handleCornerTap}
        aria-hidden="true"
        tabIndex={-1}
        className="fixed bottom-0 right-0 w-[60px] h-[60px] opacity-0 cursor-default"
      />

      {/* ── PIN exit modal ────────────────────────────────────────────── */}
      <AnimatePresence>
        {pinOpen && kioskUser && (
          <motion.div
            key="pin-modal"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <PinExitModal
              username={kioskUser}
              onClose={() => setPinOpen(false)}
              onSuccess={handlePinSuccess}
            />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
