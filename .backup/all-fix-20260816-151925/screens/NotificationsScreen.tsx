import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { Skeleton, EmptyState, useToastStore, ErrorBoundary } from '@shared'
import api from '../lib/axios'
import { timeAgo } from '../lib/format'
import { routeFor } from '../lib/notificationRoutes'

export interface Notification {
  id: string
  reference_type: string
  reference_id: string
  subject: string
  body: string
  status: string
  channel: string
  scheduled_for: string | null
  sent_at: string | null
  read_at: string | null
}

export default function NotificationsScreen() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const addToast = useToastStore((s) => s.addToast)
  const [grayedIds, setGrayedIds] = useState<Set<string>>(new Set())

  const { data: notifications, isLoading, isError, refetch } = useQuery<Notification[]>({
    queryKey: ['notifications', 'inbox'],
    queryFn: () => api.get<Notification[]>('/notifications/inbox').then((r) => r.data),
    refetchInterval: 60_000,
  })

  const markRead = useMutation({
    mutationFn: (id: string) => api.post(`/notifications/${id}/mark-read`),
    onMutate: async (id) => {
      await queryClient.cancelQueries({ queryKey: ['notifications', 'inbox'] })
      const prev = queryClient.getQueryData<Notification[]>(['notifications', 'inbox'])
      // Optimistic: remove from inbox immediately (inbox is unread-only per spec)
      queryClient.setQueryData<Notification[]>(
        ['notifications', 'inbox'],
        (old = []) => old.filter((n) => n.id !== id)
      )
      // 1.5s button grayout (Pattern 1)
      setGrayedIds((s) => new Set([...s, id]))
      setTimeout(() => setGrayedIds((s) => { const n = new Set(s); n.delete(id); return n }), 1500)
      return { prev }
    },
    onError: (_, __, ctx) => {
      queryClient.setQueryData(['notifications', 'inbox'], ctx?.prev)
      addToast({ type: 'error', message: 'Could not mark as read. Try again.' })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications', 'inbox'] })
    },
  })

  function handleTap(notif: Notification) {
    if (!notif.read_at) markRead.mutate(notif.id)
    const route = routeFor(notif.reference_type)
    if (route !== '/notifications') navigate(route)
  }

  // ── LOADING ─────────────────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="p-4 space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="flex gap-3 items-start">
            <Skeleton variant="avatar" className="w-2 h-2 shrink-0" />
            <div className="flex-1 space-y-2">
              <Skeleton variant="text" className="w-3/4" />
              <Skeleton variant="text" className="w-1/2" />
            </div>
          </div>
        ))}
      </div>
    )
  }

  // ── ERROR ────────────────────────────────────────────────────────────────────
  if (isError && !notifications) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[calc(100vh-8rem)] p-6">
        <EmptyState
          icon={
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none" aria-hidden="true">
              <path d="M24 8a14 14 0 00-14 14v8l-3 5h34l-3-5V22A14 14 0 0024 8z"
                stroke="currentColor" strokeWidth="2" />
              <path d="M20 39a4 4 0 008 0" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
          }
          title="Couldn't load notifications."
          description="Check your connection and try again."
          actionLabel="Retry"
          onAction={() => refetch()}
        />
      </div>
    )
  }

  // ── EMPTY ────────────────────────────────────────────────────────────────────
  if (!notifications?.length) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[calc(100vh-8rem)] p-6">
        <EmptyState
          icon={
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none" aria-hidden="true">
              <circle cx="24" cy="24" r="20" stroke="currentColor" strokeWidth="2" />
              <path d="M15 24l6 6 12-12" stroke="currentColor" strokeWidth="2.5"
                strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          }
          title="You're all caught up · Uko sawa"
          description="No new notifications."
        />
      </div>
    )
  }

  // ── SUCCESS ──────────────────────────────────────────────────────────────────
  return (
    <ErrorBoundary level="tile">
      <motion.div
        className="divide-y divide-white/10"
        initial="hidden"
        animate="visible"
        variants={{ visible: { transition: { staggerChildren: 0.06 } } }}
      >
        {notifications.map((notif) => {
          const isUnread = !notif.read_at
          const isGrayed = grayedIds.has(notif.id)
          return (
            <motion.button
              key={notif.id}
              variants={{ hidden: { opacity: 0, x: -10 }, visible: { opacity: 1, x: 0 } }}
              transition={{ duration: 0.22, ease: 'easeOut' }}
              onClick={() => handleTap(notif)}
              disabled={isGrayed}
              className={[
                'w-full text-left px-4 py-4 flex gap-3 items-start transition-colors',
                'hover:bg-white/5 active:bg-white/8',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary-dark',
                'disabled:opacity-50 disabled:cursor-wait',
              ].join(' ')}
            >
              {/* Unread dot */}
              <span className="shrink-0 mt-1.5 w-2 h-2 rounded-full bg-[#fa5c29]"
                style={{ opacity: isUnread ? 1 : 0 }}
                aria-hidden="true"
              />
              <div className="flex-1 min-w-0">
                <p className={['text-sm truncate', isUnread ? 'font-semibold text-[#f9dcd5]' : 'text-ink-secondary'].join(' ')}>
                  {notif.subject}
                </p>
                <p className="text-xs text-ink-tertiary mt-0.5 line-clamp-2">{notif.body}</p>
                {notif.sent_at && (
                  <p className="text-[10px] text-ink-tertiary/60 mt-1">{timeAgo(notif.sent_at)}</p>
                )}
              </div>
            </motion.button>
          )
        })}
      </motion.div>
    </ErrorBoundary>
  )
}
