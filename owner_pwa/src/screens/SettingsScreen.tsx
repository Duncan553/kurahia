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
          className="flex-1 rounded-lg border border-white/10 bg-transparent px-3 py-2 text-sm
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
            className="flex items-center justify-between gap-3 glass-card rounded-xl px-4 py-3">
            <div className="flex items-center gap-2 min-w-0">
              <span className={`w-2 h-2 rounded-full shrink-0 ${d.is_active ? 'bg-status-paid' : 'bg-ink-tertiary'}`} />
              <span className={`text-sm font-medium truncate ${d.is_active ? 'text-ink-primary' : 'text-ink-tertiary line-through'}`}>
                {d.name}
              </span>
            </div>
            {/* Row actions. These were 37x24 and 55x24 — the smallest real
                controls on the Settings screen and there are ~19 of them.
                min-h/min-w-[44px] gives each a full touch box; -my-2.5 pulls the
                extra 10px per side back OUT of the layout, so the hit area grows
                into the card's own py-3 padding and the row height never changes.
                (The negative margin does not shrink the button itself — the
                browser still hit-tests the full 44px box.) */}
            <div className="flex items-center gap-1 shrink-0">
              <button
                onClick={() => { setEditTarget(d); setEditName(d.name) }}
                className="px-2 -my-2.5 min-h-[44px] min-w-[44px] inline-flex items-center justify-center
                  text-xs text-ink-secondary hover:text-ink-primary rounded-lg"
                aria-label={`Edit ${d.name}`}
              >Edit</button>
              <button
                onClick={() => toggleMut.mutate({ id: d.id, active: !d.is_active })}
                className={`px-2 -my-2.5 min-h-[44px] min-w-[44px] inline-flex items-center justify-center
                  text-xs rounded-lg ${d.is_active ? 'text-status-failed hover:bg-status-failed/10' : 'text-status-paid hover:bg-status-paid/10'}`}
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
            className="w-full rounded-lg border border-white/10 bg-transparent px-3 py-2 text-sm
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
              className="flex items-center justify-between gap-3 glass-card rounded-xl px-4 py-3">
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
            <div key={b.id} className="glass-card rounded-xl px-4 py-3 space-y-2">
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
              {/* Same 44px hit box + negative-margin trick as the Departments rows above. */}
              <div className="flex items-center gap-1 -my-1">
                <button
                  onClick={() => { setEditTarget(b); setEditRatio(b.expected_ratio); setEditTolerance(b.tolerance_percent) }}
                  className="px-2 -my-2.5 min-h-[44px] min-w-[44px] inline-flex items-center justify-center
                    text-xs text-ink-secondary hover:text-ink-primary rounded-lg"
                  aria-label={`Edit baseline for ${b.item_name ?? b.item_id}`}
                >Edit</button>
                <button
                  onClick={() => toggleMut.mutate({ id: b.id, active: !b.is_active })}
                  className={`px-2 -my-2.5 min-h-[44px] min-w-[44px] inline-flex items-center justify-center
                    text-xs rounded-lg ${b.is_active ? 'text-status-failed hover:bg-status-failed/10' : 'text-status-paid hover:bg-status-paid/10'}`}
                  aria-label={b.is_active
                    ? `Disable baseline for ${b.item_name ?? b.item_id}`
                    : `Enable baseline for ${b.item_name ?? b.item_id}`}
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
                className="w-full rounded-lg border border-white/10 bg-transparent px-3 py-2 text-sm
                  focus:outline-none focus:ring-2 focus:ring-primary-main"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-ink-secondary mb-1">Tolerance %</label>
              <input
                type="number" step="1" min="0" max="100"
                value={editTolerance}
                onChange={e => setEditTolerance(e.target.value)}
                className="w-full rounded-lg border border-white/10 bg-transparent px-3 py-2 text-sm
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
    <div className="flex items-start gap-3 glass-card rounded-xl px-4 py-3">
      <span className={`w-2 h-2 rounded-full shrink-0 mt-1 ${
        isLoading ? 'bg-white/5' : data?.configured ? 'bg-status-paid' : 'bg-ink-tertiary'
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
      {/* Bank transfer is not offered. It was a payment method nobody could
          explain, so it produced payments nobody could verify — removed from
          every till on 14 Sep 2026. A guest pays cash, M-Pesa or card. The
          socket stays in the tree, dormant and unadvertised, rather than being
          deleted; staff PAYROLL by bank is a different thing and is unaffected. */}
      <SocketRow label="Card Gateway"              endpoint="/finance/card/status"  />
      {/* WhatsApp is not being used — decided 14 Sep 2026, and both WHATSAPP
          and WHATSAPP_FALLBACK_SMS carry an explicit is_active=false row in
          notification_channel_configs. Listing a socket the resort has ruled
          out invites somebody to go and switch it on. */}
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
                  ? 'bg-primary-main border-primary-main text-white'
                  : 'border-white/10 text-ink-secondary hover:bg-white/5',
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


// ── Conduct rules ─────────────────────────────────────────────────────────────
//
// POST /conduct/rules is owner-only and had no caller in any app, so the staff
// app's "Code of Conduct" screen — which every employee is asked to read and
// sign — could only ever say "No conduct rules published yet." The rules could
// be seeded by a command on the server, which is not a door the owner has.
//
// Publishing the same rule_key again creates version 2 and retires version 1
// (app/conduct/core.py), and a signature is against a VERSION, so re-publishing
// a rule correctly asks everyone to sign again.

interface ConductRule {
  id: string
  rule_key: string
  title: string
  body: string
  category: string
  version: number
  is_active: boolean
}

// Shape per app/conduct/core.py::compliance_report — names, not ids, and a
// count of who has NOT signed rather than who has.
interface ComplianceRow {
  rule_id: string
  rule_key: string
  title: string
  version: number
  unsigned_count: number
  unsigned_employees: string[]
  message: string
}

const RULE_CATEGORIES = ['RESPECT', 'PUNCTUALITY', 'SAFETY', 'CONFIDENTIALITY', 'GENERAL']

function ConductTab() {
  const qc = useQueryClient()
  const [title, setTitle]       = useState('')
  const [body, setBody]         = useState('')
  const [category, setCategory] = useState('GENERAL')
  const [err, setErr]           = useState('')

  const { data: rules = [], isLoading } = useQuery<ConductRule[]>({
    queryKey: ['conduct-rules'],
    queryFn: () => api.get<ConductRule[]>('/conduct/rules').then(r => Array.isArray(r.data) ? r.data : []),
  })

  const { data: compliance = [] } = useQuery<ComplianceRow[]>({
    queryKey: ['conduct-compliance'],
    queryFn: () => api.get<ComplianceRow[]>('/conduct/compliance').then(r => Array.isArray(r.data) ? r.data : []),
    staleTime: 60_000,
  })

  const publish = useMutation({
    mutationFn: () => api.post('/conduct/rules', {
      // The key is what versions chain on, so it comes from the title rather
      // than being another thing to type and get subtly different.
      rule_key: title.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, ''),
      title: title.trim(),
      body: body.trim(),
      category,
    }).then(r => r.data),
    onSuccess: () => {
      setTitle(''); setBody(''); setErr('')
      qc.invalidateQueries({ queryKey: ['conduct-rules'] })
      qc.invalidateQueries({ queryKey: ['conduct-compliance'] })
    },
    onError: (e: unknown) => setErr(
      (e as { response?: { data?: { error?: string } } })?.response?.data?.error
      ?? 'Could not publish that rule.'),
  })

  const signedFor = (ruleId: string) => compliance.find(c => c.rule_id === ruleId)

  return (
    <div className="space-y-5">
      <div className="rounded-2xl glass-card p-4 space-y-3">
        <p className="text-sm font-semibold text-ink-primary">Publish a rule</p>
        <input
          placeholder="Title — e.g. Arriving on time"
          value={title} onChange={e => setTitle(e.target.value)}
          className="w-full rounded-xl glass-card bg-transparent px-4 py-3 text-sm
            text-ink-primary focus:outline-none focus:border-primary-main" />
        <textarea
          rows={3}
          placeholder="What the rule actually says, in the words staff will read."
          value={body} onChange={e => setBody(e.target.value)}
          className="w-full rounded-xl glass-card bg-transparent px-4 py-3 text-sm
            text-ink-primary focus:outline-none focus:border-primary-main resize-none" />
        <select
          style={{ colorScheme: 'dark' }}
          value={category} onChange={e => setCategory(e.target.value)}
          className="w-full rounded-xl glass-card bg-transparent px-4 py-3 text-sm
            text-ink-primary focus:outline-none focus:border-primary-main">
          {RULE_CATEGORIES.map(c => <option key={c} value={c}>{c.toLowerCase()}</option>)}
        </select>
        {err && <p className="text-xs text-status-failed">{err}</p>}
        <button
          onClick={() => publish.mutate()}
          disabled={!title.trim() || !body.trim() || publish.isPending}
          className="w-full min-h-[44px] rounded-xl bg-primary-main text-white text-sm
            font-semibold disabled:opacity-50">
          {publish.isPending ? 'Publishing…' : 'Publish to every employee'}
        </button>
        <p className="text-[11px] text-ink-tertiary">
          Publishing a title that already exists creates a new version and asks
          everyone to sign it again.
        </p>
      </div>

      {isLoading ? (
        <p className="text-sm text-ink-tertiary">Loading…</p>
      ) : rules.length === 0 ? (
        <p className="text-sm text-ink-tertiary">
          Nothing published yet. Until there is, the staff app tells everyone there
          are no rules to sign.
        </p>
      ) : (
        <div className="space-y-3">
          {rules.map(r => {
            const c = signedFor(r.id)
            return (
              <div key={r.id} className="rounded-2xl glass-card p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-semibold text-ink-primary">{r.title}</p>
                    <p className="text-[10px] uppercase tracking-wider text-ink-tertiary mt-0.5">
                      {r.category.toLowerCase()} · v{r.version}
                    </p>
                  </div>
                  {c && (
                    <p className="text-xs shrink-0">
                      {c.unsigned_count > 0
                        ? <span className="text-status-pending">{c.unsigned_count} not signed</span>
                        : <span className="text-status-paid">everyone signed</span>}
                    </p>
                  )}
                </div>
                <p className="text-sm text-ink-secondary mt-2 whitespace-pre-wrap">{r.body}</p>
                {c && c.unsigned_count > 0 && (
                  <p className="text-[11px] text-ink-tertiary mt-2">
                    Waiting on: {(c.unsigned_employees ?? []).join(', ')}
                  </p>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ── Main screen ───────────────────────────────────────────────────────────────

type TabKey = 'departments' | 'roles' | 'conduct' | 'baselines' | 'sockets' | 'personal'

const TABS: { key: TabKey; label: string }[] = [
  { key: 'departments', label: 'Departments'     },
  { key: 'roles',       label: 'Roles'           },
  { key: 'conduct',     label: 'Code of Conduct' },
  { key: 'baselines',   label: 'Judge Baselines' },
  { key: 'sockets',     label: 'Socket Status'   },
  { key: 'personal',    label: 'Personal'        },
]

export default function SettingsScreen() {
  const [tab, setTab] = useState<TabKey>('departments')

  return (
    <div className="p-4 max-w-3xl mx-auto">
      <div className="mb-5">
        <h1 className="text-2xl font-bold text-ink-primary font-serif">Settings</h1>
        <p className="text-xs text-ink-tertiary mt-0.5">Business day, system configuration</p>
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
              // min-h-[44px] — the tab strip was 32px tall.
              'shrink-0 px-3.5 min-h-[44px] rounded-xl text-xs font-semibold transition-colors whitespace-nowrap',
              tab === t.key
                ? 'bg-primary-main text-white'
                : 'bg-white/5 text-ink-secondary hover:text-ink-primary',
            ].join(' ')}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'departments' && <DepartmentsTab />}
      {tab === 'roles'       && <RolesTab />}
      {tab === 'conduct'     && <ConductTab />}
      {tab === 'baselines'   && <BaselinesTab />}
      {tab === 'sockets'     && <SocketStatusTab />}
      {tab === 'personal'    && <PersonalTab />}
    </div>
  )
}
