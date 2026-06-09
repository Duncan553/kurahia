import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Skeleton, EmptyState, useToastStore } from '@shared'
import api from '../lib/axios'
import { formatTime, dutyTime } from '../lib/format'
import { enqueueClockEvent, drainClockQueue } from '../lib/clockQueue'
import type { ClockEventType } from '../lib/clockQueue'

interface LastEvent {
  id: string
  event_type: 'CLOCK_IN' | 'CLOCK_OUT'
  occurred_at: string
  shift_id: string | null
}

interface ClockStatus {
  status: 'CLOCK_IN' | 'CLOCK_OUT' | 'CLOCKED_OUT'
  last_event: LastEvent | null
}

interface ClockResponse {
  id: string
  event_type: 'CLOCK_IN' | 'CLOCK_OUT'
  occurred_at: string
  shift_id: string | null
  no_shift?: boolean
  duplicate?: boolean
}

export default function ClockScreen() {
  const queryClient = useQueryClient()
  const addToast = useToastStore((s) => s.addToast)
  const [btnDisabled, setBtnDisabled] = useState(false)
  const [dutyMinutes, setDutyMinutes] = useState(0)

  // Staff-accessible endpoint — returns only the current user's own status
  const { data, isLoading, isError, refetch } = useQuery<ClockStatus>({
    queryKey: ['clock-status'],
    queryFn: () => api.get<ClockStatus>('/hr/clock-status').then((r) => r.data),
  })

  const isClockedIn = data?.status === 'CLOCK_IN'
  const lastEvent   = data?.last_event ?? null

  // Live duty timer — ticks every minute while clocked in
  useEffect(() => {
    if (!isClockedIn || !lastEvent) return
    const base = new Date(lastEvent.occurred_at).getTime()
    const tick = () => setDutyMinutes(Math.floor((Date.now() - base) / 60_000))
    tick()
    const id = setInterval(tick, 60_000)
    return () => clearInterval(id)
  }, [isClockedIn, lastEvent?.occurred_at])

  // Sync offline queue when coming back online
  useEffect(() => {
    const handleOnline = async () => {
      const count = await drainClockQueue(async (type) => {
        await api.post(type === 'CLOCK_IN' ? '/hr/clock-in' : '/hr/clock-out')
      })
      if (count > 0) {
        queryClient.invalidateQueries({ queryKey: ['clock-status'] })
        addToast({ type: 'success', message: `${count} offline clock event${count > 1 ? 's' : ''} synced.` })
      }
    }
    window.addEventListener('online', handleOnline)
    return () => window.removeEventListener('online', handleOnline)
  }, [queryClient, addToast])

  const mutation = useMutation({
    mutationFn: () =>
      api.post<ClockResponse>(isClockedIn ? '/hr/clock-out' : '/hr/clock-in'),

    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: ['clock-status'] })
      const prev = queryClient.getQueryData<ClockStatus>(['clock-status'])

      // Optimistically flip the local status
      const optimisticEvent: LastEvent = {
        id:          `opt-${Date.now()}`,
        event_type:  isClockedIn ? 'CLOCK_OUT' : 'CLOCK_IN',
        occurred_at: new Date().toISOString(),
        shift_id:    null,
      }
      queryClient.setQueryData<ClockStatus>(['clock-status'], {
        status:     optimisticEvent.event_type,
        last_event: optimisticEvent,
      })

      setBtnDisabled(true)
      setTimeout(() => setBtnDisabled(false), 500)
      return { prev }
    },

    onError: (_, __, ctx) => {
      queryClient.setQueryData(['clock-status'], ctx?.prev)
      addToast({ type: 'error', message: 'Clock-in failed. Check your connection and try again.' })
    },

    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['clock-status'] })
      const event = res.data
      if (event.duplicate) return
      const time = formatTime(event.occurred_at)
      if (event.event_type === 'CLOCK_IN') {
        addToast({ type: 'success', message: `Clocked in at ${time}` })
        if (event.no_shift) addToast({ type: 'warning', message: 'No shift scheduled — clock event recorded.' })
      } else {
        addToast({ type: 'success', message: `Clocked out at ${time}` })
      }
    },
  })

  function handleTap() {
    if (!navigator.onLine) {
      const type: ClockEventType = isClockedIn ? 'CLOCK_OUT' : 'CLOCK_IN'
      queryClient.setQueryData<ClockStatus>(['clock-status'], {
        status:     type,
        last_event: {
          id:          `offline-${Date.now()}`,
          event_type:  type,
          occurred_at: new Date().toISOString(),
          shift_id:    null,
        },
      })
      enqueueClockEvent(type)
      addToast({ type: 'warning', message: `Clocked ${type === 'CLOCK_IN' ? 'in' : 'out'} (offline — will sync when connected).` })
      return
    }
    mutation.mutate()
  }

  // ── LOADING ───────────────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[calc(100vh-8rem)] p-6 gap-6">
        <Skeleton variant="text" className="w-48" />
        <Skeleton variant="row" className="w-full max-w-xs h-16" />
        <Skeleton variant="text" className="w-32" />
      </div>
    )
  }

  // ── ERROR ─────────────────────────────────────────────────────────────────
  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[calc(100vh-8rem)] p-6">
        <EmptyState
          icon={
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none" aria-hidden="true">
              <circle cx="24" cy="24" r="20" stroke="currentColor" strokeWidth="2" />
              <path d="M24 14v12M24 32v2" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
            </svg>
          }
          title="Couldn't load clock status."
          description="Check your connection and try again."
          actionLabel="Retry"
          onAction={() => refetch()}
        />
      </div>
    )
  }

  const isClockingIn = !isClockedIn

  return (
    <div className="flex flex-col items-center justify-center min-h-[calc(100vh-8rem)] p-6 gap-6">

      {/* Status label */}
      <p className="text-sm font-medium text-ink-tertiary uppercase tracking-widest">
        {isClockedIn ? 'On Duty' : 'Off Duty'}
      </p>

      {/* Duty timer — only while clocked in */}
      {isClockedIn && lastEvent && (
        <div className="text-center">
          <p className="text-4xl font-bold font-mono text-ink-primary tabular-nums">
            {dutyTime(dutyMinutes)}
          </p>
          <p className="text-xs text-ink-tertiary mt-1">
            since {formatTime(lastEvent.occurred_at)}
          </p>
        </div>
      )}

      {/* Main action button */}
      <button
        onClick={handleTap}
        disabled={btnDisabled || mutation.isPending}
        aria-label={isClockingIn ? 'Clock in' : 'Clock out'}
        className={[
          'w-full max-w-xs h-16 rounded-2xl text-lg font-semibold transition-all',
          'focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-offset-2',
          'disabled:opacity-50 disabled:cursor-not-allowed',
          isClockingIn
            ? 'bg-primary-dark text-cream-card hover:bg-primary-dark/90 active:scale-[0.98] focus-visible:ring-primary-dark'
            : 'bg-ink-tertiary/10 text-ink-primary border border-ink-tertiary/20 hover:bg-ink-tertiary/20 active:scale-[0.98] focus-visible:ring-ink-tertiary',
        ].join(' ')}
      >
        {mutation.isPending ? (
          <span className="flex items-center justify-center gap-2">
            <svg className="animate-spin w-5 h-5" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" strokeOpacity="0.25" />
              <path d="M21 12a9 9 0 01-9 9" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
            {isClockingIn ? 'Clocking in…' : 'Clocking out…'}
          </span>
        ) : (
          isClockingIn ? 'Clock In' : 'Clock Out'
        )}
      </button>

      {/* Offline badge */}
      {!navigator.onLine && (
        <p className="text-xs text-status-pending flex items-center gap-1.5">
          <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor" aria-hidden="true">
            <circle cx="6" cy="6" r="5" />
          </svg>
          Offline — tap to queue event
        </p>
      )}
    </div>
  )
}
