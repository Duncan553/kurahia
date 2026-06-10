import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import axios from 'axios'
import api from '../lib/axios'
import { decodeJWT } from '../lib/jwt'
import { useAuthStore } from '../stores/authStore'

interface LoginResponse {
  access_token: string
  refresh_token?: true
  requires_pin_setup?: true
}
interface JWTClaims extends Record<string, unknown> {
  sub: string
  role_level: number
  department?: string | null
  requires_pin_setup?: boolean
}

const HERO_URL =
  'https://waterfrontcountryclub.com/wp-content/uploads/2025/08/DJI_0669-scaled.jpg'

export default function LoginScreen() {
  const navigate = useNavigate()
  const { setAuth, setSetupToken } = useAuthStore()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [errorMsg, setErrorMsg] = useState('')

  const loginMutation = useMutation({
    mutationFn: (data: { username: string; password: string }) =>
      api.post<LoginResponse>('/auth/login', data).then((r) => r.data),
    onSuccess: (data) => {
      setErrorMsg('')
      const claims = decodeJWT<JWTClaims>(data.access_token)
      if (data.requires_pin_setup) {
        setSetupToken(data.access_token)
        navigate('/pin/setup', { state: { username } })
        return
      }
      setAuth(
        { id: claims.sub, username, role_level: claims.role_level, department: claims.department ?? null },
        data.access_token,
      )
      navigate('/clock')
    },
    onError: (err) => {
      if (axios.isAxiosError(err)) {
        setErrorMsg((err.response?.data as { error?: string })?.error ?? 'Login failed.')
      } else {
        setErrorMsg('Something went wrong. Try again.')
      }
    },
  })

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setErrorMsg('')
    loginMutation.mutate({ username, password })
  }

  return (
    <div className="relative min-h-screen overflow-hidden">

      {/* ── Hero: full-bleed aerial, darker overlay for glass contrast ── */}
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
        <div className="absolute inset-0 bg-primary-dark/45" />
      </motion.div>

      {/* ── Wordmark bottom-right (desktop only) ─────────────────────── */}
      <motion.div
        className="absolute bottom-10 right-10 hidden md:block text-right z-10 pointer-events-none"
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, delay: 0.9, ease: 'easeOut' }}
      >
        <p
          className="font-serif text-5xl font-bold tracking-widest text-white leading-none"
          style={{ textShadow: '0 2px 24px rgba(0,0,0,0.6)' }}
        >
          WATERFRONT<br />COUNTRY CLUB
        </p>
        <p className="mt-2 text-[10px] tracking-[0.3em] uppercase text-white/50 font-medium">
          JUJA · KIAMBU · KENYA
        </p>
      </motion.div>

      {/* ── Floating glass card — left on desktop, full-screen on mobile ─ */}
      <div className="relative z-10 flex items-center min-h-screen md:pl-12">

        <motion.div
          className="login-torn-edge w-full md:max-w-[480px]
            bg-cream-card/30 backdrop-blur-xl border-0 md:border md:border-white/20
            min-h-screen md:min-h-0"
          initial={{ x: -60, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          transition={{ duration: 0.5, delay: 0.25, ease: 'easeOut' }}
        >
          <div className="flex items-center min-h-screen md:min-h-0">
            <div className="w-full max-w-[360px] mx-auto md:ml-14 px-8 md:px-0 py-16">

              {/* Eyebrow + heading */}
              <motion.div
                className="mb-8"
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, delay: 0.45, ease: 'easeOut' }}
              >
                <p className="text-[10px] tracking-[0.3em] uppercase text-white/60 font-medium mb-3">
                  KURAHIA STAFF
                </p>
                <h1
                  className="font-serif text-6xl font-bold tracking-tight text-white leading-[0.92]"
                  style={{ textShadow: '0 2px 16px rgba(0,0,0,0.4)' }}
                >
                  SIGN<br />IN.
                </h1>
              </motion.div>

              {/* Accent rule */}
              <motion.div
                className="w-10 h-[2px] bg-primary-light mb-8"
                initial={{ scaleX: 0, originX: 0 }}
                animate={{ scaleX: 1 }}
                transition={{ duration: 0.35, delay: 0.6, ease: 'easeOut' }}
              />

              {/* Form */}
              <motion.form
                onSubmit={handleSubmit}
                noValidate
                className="space-y-4"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.35, delay: 0.65, ease: 'easeOut' }}
              >
                <div>
                  <label className="block text-[10px] tracking-[0.2em] uppercase text-white/60 font-medium mb-1.5">
                    Username
                  </label>
                  <input
                    type="text"
                    autoComplete="username"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    disabled={loginMutation.isPending}
                    className="
                      w-full rounded-xl px-4 py-3
                      bg-cream-card/70 backdrop-blur-sm border border-white/30
                      text-ink-primary text-sm font-medium
                      placeholder:text-ink-tertiary
                      focus:outline-none focus:border-primary-light focus:ring-2 focus:ring-primary-light/30
                      disabled:opacity-50 transition-all
                    "
                  />
                </div>

                <div>
                  <label className="block text-[10px] tracking-[0.2em] uppercase text-white/60 font-medium mb-1.5">
                    Password
                  </label>
                  <input
                    type="password"
                    autoComplete="current-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    disabled={loginMutation.isPending}
                    className="
                      w-full rounded-xl px-4 py-3
                      bg-cream-card/70 backdrop-blur-sm border border-white/30
                      text-ink-primary text-sm font-medium
                      placeholder:text-ink-tertiary
                      focus:outline-none focus:border-primary-light focus:ring-2 focus:ring-primary-light/30
                      disabled:opacity-50 transition-all
                    "
                  />
                </div>

                {errorMsg && (
                  <p role="alert" className="text-sm text-status-failed font-semibold">
                    {errorMsg}
                  </p>
                )}

                <button
                  type="submit"
                  disabled={!username || !password || loginMutation.isPending}
                  className="
                    w-full mt-2 py-3.5 rounded-xl
                    bg-primary-dark text-cream-card
                    text-sm font-semibold tracking-widest uppercase
                    hover:bg-primary-main active:scale-[0.99]
                    focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-light focus-visible:ring-offset-2 focus-visible:ring-offset-transparent
                    disabled:opacity-50 disabled:cursor-not-allowed
                    transition-all
                  "
                >
                  {loginMutation.isPending ? (
                    <span className="flex items-center justify-center gap-2">
                      <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
                        <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" strokeOpacity="0.3" />
                        <path d="M21 12a9 9 0 01-9 9" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                      </svg>
                      Signing in…
                    </span>
                  ) : 'Sign in ↗'}
                </button>
              </motion.form>

              <button
                type="button"
                onClick={() => navigate('/pin')}
                className="mt-6 text-xs text-white/70 hover:text-white font-medium
                  tracking-widest uppercase transition-colors flex items-center gap-2"
              >
                Use PIN instead <span className="text-primary-light" aria-hidden="true">↗</span>
              </button>
            </div>
          </div>
        </motion.div>
      </div>

    </div>
  )
}
