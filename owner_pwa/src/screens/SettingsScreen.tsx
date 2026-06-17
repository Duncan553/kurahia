import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Button, Modal, useToastStore, Skeleton } from '@shared'
import { useFontSizePref } from '../lib/fontSizePref'
import type { FontSizeKey } from '../lib/fontSizePref'
import api from '../lib/axios'

// ── Types ─────────────────────────────────────────────────────────────────────

interface Department { id: string; name: string; is_active: boolean }
interface Role { id: string; name: string; level: number; is_active: boolean }
interface Baseline {
  id: string; item_id: string; item_name: string | null
  business_driver: string; expected_ratio: string; tolerance_percent: string; is_active: boolean
}
interface SocketStatus { configured: boolean; message: string }

// ── Helpers ───────────────────────────────────────────────────────────────────

const extractErr = (e: unknown) =>
  (e as { response?: { data?: { error?: string } } })?.response?.data?.error ?? 'Something went wrong.'

// ── Departments tab ───────────────────────────────────────────────────────────

function DepartmentsTab() {
  const qc = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  const [newName, setNewName] = useState('')
  const [editTarget, setEditTarget] = useState<Department | null>(null)
  const [editName, setEditName] = useState('')

  const { data, isLoading } = useQuery<Department[]>({
    queryKey: ['admin-departments'],
    queryFn: () => api.get<Department[]>('/admin/departments').then(r => r.data),
    staleTime: 60_000,
  })

  const createMut = useMutation({
    mutationFn: (name: string) => api.post('/admin/departments', { name }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['admin-departments'] }); setNewName('') },
    onError: e => addToast({ type: 'error', message: extractErr(e) }),
  })

  const editMut = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      api.patch(`/admin/departments/${id}`, { name }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['admin-departments'] }); setEditTarget(null) },
    onError: e => addToast({ type: 'error', message: extractErr(e) }),
  })

  const toggleMut = useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) =>
      api.post(`/admin/departments/${id}/${active ? 'enable' : 'disable'}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-departments'] }),
    onError: e => addToast({ type: 'error', message: extractErr(e) }),
  })

  return (
    <div className="space-y-4">
      {/* Create */}
      <div className="flex gap-2">
        <input
          value={newName}
          onChange={e => setNewName(e.target.value)}
          placeholder="New department name…"
          className="flex-1 rounded-lg border border-cream-alt bg-cream-card px-3 py-2 text-sm
            text-ink-primary placeholder:text-ink-tertiary
            focus:outline-none focus:ring-2 focus:ring-primary-main"
          onKeyDown={e => { if (e.key === 'Enter' && newName.trim()) createMut.mutate(newName.trim()) }}
        />
        <Button
          variant="primary"
          size="sm"
          disabled={!newName.trim() || createMut.isPending}
          onClick={() => createMut.mutate(newName.trim())}
        >
          Add
        </Button>
      </div>

      {/* List */}
      {isLoading
        ? Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} variant="text" className="h-12 rounded-xl" />)
        : (data ?? []).map(d => (
          <div key={d.id}
            className="flex items-center justify-between gap-3 rounded-xl glass-card px-4 py-3">
            <div className="flex items-center gap-2 min-w-0">
              <span className={`w-2 h-2 rounded-full shrink-0 ${d.is_active ? 'bg-status-paid' : 'bg-ink-tertiary'}`} />
              <span className={`text-sm font-medium truncate ${d.is_active ? 'text-ink-primary' : 'text-ink-tertiary line-through'}`}>
                {d.name}
              </span>
            </div>
            <div className="flex gap-1 shrink-0">
              <button
                onClick={() => { setEditTarget(d); setEditName(d.name) }}
                className="px-2 py-1 text-xs text-ink-secondary hover:text-ink-primary rounded"
                aria-label={`Edit ${d.name}`}
              >Edit</button>
              <button
                onClick={() => toggleMut.mutate({ id: d.id, active: !d.is_active })}
                className={`px-2 py-1 text-xs rounded ${d.is_active ? 'text-status-failed hover:bg-status-failed/10' : 'text-status-paid hover:bg-status-paid/10'}`}
                aria-label={d.is_active ? `Disable ${d.name}` : `Enable ${d.name}`}
              >
                {d.is_active ? 'Disable' : 'Enable'}
              </button>
            </div>
          </div>
        ))
      }

      {/* Edit modal */}
      <Modal open={editTarget !== null} onClose={() => setEditTarget(null)} title="Rename Department">
        <div className="space-y-4">
          <input
            value={editName}
            onChange={e => setEditName(e.target.value)}
            className="w-full rounded-lg border border-cream-alt bg-cream-card px-3 py-2 text-sm
              focus:outline-none focus:ring-2 focus:ring-primary-main"
            onKeyDown={e => {
              if (e.key === 'Enter' && editName.trim() && editTarget)
                editMut.mutate({ id: editTarget.id, name: editName.trim() })
            }}
          />
          <Button
            variant="primary"
            className="w-full"
            disabled={!editName.trim() || editMut.isPending}
            onClick={() => editTarget && editMut.mutate({ id: editTarget.id, name: editName.trim() })}
          >
            {editMut.isPending ? 'Saving…' : 'Save'}
          </Button>
        </div>
      </Modal>
    </div>
  )
}

// ── Roles tab (read-only v1) ──────────────────────────────────────────────────

function RolesTab() {
  const { data, isLoading } = useQuery<Role[]>({
    queryKey: ['admin-roles'],
    queryFn: () => api.get<Role[]>('/admin/roles').then(r => r.data),
    staleTime: 120_000,
  })

  const levelLabel = (l: number) => {
    if (l >= 10) return 'Owner'
    if (l >= 5)  return 'Manager'
    return 'Staff'
  }

  return (
    <div className="space-y-3">
      <p className="text-xs text-ink-tertiary">Roles are read-only in this version.</p>
      {isLoading
        ? Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} variant="text" className="h-12 rounded-xl" />)
        : (data ?? [])
          .sort((a, b) => b.level - a.level)
          .map(r => (
            <div key={r.id}
              className="flex items-center justify-between gap-3 rounded-xl glass-card px-4 py-3">
              <div className="flex items-center gap-3">
                <span className={`w-2 h-2 rounded-full shrink-0 ${r.is_active ? 'bg-status-paid' : 'bg-ink-tertiary'}`} />
                <div>
                  <p className={`text-sm font-medium ${r.is_active ? 'text-ink-primary' : 'text-ink-tertiary'}`}>{r.name}</p>
                  <p className="text-xs text-ink-secondary">Level {r.level} · {levelLabel(r.level)}</p>
                </div>
              </div>
              {!r.is_active && <span className="text-xs text-ink-secondary">Disabled</span>}
            </div>
          ))
      }
    </div>
  )
}

// ── Judge Baselines tab ───────────────────────────────────────────────────────

function BaselinesTab() {
  const qc = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  const [editTarget, setEditTarget] = useState<Baseline | null>(null)
  const [editRatio, setEditRatio] = useState('')
  const [editTolerance, setEditTolerance] = useState('')

  const { data, isLoading } = useQuery<Baseline[]>({
    queryKey: ['admin-baselines'],
    queryFn: () => api.get<Baseline[]>('/admin/baselines').then(r => r.data),
    staleTime: 120_000,
  })

  const editMut = useMutation({
    mutationFn: ({ id, ratio, tol }: { id: string; ratio: string; tol: string }) =>
      api.patch(`/admin/baselines/${id}`, { expected_ratio: ratio, tolerance_percent: tol }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin-baselines'] })
      setEditTarget(null)
      addToast({ type: 'success', message: 'Baseline updated.' })
    },
    onError: e => addToast({ type: 'error', message: extractErr(e) }),
  })

  const toggleMut = useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) =>
      api.post(`/admin/baselines/${id}/${active ? 'enable' : 'disable'}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-baselines'] }),
    onError: e => addToast({ type: 'error', message: extractErr(e) }),
  })

  return (
    <div className="space-y-3">
      <p className="text-xs text-ink-tertiary">
        Each baseline tells the Judge what ratio of consumption vs revenue is expected. Deviations beyond the tolerance trigger an alert.
      </p>

      {isLoading
        ? Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} variant="text" className="h-16 rounded-xl" />)
        : (data ?? []).length === 0
          ? <p className="text-sm text-ink-tertiary py-4 text-center">No baselines configured.</p>
          : (data ?? []).map(b => (
            <div key={b.id} className="rounded-xl glass-card px-4 py-3 space-y-2">
              <div className="flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className={`text-sm font-medium truncate ${b.is_active ? 'text-ink-primary' : 'text-ink-tertiary'}`}>
                    {b.item_name ?? b.item_id}
                  </p>
                  <p className="text-xs text-ink-secondary">{b.business_driver}</p>
                </div>
                <div className="shrink-0 text-right">
                  <p className="text-xs font-semibold tabular-nums text-ink-primary">{b.expected_ratio}</p>
                  <p className="text-xs text-ink-secondary">±{b.tolerance_percent}%</p>
                </div>
              </div>
              <div className="flex gap-1">
                <button
                  onClick={() => { setEditTarget(b); setEditRatio(b.expected_ratio); setEditTolerance(b.tolerance_percent) }}
                  className="px-2 py-1 text-xs text-ink-secondary hover:text-ink-primary rounded"
                >Edit</button>
                <button
                  onClick={() => toggleMut.mutate({ id: b.id, active: !b.is_active })}
                  className={`px-2 py-1 text-xs rounded ${b.is_active ? 'text-status-failed hover:bg-status-failed/10' : 'text-status-paid hover:bg-status-paid/10'}`}
                >
                  {b.is_active ? 'Disable' : 'Enable'}
                </button>
              </div>
            </div>
          ))
      }

      <Modal open={editTarget !== null} onClose={() => setEditTarget(null)} title="Edit Baseline">
        <div className="space-y-4">
          <p className="text-sm text-ink-secondary">
            Item: <span className="font-medium text-ink-primary">{editTarget?.item_name}</span>
            <br />Driver: <span className="font-medium text-ink-primary">{editTarget?.business_driver}</span>
          </p>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-ink-secondary mb-1">Expected ratio</label>
              <input
                type="number" step="0.001" min="0"
                value={editRatio}
                onChange={e => setEditRatio(e.target.value)}
                className="w-full rounded-lg border border-cream-alt bg-cream-card px-3 py-2 text-sm
                  focus:outline-none focus:ring-2 focus:ring-primary-main"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-ink-secondary mb-1">Tolerance %</label>
              <input
                type="number" step="1" min="0" max="100"
                value={editTolerance}
                onChange={e => setEditTolerance(e.target.value)}
                className="w-full rounded-lg border border-cream-alt bg-cream-card px-3 py-2 text-sm
                  focus:outline-none focus:ring-2 focus:ring-primary-main"
              />
            </div>
          </div>
          <Button
            variant="primary"
            className="w-full"
            disabled={editMut.isPending}
            onClick={() => editTarget && editMut.mutate({ id: editTarget.id, ratio: editRatio, tol: editTolerance })}
          >
            {editMut.isPending ? 'Saving…' : 'Save Baseline'}
          </Button>
        </div>
      </Modal>
    </div>
  )
}

// ── Socket Status tab ─────────────────────────────────────────────────────────

function SocketRow({ label, endpoint }: { label: string; endpoint: string }) {
  const { data, isLoading } = useQuery<SocketStatus>({
    queryKey: ['socket-status', endpoint],
    queryFn: () => api.get<SocketStatus>(endpoint).then(r => r.data),
    staleTime: 5 * 60_000,
  })

  return (
    <div className="flex items-start gap-3 rounded-xl glass-card px-4 py-3">
      <span className={`w-2 h-2 rounded-full shrink-0 mt-1 ${
        isLoading ? 'bg-cream-alt' : data?.configured ? 'bg-status-paid' : 'bg-ink-tertiary'
      }`} />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-ink-primary">{label}</p>
        {!isLoading && (
          <p className={`text-xs mt-0.5 ${data?.configured ? 'text-ink-tertiary' : 'text-status-pending'}`}>
            {data?.message ?? '—'}
          </p>
        )}
      </div>
      {!isLoading && (
        <span className={`shrink-0 text-xs font-bold px-2 py-0.5 rounded-full
          ${data?.configured ? 'bg-status-paid/25 text-status-paid' : 'bg-ink-tertiary/20 text-ink-secondary'}`}>
          {data?.configured ? 'LIVE' : 'OFF'}
        </span>
      )}
    </div>
  )
}

function SocketStatusTab() {
  return (
    <div className="space-y-3">
      <p className="text-xs text-ink-tertiary">
        Payment and notification sockets. Activate by setting env vars (see docs/ runbooks).
      </p>
      <SocketRow label="M-Pesa Daraja (STK Push)"  endpoint="/finance/mpesa/status" />
      <SocketRow label="Bank Transfer (SMS + API)" endpoint="/finance/bank/status"  />
      <SocketRow label="Card Gateway"              endpoint="/finance/card/status"  />
      <SocketRow label="WhatsApp Notifications"    endpoint="/notifications/whatsapp/status" />
    </div>
  )
}

// ── Personal tab ──────────────────────────────────────────────────────────────

function PersonalTab() {
  const { size, changeSize } = useFontSizePref()
  const sizes: { key: FontSizeKey; label: string }[] = [
    { key: 'S', label: 'Small' },
    { key: 'M', label: 'Medium' },
    { key: 'L', label: 'Large' },
  ]
  return (
    <div className="space-y-5">
      <div>
        <p className="text-xs font-semibold text-ink-secondary mb-3">Font size</p>
        <div className="flex gap-2" role="group" aria-label="Text size">
          {sizes.map(s => (
            <button
              key={s.key}
              onClick={() => void changeSize(s.key)}
              aria-pressed={size === s.key}
              className={[
                'flex-1 py-2.5 rounded-xl border text-sm font-semibold transition-colors',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark',
                size === s.key
                  ? 'bg-primary-dark border-primary-dark text-cream-card'
                  : 'border-cream-alt text-ink-secondary hover:bg-cream-alt',
              ].join(' ')}
            >
              {s.label}
            </button>
          ))}
        </div>
        <p className="text-xs text-ink-tertiary mt-2">Applies to all text in the app.</p>
      </div>
    </div>
  )
}

// ── Main screen ───────────────────────────────────────────────────────────────

type TabKey = 'departments' | 'roles' | 'baselines' | 'sockets' | 'personal'

const TABS: { key: TabKey; label: string }[] = [
  { key: 'departments', label: 'Departments'     },
  { key: 'roles',       label: 'Roles'           },
  { key: 'baselines',   label: 'Judge Baselines' },
  { key: 'sockets',     label: 'Socket Status'   },
  { key: 'personal',    label: 'Personal'        },
]

export default function SettingsScreen() {
  const [tab, setTab] = useState<TabKey>('departments')

  return (
    <div className="p-4 max-w-2xl mx-auto">
      <div className="mb-5">
        <h1 className="font-serif text-2xl text-ink-primary">Settings</h1>
        <p className="text-xs text-ink-secondary mt-0.5">Admin controls and personal preferences</p>
      </div>

      {/* Tab strip */}
      <div className="flex gap-1 overflow-x-auto scrollbar-none pb-1 mb-5" role="tablist">
        {TABS.map(t => (
          <button
            key={t.key}
            role="tab"
            aria-selected={tab === t.key}
            onClick={() => setTab(t.key)}
            className={[
              'shrink-0 px-3.5 py-2 rounded-xl text-xs font-semibold transition-colors whitespace-nowrap',
              tab === t.key
                ? 'bg-primary-dark text-cream-card'
                : 'bg-cream-alt text-ink-secondary hover:text-ink-primary',
            ].join(' ')}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'departments' && <DepartmentsTab />}
      {tab === 'roles'       && <RolesTab />}
      {tab === 'baselines'   && <BaselinesTab />}
      {tab === 'sockets'     && <SocketStatusTab />}
      {tab === 'personal'    && <PersonalTab />}
    </div>
  )
}
