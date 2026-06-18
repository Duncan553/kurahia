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

export default function ClockScreen() {
  const queryClient = useQueryClient()
  const addToast = useToastStore((s) => s.addToast)
  const navigate = useNavigate()
  const clearAuth = useAuthStore((s) => s.clearAuth)
  const [btnDisabled, setBtnDisabled] = useState(false)
  const [dutyMinutes, setDutyMinutes] = useState(0)
  const [showLogout, setShowLogout] = useState(false)

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
          description="Ask your manager to complete your employee profile under Manager → Staff. You can't clock in until then."
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

  const isClockingIn = !isClockedIn

  return (
    <div className="flex flex-col min-h-[calc(100vh-8rem)]">
    <div className="mb-6 p-4">
      <h1 className="font-serif text-2xl font-bold text-white">CLOCK.</h1>
      <p className="text-xs text-white/30 mt-1">KURAHIA STAFF</p>
    </div>
    <motion.div
      className="flex-1 flex flex-col items-center justify-center p-6 gap-6"
      initial="hidden"
      animate="visible"
      variants={{ hidden: {}, visible: { transition: { staggerChildren: 0.1 } } }}
    >
      {/* Status label */}
      <motion.p
        variants={{ hidden: { opacity: 0, y: -8 }, visible: { opacity: 1, y: 0 } }}
        className="text-sm font-medium text-slate-400/50 uppercase tracking-widest"
      >
        {isClockedIn ? 'On Duty' : 'Off Duty'}
      </motion.p>

      {/* Duty timer — only while clocked in */}
      <AnimatePresence mode="wait">
        {isClockedIn && lastEvent && (
          <motion.div
            key="timer"
            initial={{ opacity: 0, scale: 0.85 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.85 }}
            transition={{ duration: 0.3, ease: 'easeOut' }}
            className="text-center"
          >
            <p className="text-4xl font-bold font-mono text-white tabular-nums">
              {dutyTime(dutyMinutes)}
            </p>
            <p className="text-xs text-slate-300/70 mt-1">
              since {formatTime(lastEvent.occurred_at)}
            </p>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Main action button */}
      <motion.button
        variants={{ hidden: { opacity: 0, y: 16 }, visible: { opacity: 1, y: 0 } }}
        transition={{ duration: 0.3, ease: 'easeOut' }}
        whileTap={{ scale: 0.97 }}
        onClick={handleTap}
        disabled={btnDisabled || mutation.isPending}
        aria-label={isClockingIn ? 'Clock in' : 'Clock out'}
        className={[
          'w-full max-w-xs h-16 rounded-2xl text-lg font-semibold transition-colors',
          'focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-offset-2',
          'disabled:opacity-50 disabled:cursor-not-allowed',
          isClockingIn
            ? 'bg-primary-dark text-white hover:bg-primary-dark/90 focus-visible:ring-primary-dark'
            : 'bg-transparent text-primary-dark border-2 border-primary-dark hover:bg-primary-dark/5 focus-visible:ring-primary-dark',
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
      </motion.button>

      {/* Offline badge */}
      <AnimatePresence>
        {!navigator.onLine && (
          <motion.p
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="text-xs text-status-pending flex items-center gap-1.5"
          >
            <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor" aria-hidden="true">
              <circle cx="6" cy="6" r="5" />
            </svg>
            Offline — tap to queue event
          </motion.p>
        )}
      </AnimatePresence>
    </motion.div>

    {/* Shift-end logout prompt — tablet handover */}
    <Modal open={showLogout} onClose={() => setShowLogout(false)} title="Shift ended" size="sm">
      <div className="space-y-4">
        <p className="text-sm text-slate-300/70">
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
