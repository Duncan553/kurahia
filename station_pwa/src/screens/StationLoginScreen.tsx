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

// Real Kurahia property photo, served locally (no external dependency at login time).
const HERO_URL = '/images/resort-bg.jpg'

export default function StationLoginScreen() {
  const navigate = useNavigate()
  const { setAuth } = useAuthStore()
  const [username, setUsername] = useState('')
  const [digits,   setDigits]   = useState('')
  const [errorMsg, setErrorMsg] = useState('')
  const [lockoutOpen, setLockoutOpen] = useState(false)
  const [lockoutMsg,  setLockoutMsg]  = useState('')
  const [focused, setFocused] = useState(false)

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
    onSuccess: async (data) => {
      setErrorMsg('')
      const claims = decodeJWT<JWTClaims>(data.access_token)
      setAuth(
        { id: claims.sub, username, role_level: claims.role_level, department: claims.department ?? null },
        data.access_token,
        data.refresh_token,
      )
      // Station tablets have no separate personal Clock screen — whoever PINs
      // in here is, by definition, on shift right now. Clock them in silently
      // so POS/orders/payments (require_clocked_in on the backend) just work.
      // 'duplicate: true' comes back harmless if they're already clocked in
      // (e.g. clocked in on their own phone earlier today).
      try {
        await api.post('/hr/clock-in')
      } catch {
        // WiFi-allowlist rejection or no employee profile — surface via the
        // work screen itself (every gated action already shows its own
        // plain-English error), not by blocking the login here.
      }
      navigate('/')
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
      <motion.div
        className="absolute inset-0"
        initial={{ opacity: 0, scale: 1.03 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 1.2, ease: 'easeOut' }}
      >
        <img src={HERO_URL} alt="" aria-hidden="true"
          className="w-full h-full object-cover object-center" />
        <div className="absolute inset-0" style={{ background: 'var(--color-chrome-75)' }} />
      </motion.div>

      <div className="relative z-10 flex items-center justify-center min-h-screen px-6 py-8">
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.3, ease: 'easeOut' }}
          className="w-full max-w-[360px]"
        >
          <div className="text-center mb-6">
            <h1 className="font-serif text-3xl font-bold text-ink-primary tracking-tight
              drop-shadow-[0_2px_12px_rgba(0,0,0,0.3)]">
              Kurahia Station
            </h1>
            <p className="text-sm text-ink-primary/60 mt-1">Enter your PIN to start your shift</p>
          </div>

          <div className="rounded-3xl p-6 border border-white/20 shadow-2xl
            glass-card backdrop-blur-xl relative overflow-hidden">
            <div className="relative space-y-5">
              <div>
                <label htmlFor="pin-username"
                  className="block text-xs font-semibold text-ink-primary/80 mb-1.5 uppercase tracking-wider">
                  Username
                </label>
                <div className={`rounded-xl border transition-all ${
                  focused ? 'border-white/50 shadow-[0_0_0_3px_rgba(255,255,255,0.1)]' : 'border-white/20'
                }`}>
                  <input
                    id="pin-username"
                    type="text"
                    autoComplete="username"
                    value={username}
                    onChange={e => { setUsername(e.target.value); setDigits('') }}
                    onFocus={() => setFocused(true)}
                    onBlur={() => setFocused(false)}
                    disabled={pinMutation.isPending}
                    placeholder="e.g. cynthia.achieng"
                    className="w-full rounded-xl bg-white/10 backdrop-blur-sm px-4 py-3
                      text-sm text-ink-primary font-medium placeholder:text-ink-primary/40
                      focus:outline-none disabled:opacity-50"
                  />
                </div>
              </div>

              <div role="group" className="flex justify-center gap-4 py-3" aria-label="PIN entry" aria-live="polite">
                {[0,1,2,3].map(i => (
                  <motion.div key={i}
                    animate={{
                      scale: i < digits.length ? 1.2 : 1,
                      backgroundColor: i < digits.length ? '#ffffff' : 'transparent',
                    }}
                    transition={{ duration: 0.1 }}
                    className="w-4 h-4 rounded-full border-2"
                    style={{ borderColor: i < digits.length ? '#ffffff' : 'rgba(255,255,255,0.35)' }}
                  />
                ))}
              </div>

              {errorMsg && (
                <motion.div initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }}
                  className="flex items-center justify-center gap-2 p-2 rounded-xl bg-status-failed/20 border border-status-failed/30">
                  <p role="alert" className="text-xs text-ink-primary font-medium">{errorMsg}</p>
                </motion.div>
              )}

              <div className="grid grid-cols-3 gap-2">
                {KEYPAD.map((key, i) => (
                  key === '' ? <div key={i} /> : (
                    <motion.button key={i} type="button"
                      onClick={() => handleKey(key)}
                      disabled={pinMutation.isPending}
                      whileTap={{ scale: 0.92 }}
                      aria-label={key === '⌫' ? 'Backspace' : key}
                      className={`min-h-[56px] w-full rounded-2xl text-xl font-semibold
                        flex items-center justify-center select-none transition-all
                        focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/40
                        disabled:opacity-40 ${
                          key === '⌫'
                            ? 'bg-transparent text-ink-primary/60 active:text-ink-primary'
                            : 'bg-white/12 backdrop-blur-sm border border-white/15 text-ink-primary hover:bg-white/20'
                        }`}
                    >
                      {key === '⌫' ? (
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                          <path d="M21 7H9.5L3 12l6.5 5H21V7z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
                          <path d="M15 10l-4 4M11 10l4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                        </svg>
                      ) : key}
                    </motion.button>
                  )
                ))}
              </div>
            </div>
          </div>
        </motion.div>
      </div>

      <Modal open={lockoutOpen} onClose={() => setLockoutOpen(false)} title="Account Locked" preventClose>
        <p className="text-base text-ink-secondary mb-6">{lockoutMsg}</p>
        <div className="flex justify-end">
          <Button variant="secondary" onClick={() => setLockoutOpen(false)}>OK</Button>
        </div>
      </Modal>
    </div>
  )
}
