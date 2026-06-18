import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Drawer, Button, useToastStore, Skeleton } from '@shared'
import api from '../lib/axios'

// ── Types ─────────────────────────────────────────────────────────────────────

interface StaffUser {
  id: string; username: string; role: string; department: string | null
  is_active: boolean; pin_set: boolean
}

interface Profile {
  user_id: string; full_name: string; phone: string
  hire_date: string | null; wage_rate: string | null; wage_period: string | null
}

interface Meta {
  roles: { id: string; name: string; level: number }[]
  departments: { id: string; name: string }[]
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const extractErr = (e: unknown) =>
  (e as { response?: { data?: { error?: string } } })?.response?.data?.error ?? 'Something went wrong.'

const toE164 = (p: string) => {
  const s = p.replace(/\s+/g, '')
  return s.startsWith('+254') ? s
    : s.startsWith('254') ? '+' + s
    : s.startsWith('0') ? '+254' + s.slice(1) : s
}

const BLANK = {
  username: '', password: '', roleId: '', deptId: '',
  fullName: '', phone: '', wageRate: '', wagePeriod: 'MONTHLY', hireDate: '',
}

// ── Staff row card ────────────────────────────────────────────────────────────

function StaffCard({
  user, profile, onSelect,
}: {
  user: StaffUser; profile: Profile | undefined; onSelect: () => void
}) {
  const initials = profile?.full_name
    ? profile.full_name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()
    : user.username.slice(0, 2).toUpperCase()

  return (
    <button
      onClick={onSelect}
      className="w-full text-left flex items-center gap-3 rounded-xl border border-white/10
        px-4 py-3 hover:border-primary-light/50 hover:shadow-sm transition-all
        focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-main"
    >
      {/* Avatar */}
      <div className={`shrink-0 w-10 h-10 rounded-full flex items-center justify-center
        text-sm font-bold leading-none
        ${user.is_active ? 'bg-primary-dark text-white' : 'bg-ink-tertiary/20 text-slate-400/50'}`}>
        {initials}
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <p className={`text-sm font-semibold truncate ${user.is_active ? 'text-white' : 'text-slate-400/50'}`}>
          {profile?.full_name ?? user.username}
        </p>
        <p className="text-xs text-slate-300/70 truncate">
          @{user.username}
          {user.role && <span className="ml-1">· {user.role}</span>}
          {user.department && <span className="ml-1">· {user.department}</span>}
        </p>
        {!profile && (
          <span className="inline-block mt-0.5 text-xs px-1.5 py-0.5 rounded bg-status-pending text-white font-bold">
            No profile
          </span>
        )}
      </div>

      {/* Status badges */}
      <div className="shrink-0 flex flex-col items-end gap-1">
        {!user.is_active && (
          <span className="text-xs px-2 py-0.5 rounded-full bg-ink-tertiary/20 text-slate-300/70 font-semibold">
            Inactive
          </span>
        )}
        {!user.pin_set && user.is_active && (
          <span className="text-xs px-2 py-0.5 rounded-full bg-status-pending text-white font-bold">
            No PIN
          </span>
        )}
      </div>
    </button>
  )
}

// ── User detail drawer ────────────────────────────────────────────────────────

function UserDrawer({
  user, profile, onClose,
}: {
  user: StaffUser; profile: Profile | undefined; onClose: () => void
}) {
  const qc = useQueryClient()
  const addToast = useToastStore(s => s.addToast)

  const toggleMut = useMutation({
    mutationFn: () =>
      user.is_active
        ? api.post(`/auth/deactivate/${user.id}`)
        : api.post(`/auth/users/${user.id}/activate`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['staff-users'] })
      addToast({ type: 'success', message: user.is_active ? 'Account deactivated.' : 'Account reactivated.' })
      onClose()
    },
    onError: e => addToast({ type: 'error', message: extractErr(e) }),
  })

  const lockoutMut = useMutation({
    mutationFn: () => api.post(`/auth/reset-lockout/${user.id}`),
    onSuccess: () => addToast({ type: 'success', message: 'Lockout cleared. User can try again.' }),
    onError: e => addToast({ type: 'error', message: extractErr(e) }),
  })

  return (
    <div className="space-y-5">
      {/* Profile card */}
      <div className="rounded-xl bg-white/5 p-4 space-y-2">
        <div className="flex items-center gap-3">
          <div className={`w-12 h-12 rounded-full flex items-center justify-center font-bold text-base
            ${user.is_active ? 'bg-primary-dark text-white' : 'bg-ink-tertiary/20 text-slate-400/50'}`}>
            {(profile?.full_name ?? user.username).slice(0, 2).toUpperCase()}
          </div>
          <div>
            <p className="font-semibold text-white">{profile?.full_name ?? user.username}</p>
            <p className="text-xs text-slate-300/70">@{user.username}</p>
          </div>
        </div>
        <div className="text-xs text-slate-300/70 space-y-1 pt-2 border-t border-cream-deep">
          <p>Role: <span className="font-medium text-white">{user.role}</span></p>
          {user.department && <p>Dept: <span className="font-medium text-white">{user.department}</span></p>}
          {profile?.phone && <p>Phone: <span className="font-medium text-white">{profile.phone}</span></p>}
          {profile?.hire_date && <p>Hired: <span className="font-medium text-white">{profile.hire_date}</span></p>}
          {profile?.wage_rate && (
            <p>Wage: <span className="font-medium text-white">
              KSh {parseFloat(profile.wage_rate).toLocaleString('en-KE')} / {profile.wage_period?.toLowerCase()}
            </span></p>
          )}
          <p>Status: <span className={`font-medium ${user.is_active ? 'text-status-paid' : 'text-status-failed'}`}>
            {user.is_active ? 'Active' : 'Inactive'}
          </span></p>
          <p>PIN: <span className={`font-medium ${user.pin_set ? 'text-status-paid' : 'text-status-pending'}`}>
            {user.pin_set ? 'Set' : 'Not set'}
          </span></p>
          {!profile && (
            <p className="text-status-pending font-medium">⚠ No employee profile linked</p>
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="space-y-2">
        <Button
          variant={user.is_active ? 'danger' : 'primary'}
          className="w-full"
          disabled={toggleMut.isPending}
          onClick={() => toggleMut.mutate()}
        >
          {toggleMut.isPending
            ? (user.is_active ? 'Deactivating…' : 'Activating…')
            : (user.is_active ? 'Deactivate Account' : 'Reactivate Account')}
        </Button>
        <Button
          variant="ghost"
          className="w-full"
          disabled={lockoutMut.isPending}
          onClick={() => lockoutMut.mutate()}
        >
          {lockoutMut.isPending ? 'Clearing…' : 'Reset Login Lockout'}
        </Button>
      </div>
    </div>
  )
}

// ── Create user flow (2 steps) ────────────────────────────────────────────────

function CreateUserFlow({
  meta, onClose,
}: {
  meta: Meta; onClose: () => void
}) {
  const qc = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  const [step, setStep] = useState<1 | 2>(1)
  const [uid, setUid] = useState('')
  const [f, setF] = useState(BLANK)
  const [err, setErr] = useState('')

  const set = (k: keyof typeof BLANK) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setF(p => ({ ...p, [k]: e.target.value }))

  const userMut = useMutation({
    mutationFn: (b: object) => api.post('/auth/users', b).then(r => r.data),
    onSuccess: (data: { id: string }) => { setUid(data.id); setStep(2); setErr('') },
    onError: e => setErr(extractErr(e)),
  })

  const profileMut = useMutation({
    mutationFn: (b: object) => api.post('/hr/profiles', b).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['staff-users'] })
      qc.invalidateQueries({ queryKey: ['staff-profiles'] })
      addToast({ type: 'success', message: `Account created for ${f.username}. Give them their credentials.` })
      onClose()
    },
    onError: e => setErr(extractErr(e)),
  })

  function handleStep1(e: React.FormEvent) {
    e.preventDefault(); setErr('')
    if (!f.username || !f.password || !f.roleId || !f.deptId) return setErr('All fields required.')
    if (f.password.length < 8) return setErr('Password must be at least 8 characters.')
    userMut.mutate({
      username: f.username.trim().toLowerCase(),
      password: f.password,
      role_id: f.roleId,
      department_id: f.deptId,
    })
  }

  function handleStep2(e: React.FormEvent) {
    e.preventDefault(); setErr('')
    if (!f.fullName.trim() || !f.phone.trim()) return setErr('Full name and phone are required.')
    const body: Record<string, unknown> = {
      user_id: uid,
      full_name: f.fullName.trim(),
      phone: toE164(f.phone),
    }
    if (f.wageRate) { body.wage_rate = f.wageRate; body.wage_period = f.wagePeriod }
    if (f.hireDate) body.hire_date = f.hireDate
    profileMut.mutate(body)
  }

  const inp = `w-full rounded-lg border border-white/10 bg-transparent px-3 py-2 text-sm
    text-white placeholder:text-slate-400/50
    focus:outline-none focus:ring-2 focus:ring-primary-main`

  return (
    <div className="space-y-4">
      {/* Step indicator */}
      <div className="flex items-center gap-2 text-xs text-slate-400/50 mb-2">
        <span className={`font-semibold ${step === 1 ? 'text-primary-dark' : 'text-slate-400/50'}`}>1 Account</span>
        <span>→</span>
        <span className={`font-semibold ${step === 2 ? 'text-primary-dark' : 'text-slate-400/50'}`}>2 Profile</span>
      </div>

      {step === 1 && (
        <form onSubmit={handleStep1} className="space-y-3">
          <div>
            <label className="block text-xs font-semibold text-slate-300/70 mb-1">Username</label>
            <input className={inp} placeholder="e.g. amina.waweru" value={f.username} onChange={set('username')} />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-300/70 mb-1">Temp password (8+ chars)</label>
            <input className={inp} type="password" placeholder="Temporary password" value={f.password} onChange={set('password')} />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-300/70 mb-1">Role</label>
            <select className={inp} value={f.roleId} onChange={set('roleId')}>
              <option value="">Select role…</option>
              {meta.roles.map(r => <option key={r.id} value={r.id}>{r.name} (level {r.level})</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-300/70 mb-1">Department</label>
            <select className={inp} value={f.deptId} onChange={set('deptId')}>
              <option value="">Select department…</option>
              {meta.departments.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>
          </div>
          {err && <p className="text-xs text-status-failed">{err}</p>}
          <Button type="submit" variant="primary" className="w-full" disabled={userMut.isPending}>
            {userMut.isPending ? 'Creating account…' : 'Create Account →'}
          </Button>
        </form>
      )}

      {step === 2 && (
        <form onSubmit={handleStep2} className="space-y-3">
          <p className="text-xs text-slate-300/70">Account created. Now add the employee profile.</p>
          <div>
            <label className="block text-xs font-semibold text-slate-300/70 mb-1">Full name</label>
            <input className={inp} placeholder="Full legal name" value={f.fullName} onChange={set('fullName')} />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-300/70 mb-1">Phone number</label>
            <input className={inp} placeholder="07xx xxx xxx" value={f.phone} onChange={set('phone')} />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-300/70 mb-1">Hire date (optional)</label>
            <input className={inp} type="date" value={f.hireDate} onChange={set('hireDate')} />
          </div>
          <div className="flex gap-2">
            <div className="flex-1">
              <label className="block text-xs font-semibold text-slate-300/70 mb-1">Wage rate (optional)</label>
              <input className={inp} type="number" placeholder="e.g. 35000" value={f.wageRate} onChange={set('wageRate')} />
            </div>
            <div className="w-32">
              <label className="block text-xs font-semibold text-slate-300/70 mb-1">Period</label>
              <select className={inp} value={f.wagePeriod} onChange={set('wagePeriod')}>
                <option value="MONTHLY">Monthly</option>
                <option value="DAILY">Daily</option>
                <option value="HOURLY">Hourly</option>
              </select>
            </div>
          </div>
          {err && <p className="text-xs text-status-failed">{err}</p>}
          <Button type="submit" variant="primary" className="w-full" disabled={profileMut.isPending}>
            {profileMut.isPending ? 'Saving profile…' : 'Finish & Create'}
          </Button>
        </form>
      )}
    </div>
  )
}

// ── Main screen ───────────────────────────────────────────────────────────────

export default function StaffScreen() {
  const [selected, setSelected] = useState<StaffUser | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [filter, setFilter] = useState<'active' | 'all'>('active')

  const { data: users = [], isLoading: uLoad } = useQuery<StaffUser[]>({
    queryKey: ['staff-users'],
    queryFn: () => api.get<StaffUser[]>('/auth/users').then(r => r.data),
    staleTime: 60_000,
  })

  const { data: profiles = [], isLoading: pLoad } = useQuery<Profile[]>({
    queryKey: ['staff-profiles'],
    queryFn: () => api.get<Profile[]>('/hr/profiles').then(r => r.data),
    staleTime: 60_000,
  })

  const { data: meta } = useQuery<Meta>({
    queryKey: ['auth-meta'],
    queryFn: () => api.get<Meta>('/auth/users/meta').then(r => r.data),
    staleTime: 5 * 60_000,
  })

  const profileMap = new Map(profiles.map(p => [p.user_id, p]))
  const isLoading  = uLoad || pLoad

  const filtered = filter === 'active'
    ? users.filter(u => u.is_active)
    : users

  return (
    <div className="p-4 max-w-2xl mx-auto">
      <div className="flex items-center justify-between mb-5 gap-3">
        <div>
          <h1 className="font-serif text-2xl text-white">Staff</h1>
          <p className="text-xs text-slate-300/70 mt-0.5">{users.length} total · {users.filter(u => u.is_active).length} active</p>
        </div>
        <Button
          variant="primary"
          size="sm"
          onClick={() => setShowCreate(true)}
        >
          + Add staff
        </Button>
      </div>

      {/* Filter toggle */}
      <div className="flex gap-1 bg-white/5 rounded-xl p-1 mb-4" role="tablist">
        {(['active', 'all'] as const).map(f => (
          <button
            key={f}
            role="tab"
            aria-selected={filter === f}
            onClick={() => setFilter(f)}
            className={[
              'flex-1 py-2 rounded-lg text-xs font-semibold transition-colors',
              filter === f ? 'bg-transparent text-white shadow-sm' : 'text-slate-300/70 hover:text-white',
            ].join(' ')}
          >
            {f === 'active' ? 'Active' : 'All'}
          </button>
        ))}
      </div>

      {/* List */}
      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="flex gap-3 rounded-xl border border-white/10 bg-transparent p-3">
              <Skeleton variant="avatar" className="w-10 h-10 rounded-full" />
              <div className="flex-1 space-y-2">
                <Skeleton variant="text" className="w-32 h-4" />
                <Skeleton variant="text" className="w-48 h-3" />
              </div>
            </div>
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="py-12 text-center">
          <p className="text-slate-300/70 text-sm">No {filter === 'active' ? 'active' : ''} staff accounts.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map(u => (
            <StaffCard
              key={u.id}
              user={u}
              profile={profileMap.get(u.id)}
              onSelect={() => setSelected(u)}
            />
          ))}
        </div>
      )}

      {/* Detail drawer */}
      <Drawer open={selected !== null} onClose={() => setSelected(null)} title={selected?.username ?? ''}>
        {selected && (
          <UserDrawer
            user={selected}
            profile={profileMap.get(selected.id)}
            onClose={() => setSelected(null)}
          />
        )}
      </Drawer>

      {/* Create drawer */}
      <Drawer open={showCreate} onClose={() => setShowCreate(false)} title="Add Staff Account">
        {meta && (
          <CreateUserFlow meta={meta} onClose={() => setShowCreate(false)} />
        )}
        {!meta && <p className="text-xs text-slate-400/50">Loading role options…</p>}
      </Drawer>
    </div>
  )
}
