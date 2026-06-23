import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import axios from 'axios'
import api from '../lib/axios'
import { decodeJWT } from '../lib/jwt'
import { useAuthStore } from '../stores/authStore'
import { Button, Input, Modal } from '@shared'

interface PinLoginResponse {
  access_token: string
  refresh_token: string
}

interface JWTClaims { sub: string; role_level: number }

const KEYPAD = ['1','2','3','4','5','6','7','8','9','','0','⌫'] as const

export default function PinEntryScreen() {
  const navigate = useNavigate()
  const { setAuth } = useAuthStore()
  const [username, setUsername] = useState('')
  const [digits, setDigits] = useState('')
  const [errorMsg, setErrorMsg] = useState('')
  const [lockoutOpen, setLockoutOpen] = useState(false)
  const [lockoutMsg, setLockoutMsg] = useState('')

  const pushDigit = useCallback((d: string) => {
    setDigits((prev) => (prev.length < 4 ? prev + d : prev))
  }, [])

  const pop = useCallback(() => {
    setDigits((prev) => prev.slice(0, -1))
  }, [])

  // Physical keyboard support
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (/^[0-9]$/.test(e.key)) { pushDigit(e.key); return }
      if (e.key === 'Backspace') { pop(); return }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [pushDigit, pop])

  const pinMutation = useMutation({
    mutationFn: (data: { username: string; pin: string }) =>
      api.post<PinLoginResponse>('/auth/pin-login', data).then((r) => r.data),

    onSuccess: (data) => {
      setErrorMsg('')
      const claims = decodeJWT<JWTClaims>(data.access_token)
      setAuth({ id: claims.sub, username, role_level: claims.role_level }, data.access_token)
      navigate('/')
    },

    onError: (err) => {
      setDigits('')
      if (axios.isAxiosError(err)) {
        const msg = (err.response?.data as { error?: string })?.error ?? 'PIN failed.'
        // Account locked → show modal instead of inline error
        if (msg.toLowerCase().includes('locked')) {
          setLockoutMsg(msg)
          setLockoutOpen(true)
        } else {
          setErrorMsg(msg)
        }
      } else {
        setErrorMsg('Something went wrong. Try again.')
      }
    },
  })

  function handleKey(key: typeof KEYPAD[number]) {
    if (key === '') return
    if (key === '⌫') { pop(); return }
    pushDigit(key)
  }

  function handleSubmit() {
    if (!username || digits.length !== 4) return
    setErrorMsg('')
    pinMutation.mutate({ username, pin: digits })
  }

  // Auto-submit once 4 digits entered (only if username is set)
  useEffect(() => {
    if (digits.length === 4 && username) handleSubmit()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [digits])

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-6">
      <div className="w-full max-w-xs">
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-bold font-serif text-ink-primary">Kurahia</h1>
          <p className="text-sm text-ink-secondary mt-1">Enter your PIN</p>
        </div>

        {/* Username field */}
        <div className="mb-6">
          <Input
            label="Username"
            type="text"
            autoComplete="username"
            value={username}
            onChange={(e) => { setUsername(e.target.value); setDigits('') }}
            disabled={pinMutation.isPending}
          />
        </div>

        {/* PIN dots */}
        <div role="group" className="flex justify-center gap-4 mb-6" aria-label="PIN entry" aria-live="polite">
          {[0,1,2,3].map((i) => (
            <div
              key={i}
              className={[
                'w-4 h-4 rounded-full border-2 transition-colors',
                i < digits.length
                  ? 'bg-ink-primary border-ink-primary'
                  : 'bg-transparent border-ink-tertiary',
              ].join(' ')}
            />
          ))}
        </div>

        {errorMsg && (
          <p role="alert" className="text-sm text-status-failed text-center mb-4">{errorMsg}</p>
        )}

        {/* Keypad — 80×80px min per key for gloves + wet hands */}
        <div className="grid grid-cols-3 gap-2 mb-6">
          {KEYPAD.map((key, i) => (
            key === '' ? (
              <div key={i} />
            ) : (
              <button
                key={i}
                type="button"
                onClick={() => handleKey(key)}
                disabled={pinMutation.isPending}
                aria-label={key === '⌫' ? 'Backspace' : key}
                className={[
                  'min-h-[80px] min-w-[80px] w-full rounded-xl text-xl font-medium',
                  'flex items-center justify-center',
                  'bg-cream-alt text-ink-primary',
                  'active:bg-primary-light active:scale-95 transition-all',
                  'disabled:opacity-50',
                  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark',
                ].join(' ')}
              >
                {key}
              </button>
            )
          ))}
        </div>

        <Button
          type="button"
          variant="primary"
          size="lg"
          className="w-full"
          onClick={handleSubmit}
          loading={pinMutation.isPending}
          disabled={!username || digits.length !== 4}
        >
          Sign in
        </Button>

        <button
          type="button"
          onClick={() => navigate('/login')}
          className="mt-4 min-h-[44px] w-full text-sm text-ink-secondary hover:text-primary-dark
            text-center transition-colors flex items-center justify-center
            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark rounded"
        >
          Use password instead
        </button>
      </div>

      {/* Lockout modal */}
      <Modal
        open={lockoutOpen}
        onClose={() => setLockoutOpen(false)}
        title="Account Locked"
        preventClose
      >
        <p className="text-base text-ink-secondary mb-6">{lockoutMsg}</p>
        <div className="flex justify-end">
          <Button variant="secondary" onClick={() => setLockoutOpen(false)}>OK</Button>
        </div>
      </Modal>
    </div>
  )
}
