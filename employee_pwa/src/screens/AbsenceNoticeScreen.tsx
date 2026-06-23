import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useToastStore } from '@shared'
import { useNavigate } from 'react-router-dom'
import api from '../lib/axios'

function genKey() { return crypto.randomUUID() }

const REASONS = [
  'Sick — feeling unwell',
  'Family emergency',
  'Bereavement',
  'Medical appointment',
  'Personal emergency',
  'Other',
]

export default function AbsenceNoticeScreen() {
  const navigate  = useNavigate()
  const addToast  = useToastStore((s) => s.addToast)
  const [reason,  setReason]  = useState('')
  const [custom,  setCustom]  = useState('')
  const [idemKey, setIdemKey] = useState(genKey)
  const [touched, setTouched] = useState(false)

  const finalReason = reason === 'Other' ? custom.trim() : reason
  const reasonErr   = touched && !finalReason ? 'Select or enter a reason.' : ''
  const customErr   = touched && reason === 'Other' && custom.trim().length < 3
    ? 'Describe the reason (min 3 chars).' : ''
  const isValid = !!finalReason && (reason !== 'Other' || custom.trim().length >= 3)

  const mutation = useMutation({
    mutationFn: () =>
      api.post('/hr/absence-notices', {
        reason:          finalReason,
        idempotency_key: idemKey,
      }).then((r) => r.data),
    onSuccess: () => {
      addToast({ type: 'success', message: 'Absence recorded. Your manager has been notified.' })
      setIdemKey(genKey())
      navigate('/profile')
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { error?: string } } })?.response?.data?.error
        ?? 'Could not record absence. Try again.'
      addToast({ type: 'error', message: msg })
    },
  })

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setTouched(true)
    if (!isValid) return
    mutation.mutate()
  }

  return (
    <div className="p-4 max-w-3xl mx-auto space-y-6">

      <div>
        <h1 className="text-xl font-bold text-white">Absence Notice</h1>
        <p className="text-sm text-ink-tertiary">Calling in? Record it so your manager knows immediately</p>
      </div>

      <form onSubmit={handleSubmit} noValidate className="space-y-4">

        {/* Reason selector */}
        <div>
          <label className="block text-sm font-medium text-ink-secondary mb-2">
            Reason *
          </label>
          <div className="space-y-2">
            {REASONS.map((r) => (
              <button
                key={r}
                type="button"
                onClick={() => { setReason(r); setTouched(false) }}
                className={[
                  'w-full py-3 px-4 rounded-xl border text-sm font-medium text-left transition-all',
                  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark',
                  reason === r
                    ? 'border-[#fa5c29] bg-[#fa5c29]/10 text-primary-dark'
                    : 'border-white/10 bg-transparent text-ink-secondary hover:border-primary-main',
                ].join(' ')}
              >
                {r}
              </button>
            ))}
          </div>
          {reasonErr && <p className="text-sm text-status-failed mt-1">{reasonErr}</p>}
        </div>

        {/* Custom reason if "Other" */}
        {reason === 'Other' && (
          <div>
            <label className="block text-sm font-medium text-ink-secondary mb-1.5">
              Describe the reason *
            </label>
            <textarea
              rows={3}
              value={custom}
              onChange={(e) => setCustom(e.target.value)}
              placeholder="Brief description…"
              autoFocus
              className="w-full rounded-xl border border-white/10 bg-transparent px-4 py-3
                text-sm text-white focus:outline-none focus:border-[#fa5c29]
                focus:ring-2 focus:ring-primary-dark/20 resize-none"
            />
            {customErr && <p className="text-sm text-status-failed mt-1">{customErr}</p>}
          </div>
        )}

        {reason && (
          <div className="rounded-xl bg-status-pending/5 border border-status-pending/20 p-3">
            <p className="text-sm text-status-pending font-medium">
              This will notify your manager immediately.
            </p>
          </div>
        )}

        <button
          type="submit"
          disabled={mutation.isPending || !reason}
          className={[
            'w-full py-4 rounded-2xl text-base font-semibold transition-all',
            'bg-[#fa5c29] text-white hover:bg-[#af3000] active:scale-[0.99]',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark focus-visible:ring-offset-2',
            'disabled:opacity-50 disabled:cursor-not-allowed',
          ].join(' ')}
        >
          {mutation.isPending ? (
            <span className="flex items-center justify-center gap-2">
              <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" strokeOpacity="0.3"/>
                <path d="M21 12a9 9 0 01-9 9" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
              </svg>
              Sending…
            </span>
          ) : 'Record Absence'}
        </button>
      </form>
    </div>
  )
}
