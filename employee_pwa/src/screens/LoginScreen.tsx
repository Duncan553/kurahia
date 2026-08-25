import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Button, Input, FormField } from '@shared'
import { useAuthStore } from '../stores/authStore'
import api from '../lib/axios'
import { decodeJWT } from '../lib/jwt'

export default function LoginScreen() {
  const navigate = useNavigate()
  const setAuth = useAuthStore((s) => s.setAuth)
  const setSetupToken = useAuthStore((s) => s.setSetupToken)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!username.trim() || !password) {
      setError('Please fill in all fields')
      return
    }
    setLoading(true)
    setError('')
    try {
      const cleanUsername = username.trim().toLowerCase()
      const res = await api.post('/auth/login', { username: cleanUsername, password })
      if (res.data.requires_pin_setup) {
        // First-ever login: backend issued a 10-minute setup-only token with
        // no refresh token, meant for /auth/set-pin, not for setAuth(). This
        // used to be ignored entirely — the user got dropped on /clock with a
        // token that silently expired ~10 minutes later and no way back to
        // PinSetupScreen (which was fully built but never navigated to).
        setSetupToken(res.data.access_token)
        navigate('/pin/setup', { state: { username: cleanUsername } })
        return
      }
      const claims = decodeJWT(res.data.access_token)
      setAuth({ id: claims.sub, username: cleanUsername, role_level: claims.role_level, department: claims.department ?? null }, res.data.access_token, res.data.refresh_token ?? '')
      navigate('/clock')
    } catch (err: any) {
      setError(err?.response?.data?.error || 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4"
      style={{ background: 'linear-gradient(160deg, rgba(35,18,12,0.9) 0%, rgba(18,9,6,0.7) 100%)' }}>
      
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-sm glass-card p-6 md:p-8"
      >
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold text-ink-primary font-serif">Welcome Back</h1>
          <p className="text-sm text-ink-tertiary mt-1">Log in to your account</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          {error && (
            <div className="p-3 rounded-lg bg-status-failed/15 border border-status-failed/25 text-status-failed text-sm text-center">
              {error}
            </div>
          )}

          <FormField label="Username" htmlFor="username" required>
            <Input
              id="username"
              value={username}
              onChange={e => { setUsername(e.target.value); setError('') }}
              placeholder="Enter your username"
              autoComplete="username"
              autoFocus
            />
          </FormField>

          <FormField label="Password" htmlFor="password" required>
            <Input
              id="password"
              type="password"
              value={password}
              onChange={e => { setPassword(e.target.value); setError('') }}
              placeholder="Enter your password"
              autoComplete="current-password"
            />
          </FormField>

          <Button
            type="submit"
            loading={loading}
            className="w-full py-4 text-base font-bold"
          >
            Log In
          </Button>
        </form>

        <p className="mt-6 text-center text-sm text-ink-tertiary">
          New staff?{' '}
          <button
            type="button"
            onClick={() => navigate('/register')}
            className="text-primary-main hover:underline font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-main rounded"
          >
            Join Kurahia
          </button>
        </p>
      </motion.div>
    </div>
  )
}
