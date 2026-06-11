import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Skeleton, EmptyState, Modal, Button, useToastStore } from '@shared'
import api from '../lib/axios'

interface Tab {
  id: string; reference: string | null; tab_type: string
  status: string; opened_at: string; balance: string
}

const kes = (v: string) =>
  `KSh ${parseFloat(v).toLocaleString('en-KE', { minimumFractionDigits: 0 })}`
const extractErr = (e: unknown) =>
  (e as { response?: { data?: { error?: string } } })?.response?.data?.error ?? 'Something went wrong.'

export default function WaiterTabsScreen() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  const [ref, setRef] = useState('')
  const [open, setOpen] = useState(false)
  const idem = useState(() => crypto.randomUUID())[0]

  const { data: tabs = [], isLoading } = useQuery<Tab[]>({
    queryKey: ['my-tabs'],
    queryFn: () => api.get<Tab[]>('/tabs?mine=true&status=OPEN').then(r => r.data),
    staleTime: 15_000,
    refetchOnWindowFocus: true,
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

  return (
    <div className="p-4 max-w-lg mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold font-serif text-ink-primary">My Tables</h1>
        <Button variant="primary" size="sm" onClick={() => setOpen(true)}>+ New Table</Button>
      </div>

      {isLoading && <div className="space-y-2">{[1,2,3].map(i => <Skeleton key={i} variant="row" />)}</div>}

      {!isLoading && tabs.length === 0 && (
        <EmptyState
          icon={<svg width="40" height="40" viewBox="0 0 40 40" fill="none" aria-hidden="true">
            <rect x="8" y="14" width="24" height="18" rx="2" stroke="currentColor" strokeWidth="1.5"/>
            <path d="M4 14h32M14 14V8a1 1 0 011-1h10a1 1 0 011 1v6"
              stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
          </svg>}
          title="No open tables. Tap + New Table to start."
        />
      )}

      <div className="space-y-2">
        {tabs.map(t => {
          const bal = parseFloat(t.balance)
          return (
            <button key={t.id} onClick={() => navigate(`/pos/tabs/${t.id}`)}
              className="w-full flex items-center justify-between p-4 rounded-2xl border border-cream-alt
                bg-cream-card hover:bg-cream-alt transition-colors text-left">
              <div>
                <p className="font-semibold text-ink-primary">{t.reference ?? 'Walk-in'}</p>
                <p className="text-xs text-ink-tertiary mt-0.5">
                  {new Date(t.opened_at).toLocaleTimeString('en-KE', { hour: '2-digit', minute: '2-digit' })}
                </p>
              </div>
              <div className="text-right">
                <p className={`text-sm font-bold tabular-nums ${bal > 0 ? 'text-status-failed' : 'text-status-paid'}`}>
                  {kes(t.balance)}
                </p>
                <p className="text-[10px] text-ink-tertiary">{bal > 0 ? 'outstanding' : 'settled'}</p>
              </div>
            </button>
          )
        })}
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
              className="w-full rounded-xl border border-cream-alt bg-cream-card px-4 py-3
                text-base text-ink-primary focus:outline-none focus:border-primary-dark"
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
    </div>
  )
}
