import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useToastStore } from '@shared'
import api from '../lib/axios'

type Category = 'MANAGEMENT' | 'OWNER_PRIVATE'

interface SuggestionPayload {
  category: Category
  subject: string
  body: string
  idempotency_key: string
}

const MAX_BODY = 500

function freshKey(): string {
  return crypto.randomUUID()
}

export default function SuggestionsScreen() {
  const addToast = useToastStore((s) => s.addToast)
  const [category, setCategory] = useState<Category>('MANAGEMENT')
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [touched, setTouched] = useState({ subject: false, body: false })
  const [idempotencyKey, setIdempotencyKey] = useState(freshKey)

  const subjectError = touched.subject && !subject.trim() ? 'Subject is required.' : ''
  const bodyError = touched.body && !body.trim() ? 'Body is required.' : ''
  const isValid = subject.trim().length > 0 && body.trim().length > 0

  const mutation = useMutation({
    mutationFn: (payload: SuggestionPayload) =>
      api.post('/suggestions', payload),
    onSuccess: () => {
      addToast({ type: 'success', message: 'Suggestion submitted. Thank you.' })
      // Reset form + generate new idempotency key for next submission
      setSubject('')
      setBody('')
      setCategory('MANAGEMENT')
      setTouched({ subject: false, body: false })
      setIdempotencyKey(freshKey())
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { message?: string } } })
        ?.response?.data?.message
      addToast({ type: 'error', message: msg ?? 'Could not submit. Try again.' })
    },
  })

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setTouched({ subject: true, body: true })
    if (!isValid) return
    mutation.mutate({ category, subject: subject.trim(), body: body.trim(), idempotency_key: idempotencyKey })
  }

  return (
    <div className="p-4 max-w-md mx-auto">
      <form onSubmit={handleSubmit} noValidate className="space-y-5">

        {/* Category toggle */}
        <div>
          <label className="block text-xs font-semibold uppercase tracking-wider text-ink-tertiary mb-2">
            Send to
          </label>
          <div className="flex rounded-xl border border-cream-alt overflow-hidden text-sm font-medium">
            {(['MANAGEMENT', 'OWNER_PRIVATE'] as Category[]).map((c) => (
              <button
                key={c}
                type="button"
                onClick={() => setCategory(c)}
                className={[
                  'flex-1 py-2.5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-sage-dark',
                  category === c
                    ? 'bg-sage-dark text-cream-card'
                    : 'text-ink-secondary hover:bg-cream-alt/40',
                ].join(' ')}
              >
                {c === 'MANAGEMENT' ? 'Management' : 'Owner Only'}
              </button>
            ))}
          </div>
          {category === 'OWNER_PRIVATE' && (
            <p className="text-xs text-ink-tertiary mt-1.5 flex items-center gap-1.5">
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
                <rect x="2" y="5" width="8" height="6" rx="1" stroke="currentColor" strokeWidth="1.2" />
                <path d="M4 5V4a2 2 0 014 0v1" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
              </svg>
              Send directly to owner — managers cannot see this.
            </p>
          )}
        </div>

        {/* Subject */}
        <div>
          <label htmlFor="subject" className="block text-sm font-semibold text-ink-primary mb-1.5">
            Subject
          </label>
          <input
            id="subject"
            type="text"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            onBlur={() => setTouched((t) => ({ ...t, subject: true }))}
            placeholder="Brief summary of your suggestion"
            aria-describedby={subjectError ? 'subject-error' : undefined}
            className={[
              'w-full px-4 py-3 rounded-xl border bg-cream-card text-sm text-ink-primary',
              'placeholder:text-ink-tertiary/60 transition-colors',
              'focus:outline-none focus:ring-2 focus:ring-sage-dark focus:border-transparent',
              subjectError ? 'border-status-failed' : 'border-cream-alt',
            ].join(' ')}
          />
          {subjectError && (
            <p id="subject-error" role="alert" className="text-xs text-status-failed mt-1">
              {subjectError}
            </p>
          )}
        </div>

        {/* Body */}
        <div>
          <div className="flex items-baseline justify-between mb-1.5">
            <label htmlFor="body" className="block text-sm font-semibold text-ink-primary">
              Details
            </label>
            <span className={['text-xs tabular-nums', body.length > MAX_BODY * 0.9 ? 'text-status-failed' : 'text-ink-tertiary'].join(' ')}>
              {body.length}/{MAX_BODY}
            </span>
          </div>
          <textarea
            id="body"
            rows={6}
            value={body}
            maxLength={MAX_BODY}
            onChange={(e) => setBody(e.target.value)}
            onBlur={() => setTouched((t) => ({ ...t, body: true }))}
            placeholder="Describe your suggestion in detail…"
            aria-describedby={bodyError ? 'body-error' : undefined}
            className={[
              'w-full px-4 py-3 rounded-xl border bg-cream-card text-sm text-ink-primary resize-none',
              'placeholder:text-ink-tertiary/60 transition-colors',
              'focus:outline-none focus:ring-2 focus:ring-sage-dark focus:border-transparent',
              bodyError ? 'border-status-failed' : 'border-cream-alt',
            ].join(' ')}
          />
          {bodyError && (
            <p id="body-error" role="alert" className="text-xs text-status-failed mt-1">
              {bodyError}
            </p>
          )}
        </div>

        {/* Submit */}
        <button
          type="submit"
          disabled={!isValid || mutation.isPending}
          className={[
            'w-full py-3.5 rounded-xl text-sm font-semibold transition-all',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sage-dark focus-visible:ring-offset-2',
            'disabled:opacity-50 disabled:cursor-not-allowed',
            'bg-sage-dark text-cream-card hover:bg-sage-dark/90 active:scale-[0.99]',
          ].join(' ')}
        >
          {mutation.isPending ? (
            <span className="flex items-center justify-center gap-2">
              <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" strokeOpacity="0.25" />
                <path d="M21 12a9 9 0 01-9 9" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              </svg>
              Submitting…
            </span>
          ) : 'Submit Suggestion'}
        </button>
      </form>
    </div>
  )
}
