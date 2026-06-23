import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { Skeleton, EmptyState, Modal, Button, useToastStore } from '@shared'
import api from '../lib/axios'
import { formatTime, dutyTime } from '../lib/format'
import { enqueueClockEvent, drainClockQueue } from '../lib/clockQueue'
import type { ClockEventType } from '../lib/clockQueue'
import { useAuthStore } from '../stores/authStore'

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

/* Live wall clock — ticks every second */
function useWallClock() {
  const [now, setNow] = useState(new Date())
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1_000)
    return () => clearInterval(id)
  }, [])
  return now
}

export default function ClockScreen() {
  const queryClient = useQueryClient()
  const addToast = useToastStore((s) => s.addToast)
  const navigate = useNavigate()
  const clearAuth = useAuthStore((s) => s.clearAuth)
  const [btnDisabled, setBtnDisabled] = useState(false)
  const [dutyMinutes, setDutyMinutes] = useState(0)
  const [showLogout, setShowLogout] = useState(false)
  const now = useWallClock()

  // Staff-accessible endpoint — returns only the current user's own status
  const { data, isLoading, isError, error, refetch } = useQuery<ClockStatus>({
    queryKey: ['clock-status'],
    queryFn: () => api.get<ClockStatus>('/hr/clock-status').then((r) => r.data),
    retry: (count, err) =>
      (err as { response?: { status?: number } })?.response?.status === 404 ? false : count < 1,
  })
  // 404 = account exists but no EmployeeProfile yet — clocking in is impossible
  const noProfile = (error as { response?: { status?: number } } | null)?.response?.status === 404

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
        setShowLogout(true)
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

  /* Format helpers for the Stitch layout */
  const dateLabel = now.toLocaleDateString('en-KE', { weekday: 'long', month: 'long', day: 'numeric' }).toUpperCase()
  const hours = now.getHours().toString().padStart(2, '0')
  const minutes = now.getMinutes().toString().padStart(2, '0')
  const isClockingIn = !isClockedIn

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

  // ── NO PROFILE ────────────────────────────────────────────────────────────
  if (noProfile) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[calc(100vh-8rem)] p-6">
        <EmptyState
          icon={
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none" aria-hidden="true">
              <circle cx="24" cy="17" r="8" stroke="currentColor" strokeWidth="2" />
              <path d="M8 40c0-8 7.2-13 16-13s16 5 16 13" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
          }
          title="Your profile isn't set up yet."
          description="Ask your manager to complete your employee profile under Manager - Staff. You can't clock in until then."
        />
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

  return (
    <div className="flex flex-col min-h-[calc(100vh-8rem)]">
      <motion.div
        className="flex-1 flex flex-col items-center justify-center p-6"
        initial="hidden"
        animate="visible"
        variants={{ hidden: {}, visible: { transition: { staggerChildren: 0.1 } } }}
      >
        {/* ── Glass container card ─────────────────────────────────── */}
        <motion.div
          variants={{ hidden: { opacity: 0, y: 16 }, visible: { opacity: 1, y: 0 } }}
          className="glass-card rounded-2xl p-8 md:p-10 w-full max-w-md flex flex-col items-center"
        >
          {/* Date label — e.g. "MONDAY, JUNE 22" */}
          <p className="text-[10px] font-bold tracking-[0.25em] uppercase text-ink-tertiary mb-6">
            {dateLabel}
          </p>

          {/* Massive time display — Fraunces serif like Stitch design */}
          <motion.div
            variants={{ hidden: { opacity: 0, scale: 0.9 }, visible: { opacity: 1, scale: 1 } }}
            className="mb-10"
          >
            <p className="text-7xl md:text-8xl font-bold font-serif text-ink-primary tabular-nums tracking-tight leading-none">
              {hours}<span className="text-ink-tertiary">:</span>{minutes}
            </p>
          </motion.div>

          {/* Big orange circle button */}
          <motion.button
            variants={{ hidden: { opacity: 0, scale: 0.8 }, visible: { opacity: 1, scale: 1 } }}
            transition={{ duration: 0.3, ease: 'easeOut' }}
            whileTap={{ scale: 0.93 }}
            onClick={handleTap}
            disabled={btnDisabled || mutation.isPending}
            aria-label={isClockingIn ? 'Clock in' : 'Clock out'}
            className={[
              'w-36 h-36 rounded-full flex flex-col items-center justify-center gap-2 transition-all shadow-lg',
              'focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-offset-2 focus-visible:ring-offset-cream-card',
              'disabled:opacity-50 disabled:cursor-not-allowed',
              isClockingIn
                ? 'bg-primary-main hover:bg-primary-main/90 focus-visible:ring-primary-main'
                : 'bg-transparent border-2 border-primary-main text-primary-main hover:bg-primary-main/10 focus-visible:ring-primary-main',
            ].join(' ')}
          >
            {mutation.isPending ? (
              <svg className="animate-spin w-8 h-8 text-white" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" strokeOpacity="0.25" />
                <path d="M21 12a9 9 0 01-9 9" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              </svg>
            ) : (
              <>
                {/* Clock icon */}
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" className={isClockingIn ? 'text-white' : ''} aria-hidden="true">
                  <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.5" />
                  <path d="M12 7v5l3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                <span className={`text-sm font-bold uppercase tracking-wider ${isClockingIn ? 'text-white' : ''}`}>
                  {isClockingIn ? 'Clock In' : 'Clock Out'}
                </span>
              </>
            )}
          </motion.button>

          {/* Shift status + Start time — below the button */}
          <div className="mt-10 w-full grid grid-cols-2 gap-6 text-center">
            <div>
              <p className="text-[10px] font-bold tracking-[0.15em] uppercase text-ink-tertiary mb-1">
                Shift Status
              </p>
              <p className="text-sm font-semibold text-ink-primary">
                {isClockedIn ? `On duty: ${dutyTime(dutyMinutes)}` : 'Off Duty'}
              </p>
            </div>
            <div>
              <p className="text-[10px] font-bold tracking-[0.15em] uppercase text-ink-tertiary mb-1">
                Start Time
              </p>
              <p className="text-sm font-semibold text-ink-primary">
                {isClockedIn && lastEvent ? formatTime(lastEvent.occurred_at) : '--:--'}
              </p>
            </div>
          </div>

          {/* Schedule + Assigned To — bottom info boxes */}
          <div className="mt-6 w-full grid grid-cols-2 gap-4">
            <div className="glass-card-sage rounded-xl p-4 text-center">
              <p className="text-[10px] font-bold tracking-[0.15em] uppercase text-ink-tertiary mb-1">
                Schedule
              </p>
              <p className="text-xs font-medium text-ink-secondary">
                {isClockedIn ? 'On Shift' : 'No active shift'}
              </p>
            </div>
            <div className="glass-card-sage rounded-xl p-4 text-center">
              <p className="text-[10px] font-bold tracking-[0.15em] uppercase text-ink-tertiary mb-1">
                Assigned To
              </p>
              <p className="text-xs font-medium text-ink-secondary">
                {lastEvent?.shift_id ? 'Scheduled Shift' : 'Walk-in'}
              </p>
            </div>
          </div>

          {/* Offline badge */}
          <AnimatePresence>
            {!navigator.onLine && (
              <motion.p
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="mt-4 text-xs text-status-pending flex items-center gap-1.5"
              >
                <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor" aria-hidden="true">
                  <circle cx="6" cy="6" r="5" />
                </svg>
                Offline — tap to queue event
              </motion.p>
            )}
          </AnimatePresence>
        </motion.div>
      </motion.div>

      {/* Shift-end logout prompt — tablet handover */}
      <Modal open={showLogout} onClose={() => setShowLogout(false)} title="Shift ended" size="sm">
        <div className="space-y-4">
          <p className="text-sm text-ink-secondary">
            Hand the tablet to your manager or the next person. Log out now to protect this account.
          </p>
          <div className="flex gap-2">
            <Button variant="ghost" size="sm" className="flex-1" onClick={() => setShowLogout(false)}>
              Stay Logged In
            </Button>
            <Button variant="primary" size="sm" className="flex-1"
              onClick={() => { clearAuth(); navigate('/pin') }}>
              Log Out
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  )
}
