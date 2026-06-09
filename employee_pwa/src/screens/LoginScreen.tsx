import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import axios from 'axios'
import api from '../lib/axios'
import { decodeJWT } from '../lib/jwt'
import { useAuthStore } from '../stores/authStore'
import { Input } from '@shared'

interface LoginResponse {
  access_token: string
  refresh_token?: string
  requires_pin_setup?: true
}
interface JWTClaims extends Record<string, unknown> {
  sub: string
  role_level: number
  department?: string | null
  requires_pin_setup?: boolean
}

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
      setAuth({ id: claims.sub, username, role_level: claims.role_level, department: claims.department ?? null }, data.access_token)
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
    <div className="min-h-screen bg-primary-dark">

      {/* ── Brand header — fixed padding, never flex-1 ───────────── */}
      <div className="flex flex-col items-center px-6 pt-16 pb-10 gap-3">
        <svg width="36" height="36" viewBox="0 0 40 40" fill="none" aria-hidden="true"
          className="text-cream-card/40 mb-1">
          <path d="M20 36C20 36 8 28 8 18a12 12 0 0124 0c0 10-12 18-12 18z"
            stroke="currentColor" strokeWidth="1.5" fill="none" />
          <path d="M20 36V18" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          <path d="M14 22c2-2 4-3 6-4M26 22c-2-2-4-3-6-4"
            stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
        </svg>
        <h1 className="text-4xl font-bold font-serif text-cream-card tracking-wide">Kurahia</h1>
        <p className="text-sm text-cream-card/60 tracking-widest uppercase">Staff Portal</p>
      </div>

      {/* ── Form card ────────────────────────────────────────────── */}
      <div className="bg-cream-card rounded-t-3xl px-6 pt-8 pb-16 shadow-2xl">
        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          <Input
            label="Username"
            type="text"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            disabled={loginMutation.isPending}
          />
          <Input
            label="Password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={loginMutation.isPending}
          />

          {errorMsg && (
            <p role="alert" className="text-sm text-status-failed">{errorMsg}</p>
          )}

          <button
            type="submit"
            disabled={!username || !password || loginMutation.isPending}
            className={[
              'w-full py-4 rounded-2xl text-base font-semibold transition-all mt-2',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark focus-visible:ring-offset-2',
              'disabled:opacity-50 disabled:cursor-not-allowed',
              'bg-primary-dark text-cream-card hover:bg-primary-dark/90 active:scale-[0.99]',
            ].join(' ')}
          >
            {loginMutation.isPending ? (
              <span className="flex items-center justify-center gap-2">
                <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
                  <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" strokeOpacity="0.3" />
                  <path d="M21 12a9 9 0 01-9 9" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                </svg>
                Signing in…
              </span>
            ) : 'Sign in'}
          </button>
        </form>

        <button
          type="button"
          onClick={() => navigate('/pin')}
          className="mt-5 w-full text-sm text-ink-tertiary hover:text-ink-secondary text-center transition-colors"
        >
          Use PIN instead →
        </button>
      </div>
    </div>
  )
}
