import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import axios from 'axios'
import axiosBase from 'axios'
import { decodeJWT } from '../lib/jwt'
import { useAuthStore } from '../stores/authStore'
import { Button, Input } from '@shared'

interface SetPinResponse { access_token: string; refresh_token: string }
interface JWTClaims { sub: string; role_level: number }

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
        `${import.meta.env.VITE_API_URL ?? ''}/auth/set-pin`,
        { pin },
        { headers: { Authorization: `Bearer ${setupToken}` }, withCredentials: true }
      ).then((r) => r.data)
    },

    onSuccess: (data) => {
      setErrorMsg('')
      const claims = decodeJWT<JWTClaims>(data.access_token)
      setAuth({ id: claims.sub, username, role_level: claims.role_level }, data.access_token)
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
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-bold font-serif text-ink-primary">Set your PIN</h1>
          <p className="text-sm text-ink-secondary mt-1">
            You'll use this PIN every time you sign in.
          </p>
        </div>

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
          <ul className="space-y-1 pl-1">
            <CriteriaRow met={c.length}  label="4 digits required" />
            <CriteriaRow met={c.digits}  label="Digits only (0–9)" />
            <CriteriaRow met={c.matches} label="PINs match" />
          </ul>

          {errorMsg && (
            <p role="alert" className="text-sm text-status-failed">{errorMsg}</p>
          )}

          <Button
            type="submit"
            variant="primary"
            size="lg"
            className="w-full"
            loading={setupMutation.isPending}
            disabled={!ready}
          >
            Set PIN & sign in
          </Button>
        </form>
      </div>
    </div>
  )
}
