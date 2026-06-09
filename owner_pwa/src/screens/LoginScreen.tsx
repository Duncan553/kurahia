import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { motion } from 'framer-motion'
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

const HERO_URL = 'https://picsum.photos/1400/1000?image=1015'

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
    <div className="min-h-screen flex flex-col md:flex-row overflow-hidden">

      {/* ── Left: form column ──────────────────────────────────────── */}
      <motion.div
        initial={{ x: -40, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        transition={{ duration: 0.4, ease: 'easeOut' }}
        className="relative flex-1 md:flex-none md:w-[55%] flex items-center justify-center
          min-h-screen md:min-h-0"
        style={{
          backgroundImage: `url(${HERO_URL})`,
          backgroundSize: 'cover',
          backgroundPosition: 'center',
        }}
      >
        {/* Cream overlay */}
        <div className="absolute inset-0 bg-cream-card/92 md:bg-cream-card" />

        <div className="relative z-10 w-full max-w-[420px] px-8 py-12 md:px-12">

          <div className="mb-10">
            <p className="text-xs tracking-widest uppercase text-ink-tertiary font-medium mb-1">
              KURAHIA OWNER
            </p>
            <h1 className="font-serif text-4xl font-bold tracking-widest text-ink-primary leading-none">
              WELCOME
            </h1>
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
              className="w-full mt-2"
              loading={loginMutation.isPending}
              disabled={!username || !password}
            >
              Sign in
            </Button>
          </form>
        </div>
      </motion.div>

      {/* ── Right: hero image column (desktop only) ────────────────── */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.6, delay: 0.15, ease: 'easeOut' }}
        className="hidden md:block md:w-[45%] relative overflow-hidden"
      >
        <img
          src={HERO_URL}
          alt="Waterfront Kurahia aerial view"
          className="absolute inset-0 w-full h-full object-cover"
        />

        <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/10 to-transparent" />

        <div className="absolute bottom-12 left-12">
          <p
            className="font-serif text-5xl font-bold tracking-widest text-white leading-none"
            style={{ textShadow: '0 2px 16px rgba(0,0,0,0.5)' }}
          >
            WATERFRONT<br />KURAHIA
          </p>
          <p className="mt-2 text-xs tracking-widest uppercase text-white/80 font-medium">
            DAM RESORT · KENYA
          </p>
        </div>
      </motion.div>

    </div>
  )
}
