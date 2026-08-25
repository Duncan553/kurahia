import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Skeleton, EmptyState, Modal, Button, useToastStore, ErrorBoundary } from '@shared'
import api from '../lib/axios'
import { useAuthStore } from '../stores/authStore'

interface Tab {
  id: string; reference: string | null; tab_type: string
  status: string; opened_at: string; balance: string
  assigned_to: string | null; assigned_to_id: string | null
}
interface Ping { id: string; reference_type: string; subject: string; body: string }
interface StaffUser { id: string; username: string }

const kes = (v: string) =>
  `KSh ${parseFloat(v).toLocaleString('en-KE', { minimumFractionDigits: 0 })}`
const extractErr = (e: unknown) =>
  (e as { response?: { data?: { error?: string } } })?.response?.data?.error ?? 'Something went wrong.'

/* Derive a friendly location from reference text */
function tabLocation(ref: string | null): string {
  if (!ref) return 'Walk-in'
  const lower = ref.toLowerCase()
  if (lower.includes('deck'))    return 'Main Deck'
  if (lower.includes('pool'))    return 'Poolside'
  if (lower.includes('terrace')) return 'Terrace'
  if (lower.includes('lounge'))  return 'Lounge'
  if (lower.includes('bar'))     return 'Bar Area'
  if (lower.includes('beach'))   return 'Beach'
  if (lower.includes('cabana'))  return 'Poolside'
  return 'Dining'
}

/* How long since tab opened */
function timeSinceOpen(opened_at: string): string {
  const diff = Math.floor((Date.now() - new Date(opened_at).getTime()) / 60_000)
  if (diff < 1) return 'Just seated'
  if (diff < 60) return `Seated ${diff}m ago`
  const h = Math.floor(diff / 60)
  const m = diff % 60
  return `${h}h ${m}m`
}

export default function WaiterTabsScreen() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  const user = useAuthStore(s => s.user)
  const isManager = (user?.role_level ?? 0) >= 5
  const [ref, setRef] = useState('')
  const [open, setOpen] = useState(false)
  const [band, setBand] = useState('')
  const [assigning, setAssigning] = useState<string | null>(null)   // tab id being assigned
  const [assignTarget, setAssignTarget] = useState('')
  const idem = useState(() => crypto.randomUUID())[0]

  // Manager sees every open table (to assign waiters to them); a waiter sees
  // only what's been assigned to them — mirrors HousekeepingScreen's split.
  const { data: tabs = [], isLoading } = useQuery<Tab[]>({
    queryKey: ['my-tabs', isManager],
    // mine=true also includes unassigned tables now (so a pending-payment
    // table nobody's claimed yet isn't invisible to every waiter) — scoped on
    // the backend to WALK_IN/VILLA (waiters deliver to villas too) and never
    // BAND (gate wristband accounts — a different workflow entirely).
    queryFn: () => api.get<Tab[]>(isManager ? '/tabs?status=OPEN' : '/tabs?mine=true&status=OPEN').then(r => r.data),
    staleTime: 15_000,
    refetchOnWindowFocus: true,
  })

  // Staff list for the assign dropdown (manager only)
  const { data: staff = [] } = useQuery<StaffUser[]>({
    queryKey: ['tabs', 'staff'],
    queryFn: () => api.get<StaffUser[]>('/auth/users').then(r => r.data),
    enabled: isManager,
    staleTime: 120_000,
  })

  const assignMut = useMutation({
    mutationFn: ({ tabId, employeeId }: { tabId: string; employeeId: string }) =>
      api.post(`/tabs/${tabId}/assign`, { employee_id: employeeId }),
    onSuccess: () => {
      addToast({ type: 'success', message: 'Waiter assigned.' })
      qc.invalidateQueries({ queryKey: ['my-tabs'] })
      setAssigning(null); setAssignTarget('')
    },
    onError: (e) => addToast({ type: 'error', message: extractErr(e) }),
  })

  // Kitchen/bar "order ready" pings — shown right here, no separate alerts tab
  const { data: pings = [] } = useQuery<Ping[]>({
    queryKey: ['notifications', 'inbox'],
    queryFn: () => api.get<Ping[]>('/notifications/inbox').then(r => r.data),
    refetchInterval: 15_000,
    select: (all) => all.filter(n => n.reference_type === 'order_ready'),
  })

  const dismissPing = useMutation({
    mutationFn: (id: string) => api.post(`/notifications/${id}/mark-read`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications', 'inbox'] }),
  })

  const openMut = useMutation({
    mutationFn: (reference: string) =>
      api.post<Tab>('/tabs', { reference: reference.trim() || null, idempotency_key: idem }).then(r => r.data),
    onSuccess: (tab) => {
      qc.invalidateQueries({ queryKey: ['my-tabs'] })
      setOpen(false); setRef('')
      navigate(`/pos/tabs/${tab.id}`)
    },
    onError: (e) => addToast({ type: 'error', message: extractErr(e) }),
  })

  // Wristband redemption: guest paid KSh 3,000 at the gate — that credit sits
  // on the band's tab. Look the band up, order straight against its credit.
  const bandMut = useMutation({
    mutationFn: (num: string) =>
      api.get<{ tab_id: string; status: string }>(`/gate/bands/${num.trim()}`).then(r => r.data),
    onSuccess: (band) => {
      if (band.status !== 'ACTIVE') {
        addToast({ type: 'error', message: 'That band is not active. Send the guest to the gate.' })
        return
      }
      navigate(`/pos/tabs/${band.tab_id}`)
    },
    onError: (e) => addToast({ type: 'error', message: extractErr(e) }),
  })

  return (
    <div className="p-4 md:p-6 max-w-6xl mx-auto">
      <ErrorBoundary level="tile">
      {/* ── Header: "My Tables" + New Table button ─────────────── */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <p className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary">Current Service</p>
          <h1 className="text-3xl md:text-4xl font-bold font-serif text-ink-primary">
            {isManager ? 'All Tables' : 'My Tables'}
          </h1>
        </div>
        <Button variant="primary" size="sm" onClick={() => setOpen(true)}>+ New Table</Button>
      </div>

      {/* ── HERO: Ready-for-pickup pings — BIGGEST element when present ── */}
      {pings.length > 0 && (
        <div className="mb-8 space-y-3">
          {pings.map(n => (
            <button key={n.id}
              onClick={() => dismissPing.mutate(n.id)}
              className="w-full text-left p-5 rounded-2xl border-2 border-status-paid/50 bg-status-paid/10
                flex items-center gap-4 animate-pulse
                hover:bg-status-paid/15 transition-colors">
              <span className="text-3xl shrink-0" aria-hidden="true">&#128276;</span>
              <span className="flex-1 text-base font-bold text-ink-primary leading-snug">{n.body}</span>
              <span className="text-[10px] uppercase tracking-widest text-status-paid font-bold shrink-0">
                tap when picked up
              </span>
            </button>
          ))}
        </div>
      )}

      {/* Wristband redemption — order against the guest's KSh 3,000 gate credit */}
      <p className="text-[10px] text-ink-tertiary mb-1">Type the guest's wristband number to charge their tab</p>
      <div className="flex gap-2 mb-6">
        <input
          type="number" min="1" inputMode="numeric"
          aria-label="Wristband number"
          placeholder="Wristband # — charge to band credit"
          value={band}
          onChange={e => setBand(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && band && bandMut.mutate(band)}
          className="flex-1 rounded-xl glass-card bg-transparent px-4 py-2.5
            text-sm text-ink-primary placeholder:text-ink-tertiary
            focus:outline-none focus:border-primary-main focus-visible:ring-2 focus-visible:ring-primary-main"
        />
        <Button variant="ghost" size="sm" loading={bandMut.isPending}
          onClick={() => band && bandMut.mutate(band)}>
          Open Band
        </Button>
      </div>

      {isLoading && <div className="space-y-2 mb-6">{[1,2,3].map(i => <Skeleton key={i} variant="row" />)}</div>}

      {!isLoading && tabs.length === 0 && (
        <EmptyState
          icon={<svg width="40" height="40" viewBox="0 0 40 40" fill="none" aria-hidden="true">
            <rect x="8" y="14" width="24" height="18" rx="2" stroke="currentColor" strokeWidth="1.5"/>
            <path d="M4 14h32M14 14V8a1 1 0 011-1h10a1 1 0 011 1v6"
              stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
          </svg>}
          title={isManager ? 'No open tables right now.' : 'No tables assigned to you yet. Ask your manager.'}
        />
      )}

      {/* ── TABLE CARDS — consistent grid ─────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 mb-8">
        {tabs.map(t => {
          const bal = parseFloat(t.balance)
          return (
            <div key={t.id}
              className="glass-card rounded-2xl p-4 flex flex-col justify-between min-h-[160px]">
              <div
                role="button" tabIndex={0}
                onClick={() => navigate(`/pos/tabs/${t.id}`)}
                onKeyDown={e => e.key === 'Enter' && navigate(`/pos/tabs/${t.id}`)}
                aria-label={`Open tab ${t.reference ?? 'Walk-in'}`}
                className="text-left cursor-pointer hover:opacity-90 transition-opacity
                  focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-main rounded-lg">
                {/* Top: table name + status badges */}
                <div>
                  <div className="flex items-start justify-between mb-1">
                    <h3 className="text-lg font-bold text-ink-primary leading-tight">
                      {t.reference ?? 'Walk-in'}
                    </h3>
                    {bal > 0 && (
                      <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-status-pending/20 text-status-pending">
                        Paying
                      </span>
                    )}
                  </div>
                  <p className="text-[10px] font-bold tracking-widest uppercase text-ink-tertiary">
                    {tabLocation(t.reference)}
                  </p>
                </div>

                {/* Middle: time + guests */}
                <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
                  <div>
                    <p className="text-[10px] text-ink-tertiary">Status</p>
                    <p className="font-semibold text-ink-primary">{timeSinceOpen(t.opened_at)}</p>
                  </div>
                  <div>
                    <p className="text-[10px] text-ink-tertiary">Type</p>
                    <p className="font-semibold text-ink-primary">{t.tab_type || 'Dine-in'}</p>
                  </div>
                </div>

                {/* Bottom: current total */}
                <div className="mt-3 pt-2 border-t border-white/5">
                  <p className="text-[10px] text-ink-tertiary">Current Total</p>
                  <p className={`text-sm font-bold tabular-nums ${bal > 0 ? 'text-status-failed' : 'text-status-paid'}`}>
                    {kes(t.balance)}
                  </p>
                </div>
              </div>

              {/* Manager: who's this table assigned to + (re)assign control.
                  Tracked by name — same shape as HousekeepingScreen's assign block. */}
              {isManager && (
                <div className="mt-3 pt-2 border-t border-white/5" onClick={e => e.stopPropagation()}>
                  <p className="text-[10px] text-ink-tertiary mb-1">
                    Waiter: <span className="font-semibold text-ink-primary">{t.assigned_to ?? 'Unassigned'}</span>
                  </p>
                  {assigning === t.id ? (
                    <div className="space-y-1.5">
                      <select
                        style={{ colorScheme: 'dark' }}
                        value={assignTarget}
                        onChange={e => setAssignTarget(e.target.value)}
                        className="w-full rounded-lg glass-card bg-transparent px-2 py-1.5
                          text-xs text-ink-primary focus:outline-none focus:border-primary-main"
                      >
                        <option value="">Select waiter...</option>
                        {staff.filter(s => s.id !== t.assigned_to_id).map(s => (
                          <option key={s.id} value={s.id}>{s.username}</option>
                        ))}
                      </select>
                      <div className="flex gap-1.5">
                        <Button variant="ghost" size="sm" className="flex-1"
                          onClick={() => { setAssigning(null); setAssignTarget('') }}>
                          Cancel
                        </Button>
                        <Button variant="primary" size="sm" className="flex-1"
                          loading={assignMut.isPending} disabled={!assignTarget}
                          onClick={() => assignMut.mutate({ tabId: t.id, employeeId: assignTarget })}>
                          Assign
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <Button variant="ghost" size="sm" className="w-full"
                      onClick={() => { setAssigning(t.id); setAssignTarget('') }}>
                      {t.assigned_to ? 'Reassign' : 'Assign Waiter'}
                    </Button>
                  )}
                </div>
              )}
            </div>
          )
        })}

        {/* "Assign New Table" placeholder card */}
        {!isLoading && (
          <button
            onClick={() => setOpen(true)}
            className="glass-card-sage rounded-2xl border border-dashed border-white/10 p-4
              flex flex-col items-center justify-center min-h-[160px]
              hover:border-white/20 transition-all text-ink-tertiary hover:text-ink-secondary"
          >
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M12 5v14M5 12h14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
            <p className="text-xs font-semibold mt-2">Assign New Table</p>
          </button>
        )}
      </div>

      <Modal open={open} onClose={() => setOpen(false)} title="New Table" size="sm">
        <div className="space-y-4">
          <div>
            <label className="block text-[10px] tracking-widest uppercase text-ink-tertiary mb-1">
              Table / Reference
            </label>
            <input
              autoFocus
              value={ref}
              onChange={e => setRef(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && openMut.mutate(ref)}
              placeholder="e.g. Table 7, Beach Bar 3"
              className="w-full rounded-xl glass-card bg-transparent px-4 py-3
                text-base text-ink-primary placeholder:text-ink-tertiary
                focus:outline-none focus:border-primary-main"
            />
          </div>
          <div className="flex gap-2 justify-end">
            <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>Cancel</Button>
            <Button variant="primary" size="sm" loading={openMut.isPending} onClick={() => openMut.mutate(ref)}>
              Open Table
            </Button>
          </div>
        </div>
      </Modal>
      </ErrorBoundary>
    </div>
  )
}
