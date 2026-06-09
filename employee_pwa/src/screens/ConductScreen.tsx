import { useRef, useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Skeleton, EmptyState, StatusBadge, useToastStore } from '@shared'
import api from '../lib/axios'
import { useAuthStore } from '../stores/authStore'
import { formatDateTime } from '../lib/format'

interface ConductRule {
  id: string
  rule_key: string
  version: number
  title: string
  body: string
  category: string
  is_active: boolean
  created_at: string
}

interface ConductSignature {
  id: string
  rule_key: string
  version: number
  title: string
  signed_at: string
}

export default function ConductScreen() {
  const queryClient = useQueryClient()
  const addToast = useToastStore((s) => s.addToast)
  const userId = useAuthStore((s) => s.user?.id)
  const scrollRef = useRef<HTMLDivElement>(null)
  const [scrollReady, setScrollReady] = useState(false)

  const rulesQ = useQuery<ConductRule[]>({
    queryKey: ['conduct', 'rules'],
    queryFn: () => api.get<ConductRule[]>('/conduct/rules').then((r) => r.data),
  })
  const sigsQ = useQuery<ConductSignature[]>({
    queryKey: ['conduct', 'signatures', userId],
    queryFn: () => api.get<ConductSignature[]>(`/conduct/signatures/${userId}`).then((r) => r.data),
    enabled: !!userId,
  })

  const isLoading = rulesQ.isLoading || sigsQ.isLoading
  const isError = rulesQ.isError || sigsQ.isError
  const rules = (rulesQ.data ?? []).filter((r) => r.is_active)
  const signatures = sigsQ.data ?? []

  // If content fits without scrolling, enable sign immediately once data loads
  useEffect(() => {
    if (!rules.length) return
    const el = scrollRef.current
    if (!el) return
    if (el.scrollHeight <= el.clientHeight + 1) setScrollReady(true)
  }, [rules.length])

  function handleScroll() {
    const el = scrollRef.current
    if (!el) return
    const ratio = el.scrollTop / (el.scrollHeight - el.clientHeight)
    if (ratio >= 0.9) setScrollReady(true)
  }

  function isSigned(rule: ConductRule): ConductSignature | undefined {
    return signatures.find((s) => s.rule_key === rule.rule_key && s.version === rule.version)
  }

  const signMutation = useMutation({
    mutationFn: ({ rule_key, version }: { rule_key: string; version: number }) =>
      api.post('/conduct/sign', { rule_key, version, idempotency_key: crypto.randomUUID() }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['conduct', 'signatures', userId] })
      addToast({ type: 'success', message: 'Code of conduct signed.' })
    },
    onError: () => {
      addToast({ type: 'error', message: 'Could not sign. Try again.' })
    },
  })

  // ── LOADING ─────────────────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="p-4 space-y-4">
        <Skeleton variant="text" className="w-1/3" />
        <Skeleton variant="card" />
        <Skeleton variant="text" />
        <Skeleton variant="text" className="w-3/4" />
        <Skeleton variant="text" className="w-2/3" />
        <Skeleton variant="button" />
      </div>
    )
  }

  // ── ERROR ────────────────────────────────────────────────────────────────────
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
          title="Couldn't load conduct rules."
          description="Check your connection and try again."
          actionLabel="Retry"
          onAction={() => { rulesQ.refetch(); sigsQ.refetch() }}
        />
      </div>
    )
  }

  // ── EMPTY ────────────────────────────────────────────────────────────────────
  if (!rules.length) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[calc(100vh-8rem)] p-6">
        <EmptyState
          icon={
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none" aria-hidden="true">
              <path d="M14 8h20M14 16h20M14 24h12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              <rect x="8" y="4" width="32" height="40" rx="3" stroke="currentColor" strokeWidth="2" />
            </svg>
          }
          title="No conduct rules published yet."
          description="Check back later."
        />
      </div>
    )
  }

  // ── SUCCESS ──────────────────────────────────────────────────────────────────
  const allSigned = rules.every((r) => isSigned(r))

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)]">

      {/* Scroll hint banner — disappears once scrollReady */}
      {!scrollReady && !allSigned && (
        <div className="shrink-0 px-4 py-2 bg-status-pending/10 text-status-pending text-xs text-center">
          Scroll to the bottom to enable the sign button.
        </div>
      )}

      {/* Scrollable rule content */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto p-4 space-y-8"
      >
        {rules.map((rule) => {
          const sig = isSigned(rule)
          return (
            <section key={rule.id} aria-labelledby={`rule-${rule.id}-title`}>
              {/* Rule header */}
              <div className="flex items-start justify-between gap-3 mb-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wider text-ink-tertiary">
                    {rule.category} · v{rule.version}
                  </p>
                  <h2 id={`rule-${rule.id}-title`} className="text-base font-bold text-ink-primary mt-0.5">
                    {rule.title}
                  </h2>
                </div>
                {sig && <StatusBadge status="confirmed" />}
              </div>

              {/* Rule body */}
              <div className="text-sm text-ink-secondary leading-relaxed whitespace-pre-wrap">
                {rule.body}
              </div>

              {/* Signature state */}
              <div className="mt-4">
                {sig ? (
                  <p className="text-xs text-ink-tertiary">
                    Signed on {formatDateTime(sig.signed_at)}
                  </p>
                ) : (
                  <button
                    onClick={() => signMutation.mutate({ rule_key: rule.rule_key, version: rule.version })}
                    disabled={!scrollReady || signMutation.isPending}
                    className={[
                      'px-5 py-2.5 rounded-xl text-sm font-semibold transition-all',
                      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark',
                      scrollReady
                        ? 'bg-primary-dark text-cream-card hover:bg-primary-dark/90 active:scale-[0.98]'
                        : 'bg-ink-tertiary/15 text-ink-tertiary cursor-not-allowed',
                      'disabled:opacity-60 disabled:cursor-not-allowed',
                    ].join(' ')}
                  >
                    {signMutation.isPending ? 'Signing…' : 'Sign Now'}
                  </button>
                )}
              </div>
            </section>
          )
        })}

        {/* Extra bottom padding so last rule doesn't sit right at scroll edge */}
        <div className="h-8" aria-hidden="true" />
      </div>
    </div>
  )
}
