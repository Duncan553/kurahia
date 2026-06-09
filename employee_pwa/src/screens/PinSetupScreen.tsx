import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import axios from 'axios'
import axiosBase from 'axios'
import { decodeJWT } from '../lib/jwt'
import { useAuthStore } from '../stores/authStore'
import { Input } from '@shared'

interface SetPinResponse { access_token: string; refresh_token: string }
interface JWTClaims extends Record<string, unknown> {
  sub: string
  role_level: number
  department?: string | null
}

function criteria(pin: string, confirm: string) {
  return {
    length:  pin.length === 4,
    digits:  /^\d+$/.test(pin) || pin === '',
    matches: pin.length === 4 && pin === confirm,
  }
}

function CriteriaRow({ met, label }: { met: boolean; label: string }) {
  return (
    <li className="flex items-center gap-2 text-sm">
      <span className={met ? 'text-status-paid' : 'text-ink-tertiary'}>
        {met ? '✓' : '○'}
      </span>
      <span className={met ? 'text-ink-primary' : 'text-ink-tertiary'}>{label}</span>
    </li>
  )
}

export default function PinSetupScreen() {
  const navigate = useNavigate()
  const { state } = useLocation()
  const username = (state as { username?: string } | null)?.username ?? ''
  const { setupToken, setAuth } = useAuthStore()
  const [pin, setPin] = useState('')
  const [confirm, setConfirm] = useState('')
  const [errorMsg, setErrorMsg] = useState('')

  const c = criteria(pin, confirm)
  const ready = c.length && c.digits && c.matches

  const setupMutation = useMutation({
    mutationFn: () => {
      if (!setupToken) return Promise.reject(new Error('No setup token'))
      // Use a plain axios call with the setup token directly — the interceptor
      // would overwrite Authorization with the (empty) in-memory token otherwise
      return axiosBase.post<SetPinResponse>(
        `${import.meta.env.VITE_API_URL as string}/auth/set-pin`,
        { pin },
        { headers: { Authorization: `Bearer ${setupToken}` }, withCredentials: true }
      ).then((r) => r.data)
    },

    onSuccess: (data) => {
      setErrorMsg('')
      const claims = decodeJWT<JWTClaims>(data.access_token)
      setAuth({ id: claims.sub, username, role_level: claims.role_level, department: claims.department ?? null }, data.access_token)
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
    <div className="min-h-screen bg-sage-dark">

      {/* Brand header */}
      <div className="flex flex-col items-center px-6 pt-16 pb-10 gap-3">
        <h1 className="text-4xl font-bold font-serif text-cream-card tracking-wide">Kurahia</h1>
        <p className="text-sm text-cream-card/60 tracking-widest uppercase">Set your PIN</p>
        <p className="text-xs text-cream-card/50 text-center max-w-xs">
          You'll use this 4-digit PIN every time you sign in.
        </p>
      </div>

      {/* Form card */}
      <div className="bg-cream-card rounded-t-3xl px-6 pt-8 pb-16 shadow-2xl">
        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          <Input
            label="New PIN"
            type="password"
            inputMode="numeric"
            maxLength={4}
            value={pin}
            onChange={(e) => setPin(e.target.value.replace(/\D/g, '').slice(0, 4))}
            disabled={setupMutation.isPending}
          />
          <Input
            label="Confirm PIN"
            type="password"
            inputMode="numeric"
            maxLength={4}
            value={confirm}
            onChange={(e) => setConfirm(e.target.value.replace(/\D/g, '').slice(0, 4))}
            disabled={setupMutation.isPending}
          />

          {/* Live requirements */}
          <ul className="space-y-1.5 pl-1">
            <CriteriaRow met={c.length}  label="4 digits required" />
            <CriteriaRow met={c.digits}  label="Digits only (0–9)" />
            <CriteriaRow met={c.matches} label="PINs match" />
          </ul>

          {errorMsg && (
            <p role="alert" className="text-sm text-status-failed">{errorMsg}</p>
          )}

          <button
            type="submit"
            disabled={!ready || setupMutation.isPending}
            className={[
              'w-full py-4 rounded-2xl text-base font-semibold transition-all mt-1',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sage-dark focus-visible:ring-offset-2',
              'disabled:opacity-50 disabled:cursor-not-allowed',
              'bg-sage-dark text-cream-card hover:bg-sage-dark/90 active:scale-[0.99]',
            ].join(' ')}
          >
            {setupMutation.isPending ? (
              <span className="flex items-center justify-center gap-2">
                <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
                  <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" strokeOpacity="0.3" />
                  <path d="M21 12a9 9 0 01-9 9" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                </svg>
                Setting PIN…
              </span>
            ) : 'Set PIN & sign in'}
          </button>
        </form>
      </div>
    </div>
  )
}
