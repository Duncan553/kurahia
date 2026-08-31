import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Button, useToastStore, Skeleton } from '@shared'
import api from '../lib/axios'

// ── Types ─────────────────────────────────────────────────────────────────

interface StaffUser {
  id: string; username: string; role: string; department: string | null; is_active: boolean
}
interface DeptInfo { id: string; name: string }
interface RosterEntry {
  user_id: string; department_id: string; department: string; roster_date: string
}

const extractErr = (e: unknown) =>
  (e as { response?: { data?: { error?: string } } })?.response?.data?.error ?? 'Something went wrong.'

// ── Screen ────────────────────────────────────────────────────────────────
// Today's station roster: which department each employee is actually working
// today, separate from their fixed home department on the account. Lets a
// manager cover gaps (e.g. a waiter helping Front Desk today) without
// touching anyone's account — see app/hr/roster.py.

export default function RosterScreen() {
  const qc = useQueryClient()
  const addToast = useToastStore(s => s.addToast)
  const [pending, setPending] = useState<Record<string, string>>({}) // user_id -> department_id being chosen

  const { data: staff = [], isLoading: sLoad } = useQuery<StaffUser[]>({
    queryKey: ['roster', 'staff'],
    queryFn: () => api.get<StaffUser[]>('/auth/users').then(r => r.data.filter(u => u.is_active)),
    staleTime: 60_000,
  })
  const { data: meta } = useQuery<{ departments: DeptInfo[] }>({
    queryKey: ['users-meta'],
    queryFn: () => api.get('/auth/users/meta').then(r => r.data),
    staleTime: 5 * 60_000,
  })
  const { data: today = [], isLoading: rLoad } = useQuery<RosterEntry[]>({
    queryKey: ['roster', 'today'],
    queryFn: () => api.get<RosterEntry[]>('/hr/roster').then(r => r.data),
    staleTime: 30_000,
  })

  const assignMut = useMutation({
    mutationFn: ({ userId, departmentId }: { userId: string; departmentId: string }) =>
      api.post('/hr/roster', { user_id: userId, department_id: departmentId }),
    onSuccess: (_res, vars) => {
      addToast({ type: 'success', message: 'Station assigned for today.' })
      qc.invalidateQueries({ queryKey: ['roster'] })
      setPending(p => { const n = { ...p }; delete n[vars.userId]; return n })
    },
    onError: e => addToast({ type: 'error', message: extractErr(e) }),
  })

  const todayMap = new Map(today.map(r => [r.user_id, r]))
  const departments = meta?.departments ?? []
  const isLoading = sLoad || rLoad

  return (
    <div className="p-4 md:p-6 max-w-3xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-ink-primary font-serif">Today's Roster</h1>
        <p className="text-xs text-ink-tertiary mt-0.5">
          Put staff on a different station for today — this is what decides which work
          dashboard they land on, not their fixed department.
        </p>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} variant="row" />)}
        </div>
      ) : (
        <div className="space-y-2">
          {staff.map(u => {
            const rostered = todayMap.get(u.id)
            const current = pending[u.id] ?? rostered?.department_id ?? ''
            const homeDept = departments.find(d => d.name === u.department)
            const isOverridden = rostered && rostered.department_id !== homeDept?.id

            return (
              <div key={u.id} className="glass-card rounded-xl px-4 py-3 flex items-center gap-3">
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-ink-primary truncate">{u.username}</p>
                  <p className="text-xs text-ink-tertiary truncate">
                    {u.role} · home: {u.department ?? '—'}
                    {isOverridden && <span className="text-status-pending font-semibold"> · on {rostered!.department} today</span>}
                  </p>
                </div>
                <select
                  style={{ colorScheme: 'dark' }}
                  value={current}
                  onChange={e => setPending(p => ({ ...p, [u.id]: e.target.value }))}
                  className="rounded-lg glass-card bg-transparent px-2 py-1.5 text-xs text-ink-primary
                    focus:outline-none focus:border-primary-main"
                >
                  {/* homeDept can be missing (e.g. a disabled/legacy department still on
                      the account) — show the raw value instead of a blank-looking default */}
                  <option value="">{homeDept ? `${homeDept.name} (home)` : `${u.department ?? 'No department'} (home)`}</option>
                  {departments.filter(d => d.id !== homeDept?.id).map(d => (
                    <option key={d.id} value={d.id}>{d.name}</option>
                  ))}
                </select>
                <Button
                  variant="ghost" size="sm"
                  disabled={!pending[u.id] || pending[u.id] === rostered?.department_id || assignMut.isPending}
                  onClick={() => assignMut.mutate({ userId: u.id, departmentId: pending[u.id] })}
                >
                  Set
                </Button>
              </div>
            )
          })}
          {staff.length === 0 && <p className="text-sm text-ink-tertiary">No active staff.</p>}
        </div>
      )}
    </div>
  )
}
