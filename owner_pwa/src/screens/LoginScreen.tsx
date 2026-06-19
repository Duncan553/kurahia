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

const HERO_URL =
  'https://waterfrontcountryclub.com/wp-content/uploads/2025/08/DJI_0669-scaled.jpg'

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
    <div className="relative min-h-screen overflow-hidden">

      <motion.div
        className="absolute inset-0"
        initial={{ opacity: 0, scale: 1.03 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 1.2, ease: 'easeOut' }}
      >
        <img src={HERO_URL} alt="" aria-hidden="true"
          className="w-full h-full object-cover object-center" />
        <div className="absolute inset-0 bg-gradient-to-b from-primary-dark/60 via-primary-dark/40 to-primary-dark/70" />
      </motion.div>

      <div className="relative z-10 flex items-center justify-center min-h-screen px-6 py-12">
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.3, ease: 'easeOut' }}
          className="w-full max-w-[400px]"
        >
          <div className="text-center mb-8">
            <motion.div
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ duration: 0.4, delay: 0.4 }}
              className="w-16 h-16 mx-auto mb-4 rounded-2xl
                bg-gradient-to-b from-emerald-500/20 to-emerald-700/20
                backdrop-blur-md border border-emerald-400/20
                flex items-center justify-center shadow-lg"
            >
              <span className="text-2xl font-serif font-bold text-white tracking-tight">K</span>
            </motion.div>
            <h1 className="font-serif text-4xl font-bold text-white tracking-tight
              drop-shadow-[0_2px_12px_rgba(0,0,0,0.3)]">
              Kurahia
            </h1>
            <p className="text-sm text-white/70 mt-1">Owner Portal</p>
          </div>

          <div className="rounded-3xl p-8 border border-white/20 shadow-2xl
            bg-cream-card/25 backdrop-blur-xl relative overflow-hidden">

            <form onSubmit={handleSubmit} noValidate className="relative space-y-5">

              <div>
                <label htmlFor="login-username"
                  className="block text-xs font-semibold text-white/80 mb-1.5 uppercase tracking-wider">
                  Username
                </label>
                <div className={`rounded-xl border transition-all ${
                  focused === 'user'
                    ? 'border-white/50 shadow-[0_0_0_3px_rgba(255,255,255,0.1)]'
                    : 'border-white/20'
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
                    className="w-full rounded-xl bg-white/10 backdrop-blur-sm px-4 py-3.5
                      text-sm text-white font-medium placeholder:text-white/40
                      focus:outline-none disabled:opacity-50"
                  />
                </div>
              </div>

              <div>
                <label htmlFor="login-password"
                  className="block text-xs font-semibold text-white/80 mb-1.5 uppercase tracking-wider">
                  Password
                </label>
                <div className={`rounded-xl border transition-all ${
                  focused === 'pass'
                    ? 'border-white/50 shadow-[0_0_0_3px_rgba(255,255,255,0.1)]'
                    : 'border-white/20'
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
                    className="w-full rounded-xl bg-white/10 backdrop-blur-sm px-4 py-3.5
                      text-sm text-white font-medium placeholder:text-white/40
                      focus:outline-none disabled:opacity-50"
                  />
                </div>
              </div>

              {errorMsg && (
                <motion.div
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="flex items-start gap-2 p-3 rounded-xl bg-status-failed/20 border border-status-failed/30"
                >
                  <span className="text-white text-sm shrink-0 mt-0.5">!</span>
                  <p role="alert" className="text-sm text-white font-medium">{errorMsg}</p>
                </motion.div>
              )}

              <motion.button
                type="submit"
                disabled={!username || !password || loginMutation.isPending}
                whileTap={{ scale: 0.97 }}
                className="w-full py-4 rounded-2xl
                  bg-gradient-to-b from-emerald-500 to-emerald-700
                  border border-emerald-500/30
                  text-white text-sm font-bold tracking-widest uppercase
                  shadow-[0_4px_20px_rgba(16,185,129,0.35)]
                  hover:from-emerald-400 hover:to-emerald-600
                  hover:shadow-[0_6px_24px_rgba(16,185,129,0.45)]
                  focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400
                  disabled:opacity-40 disabled:cursor-not-allowed transition-all"
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

          <p className="text-center text-[10px] text-white/40 mt-6 tracking-widest uppercase">
            Waterfront Country Club &middot; Juja
          </p>
        </motion.div>
      </div>
    </div>
  )
}
