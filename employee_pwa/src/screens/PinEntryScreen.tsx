import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import axios from 'axios'
import api from '../lib/axios'
import { decodeJWT } from '../lib/jwt'
import { useAuthStore } from '../stores/authStore'
import { Input, Modal, Button } from '@shared'

interface PinLoginResponse { access_token: string; refresh_token: string }
interface JWTClaims extends Record<string, unknown> { sub: string; role_level: number }

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
  const pop = useCallback(() => setDigits((prev) => prev.slice(0, -1)), [])

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
      navigate('/clock')
    },
    onError: (err) => {
      setDigits('')
      if (axios.isAxiosError(err)) {
        const msg = (err.response?.data as { error?: string })?.error ?? 'PIN failed.'
        if (msg.toLowerCase().includes('locked')) {
          setLockoutMsg(msg); setLockoutOpen(true)
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

  useEffect(() => {
    if (digits.length === 4 && username) handleSubmit()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [digits])

  return (
    <div className="min-h-screen bg-sage-dark">

      {/* ── Brand + PIN state — fixed padding ────────────────────── */}
      <div className="flex flex-col items-center px-6 pt-14 pb-8 gap-4">
        <h1 className="text-4xl font-bold font-serif text-cream-card tracking-wide">Kurahia</h1>
        <p className="text-sm text-cream-card/60 tracking-widest uppercase">Enter your PIN</p>

        {/* PIN dots */}
        <div className="flex gap-4 mt-1" aria-label="PIN entry" aria-live="polite">
          {[0,1,2,3].map((i) => (
            <div
              key={i}
              className={[
                'w-4 h-4 rounded-full border-2 transition-all duration-150',
                i < digits.length
                  ? 'bg-cream-card border-cream-card scale-110'
                  : 'bg-transparent border-cream-card/40',
              ].join(' ')}
            />
          ))}
        </div>

        {errorMsg && (
          <p role="alert" className="text-sm text-status-failed bg-cream-card/10
            px-3 py-1.5 rounded-lg">{errorMsg}</p>
        )}
      </div>

      {/* ── Form + keypad card ────────────────────────────────────── */}
      <div className="bg-cream-card rounded-t-3xl px-5 pt-6 pb-10 shadow-2xl">
        {/* Username */}
        <div className="mb-5">
          <Input
            label="Username"
            type="text"
            autoComplete="username"
            value={username}
            onChange={(e) => { setUsername(e.target.value); setDigits('') }}
            disabled={pinMutation.isPending}
          />
        </div>

        {/* Keypad */}
        <div className="grid grid-cols-3 gap-3">
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
                  'min-h-[72px] w-full rounded-2xl text-2xl font-semibold',
                  'flex items-center justify-center select-none',
                  'transition-all duration-75',
                  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sage-dark',
                  'disabled:opacity-40',
                  key === '⌫'
                    ? 'bg-transparent text-ink-tertiary active:text-ink-primary active:scale-95'
                    : 'bg-white shadow-sm border border-cream-alt text-ink-primary active:bg-sage-light/40 active:shadow-none active:scale-95',
                ].join(' ')}
              >
                {key === '⌫' ? (
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <path d="M21 7H9.5L3 12l6.5 5H21V7z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
                    <path d="M15 10l-4 4M11 10l4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                  </svg>
                ) : key}
              </button>
            )
          ))}
        </div>

        <button
          type="button"
          onClick={() => navigate('/login')}
          className="mt-5 w-full text-sm text-ink-tertiary hover:text-ink-secondary text-center transition-colors"
        >
          Use password instead →
        </button>
      </div>

      {/* Lockout modal */}
      <Modal open={lockoutOpen} onClose={() => setLockoutOpen(false)} title="Account Locked" preventClose>
        <p className="text-base text-ink-secondary mb-6">{lockoutMsg}</p>
        <div className="flex justify-end">
          <Button variant="secondary" onClick={() => setLockoutOpen(false)}>OK</Button>
        </div>
      </Modal>
    </div>
  )
}
