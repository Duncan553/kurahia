import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import axios from 'axios'
import api from '../lib/axios'
import { decodeJWT } from '../lib/jwt'
import { useAuthStore } from '../stores/authStore'
import { Button, Input } from '@shared'

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

  const loginMutation = useMutation({
    mutationFn: (data: { username: string; password: string }) =>
      api.post<LoginResponse>('/auth/login', data).then((r) => r.data),

    onSuccess: (data) => {
      setErrorMsg('')
      const claims = decodeJWT<JWTClaims>(data.access_token)

      if (data.requires_pin_setup) {
        // Short-lived setup token — don't call setAuth yet
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
    <div className="min-h-screen bg-cream-card flex items-center justify-center p-6">
      <div className="w-full max-w-sm">
        <div className="mb-10 text-center">
          <h1 className="text-3xl font-bold font-serif text-ink-primary">Kurahia</h1>
          <p className="text-sm text-ink-secondary mt-1">Staff Portal</p>
        </div>

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

          <Button
            type="submit"
            variant="primary"
            size="lg"
            className="w-full"
            loading={loginMutation.isPending}
            disabled={!username || !password}
          >
            Sign in
          </Button>
        </form>
      </div>
    </div>
  )
}
