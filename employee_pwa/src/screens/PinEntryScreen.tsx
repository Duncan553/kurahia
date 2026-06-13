import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import axios from 'axios'
import api from '../lib/axios'
import { decodeJWT } from '../lib/jwt'
import { useAuthStore } from '../stores/authStore'
import { Modal, Button } from '@shared'

interface PinLoginResponse { access_token: string; refresh_token: string }
interface JWTClaims extends Record<string, unknown> {
  sub: string
  role_level: number
  department?: string | null
}

const KEYPAD = ['1','2','3','4','5','6','7','8','9','','0','⌫'] as const

const HERO_URL =
  'https://waterfrontcountryclub.com/wp-content/uploads/2025/08/DJI_0669-scaled.jpg'

export default function PinEntryScreen() {
  const navigate = useNavigate()
  const { setAuth } = useAuthStore()
  const [username, setUsername] = useState('')
  const [digits,   setDigits]   = useState('')
  const [errorMsg, setErrorMsg] = useState('')
  const [lockoutOpen, setLockoutOpen] = useState(false)
  const [lockoutMsg,  setLockoutMsg]  = useState('')

  const pushDigit = useCallback((d: string) => {
    setDigits((prev) => (prev.length < 4 ? prev + d : prev))
  }, [])
  const pop = useCallback(() => setDigits((prev) => prev.slice(0, -1)), [])

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (/^[0-9]$/.test(e.key)) { pushDigit(e.key); return }
      if (e.key === 'Backspace')  { pop(); return }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [pushDigit, pop])

  const pinMutation = useMutation({
    mutationFn: (data: { username: string; pin: string }) =>
      api.post<PinLoginResponse>('/auth/pin-login', data).then((r) => r.data),
    onSuccess: (data) => {
      setErrorMsg('')
      const claims = decodeJWT<JWTClaims>(data.access_token)
      setAuth(
        { id: claims.sub, username, role_level: claims.role_level, department: claims.department ?? null },
        data.access_token,
      )
      navigate('/clock')
    },
    onError: (err) => {
      setDigits('')
      if (axios.isAxiosError(err)) {
        const msg = (err.response?.data as { error?: string })?.error ?? 'PIN failed.'
        if (msg.toLowerCase().includes('locked')) {
          setLockoutMsg(msg); setLockoutOpen(true)
        } else {
          setErrorMsg(msg)
        }
      } else {
        setErrorMsg('Something went wrong. Try again.')
      }
    },
  })

  function handleKey(key: typeof KEYPAD[number]) {
    if (key === '') return
    if (key === '⌫') { pop(); return }
    pushDigit(key)
  }

  function handleSubmit() {
    if (!username || digits.length !== 4) return
    setErrorMsg('')
    pinMutation.mutate({ username, pin: digits })
  }

  // Auto-submit when 4 digits entered + username filled
  useEffect(() => {
    if (digits.length !== 4) return
    if (!username.trim()) {
      setErrorMsg('Enter your username above first.')
      return
    }
    handleSubmit()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [digits])

  return (
    <div className="relative min-h-screen overflow-hidden">

      {/* ── Hero: same aerial photo as LoginScreen ─────────────────── */}
      <motion.div
        className="absolute inset-0"
        initial={{ opacity: 0, scale: 1.04 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 1.1, ease: 'easeOut' }}
      >
        <img
          src={HERO_URL}
          alt=""
          aria-hidden="true"
          className="w-full h-full object-cover object-center"
        />
        <div className="absolute inset-0 bg-primary-dark/20 mix-blend-multiply" />
      </motion.div>

      {/* ── Wordmark bottom-right (desktop only) ─────────────────── */}
      <motion.div
        className="absolute bottom-10 right-10 hidden md:block text-right z-10 pointer-events-none"
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.8, ease: 'easeOut' }}
      >
        <p
          className="font-serif text-5xl font-bold tracking-widest text-white leading-none"
          style={{ textShadow: '0 2px 20px rgba(0,0,0,0.55)' }}
        >
          WATERFRONT<br />COUNTRY CLUB
        </p>
        <p className="mt-2 text-[10px] tracking-[0.3em] uppercase text-white/60 font-medium">
          JUJA · KIAMBU · KENYA
        </p>
      </motion.div>

      {/* ── Torn card ────────────────────────────────────────────────── */}
      <div className="relative z-10 flex min-h-screen">
        <motion.div
          className="login-torn-edge w-full md:w-[52%] bg-cream-card min-h-screen"
          initial={{ x: -60, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          transition={{ duration: 0.5, delay: 0.25, ease: 'easeOut' }}
        >
          <div className="flex items-center min-h-screen">
            <div className="w-full max-w-[360px] mx-auto md:ml-14 px-8 md:px-0 py-12">

              {/* Heading */}
              <motion.div
                className="mb-6"
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, delay: 0.45, ease: 'easeOut' }}
              >
                <p className="text-[10px] tracking-[0.3em] uppercase text-ink-secondary font-medium mb-3">
                  KURAHIA STAFF
                </p>
                <h1 className="font-serif text-5xl font-bold tracking-tight text-ink-primary leading-[0.92]">
                  ENTER<br />PIN.
                </h1>
              </motion.div>

              {/* Terracotta rule */}
              <motion.div
                className="w-10 h-[2px] bg-primary-main mb-6"
                initial={{ scaleX: 0, originX: 0 }}
                animate={{ scaleX: 1 }}
                transition={{ duration: 0.35, delay: 0.6, ease: 'easeOut' }}
              />

              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.35, delay: 0.65, ease: 'easeOut' }}
                className="space-y-5"
              >
                {/* Username field */}
                <div>
                  <label htmlFor="pin-username" className="block text-[10px] tracking-[0.2em] uppercase text-ink-secondary font-medium mb-1.5">
                    Username
                  </label>
                  <input
                    id="pin-username"
                    type="text"
                    autoComplete="username"
                    value={username}
                    onChange={(e) => { setUsername(e.target.value); setDigits('') }}
                    disabled={pinMutation.isPending}
                    className="
                      w-full rounded-xl px-4 py-3
                      bg-cream-alt border border-cream-deep
                      text-ink-primary text-sm font-medium
                      placeholder:text-ink-tertiary
                      focus:outline-none focus:border-primary-main focus:ring-2 focus:ring-primary-main/20
                      disabled:opacity-50 transition-all
                    "
                  />
                </div>

                {/* PIN dots */}
                <div
                  role="group"
                  className="flex justify-center gap-4 py-2"
                  aria-label="PIN entry"
                  aria-live="polite"
                >
                  {[0,1,2,3].map((i) => (
                    <motion.div
                      key={i}
                      animate={{
                        scale: i < digits.length ? 1.15 : 1,
                        backgroundColor: i < digits.length ? 'var(--color-primary-dark)' : 'transparent',
                      }}
                      transition={{ duration: 0.1 }}
                      className="w-4 h-4 rounded-full border-2"
                      style={{ borderColor: i < digits.length ? 'var(--color-primary-dark)' : 'var(--color-cream-deep)' }}
                    />
                  ))}
                </div>

                {/* Error */}
                {errorMsg && (
                  <p role="alert" className="text-sm text-status-failed font-medium text-center">
                    {errorMsg}
                  </p>
                )}

                {/* Keypad */}
                <div className="grid grid-cols-3 gap-2.5">
                  {KEYPAD.map((key, i) => (
                    key === '' ? (
                      <div key={i} />
                    ) : (
                      <button
                        key={i}
                        type="button"
                        onClick={() => handleKey(key)}
                        disabled={pinMutation.isPending}
                        aria-label={key === '⌫' ? 'Backspace' : key}
                        className={[
                          'min-h-[64px] w-full rounded-2xl text-2xl font-semibold',
                          'flex items-center justify-center select-none',
                          'transition-all duration-75',
                          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-main',
                          'disabled:opacity-40',
                          key === '⌫'
                            ? 'bg-transparent text-ink-secondary active:text-ink-primary active:scale-95'
                            : 'bg-white shadow-sm border border-cream-alt text-ink-primary active:bg-primary-light/30 active:shadow-none active:scale-95',
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

                {/* Switch to password */}
                <button
                  type="button"
                  onClick={() => navigate('/login')}
                  className="w-full min-h-[44px] text-xs text-ink-secondary hover:text-primary-dark
                    tracking-widest uppercase transition-colors flex items-center justify-center gap-2 font-medium
                    focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark rounded"
                >
                  Use password instead <span className="text-primary-main" aria-hidden="true">↗</span>
                </button>
              </motion.div>
            </div>
          </div>
        </motion.div>
      </div>

      {/* Lockout modal — logic unchanged */}
      <Modal open={lockoutOpen} onClose={() => setLockoutOpen(false)} title="Account Locked" preventClose>
        <p className="text-base text-ink-secondary mb-6">{lockoutMsg}</p>
        <div className="flex justify-end">
          <Button variant="secondary" onClick={() => setLockoutOpen(false)}>OK</Button>
        </div>
      </Modal>
    </div>
  )
}
