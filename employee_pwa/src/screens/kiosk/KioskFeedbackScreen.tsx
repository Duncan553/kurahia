import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import api from '../../lib/axios'
import { useKioskStore } from '../../stores/kioskStore'
import { useToastStore } from '@shared'

// ── Constants ─────────────────────────────────────────────────────────────────

const IDLE_60S = 60_000  // auto-submit (or return to welcome) after 60s of no interaction
const SUCCESS_DELAY = 5_000

type Step = 'welcome' | 'rating' | 'comment' | 'done'

const STAR_LABELS = ['Poor', 'Fair', 'Good', 'Great', 'Excellent']

// ── Star SVG ──────────────────────────────────────────────────────────────────

function StarIcon({ filled }: { filled: boolean }) {
  return (
    <svg width="56" height="56" viewBox="0 0 56 56" fill="none" aria-hidden="true">
      <path
        d="M28 6l5.5 16.5H51L37.5 33l5.5 16.5L28 39 13 49.5 18.5 33 5 22.5h17.5L28 6z"
        fill={filled ? 'currentColor' : 'none'}
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
      />
    </svg>
  )
}

// ── Star row ──────────────────────────────────────────────────────────────────

function StarRow({
  score,
  onSelect,
  onInteract,
}: {
  score: number | null
  onSelect: (s: number) => void
  onInteract: () => void
}) {
  const [lastTapped, setLastTapped] = useState<number | null>(null)

  function handleTap(i: number) {
    setLastTapped(i)
    onSelect(i + 1)
    onInteract()
    setTimeout(() => setLastTapped(null), 600)
  }

  return (
    <div className="flex gap-2 justify-center" role="group" aria-label="Star rating">
      {[0, 1, 2, 3, 4].map((i) => {
        const filled   = score !== null && i < score
        const popping  = lastTapped !== null && i <= lastTapped

        return (
          <motion.button
            key={i}
            onClick={() => handleTap(i)}
            animate={popping
              ? { scale: [1, 0.8, 1.15, 1.0] }
              : { scale: 1 }
            }
            transition={popping
              ? { delay: i * 0.05, duration: 0.25, times: [0, 0.2, 0.7, 1] }
              : { duration: 0.1 }
            }
            className={[
              'w-[72px] h-[72px] flex items-center justify-center',
              'rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tea-brown',
              'transition-colors select-none',
              filled ? 'text-leaf-green' : 'text-tea-brown/30',
            ].join(' ')}
            aria-label={`${i + 1} star${i === 0 ? '' : 's'}`}
            aria-pressed={filled}
          >
            <StarIcon filled={filled} />
          </motion.button>
        )
      })}
    </div>
  )
}

// ── Main screen ───────────────────────────────────────────────────────────────

export default function KioskFeedbackScreen() {
  const navigate        = useNavigate()
  const kioskMode       = useKioskStore((s) => s.kioskMode)
  const kioskUser       = useKioskStore((s) => s.kioskUser)  // kept for future PIN exit
  const deactivateKiosk = useKioskStore((s) => s.deactivateKiosk)
  const addToast        = useToastStore((s) => s.addToast)

  const [step,     setStep]     = useState<Step>('welcome')
  const [score,    setScore]    = useState<number | null>(null)
  const [comments, setComments] = useState<string>('')
  const [idempKey, setIdempKey] = useState<string>(() => crypto.randomUUID())

  // Refs for reading inside timeouts (avoid stale closure)
  const scoreRef    = useRef<number | null>(null)
  const commentsRef = useRef<string>('')
  const idempKeyRef = useRef<string>(idempKey)
  useEffect(() => { scoreRef.current    = score    }, [score])
  useEffect(() => { commentsRef.current = comments }, [comments])
  useEffect(() => { idempKeyRef.current = idempKey }, [idempKey])

  // Hidden corner tap (3-tap fast exit, no PIN required)
  const tapCount = useRef(0)
  const tapTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  // 60s idle timer
  const idleTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  // ── New session — reset all state for next guest ──────────────────────────
  function newSession() {
    setScore(null)
    setComments('')
    setIdempKey(crypto.randomUUID())
  }

  // ── POST /feedback mutation ───────────────────────────────────────────────
  const mutation = useMutation<unknown, { response?: { data?: { error?: string } } }>({
    mutationFn: () => {
      const s = scoreRef.current
      if (!s) return Promise.reject(new Error('No score'))
      return api.post('/feedback', {
        score:           s,
        comments:        commentsRef.current.trim() || undefined,
        idempotency_key: idempKeyRef.current,
        // department_id: omitted in v1 (requires UUID FK — no public endpoint to fetch)
        // served_by_employee_id: omitted in v1
      }).then((r) => r.data)
    },
    onSuccess: () => {
      setStep('done')
      setTimeout(() => {
        newSession()
        setStep('welcome')
      }, SUCCESS_DELAY)
    },
    onError: (err) => {
      const msg = err.response?.data?.error ?? 'Could not save feedback. Please ask a staff member.'
      addToast({ type: 'error', message: msg })
      newSession()
      setStep('welcome')
    },
  })

  // ── Guard: kiosk must be active ───────────────────────────────────────────
  useEffect(() => {
    if (!kioskMode) navigate('/', { replace: true })
  }, [kioskMode, navigate])

  // ── Disable back navigation ───────────────────────────────────────────────
  useEffect(() => {
    window.history.pushState(null, '', window.location.href)
    const handler = () => window.history.pushState(null, '', window.location.href)
    window.addEventListener('popstate', handler)
    return () => window.removeEventListener('popstate', handler)
  }, [])

  // ── 60s idle timer (rating + comment steps only) ──────────────────────────
  useEffect(() => {
    if (step !== 'rating' && step !== 'comment') {
      clearTimeout(idleTimer.current)
      return
    }

    function onIdle() {
      if (scoreRef.current !== null) {
        mutation.mutate()   // mutation reads from refs — no stale state issue
      } else {
        newSession()
        setStep('welcome')
      }
    }

    function onInteraction() {
      clearTimeout(idleTimer.current)
      idleTimer.current = setTimeout(onIdle, IDLE_60S)
    }

    const events = ['touchstart', 'mousedown', 'keydown'] as const
    events.forEach((e) => window.addEventListener(e, onInteraction, { passive: true }))

    // Arm immediately
    idleTimer.current = setTimeout(onIdle, IDLE_60S)

    return () => {
      clearTimeout(idleTimer.current)
      events.forEach((e) => window.removeEventListener(e, onInteraction))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step])

  // ── Corner 3-tap exit (instant, no PIN) ───────────────────────────────────
  function handleCornerTap() {
    tapCount.current += 1
    clearTimeout(tapTimer.current)
    if (tapCount.current >= 3) {
      tapCount.current = 0
      deactivateKiosk()
      navigate('/', { replace: true })
    } else {
      tapTimer.current = setTimeout(() => { tapCount.current = 0 }, 1500)
    }
  }

  // ── Submit helpers ────────────────────────────────────────────────────────
  function submitNow() {
    if (!score) return
    mutation.mutate()
  }

  // ── STEP: WELCOME ─────────────────────────────────────────────────────────
  if (step === 'welcome') {
    return (
      <div
        className="min-h-screen bg-ticket-paper flex flex-col items-center justify-center p-8 gap-10
          select-none"
        onContextMenu={(e) => e.preventDefault()}
        style={{ touchAction: 'pan-y', overscrollBehavior: 'none' }}
      >
        <div className="text-center space-y-4">
          <h1 className="font-serif text-8xl font-bold text-tea-brown tracking-widest leading-none">
            KARIBU
          </h1>
          <p className="font-serif text-3xl text-ticket-ink/70 tracking-wide leading-snug">
            How was your visit today?
          </p>
        </div>

        <button
          onClick={() => setStep('rating')}
          className="min-h-[64px] px-12 rounded-2xl bg-tea-brown text-ticket-paper
            text-xl font-semibold tracking-wide
            hover:bg-tea-brown/90 active:scale-[0.99] transition-all
            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tea-brown"
        >
          Tap to begin
        </button>

        <p className="text-xs text-ticket-ink/30 tracking-widest uppercase">
          Waterfront Kurahia · Juja · Kiambu · Kenya
        </p>

        {/* Hidden corner exit */}
        <button
          onClick={handleCornerTap}
          aria-hidden="true"
          tabIndex={-1}
          className="fixed bottom-0 right-0 w-[60px] h-[60px] opacity-0 cursor-default"
        />
      </div>
    )
  }

  // ── STEP: RATING ──────────────────────────────────────────────────────────
  if (step === 'rating') {
    return (
      <div
        className="min-h-screen bg-ticket-paper flex flex-col items-center justify-center p-8 gap-8
          select-none"
        onContextMenu={(e) => e.preventDefault()}
        style={{ touchAction: 'pan-y', overscrollBehavior: 'none' }}
      >
        <div className="text-center space-y-2">
          <p className="text-xs tracking-[0.4em] text-tea-brown/50 uppercase">Waterfront Kurahia</p>
          <h1 className="font-serif text-5xl font-bold text-tea-brown tracking-widest">
            RATE YOUR VISIT
          </h1>
        </div>

        <div className="flex flex-col items-center gap-6 w-full max-w-sm">
          <p className="text-xs font-semibold text-ticket-ink/40 tracking-[0.3em] uppercase">
            Tap a star
          </p>

          <StarRow
            score={score}
            onSelect={setScore}
            onInteract={() => clearTimeout(idleTimer.current)}
          />

          {/* Star label row */}
          <div className="flex gap-2 w-full">
            {STAR_LABELS.map((label, i) => (
              <div key={i} className="flex-1 text-center">
                <span className={[
                  'text-xs font-medium transition-colors',
                  score === i + 1 ? 'text-tea-brown font-bold' : 'text-ticket-ink/30',
                ].join(' ')}>
                  {label}
                </span>
              </div>
            ))}
          </div>

          <div className="w-full space-y-3 pt-2">
            <button
              onClick={() => setStep('comment')}
              disabled={!score}
              className="w-full min-h-[56px] rounded-2xl bg-tea-brown text-ticket-paper
                text-lg font-semibold tracking-wide
                hover:bg-tea-brown/90 active:scale-[0.99] transition-all
                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tea-brown
                disabled:opacity-30 disabled:cursor-not-allowed"
            >
              Next
            </button>

            <button
              onClick={submitNow}
              disabled={!score || mutation.isPending}
              className="w-full min-h-[44px] text-sm text-ticket-ink/40 hover:text-tea-brown
                underline transition-colors focus-visible:outline-none
                disabled:opacity-30 disabled:cursor-not-allowed"
            >
              {mutation.isPending ? 'Submitting…' : 'Skip details, submit now'}
            </button>
          </div>
        </div>

        {/* Hidden corner exit */}
        <button
          onClick={handleCornerTap}
          aria-hidden="true"
          tabIndex={-1}
          className="fixed bottom-0 right-0 w-[60px] h-[60px] opacity-0 cursor-default"
        />
      </div>
    )
  }

  // ── STEP: COMMENT ─────────────────────────────────────────────────────────
  if (step === 'comment') {
    const remaining = 500 - comments.length

    return (
      <div
        className="min-h-screen bg-ticket-paper flex flex-col items-center justify-center p-8 gap-8
          select-none"
        onContextMenu={(e) => e.preventDefault()}
        style={{ touchAction: 'pan-y', overscrollBehavior: 'none' }}
      >
        <div className="text-center space-y-2">
          <p className="text-xs tracking-[0.4em] text-tea-brown/50 uppercase">Waterfront Kurahia</p>
          <h1 className="font-serif text-5xl font-bold text-tea-brown tracking-widest">
            ANYTHING ELSE?
          </h1>
          <p className="text-base text-ticket-ink/60">
            Optional — your feedback helps us improve.
          </p>
        </div>

        <div className="w-full max-w-sm space-y-2">
          <textarea
            value={comments}
            onChange={(e) => {
              setComments(e.target.value)
              clearTimeout(idleTimer.current)
            }}
            maxLength={500}
            rows={5}
            placeholder="Tell us about your experience…"
            className="w-full rounded-2xl border border-tea-brown/30 bg-white px-5 py-4
              text-lg text-ticket-ink leading-relaxed resize-none
              focus:outline-none focus:border-tea-brown focus:ring-2 focus:ring-tea-brown/20
              placeholder:text-ticket-ink/25"
            style={{ touchAction: 'auto' }}  // allow scroll inside textarea
          />
          <p className="text-right text-xs text-ticket-ink/30">
            {remaining} characters remaining
          </p>
        </div>

        <div className="w-full max-w-sm space-y-3">
          <button
            onClick={submitNow}
            disabled={mutation.isPending}
            className="w-full min-h-[56px] rounded-2xl bg-tea-brown text-ticket-paper
              text-lg font-semibold tracking-wide
              hover:bg-tea-brown/90 active:scale-[0.99] transition-all
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tea-brown
              disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {mutation.isPending ? 'Submitting…' : 'Submit Feedback'}
          </button>

          <button
            onClick={submitNow}
            disabled={mutation.isPending}
            className="w-full min-h-[44px] text-sm text-ticket-ink/40 hover:text-tea-brown
              underline transition-colors focus-visible:outline-none
              disabled:opacity-30 disabled:cursor-not-allowed"
          >
            Skip and submit
          </button>
        </div>

        {/* Hidden corner exit */}
        <button
          onClick={handleCornerTap}
          aria-hidden="true"
          tabIndex={-1}
          className="fixed bottom-0 right-0 w-[60px] h-[60px] opacity-0 cursor-default"
        />
      </div>
    )
  }

  // ── STEP: DONE ────────────────────────────────────────────────────────────
  return (
    <div
      className="min-h-screen bg-ticket-paper flex flex-col items-center justify-center p-8 gap-8
        select-none"
      onContextMenu={(e) => e.preventDefault()}
    >
      <AnimatePresence>
        <motion.div
          key="done"
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.35, ease: 'easeOut' }}
          className="flex flex-col items-center gap-6 text-center"
        >
          <div className="text-leaf-green">
            <svg width="72" height="72" viewBox="0 0 72 72" fill="none" aria-hidden="true">
              <circle cx="36" cy="36" r="34" stroke="currentColor" strokeWidth="2.5"/>
              <path
                d="M22 36l11 11 17-22"
                stroke="currentColor"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>

          <h1 className="font-serif text-8xl font-bold text-leaf-green tracking-widest leading-none">
            ASANTE!
          </h1>

          <p className="font-serif text-2xl text-ticket-ink/70 tracking-wide">
            Your feedback helps us improve.
          </p>

          <p className="text-sm text-ticket-ink/30 tracking-widest uppercase mt-4">
            Returning in 5 seconds…
          </p>
        </motion.div>
      </AnimatePresence>

      {/* Hidden corner exit */}
      <button
        onClick={handleCornerTap}
        aria-hidden="true"
        tabIndex={-1}
        className="fixed bottom-0 right-0 w-[60px] h-[60px] opacity-0 cursor-default"
      />
    </div>
  )
}
