import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { RequireRole } from '../components/AuthGate'
import { Button, SearchInput, ErrorBoundary, useToastStore } from '@shared'
import api from '../lib/axios'

interface StaffUser { id: string; username: string; role: string; department: string | null; is_active: boolean; pin_set: boolean }
interface StaffProfile {
  id: string; user_id: string; full_name: string
  wage_rate: string | null; wage_period: string | null
}
interface Meta { roles: { id: string; name: string; level: number }[]; departments: { id: string; name: string }[] }

const BLANK = { username:'', password:'', roleId:'', deptId:'', fullName:'', phone:'', wageRate:'', wagePeriod:'', hireDate:'', nationalId:'', emgName:'', emgPhone:'' }
const inp = 'w-full rounded-xl px-3 py-2.5 glass-card bg-transparent text-sm text-ink-primary focus:outline-none focus:border-primary-main'
const toE164 = (p: string) => { const s = p.replace(/\s+/g,''); return s.startsWith('+254')?s : s.startsWith('254')?'+'+s : s.startsWith('0')?'+254'+s.slice(1):s }
const extractErr = (e: unknown) => (e as {response?:{data?:{error?:string}}})?.response?.data?.error ?? 'Something went wrong.'
const LBL = ({ children }: { children: React.ReactNode }) => (
  <label className="block text-[10px] tracking-widest uppercase text-ink-secondary mb-1">{children}</label>
)

export default function StaffAccountsScreen() {
  const qc = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  const [searchQ, setSearchQ] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [step, setStep] = useState<1|2>(1)
  const [uid, setUid] = useState('')
  const [credentials, setCredentials] = useState<{u:string;p:string}|null>(null)
  const [f, setF] = useState(BLANK)
  const [err, setErr] = useState('')

  const set = (k: keyof typeof BLANK) => (e: React.ChangeEvent<HTMLInputElement|HTMLSelectElement>) =>
    setF(p => ({...p, [k]: e.target.value}))

  const { data: staff = [], isLoading: staffLoading } = useQuery<StaffUser[]>({
    queryKey: ['staff-accounts', searchQ],
    queryFn: () => api.get<StaffUser[]>(`/auth/users${searchQ ? `?q=${encodeURIComponent(searchQ)}` : ''}`).then(r => r.data),
    refetchInterval: 60_000,
  })
  const { data: meta } = useQuery<Meta>({
    queryKey: ['auth-meta'],
    queryFn: () => api.get<Meta>('/auth/users/meta').then(r => r.data),
  })
  const { data: profiles = [] } = useQuery<StaffProfile[]>({
    queryKey: ['staff-profiles'],
    queryFn: () => api.get<StaffProfile[]>('/hr/profiles').then(r => r.data),
  })
  const hasProfile = new Set(profiles.map(p => p.user_id))
  const profileFor = new Map(profiles.map(p => [p.user_id, p]))

  // Editing a wage on an EXISTING person had no screen anywhere: the hire
  // wizard could set one at step 2 and nothing could ever change it, so
  // thirteen of fifteen staff had no wage and payroll could not pay them.
  // PATCH /hr/profiles/<id> existed on the server the whole time; nothing
  // called it.
  const [wageEdit, setWageEdit] = useState<{id:string; value:string}|null>(null)
  const wageMut = useMutation({
    mutationFn: (v: {id:string; wage:string}) =>
      api.patch(`/hr/profiles/${v.id}`, { wage_rate: v.wage, wage_period: 'MONTHLY' })
         .then(r => r.data),
    onSuccess: () => { setWageEdit(null); setErr(''); qc.invalidateQueries({ queryKey: ['staff-profiles'] }) },
    onError:   (e) => setErr(extractErr(e)),
  })

  const userMut = useMutation({
    mutationFn: (b: object) => api.post('/auth/users', b).then(r => r.data),
    onSuccess: (data: {id:string}) => { setUid(data.id); setStep(2); setErr('') },
    onError: (e) => setErr(extractErr(e)),
  })

  /**
   * Assign a role / department.
   *
   * The backend has always supported this (PATCH /auth/users/<id> with role_id),
   * and /auth/users/meta already returns only the roles BELOW the actor's own
   * level so the escalation guard holds on the list as well as the write. It was
   * simply never wired to a control — which meant every employee was stuck on
   * the level-1 role registration hands out, forever. A head chef could never
   * actually be made a head chef.
   */
  const assignMut = useMutation({
    mutationFn: (v: { id: string; body: Record<string, string> }) =>
      api.patch(`/auth/users/${v.id}`, v.body).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['staff'] })
      addToast({ type: 'success', message: 'Role updated.' })
    },
    onError: (e) => addToast({ type: 'error', message: extractErr(e) }),
  })

  const toggleMut = useMutation({
    mutationFn: (u: StaffUser) =>
      api.post(u.is_active ? `/auth/deactivate/${u.id}` : `/auth/users/${u.id}/activate`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['staff-accounts'] }),
    onError: (e) => setErr(extractErr(e)),
  })

  const profileMut = useMutation({
    mutationFn: (b: object) => api.post('/hr/profiles', b).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['staff-accounts'] })
      qc.invalidateQueries({ queryKey: ['staff-profiles'] })
      setCredentials({ u: f.username, p: f.password })
      setShowForm(false); setStep(1); setUid(''); setF(BLANK); setErr('')
    },
    onError: (e) => setErr(extractErr(e)),
  })

  function handleStep1(e: React.FormEvent) {
    e.preventDefault(); setErr('')
    if (!f.username || !f.password || !f.roleId || !f.deptId) return setErr('All fields required.')
    if (f.password.length < 8) return setErr('Password must be at least 8 characters.')
    userMut.mutate({ username: f.username.trim().toLowerCase(), password: f.password, role_id: f.roleId, department_id: f.deptId })
  }

  function handleStep2(e: React.FormEvent) {
    e.preventDefault(); setErr('')
    if (!f.fullName.trim() || !f.phone.trim()) return setErr('Name and phone are required.')
    const body: Record<string, unknown> = { user_id: uid, full_name: f.fullName.trim(), phone: toE164(f.phone) }
    if (f.wageRate) { body.wage_rate = f.wageRate; body.wage_period = f.wagePeriod || 'MONTHLY' }
    if (f.hireDate) body.hire_date = f.hireDate
    if (f.nationalId) body.national_id = f.nationalId
    if (f.emgName) body.emergency_contact_name = f.emgName
    if (f.emgPhone) body.emergency_contact_phone = f.emgPhone
    profileMut.mutate(body)
  }

  return (
    <RequireRole minLevel={5}>
      <ErrorBoundary level="tile">
      <div className="max-w-3xl mx-auto p-4 md:p-6 pb-8 space-y-4">
        <div className="mb-6">
          <h1 className="font-serif text-2xl font-bold text-ink-primary">Staff Accounts</h1>
          <p className="text-xs text-ink-tertiary mt-1">Create accounts, manage access</p>
        </div>

          {/* Credentials handover card */}
          <AnimatePresence>
            {credentials && (
              <motion.div initial={{opacity:0,y:-10}} animate={{opacity:1,y:0}} exit={{opacity:0}}
                className="rounded-2xl border-2 border-primary-main bg-primary-main/5 p-4 space-y-2">
                <p className="text-xs font-semibold tracking-widest text-primary-dark uppercase">Account ready — give these to the staff member</p>
                <div className="space-y-1 font-mono text-sm text-ink-primary">
                  <p><span className="text-ink-tertiary">Username:</span> {credentials.u}</p>
                  <p><span className="text-ink-tertiary">Password:</span> {credentials.p}</p>
                </div>
                <p className="text-xs text-ink-secondary">Staff will set their PIN on first login.</p>
                <button onClick={() => setCredentials(null)} className="text-xs text-primary-dark underline font-medium">Dismiss</button>
              </motion.div>
            )}
          </AnimatePresence>

          {/* Creation form — two steps */}
          <AnimatePresence>
            {showForm && (
              <motion.div initial={{opacity:0,height:0}} animate={{opacity:1,height:'auto'}} exit={{opacity:0,height:0}}
                className="glass-card rounded-2xl p-4 space-y-3 overflow-hidden">

                <div className="flex items-center justify-between">
                  <p className="text-sm font-semibold text-ink-primary">
                    {step === 1 ? 'New account — login details' : 'Employee profile'}
                  </p>
                  {step === 2 && <span className="text-xs text-status-ok font-semibold">Step 2 of 2</span>}
                </div>

                {step === 1 && (
                  <form onSubmit={handleStep1} className="space-y-3">
                    <div><LBL>Username</LBL><input className={inp} value={f.username} onChange={set('username')} placeholder="e.g. john.mwangi" /></div>
                    <div><LBL>Temporary password <span className="normal-case">(min 8 chars)</span></LBL><input className={inp} value={f.password} onChange={set('password')} placeholder="Write this down" /></div>
                    <div>
                      <LBL>Role</LBL>
                      <select style={{ colorScheme: 'dark' }} className={inp} value={f.roleId} onChange={set('roleId')}>
                        <option value="">Select role</option>
                        {meta?.roles.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
                      </select>
                    </div>
                    <div>
                      <LBL>Department</LBL>
                      <select style={{ colorScheme: 'dark' }} className={inp} value={f.deptId} onChange={set('deptId')}>
                        <option value="">Select department</option>
                        {meta?.departments.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
                      </select>
                    </div>
                    {err && <p className="text-xs text-status-failed font-semibold">{err}</p>}
                    <div className="flex gap-2 pt-1">
                      <Button type="submit" variant="primary" size="sm" loading={userMut.isPending}>Next: profile →</Button>
                      <Button type="button" variant="ghost" size="sm" onClick={() => { setShowForm(false); setErr('') }}>Cancel</Button>
                    </div>
                  </form>
                )}

                {step === 2 && (
                  <form onSubmit={handleStep2} className="space-y-3">
                    <div><LBL>Full name *</LBL><input className={inp} value={f.fullName} onChange={set('fullName')} placeholder="e.g. John Mwangi" /></div>
                    <div><LBL>Phone * (0712… or +254…)</LBL><input className={inp} value={f.phone} onChange={set('phone')} placeholder="0712 345 678" /></div>
                    <div className="grid grid-cols-2 gap-3">
                      <div><LBL>Wage rate (optional)</LBL><input className={inp} value={f.wageRate} onChange={set('wageRate')} placeholder="1500" /></div>
                      <div>
                        <LBL>Period</LBL>
                        <select style={{ colorScheme: 'dark' }} className={inp} value={f.wagePeriod} onChange={set('wagePeriod')}>
                          <option value="">—</option>
                          <option value="HOURLY">Hourly</option>
                          <option value="DAILY">Daily</option>
                          <option value="MONTHLY">Monthly</option>
                        </select>
                      </div>
                    </div>
                    <div><LBL>Hire date (optional)</LBL><input className={inp} type="date" value={f.hireDate} onChange={set('hireDate')} /></div>
                    <div><LBL>National ID (optional)</LBL><input className={inp} value={f.nationalId} onChange={set('nationalId')} placeholder="Leave blank if unknown" /></div>
                    <div><LBL>Emergency contact name (optional)</LBL><input className={inp} value={f.emgName} onChange={set('emgName')} /></div>
                    <div><LBL>Emergency contact phone (optional)</LBL><input className={inp} value={f.emgPhone} onChange={set('emgPhone')} placeholder="0712 345 678" /></div>
                    {err && (
                      <p className="text-xs text-status-failed font-semibold">
                        {profileMut.isError ? 'Account created but profile incomplete. Fix above and tap Retry.' : err}
                      </p>
                    )}
                    <div className="flex gap-2 pt-1">
                      <Button type="submit" variant="primary" size="sm" loading={profileMut.isPending}>
                        {profileMut.isError ? 'Retry profile' : 'Create profile'}
                      </Button>
                      <Button type="button" variant="ghost" size="sm" onClick={() => { setShowForm(false); setStep(1); setUid(''); setF(BLANK); setErr('') }}>
                        Cancel
                      </Button>
                    </div>
                  </form>
                )}
              </motion.div>
            )}
          </AnimatePresence>

          {/* Add button */}
          {!showForm && (
            <button onClick={() => setShowForm(true)}
              className="w-full rounded-2xl border-2 border-dashed border-white/10 py-4
                text-sm font-semibold text-ink-tertiary hover:border-primary-main hover:text-primary-dark
                transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark">
              + Create new account
            </button>
          )}

          {/* Search */}
          <SearchInput value={searchQ} onChange={setSearchQ} placeholder="Search staff..." label="Search staff" />

          {searchQ && staff.length === 0 && !staffLoading && (
            <p className="text-sm text-ink-tertiary text-center py-8">No results for &lsquo;{searchQ}&rsquo; &middot; Hakuna kitu</p>
          )}

          {/* Staff list */}
          <div className="space-y-2">
            {!searchQ && staff.length === 0 && <p className="text-sm text-ink-tertiary text-center py-8">No staff accounts yet.</p>}
            {staff.map(u => (
              <div key={u.id} className={`flex items-center justify-between gap-2 px-4 py-3 rounded-2xl glass-card ${!u.is_active ? 'opacity-60' : ''}`}>
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-ink-primary truncate">{u.username}</p>
                  <p className="text-xs text-ink-secondary">{u.role}{u.department ? ` · ${u.department}` : ''}</p>
                  {/* Monthly pay, editable in place. Everyone here is paid
                      monthly, so the period is not asked — it is sent as
                      MONTHLY. The server still accepts HOURLY and DAILY for
                      anyone unusual; this screen just does not make fourteen
                      people answer a question with one answer. */}
                  {hasProfile.has(u.id) && (() => {
                    const prof = profileFor.get(u.id)!
                    const editing = wageEdit?.id === prof.id
                    if (editing) {
                      return (
                        <form
                          className="flex items-center gap-1 mt-1"
                          onSubmit={(e) => { e.preventDefault()
                            if (wageEdit.value.trim()) wageMut.mutate({ id: prof.id, wage: wageEdit.value.trim() }) }}
                        >
                          <span className="text-[10px] text-ink-tertiary">KSh</span>
                          <input
                            autoFocus type="number" min="0" step="1" inputMode="numeric"
                            aria-label={`Monthly pay for ${u.username}`}
                            value={wageEdit.value}
                            onChange={(e) => setWageEdit({ id: prof.id, value: e.target.value })}
                            className="w-24 px-2 py-0.5 text-xs rounded-lg bg-white/5 border border-white/10 text-ink-primary"
                          />
                          <button type="submit" disabled={wageMut.isPending}
                            className="text-[10px] px-2 py-0.5 rounded-lg bg-primary-main/20 text-primary-main font-semibold">
                            {wageMut.isPending ? '…' : 'Save'}
                          </button>
                          <button type="button" onClick={() => setWageEdit(null)}
                            className="text-[10px] px-1 text-ink-tertiary">Cancel</button>
                        </form>
                      )
                    }
                    return (
                      <button
                        onClick={() => setWageEdit({ id: prof.id, value: prof.wage_rate ? String(Math.round(parseFloat(prof.wage_rate))) : '' })}
                        className="mt-1 text-[11px] text-ink-tertiary hover:text-ink-secondary underline decoration-dotted"
                      >
                        {prof.wage_rate
                          ? `KSh ${Math.round(parseFloat(prof.wage_rate)).toLocaleString()} / month`
                          : 'Set monthly pay'}
                      </button>
                    )
                  })()}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {/* Role + department, editable in place. Only roles strictly
                      below this manager's own level are offered — the server
                      enforces the same rule, this just avoids showing options
                      that would be rejected. */}
                  <select
                    aria-label={`Role for ${u.username}`}
                    value={meta?.roles.find(r => r.name === u.role)?.id ?? ''}
                    disabled={assignMut.isPending}
                    onChange={e => e.target.value &&
                      assignMut.mutate({ id: u.id, body: { role_id: e.target.value } })}
                    style={{ colorScheme: 'dark' }}
                    className="min-h-[44px] rounded-xl px-2 py-1.5 text-xs glass-card
                      bg-transparent text-ink-primary focus:outline-none focus:border-primary-main"
                  >
                    {/* An empty option only while the current role is above what
                        this manager may assign — otherwise the box would look
                        blank for no visible reason. */}
                    {!meta?.roles.some(r => r.name === u.role) && (
                      <option value="">{u.role} (cannot change)</option>
                    )}
                    {meta?.roles.map(r => (
                      <option key={r.id} value={r.id}>{r.name}</option>
                    ))}
                  </select>
                  <select
                    aria-label={`Department for ${u.username}`}
                    value={meta?.departments.find(d => d.name === u.department)?.id ?? ''}
                    disabled={assignMut.isPending}
                    onChange={e => e.target.value &&
                      assignMut.mutate({ id: u.id, body: { department_id: e.target.value } })}
                    style={{ colorScheme: 'dark' }}
                    className="min-h-[44px] rounded-xl px-2 py-1.5 text-xs glass-card
                      bg-transparent text-ink-primary focus:outline-none focus:border-primary-main"
                  >
                    <option value="">No department</option>
                    {meta?.departments.map(d => (
                      <option key={d.id} value={d.id}>{d.name}</option>
                    ))}
                  </select>
                  <div className="flex flex-col items-end gap-1">
                    {!hasProfile.has(u.id) && <span className="text-[10px] font-semibold tracking-wide text-orange-600 bg-orange-50 px-2 py-0.5 rounded-full">No profile</span>}
                    {!u.pin_set && <span className="text-[10px] font-semibold tracking-wide text-amber-600 bg-amber-50 px-2 py-0.5 rounded-full">PIN not set</span>}
                    {!u.is_active && <span className="text-[10px] font-semibold tracking-wide text-status-failed bg-status-failed/10 px-2 py-0.5 rounded-full">Inactive</span>}
                  </div>
                  {/* Kill switch — deactivation locks them out on their next request */}
                  <Button
                    variant={u.is_active ? 'ghost' : 'primary'} size="sm"
                    loading={toggleMut.isPending && toggleMut.variables?.id === u.id}
                    onClick={() => toggleMut.mutate(u)}>
                    {u.is_active ? 'Deactivate' : 'Reactivate'}
                  </Button>
                </div>
              </div>
            ))}
          </div>

      </div>
      </ErrorBoundary>
    </RequireRole>
  )
}
