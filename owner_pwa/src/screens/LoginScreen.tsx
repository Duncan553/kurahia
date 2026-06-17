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
  requires_pin_setup?: boolean
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
      if (data.requires_pin_setup) {
        setSetupToken(data.access_token)
        navigate('/pin/setup', { state: { username } })
        return
      }
      setAuth({ id: claims.sub, username, role_level: claims.role_level }, data.access_token)
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
    <div className="min-h-screen bg-cream-card flex flex-col">

      <div className="h-1 gradient-hero" />

      <div className="flex-1 flex items-center justify-center px-6 py-12">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: 'easeOut' }}
          className="w-full max-w-[380px]"
        >
          {/* Brand */}
          <div className="text-center mb-10">
            <motion.div
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ duration: 0.4, delay: 0.1 }}
              className="w-16 h-16 mx-auto mb-5 rounded-2xl gradient-hero flex items-center justify-center shadow-lg"
            >
              <span className="text-2xl font-serif font-bold text-white tracking-tight">K</span>
            </motion.div>
            <h1 className="font-serif text-3xl font-bold text-ink-primary tracking-tight">
              Kurahia
            </h1>
            <p className="text-sm text-ink-secondary mt-1">Owner portal &middot; Waterfront</p>
          </div>

          {/* Card */}
          <div className="bg-cream-alt/40 rounded-3xl p-8 border border-cream-alt shadow-sm">
            <form onSubmit={handleSubmit} noValidate className="space-y-5">

              <div>
                <label htmlFor="login-username"
                  className="block text-xs font-semibold text-ink-secondary mb-1.5 uppercase tracking-wider">
                  Username
                </label>
                <div className={`relative rounded-xl border-2 transition-all ${
                  focused === 'user' ? 'border-primary-main shadow-[0_0_0_3px_rgba(64,83,76,0.12)]' : 'border-cream-alt'
                }`}>
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
                    className="w-full rounded-xl bg-cream-card px-4 py-3.5
                      text-sm text-ink-primary font-medium
                      placeholder:text-ink-tertiary/50
                      focus:outline-none disabled:opacity-50"
                  />
                </div>
              </div>

              <div>
                <label htmlFor="login-password"
                  className="block text-xs font-semibold text-ink-secondary mb-1.5 uppercase tracking-wider">
                  Password
                </label>
                <div className={`relative rounded-xl border-2 transition-all ${
                  focused === 'pass' ? 'border-primary-main shadow-[0_0_0_3px_rgba(64,83,76,0.12)]' : 'border-cream-alt'
                }`}>
                  <input
                    id="login-password"
                    type="password"
                    autoComplete="current-password"
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                    onFocus={() => setFocused('pass')}
                    onBlur={() => setFocused(null)}
                    disabled={loginMutation.isPending}
                    className="w-full rounded-xl bg-cream-card px-4 py-3.5
                      text-sm text-ink-primary font-medium
                      placeholder:text-ink-tertiary/50
                      focus:outline-none disabled:opacity-50"
                  />
                </div>
              </div>

              {errorMsg && (
                <motion.div
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="flex items-start gap-2 p-3 rounded-xl bg-status-failed/10 border border-status-failed/20"
                >
                  <span className="text-status-failed text-sm shrink-0 mt-0.5">!</span>
                  <p role="alert" className="text-sm text-status-failed font-medium">{errorMsg}</p>
                </motion.div>
              )}

              <motion.button
                type="submit"
                disabled={!username || !password || loginMutation.isPending}
                whileTap={{ scale: 0.97 }}
                className="w-full py-4 rounded-2xl gradient-hero text-white
                  text-sm font-bold tracking-widest uppercase
                  shadow-md hover:shadow-lg
                  focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-main focus-visible:ring-offset-2
                  disabled:opacity-50 disabled:cursor-not-allowed
                  transition-shadow"
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
          </div>

          <p className="text-center text-[10px] text-ink-tertiary mt-6 tracking-wide">
            JUJA &middot; KIAMBU &middot; KENYA
          </p>
        </motion.div>
      </div>
    </div>
  )
}
