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
  refresh_token?: string
  requires_pin_setup?: true
}
interface JWTClaims {
  sub: string
  role_level: number
}

export default function LoginScreen() {
  const navigate = useNavigate()
  const { setAuth, setSetupToken } = useAuthStore()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [errorMsg, setErrorMsg] = useState('')
  const [focused, setFocused] = useState<'user' | 'pass' | null>(null)

  const loginMutation = useMutation({
    mutationFn: (data: { username: string; password: string }) =>
      api.post<LoginResponse>('/auth/login', data).then((r) => r.data),
    onSuccess: (data) => {
      setErrorMsg('')
      const claims = decodeJWT<JWTClaims>(data.access_token)
      // If backend requires PIN setup, redirect there with a temp token
      if (data.requires_pin_setup) {
        setSetupToken(data.access_token)
        navigate('/pin/setup', { state: { username } })
        return
      }
      // Normal login — store auth and go to dashboard
      setAuth({ id: claims.sub, username, role_level: claims.role_level }, data.access_token, data.refresh_token ?? '')
      navigate('/')
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
    /* Warm dark background with resort photo overlay */
    <div className="relative min-h-screen bg-transparent flex items-center justify-center px-6">

      {/* Resort background photo with warm dark overlay */}
      <div className="absolute inset-0">
        <img src="/images/resort-bg.jpg" alt="" aria-hidden="true"
          className="w-full h-full object-cover" />
        <div className="absolute inset-0" style={{ background: 'rgba(30, 16, 12, 0.75)' }} />
      </div>

      {/* Ambient glow — faint orange radial behind the card for depth */}
      <div
        className="pointer-events-none absolute w-[480px] h-[480px] rounded-full opacity-[0.07]"
        style={{
          background: 'radial-gradient(circle, #fa5c29 0%, transparent 70%)',
        }}
      />

      {/* Main content — vertically centered column */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: 'easeOut' }}
        className="w-full max-w-[380px] relative z-10"
      >
        {/* Brand mark */}
        <div className="text-center mb-10">
          <motion.div
            initial={{ scale: 0.85, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ duration: 0.4, delay: 0.15 }}
            className="w-14 h-14 mx-auto mb-5 rounded-2xl
              bg-white/[0.06] border border-white/[0.08]
              flex items-center justify-center"
          >
            <span className="text-xl font-serif font-bold text-ink-primary tracking-tight">K</span>
          </motion.div>
          <h1 className="font-serif text-3xl font-bold text-ink-primary tracking-tight">
            Kurahia
          </h1>
          <p className="text-xs text-ink-tertiary mt-1.5 tracking-wide uppercase">
            Waterfront Club
          </p>
        </div>

        {/* Glass form card */}
        <div className="glass-card p-7">
          <form onSubmit={handleSubmit} noValidate className="space-y-5">

            {/* Username field */}
            <div>
              <label htmlFor="login-username"
                className="block text-xs font-medium text-ink-secondary mb-2 tracking-wide">
                Username
              </label>
              <input
                id="login-username"
                type="text"
                autoComplete="username"
                value={username}
                onChange={e => setUsername(e.target.value)}
                onFocus={() => setFocused('user')}
                onBlur={() => setFocused(null)}
                disabled={loginMutation.isPending}
                placeholder="e.g. wachira"
                className={`w-full rounded-xl bg-white/[0.04] px-4 py-3
                  text-sm text-ink-primary font-medium
                  placeholder:text-ink-tertiary
                  border transition-all duration-200
                  focus:outline-none disabled:opacity-50
                  ${focused === 'user'
                    ? 'border-primary-main/50 shadow-[0_0_0_2px_rgba(250,92,41,0.20)]'
                    : 'border-white/[0.08] hover:border-white/[0.14]'
                  }`}
              />
            </div>

            {/* Password field */}
            <div>
              <label htmlFor="login-password"
                className="block text-xs font-medium text-ink-secondary mb-2 tracking-wide">
                Password
              </label>
              <input
                id="login-password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                onFocus={() => setFocused('pass')}
                onBlur={() => setFocused(null)}
                disabled={loginMutation.isPending}
                className={`w-full rounded-xl bg-white/[0.04] px-4 py-3
                  text-sm text-ink-primary font-medium
                  placeholder:text-ink-tertiary
                  border transition-all duration-200
                  focus:outline-none disabled:opacity-50
                  ${focused === 'pass'
                    ? 'border-primary-main/50 shadow-[0_0_0_2px_rgba(250,92,41,0.20)]'
                    : 'border-white/[0.08] hover:border-white/[0.14]'
                  }`}
              />
            </div>

            {/* Error message */}
            {errorMsg && (
              <motion.div
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex items-start gap-2.5 p-3 rounded-xl
                  bg-status-failed/10 border border-status-failed/20"
              >
                <span className="text-status-failed text-xs font-bold shrink-0 mt-0.5">!</span>
                <p role="alert" className="text-sm text-ink-primary">{errorMsg}</p>
              </motion.div>
            )}

            {/* Submit button — the ONLY orange element */}
            <motion.button
              type="submit"
              disabled={!username || !password || loginMutation.isPending}
              whileTap={{ scale: 0.97 }}
              className="w-full py-3.5 rounded-xl
                bg-primary-main hover:bg-[#ffb59f] active:bg-[#af3000]
                text-white text-sm font-semibold tracking-wider uppercase
                shadow-none
                hover:shadow-none
                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-main/60 focus-visible:ring-offset-2 focus-visible:ring-offset-transparent
                disabled:opacity-35 disabled:cursor-not-allowed disabled:shadow-none
                transition-all duration-200"
            >
              {loginMutation.isPending ? (
                <span className="flex items-center justify-center gap-2">
                  <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" strokeOpacity="0.3" />
                    <path d="M21 12a9 9 0 01-9 9" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                  </svg>
                  Signing in&hellip;
                </span>
              ) : 'Sign In'}
            </motion.button>
          </form>

          {/* Subtle bottom padding inside card — no PIN link for owner */}
          <div className="mt-2" />
        </div>

        {/* Footer */}
        <p className="text-center text-[10px] text-ink-tertiary mt-8 tracking-widest uppercase">
          Waterfront Country Club &middot; Juja
        </p>
      </motion.div>
    </div>
  )
}
