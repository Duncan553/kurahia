import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import axios from 'axios'
import axiosBase from 'axios'
import { decodeJWT } from '../lib/jwt'
import { useAuthStore } from '../stores/authStore'

interface SetPinResponse { access_token: string; refresh_token: string }
interface JWTClaims extends Record<string, unknown> {
  sub: string
  role_level: number
  department?: string | null
}

const HERO_URL =
  'https://waterfrontcountryclub.com/wp-content/uploads/2025/08/DJI_0669-scaled.jpg'

function criteria(pin: string, confirm: string) {
  return {
    length:  pin.length === 4,
    digits:  /^\d+$/.test(pin) || pin === '',
    matches: pin.length === 4 && pin === confirm,
  }
}

function CriteriaRow({ met, label }: { met: boolean; label: string }) {
  return (
    <li className="flex items-center gap-2 text-xs">
      <motion.span
        animate={{ color: met ? 'var(--color-status-paid)' : 'var(--color-ink-tertiary)' }}
        transition={{ duration: 0.2 }}
      >
        {met ? '✓' : '○'}
      </motion.span>
      <span className={met ? 'text-ink-primary' : 'text-ink-tertiary'}>{label}</span>
    </li>
  )
}

export default function PinSetupScreen() {
  const navigate = useNavigate()
  const { state } = useLocation()
  const username = (state as { username?: string } | null)?.username ?? ''
  const { setupToken, setAuth } = useAuthStore()
  const [pin,     setPin]     = useState('')
  const [confirm, setConfirm] = useState('')
  const [errorMsg, setErrorMsg] = useState('')

  const c = criteria(pin, confirm)
  const ready = c.length && c.digits && c.matches

  const setupMutation = useMutation({
    mutationFn: () => {
      if (!setupToken) return Promise.reject(new Error('No setup token'))
      return axiosBase.post<SetPinResponse>(
        // Fall back to relative URL (dev/preview proxy) when VITE_API_URL is unset —
        // interpolating undefined produced "undefined/auth/set-pin" in prod builds
        `${import.meta.env.VITE_API_URL ?? ''}/auth/set-pin`,
        { pin },
        { headers: { Authorization: `Bearer ${setupToken}` }, withCredentials: true }
      ).then((r) => r.data)
    },
    onSuccess: (data) => {
      setErrorMsg('')
      const claims = decodeJWT<JWTClaims>(data.access_token)
      setAuth(
        { id: claims.sub, username, role_level: claims.role_level, department: claims.department ?? null },
        data.access_token,
      )
      navigate('/')
    },
    onError: (err) => {
      if (axios.isAxiosError(err)) {
        setErrorMsg((err.response?.data as { error?: string })?.error ?? 'PIN setup failed.')
      } else {
        setErrorMsg(String(err))
      }
    },
  })

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!ready) return
    setupMutation.mutate()
  }

  return (
    <div className="relative min-h-screen overflow-hidden">

      {/* ── Hero ──────────────────────────────────────────────────── */}
      <motion.div
        className="absolute inset-0"
        initial={{ opacity: 0, scale: 1.04 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 1.1, ease: 'easeOut' }}
      >
        <img src={HERO_URL} alt="" aria-hidden="true"
          className="w-full h-full object-cover object-center" />
        <div className="absolute inset-0 bg-primary-dark/20 mix-blend-multiply" />
      </motion.div>

      {/* ── Wordmark bottom-right (desktop) ───────────────────────── */}
      <motion.div
        className="absolute bottom-10 right-10 hidden md:block text-right z-10 pointer-events-none"
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.8, ease: 'easeOut' }}
      >
        <p className="font-serif text-5xl font-bold tracking-widest text-white leading-none"
          style={{ textShadow: '0 2px 20px rgba(0,0,0,0.55)' }}>
          WATERFRONT<br />COUNTRY CLUB
        </p>
        <p className="mt-2 text-[10px] tracking-[0.3em] uppercase text-white/60 font-medium">
          JUJA · KIAMBU · KENYA
        </p>
      </motion.div>

      {/* ── Torn card ─────────────────────────────────────────────── */}
      <div className="relative z-10 flex min-h-screen">
        <motion.div
          className="login-torn-edge w-full md:w-[52%] bg-cream-card min-h-screen"
          initial={{ x: -60, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          transition={{ duration: 0.5, delay: 0.25, ease: 'easeOut' }}
        >
          <div className="flex items-center min-h-screen">
            <div className="w-full max-w-[360px] mx-auto md:ml-14 px-8 md:px-0 py-16">

              {/* Heading */}
              <motion.div className="mb-6"
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, delay: 0.45, ease: 'easeOut' }}>
                <p className="text-[10px] tracking-[0.3em] uppercase text-ink-secondary font-medium mb-3">
                  KURAHIA STAFF
                </p>
                <h1 className="font-serif text-5xl font-bold tracking-tight text-ink-primary leading-[0.92]">
                  SET YOUR<br />PIN.
                </h1>
                {username && (
                  <p className="mt-3 text-xs text-ink-secondary tracking-wide">
                    Account: <span className="text-ink-primary font-medium">{username}</span>
                  </p>
                )}
              </motion.div>

              {/* Terracotta rule */}
              <motion.div className="w-10 h-[2px] bg-primary-main mb-6"
                initial={{ scaleX: 0, originX: 0 }}
                animate={{ scaleX: 1 }}
                transition={{ duration: 0.35, delay: 0.6, ease: 'easeOut' }} />

              <motion.form
                onSubmit={handleSubmit}
                noValidate
                className="space-y-4"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.35, delay: 0.65, ease: 'easeOut' }}
              >
                <div>
                  <label className="block text-[10px] tracking-[0.2em] uppercase text-ink-secondary font-medium mb-1.5">
                    New PIN
                  </label>
                  <input
                    type="password"
                    inputMode="numeric"
                    maxLength={4}
                    value={pin}
                    onChange={(e) => setPin(e.target.value.replace(/\D/g, '').slice(0, 4))}
                    disabled={setupMutation.isPending}
                    placeholder="••••"
                    className="
                      w-full rounded-xl px-4 py-3
                      bg-cream-alt border border-cream-deep
                      text-ink-primary text-sm font-medium tracking-[0.4em]
                      placeholder:text-ink-tertiary placeholder:tracking-normal
                      focus:outline-none focus:border-primary-main focus:ring-2 focus:ring-primary-main/20
                      disabled:opacity-50 transition-all
                    "
                  />
                </div>

                <div>
                  <label className="block text-[10px] tracking-[0.2em] uppercase text-ink-secondary font-medium mb-1.5">
                    Confirm PIN
                  </label>
                  <input
                    type="password"
                    inputMode="numeric"
                    maxLength={4}
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value.replace(/\D/g, '').slice(0, 4))}
                    disabled={setupMutation.isPending}
                    placeholder="••••"
                    className="
                      w-full rounded-xl px-4 py-3
                      bg-cream-alt border border-cream-deep
                      text-ink-primary text-sm font-medium tracking-[0.4em]
                      placeholder:text-ink-tertiary placeholder:tracking-normal
                      focus:outline-none focus:border-primary-main focus:ring-2 focus:ring-primary-main/20
                      disabled:opacity-50 transition-all
                    "
                  />
                </div>

                {/* Live criteria */}
                <ul className="space-y-1.5 pl-1">
                  <CriteriaRow met={c.length}  label="4 digits required" />
                  <CriteriaRow met={c.digits}  label="Digits only (0–9)" />
                  <CriteriaRow met={c.matches} label="PINs match" />
                </ul>

                {errorMsg && (
                  <p role="alert" className="text-sm text-status-failed font-medium">{errorMsg}</p>
                )}

                <button
                  type="submit"
                  disabled={!ready || setupMutation.isPending}
                  className="
                    w-full mt-2 py-3.5 rounded-xl
                    bg-primary-dark text-cream-card
                    text-sm font-semibold tracking-widest uppercase
                    hover:bg-primary-main active:scale-[0.99]
                    focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-main focus-visible:ring-offset-2
                    disabled:opacity-50 disabled:cursor-not-allowed
                    transition-all
                  "
                >
                  {setupMutation.isPending ? (
                    <span className="flex items-center justify-center gap-2">
                      <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
                        <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" strokeOpacity="0.3" />
                        <path d="M21 12a9 9 0 01-9 9" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                      </svg>
                      Setting PIN…
                    </span>
                  ) : 'Set PIN & sign in ↗'}
                </button>
              </motion.form>

              <button type="button" onClick={() => navigate('/login')}
                className="mt-6 min-h-[44px] text-xs text-ink-secondary hover:text-primary-dark font-medium
                  tracking-widest uppercase transition-colors flex items-center gap-2
                  focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark rounded">
                Back to login <span className="text-primary-main" aria-hidden="true">↗</span>
              </button>
            </div>
          </div>
        </motion.div>
      </div>
    </div>
  )
}
