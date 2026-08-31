import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { Input, Select, useToastStore } from '@shared'
import api from '../lib/axios'

// Backend only supports WATER_ACTIVITY. Add more enum values here when backend expands.
const ACTIVITY_OPTS = [
  { value: 'WATER_ACTIVITY', label: 'Water Activity' },
]

interface WaiverResponse {
  id: string
  booking_id: string
  activity_type: string
  signed_by: string
  signed_at: string
}

function genKey() { return crypto.randomUUID() }

export default function WaiverScreen() {
  const addToast = useToastStore((s) => s.addToast)

  // Front desk arrives here from Check-In with ?booking=<id> when an arrival
  // still needs a waiver, so the ID does not have to be copied by hand off
  // another screen. Opened directly from the nav it is simply empty.
  const [params] = useSearchParams()

  const [guestName,    setGuestName]    = useState('')
  const [bookingId,    setBookingId]    = useState(params.get('booking') ?? '')
  const [activityType, setActivityType] = useState('WATER_ACTIVITY')
  const [notes,        setNotes]        = useState('')
  const [idemKey,      setIdemKey]      = useState(genKey)

  // Track which fields have been blurred so we only show errors after interaction
  const [touched, setTouched] = useState({ guestName: false, bookingId: false })

  const touch = (field: keyof typeof touched) =>
    setTouched((prev) => ({ ...prev, [field]: true }))

  const guestErr   = touched.guestName && !guestName.trim() ? 'Guest name is required.' : ''
  const bookingErr = touched.bookingId && !bookingId.trim() ? 'Booking ID is required.' : ''
  const isValid    = !!guestName.trim() && !!bookingId.trim()

  const mutation = useMutation({
    mutationFn: () =>
      api.post<WaiverResponse>('/waivers', {
        signed_by_name:  guestName.trim(),
        booking_id:      bookingId.trim(),
        activity_type:   activityType,
        notes:           notes.trim() || undefined,
        idempotency_key: idemKey,
      }).then((r) => r.data),

    onSuccess: (data) => {
      addToast({ type: 'success', message: `Waiver recorded for ${data.signed_by}.` })
      // Full reset + new idempotency key
      setGuestName('')
      setBookingId('')
      setNotes('')
      setActivityType('WATER_ACTIVITY')
      setTouched({ guestName: false, bookingId: false })
      setIdemKey(genKey())
    },

    onError: () => {
      addToast({ type: 'error', message: 'Waiver not saved. Check connection and retry.' })
    },
  })

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    // Touch all fields to reveal any errors
    setTouched({ guestName: true, bookingId: true })
    if (!isValid) return
    mutation.mutate()
  }

  return (
    <div className="p-4 max-w-3xl mx-auto space-y-5">

      {/* ── Header ─────────────────────────────────────────────────── */}
      <div>
        <h1 className="text-xl font-bold text-ink-primary">Record Waiver</h1>
        <p className="text-sm text-ink-tertiary">Liability waiver for activities</p>
      </div>

      {/* ── Form ───────────────────────────────────────────────────── */}
      <form onSubmit={handleSubmit} noValidate className="space-y-4">
        <Input
          label="Guest name *"
          type="text"
          autoComplete="off"
          value={guestName}
          onChange={(e) => setGuestName(e.target.value)}
          onBlur={() => touch('guestName')}
          disabled={mutation.isPending}
        />
        {guestErr && <p className="text-sm text-status-failed -mt-2">{guestErr}</p>}

        <Input
          label="Booking ID *"
          type="text"
          autoComplete="off"
          placeholder="e.g. abc123…"
          value={bookingId}
          onChange={(e) => setBookingId(e.target.value)}
          onBlur={() => touch('bookingId')}
          disabled={mutation.isPending}
        />
        {bookingErr && <p className="text-sm text-status-failed -mt-2">{bookingErr}</p>}

        <Select
          label="Activity type"
          value={activityType}
          onChange={(e) => setActivityType(e.target.value)}
          options={ACTIVITY_OPTS}
          disabled={mutation.isPending}
        />

        <Input
          label="Notes (optional)"
          type="text"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          disabled={mutation.isPending}
        />

        <button
          type="submit"
          disabled={mutation.isPending}
          className={[
            'w-full py-4 rounded-2xl text-base font-semibold transition-all mt-1',
            'bg-primary-main text-white hover:bg-primary-dark active:scale-[0.99]',
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
              Saving…
            </span>
          ) : 'Record Waiver'}
        </button>
      </form>
    </div>
  )
}
