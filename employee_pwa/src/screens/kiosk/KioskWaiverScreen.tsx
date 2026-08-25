import { useState, useEffect, useRef } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import api from '../../lib/axios'
import { useKioskStore } from '../../stores/kioskStore'
import { useToastStore } from '@shared'

// ── Types ─────────────────────────────────────────────────────────────────────

interface WaiverResponse {
  id: string
  booking_id: string
  activity_type: string
  signed_by: string
  signed_at: string
}

// ── Waiver text ───────────────────────────────────────────────────────────────

const WAIVER_TITLE = 'LIABILITY WAIVER — WATER ACTIVITIES'

const WAIVER_BODY = `By signing this waiver, I voluntarily participate in water-based activities at Waterfront Kurahia, Juja Farm, Kiambu County, Kenya.

1. ASSUMPTION OF RISK
I understand that water activities — including use of jetskis, motorboats, inflatables, and swimming — carry inherent risks: drowning, physical injury, collision, and equipment malfunction. I voluntarily assume all such risks.

2. RELEASE OF LIABILITY
I release, waive, and discharge Waterfront Kurahia and its owners, managers, employees, and agents from all claims, damages, or liability arising from my participation in water activities, to the fullest extent permitted by Kenyan law.

3. MEDICAL FITNESS
I confirm I am physically fit and have no medical condition — including heart disease, epilepsy, or pregnancy — that would make water activities unsafe for me.

4. SAFETY RULES
I agree to follow all safety instructions from Waterfront Kurahia staff at all times. Non-compliance may result in immediate removal from the activity without refund.

5. CHILDREN
If signing on behalf of a minor, I confirm I am the parent or legal guardian and accept these terms on their behalf.

6. PHOTOGRAPHY
I consent to being photographed or filmed during activities for Waterfront Kurahia's records and promotional use.

I confirm I have read and understood the above terms fully before signing.`

// ── Keypad constant ───────────────────────────────────────────────────────────

const KEYPAD = ['1','2','3','4','5','6','7','8','9','','0','⌫'] as const

// ── PIN confirmation modal ────────────────────────────────────────────────────

function PinModal({
  username,
  onConfirm,
  onCancel,
}: {
  username: string
  onConfirm: (pin: string) => void
  onCancel: () => void
}) {
  const [digits, setDigits] = useState<string[]>([])
  const [error, setError]   = useState('')

  const verifyMutation = useMutation<{ access_token: string }, { response?: { data?: { error?: string } } }>({
    mutationFn: () =>
      api.post('/auth/pin-login', { username, pin: digits.join('') }).then((r) => r.data),
    onSuccess: () => onConfirm(digits.join('')),
    onError: (err) => {
      setError(err.response?.data?.error ?? 'Incorrect PIN.')
      setDigits([])
    },
  })

  function handleKey(key: string) {
    if (verifyMutation.isPending) return
    setError('')
    if (key === '⌫') {
      setDigits((d) => d.slice(0, -1))
    } else if (digits.length < 4) {
      setDigits((d) => [...d, key])
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-tea-brown/60 backdrop-blur-sm p-6">
      <div className="w-full max-w-xs bg-ticket-paper rounded-2xl p-6 space-y-5 border border-tea-brown/30">
        <div className="text-center">
          <h2 className="font-serif text-2xl font-bold text-tea-brown tracking-wide">Staff PIN</h2>
          <p className="text-sm text-ticket-ink/60 mt-1">Enter your PIN to record this waiver</p>
        </div>

        <div className="flex justify-center gap-4">
          {[0,1,2,3].map((i) => (
            <div key={i} className={[
              'w-4 h-4 rounded-full border-2 transition-colors',
              i < digits.length ? 'bg-tea-brown border-tea-brown' : 'border-tea-brown/30',
            ].join(' ')} />
          ))}
        </div>

        {error && <p className="text-sm text-stamp-red text-center font-medium">{error}</p>}

        <div className="grid grid-cols-3 gap-2">
          {KEYPAD.map((key, i) => (
            key === '' ? <div key={i} /> : (
              <button
                key={i}
                type="button"
                onClick={() => handleKey(key)}
                disabled={verifyMutation.isPending}
                className={[
                  'min-h-[56px] w-full rounded-xl font-semibold text-xl',
                  'flex items-center justify-center select-none transition-all disabled:opacity-40',
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

        <div className="flex gap-3">
          <button
            onClick={onCancel}
            disabled={verifyMutation.isPending}
            className="flex-1 min-h-[44px] rounded-xl border border-tea-brown/30
              text-ticket-ink/60 text-sm font-medium hover:bg-ticket-alt transition-colors
              focus-visible:outline-none disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={() => verifyMutation.mutate()}
            disabled={digits.length !== 4 || verifyMutation.isPending}
            className="flex-1 min-h-[44px] rounded-xl bg-tea-brown text-ticket-paper
              text-sm font-semibold hover:bg-tea-brown/90 transition-colors
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tea-brown
              disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {verifyMutation.isPending ? 'Verifying…' : 'Confirm'}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Main screen ───────────────────────────────────────────────────────────────

export default function KioskWaiverScreen() {
  const { bookingId }   = useParams<{ bookingId: string }>()
  const navigate        = useNavigate()
  const kioskMode       = useKioskStore((s) => s.kioskMode)
  const kioskUser       = useKioskStore((s) => s.kioskUser)
  const deactivateKiosk = useKioskStore((s) => s.deactivateKiosk)
  const addToast        = useToastStore((s) => s.addToast)

  const [signedByName, setSignedByName] = useState('')
  const [agreed, setAgreed]             = useState(false)
  const [hasSigned, setHasSigned]       = useState(false)
  const [pinOpen, setPinOpen]           = useState(false)
  // Which action the PIN prompt is gating — set before opening it, read in
  // onConfirm below, so "exit" can't accidentally trigger a waiver submit.
  const [pinAction, setPinAction]       = useState<'submit' | 'exit'>('submit')
  const [submitted, setSubmitted]       = useState(false)
  // Stable across retries, rotated only after a real success in onSuccess below —
  // matches KioskFeedbackScreen's pattern. Was crypto.randomUUID() *inside*
  // mutationFn, so every retry got a fresh key and could never be deduped by
  // the backend's idempotency check (app/bookings/waivers.py) — a network
  // hiccup or a guest's second tap after a failed attempt created a second
  // waiver row for the same signature.
  const [idemKey, setIdemKey] = useState(() => crypto.randomUUID())

  // Hidden corner tap counter
  const tapCount = useRef(0)
  const tapTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  // Canvas refs
  const containerRef = useRef<HTMLDivElement>(null)
  const canvasRef    = useRef<HTMLCanvasElement>(null)
  const drawing      = useRef(false)

  // Guard: kiosk mode must be active
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

  // Initialise canvas size + context
  useEffect(() => {
    const canvas    = canvasRef.current
    const container = containerRef.current
    if (!canvas || !container) return
    canvas.width  = container.offsetWidth
    canvas.height = 200
    const ctx = canvas.getContext('2d')!
    ctx.strokeStyle = '#1F1B14'
    ctx.lineWidth   = 2.5
    ctx.lineCap     = 'round'
    ctx.lineJoin    = 'round'
  }, [])

  // Touch events — passive: false required to prevent page scroll while signing
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    function scale(e: TouchEvent) {
      const rect   = canvas!.getBoundingClientRect()
      const scaleX = canvas!.width  / rect.width
      const scaleY = canvas!.height / rect.height
      return {
        x: (e.touches[0].clientX - rect.left) * scaleX,
        y: (e.touches[0].clientY - rect.top)  * scaleY,
      }
    }

    function onStart(e: TouchEvent) {
      e.preventDefault()
      drawing.current = true
      const ctx = canvas!.getContext('2d')!
      const { x, y } = scale(e)
      ctx.beginPath()
      ctx.moveTo(x, y)
    }

    function onMove(e: TouchEvent) {
      if (!drawing.current) return
      e.preventDefault()
      const ctx = canvas!.getContext('2d')!
      const { x, y } = scale(e)
      ctx.lineTo(x, y)
      ctx.stroke()
      ctx.beginPath()
      ctx.moveTo(x, y)
      setHasSigned(true)
    }

    function onEnd() { drawing.current = false }

    canvas.addEventListener('touchstart', onStart, { passive: false })
    canvas.addEventListener('touchmove',  onMove,  { passive: false })
    canvas.addEventListener('touchend',   onEnd)
    return () => {
      canvas.removeEventListener('touchstart', onStart)
      canvas.removeEventListener('touchmove',  onMove)
      canvas.removeEventListener('touchend',   onEnd)
    }
  }, [])

  // Mouse events for desktop testing
  function getMousePos(e: React.MouseEvent<HTMLCanvasElement>) {
    const canvas = canvasRef.current!
    const rect   = canvas.getBoundingClientRect()
    const scaleX = canvas.width  / rect.width
    const scaleY = canvas.height / rect.height
    return {
      x: (e.clientX - rect.left) * scaleX,
      y: (e.clientY - rect.top)  * scaleY,
    }
  }

  function handleMouseDown(e: React.MouseEvent<HTMLCanvasElement>) {
    drawing.current = true
    const ctx = canvasRef.current!.getContext('2d')!
    const { x, y } = getMousePos(e)
    ctx.beginPath()
    ctx.moveTo(x, y)
  }

  function handleMouseMove(e: React.MouseEvent<HTMLCanvasElement>) {
    if (!drawing.current) return
    const ctx = canvasRef.current!.getContext('2d')!
    const { x, y } = getMousePos(e)
    ctx.lineTo(x, y)
    ctx.stroke()
    ctx.beginPath()
    ctx.moveTo(x, y)
    setHasSigned(true)
  }

  function handleMouseUp() { drawing.current = false }

  function clearCanvas() {
    const canvas = canvasRef.current!
    canvas.getContext('2d')!.clearRect(0, 0, canvas.width, canvas.height)
    setHasSigned(false)
  }

  // POST waiver
  const mutation = useMutation<WaiverResponse, { response?: { data?: { error?: string } } }>({
    mutationFn: () => {
      const signature_proof = canvasRef.current!.toDataURL('image/png')
      return api.post<WaiverResponse>('/waivers', {
        booking_id:     bookingId,
        activity_type:  'WATER_ACTIVITY',
        signed_by_name: signedByName.trim(),
        signature_proof,
        idempotency_key: idemKey,
      }).then((r) => r.data)
    },
    onSuccess: (data) => {
      addToast({ type: 'success', message: `Waiver recorded for ${data.signed_by}.` })
      setSubmitted(true)
      setIdemKey(crypto.randomUUID())  // done with this attempt — next signature gets a fresh key
      setTimeout(() => {
        deactivateKiosk()
        navigate('/', { replace: true })
      }, 5000)
    },
    onError: (err) => {
      addToast({
        type: 'error',
        message: err.response?.data?.error ?? 'Failed to record waiver. Please try again.',
      })
    },
  })

  // Hidden corner exit: 3 taps in 1.5s. Requires the staff PIN like every
  // other kiosk exit path (KioskMenuScreen's PinExitModal) — this used to
  // deactivate straight away, so a guest signing alone at the tablet could
  // 3-tap out into the staff member's full logged-in session with no
  // re-authentication.
  function handleCornerTap() {
    tapCount.current += 1
    clearTimeout(tapTimer.current)
    if (tapCount.current >= 3) {
      tapCount.current = 0
      setPinAction('exit')
      setPinOpen(true)
    } else {
      tapTimer.current = setTimeout(() => { tapCount.current = 0 }, 1500)
    }
  }

  // Guard: missing booking_id — below every hook (Rules of Hooks). This used
  // to sit above the 4 useEffects and the useMutation above, so a route-param
  // transition from no bookingId to a real one (no full unmount) changed the
  // number of hooks React saw between renders: "Rendered fewer hooks than
  // expected" — a real, reproduced crash, not theoretical.
  if (!bookingId) {
    return (
      <div className="min-h-screen bg-ticket-paper flex flex-col items-center justify-center p-8 text-center gap-4">
        <h1 className="font-serif text-3xl font-bold text-stamp-red tracking-wide">No Booking Selected</h1>
        <p className="text-ticket-ink/70">Staff must launch the waiver kiosk from a booking card.</p>
        <button
          onClick={() => { deactivateKiosk(); navigate('/', { replace: true }) }}
          className="mt-4 min-h-[44px] px-6 rounded-xl bg-tea-brown text-ticket-paper font-semibold
            hover:bg-tea-brown/90 transition-colors"
        >
          Return to Staff App
        </button>
      </div>
    )
  }

  const canSubmit = signedByName.trim().length >= 3 && agreed && hasSigned

  // ── Success screen ────────────────────────────────────────────────────────

  if (submitted) {
    return (
      <div className="min-h-screen bg-ticket-paper flex flex-col items-center justify-center p-8 text-center gap-6">
        <div className="text-leaf-green">
          <svg width="64" height="64" viewBox="0 0 64 64" fill="none" aria-hidden="true">
            <circle cx="32" cy="32" r="30" stroke="currentColor" strokeWidth="2.5"/>
            <path d="M20 32l9 9 15-18" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </div>
        <h1 className="font-serif text-5xl font-bold text-tea-brown tracking-widest leading-tight">
          Waiver Recorded
        </h1>
        <p className="font-serif text-2xl text-tea-brown/70 tracking-wide">
          Karibu! Enjoy your activity.
        </p>
        <p className="text-sm text-ticket-ink/40 mt-4">Returning to staff app in 5 seconds…</p>
      </div>
    )
  }

  // ── Main waiver form ──────────────────────────────────────────────────────

  return (
    <div
      className="min-h-screen bg-ticket-paper flex flex-col"
      onContextMenu={(e) => e.preventDefault()}
      style={{ touchAction: 'pan-y', overscrollBehavior: 'none' }}
    >
      {/* Header */}
      <header className="shrink-0 text-center pt-8 pb-4 px-6 border-b border-tea-brown/20">
        <p className="font-serif text-sm tracking-[0.4em] text-tea-brown/60 uppercase mb-1">
          Waterfront Kurahia
        </p>
        <h1 className="font-serif text-4xl font-bold text-tea-brown tracking-widest leading-tight">
          {WAIVER_TITLE}
        </h1>
      </header>

      {/* Scrollable form */}
      <main className="flex-1 overflow-y-auto px-6 py-6 max-w-2xl mx-auto w-full space-y-6">

        {/* Waiver body text */}
        <div className="rounded-xl bg-ticket-alt/60 border border-tea-brown/20 p-5">
          <pre className="font-sans text-base text-ticket-ink leading-relaxed whitespace-pre-wrap">
            {WAIVER_BODY}
          </pre>
        </div>

        {/* Guest name */}
        <div className="space-y-1.5">
          <label className="block text-sm font-semibold text-tea-brown uppercase tracking-wider">
            Full name *
          </label>
          <input
            type="text"
            autoComplete="off"
            value={signedByName}
            onChange={(e) => setSignedByName(e.target.value)}
            placeholder="Enter your full name"
            className="w-full rounded-xl border border-tea-brown/30 bg-white px-4 py-3
              text-base text-ticket-ink min-h-[44px]
              focus:outline-none focus:border-tea-brown focus:ring-2 focus:ring-tea-brown/20
              placeholder:text-ticket-ink/30"
          />
          {signedByName.trim().length > 0 && signedByName.trim().length < 3 && (
            <p className="text-sm text-stamp-red">Name must be at least 3 characters.</p>
          )}
        </div>

        {/* Agreement checkbox */}
        <label className="flex items-start gap-3 cursor-pointer">
          <div className="relative shrink-0 mt-0.5">
            <input
              type="checkbox"
              checked={agreed}
              onChange={(e) => setAgreed(e.target.checked)}
              className="sr-only"
            />
            <div className={[
              'w-6 h-6 rounded border-2 flex items-center justify-center transition-colors',
              agreed ? 'bg-tea-brown border-tea-brown' : 'border-tea-brown/40 bg-white',
            ].join(' ')}>
              {agreed && (
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
                  <path d="M2.5 7l3.5 3.5 5.5-7" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              )}
            </div>
          </div>
          <span className="text-base text-ticket-ink leading-snug">
            I have read and fully understand the terms above. I agree to be bound by this waiver.
          </span>
        </label>

        {/* Signature canvas */}
        <div className="space-y-2">
          <p className="text-sm font-semibold text-tea-brown uppercase tracking-wider">Signature *</p>
          <div
            ref={containerRef}
            className="w-full rounded-xl border-2 border-dashed border-tea-brown/40 bg-white overflow-hidden"
          >
            <canvas
              ref={canvasRef}
              className="w-full block touch-none"
              style={{ height: 200 }}
              onMouseDown={handleMouseDown}
              onMouseMove={handleMouseMove}
              onMouseUp={handleMouseUp}
              onMouseLeave={handleMouseUp}
            />
          </div>
          {!hasSigned && (
            <p className="text-sm text-ticket-ink/40 text-center">Draw your signature above</p>
          )}
          <button
            type="button"
            onClick={clearCanvas}
            className="text-sm text-tea-brown/70 hover:text-tea-brown underline
              min-h-[44px] flex items-center transition-colors
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tea-brown rounded"
          >
            Clear signature
          </button>
        </div>

        {/* Submit */}
        <button
          type="button"
          onClick={() => { setPinAction('submit'); setPinOpen(true) }}
          disabled={!canSubmit || mutation.isPending}
          className="w-full py-4 rounded-2xl bg-tea-brown text-ticket-paper
            text-base font-semibold tracking-wide
            hover:bg-tea-brown/90 active:scale-[0.99] transition-all
            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tea-brown
            disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Submit Waiver
        </button>

        <div className="h-8" /> {/* bottom breathing room */}
      </main>

      {/* Footer */}
      <footer className="shrink-0 text-center py-4 border-t border-tea-brown/20">
        <p className="text-xs text-ticket-ink/40 tracking-widest uppercase">
          Waterfront Kurahia · Juja · Kiambu · Kenya
        </p>
      </footer>

      {/* Hidden 60×60 staff exit corner (3-tap) */}
      <button
        onClick={handleCornerTap}
        aria-hidden="true"
        tabIndex={-1}
        className="fixed bottom-0 right-0 w-[60px] h-[60px] opacity-0 cursor-default"
      />

      {/* PIN modal */}
      <AnimatePresence>
        {pinOpen && kioskUser && (
          <motion.div
            key="pin-modal"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <PinModal
              username={kioskUser}
              onCancel={() => setPinOpen(false)}
              onConfirm={() => {
                setPinOpen(false)
                if (pinAction === 'exit') {
                  deactivateKiosk()
                  navigate('/', { replace: true })
                } else {
                  mutation.mutate()
                }
              }}
            />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
