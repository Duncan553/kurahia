import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Avatar, Button, useToastStore } from '@shared'
import { useAuthStore } from '../stores/authStore'
import { useFontSizePref, type FontSizeKey } from '../lib/fontSizePref'
import api from '../lib/axios'

interface MyProfile {
  full_name: string; phone: string
  photo_path: string | null
  payment_method: string | null; payment_account_number: string | null
}
const extractErr = (e: unknown) =>
  (e as { response?: { data?: { error?: string } } })?.response?.data?.error ?? 'Something went wrong.'

function roleName(level: number): string {
  if (level >= 10) return 'Owner'
  if (level >= 5)  return 'Manager'
  if (level >= 3)  return 'Gate Staff'
  return 'Staff'
}

function NavCard({ label, description, path, icon, danger }: {
  label: string; description: string; path: string
  icon: React.ReactNode; danger?: boolean
}) {
  const navigate = useNavigate()
  return (
    <motion.button
      whileTap={{ scale: 0.97 }}
      whileHover={{ y: -2 }}
      onClick={() => navigate(path)}
      className={[
        'w-full flex items-center gap-4 p-4 rounded-2xl transition-colors text-left',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark',
        danger
          ? 'border border-status-failed/20 bg-status-failed/5 hover:bg-status-failed/10'
          : 'glass-card hover:bg-white/5 active:bg-white/8',
      ].join(' ')}
    >
      <span className={danger ? 'text-status-failed shrink-0' : 'text-ink-secondary shrink-0'}>
        {icon}
      </span>
      <div className="flex-1 min-w-0">
        <p className={`text-sm font-semibold ${danger ? 'text-status-failed' : 'text-ink-primary'}`}>
          {label}
        </p>
        <p className="text-xs text-ink-tertiary mt-0.5">{description}</p>
      </div>
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true"
        className="text-ink-tertiary shrink-0">
        <path d="M6 4l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </motion.button>
  )
}

/* Payment account — where payroll pays this employee. Employee edits their
   own; manager/owner see it read-only on owner_pwa's StaffScreen. */
function PaymentAccountCard() {
  const addToast = useToastStore(s => s.addToast)
  const qc = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [method, setMethod] = useState<'MPESA' | 'BANK'>('MPESA')
  const [number, setNumber] = useState('')

  const { data, isLoading } = useQuery<MyProfile>({
    queryKey: ['my-profile'],
    queryFn: () => api.get<MyProfile>('/hr/profiles/me').then(r => r.data),
    retry: (count, err) =>
      (err as { response?: { status?: number } })?.response?.status === 404 ? false : count < 1,
  })

  const saveMut = useMutation({
    mutationFn: () => api.patch('/hr/profiles/me/payment', { payment_method: method, payment_account_number: number }),
    onSuccess: () => {
      addToast({ type: 'success', message: 'Payment account saved.' })
      qc.invalidateQueries({ queryKey: ['my-profile'] })
      setEditing(false)
    },
    onError: (e) => addToast({ type: 'error', message: extractErr(e) }),
  })

  if (isLoading) return null
  // No employee profile yet (see ClockScreen's identical check) — nothing to show.
  if (data === undefined) return null

  function startEdit() {
    setMethod((data?.payment_method as 'MPESA' | 'BANK') || 'MPESA')
    setNumber(data?.payment_account_number ?? '')
    setEditing(true)
  }

  return (
    <div className="glass-card rounded-2xl p-4 space-y-3">
      <p className="text-xs font-semibold uppercase tracking-wider text-ink-tertiary">
        Payment Account
      </p>
      {!editing ? (
        <>
          {data.payment_account_number ? (
            <p className="text-sm text-ink-primary">
              {data.payment_method === 'BANK' ? 'Bank account' : 'M-Pesa'}: <span className="font-semibold">{data.payment_account_number}</span>
            </p>
          ) : (
            <p className="text-sm text-ink-tertiary">No payment account on file — payroll needs this to pay you.</p>
          )}
          <Button variant="ghost" size="sm" onClick={startEdit}>
            {data.payment_account_number ? 'Change' : 'Add payment account'}
          </Button>
        </>
      ) : (
        <div className="space-y-2">
          <div className="flex gap-2" role="group" aria-label="Payment method">
            {(['MPESA', 'BANK'] as const).map(m => (
              <button key={m} type="button" onClick={() => setMethod(m)}
                aria-pressed={method === m}
                className={[
                  'flex-1 py-2 rounded-xl border text-sm font-semibold transition-colors',
                  method === m ? 'bg-ink-primary text-cream-card border-ink-primary' : 'border-white/10 text-ink-secondary',
                ].join(' ')}>
                {m === 'MPESA' ? 'M-Pesa' : 'Bank'}
              </button>
            ))}
          </div>
          <input
            value={number}
            onChange={e => setNumber(e.target.value)}
            placeholder={method === 'MPESA' ? 'M-Pesa number, e.g. 0712345678' : 'Bank account number'}
            className="w-full rounded-xl glass-card bg-transparent px-4 py-2.5
              text-sm text-ink-primary placeholder:text-ink-tertiary
              focus:outline-none focus:border-primary-main"
          />
          <div className="flex gap-2">
            <Button variant="ghost" size="sm" className="flex-1" onClick={() => setEditing(false)}>Cancel</Button>
            <Button variant="primary" size="sm" className="flex-1"
              loading={saveMut.isPending} disabled={!number.trim()}
              onClick={() => saveMut.mutate()}>
              Save
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

export default function ProfileScreen() {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const clearAuth = useAuthStore((s) => s.clearAuth)
  const { size: fontSize, changeSize: changeFontSize } = useFontSizePref()

  // Same key as the payment section below, so react-query serves both from one
  // request rather than fetching the profile twice on one screen.
  const { data: profile } = useQuery<MyProfile>({
    queryKey: ['my-profile'],
    queryFn: () => api.get<MyProfile>('/hr/profiles/me').then(r => r.data),
    retry: false,          // no profile yet is a normal state, not an error
  })

  function signOut() { clearAuth(); navigate('/pin') }

  const containerVariants = {
    hidden: {},
    visible: { transition: { staggerChildren: 0.07 } },
  }
  const itemVariants = {
    hidden: { opacity: 0, y: 12 },
    visible: { opacity: 1, y: 0, transition: { duration: 0.25, ease: 'easeOut' as const } },
  }

  return (
    <motion.div
      className="max-w-3xl mx-auto"
      initial="hidden"
      animate="visible"
      variants={containerVariants}
    >

      {/* ── Header ─────────────────────────────────────────────────── */}
      <div className="mb-6 p-4">
        <h1 className="font-serif text-2xl font-bold text-ink-primary">PROFILE.</h1>
        <p className="text-xs text-ink-tertiary mt-1">KURAHIA STAFF</p>
      </div>

      <div className="p-4 space-y-6">

      {/* ── Identity card ─────────────────────────────────────────── */}
      <motion.div variants={itemVariants} className="flex items-center gap-4 -mt-2">
        {/* Real photo when there is one, initials in a stable colour when there
            is not. Was a single letter taken from the USERNAME, so "peter.mwendwa"
            showed a "P" — the login handle, not the person. */}
        <Avatar
          name={profile?.full_name || user?.username || '?'}
          photoPath={profile?.photo_path}
          size="lg"
          className="ring-4 ring-cream-card"
        />
        <div>
          <p className="text-base font-bold text-ink-primary">
            {profile?.full_name || user?.username}
          </p>
          <p className="text-sm text-ink-tertiary">
            {roleName(user?.role_level ?? 0)}
            {user?.department ? ` · ${user.department}` : ''}
          </p>
        </div>
      </motion.div>

      {/* ── Payment account (payroll) ─────────────────────────────── */}
      <motion.div variants={itemVariants}>
        <PaymentAccountCard />
      </motion.div>

      {/* ── HR actions ────────────────────────────────────────────── */}
      <motion.div variants={itemVariants} className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-wider text-ink-tertiary px-1">
          Leave & Attendance
        </p>
        <NavCard
          path="/leave"
          label="Leave Request"
          description="Request annual, sick, emergency, or unpaid leave."
          icon={
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <rect x="3" y="4" width="18" height="17" rx="2" stroke="currentColor" strokeWidth="1.5"/>
              <path d="M8 2v4M16 2v4M3 10h18" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
              <path d="M8 15h8M8 18h5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
          }
        />
        <NavCard
          path="/absence"
          label="Absence Notice"
          description="Calling in today? Record it immediately — manager is notified."
          danger
          icon={
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.5"/>
              <path d="M12 8v4M12 16h.01" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
          }
        />
      </motion.div>

      {/* ── Company actions ───────────────────────────────────────── */}
      <motion.div variants={itemVariants} className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-wider text-ink-tertiary px-1">
          Company
        </p>
        <NavCard
          path="/conduct"
          label="Code of Conduct"
          description="Review and sign the employee conduct rules."
          icon={
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M9 12l2 2 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              <path d="M7 3H4a1 1 0 00-1 1v16a1 1 0 001 1h16a1 1 0 001-1V8l-5-5H7z"
                stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
              <path d="M14 3v5h5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
          }
        />
        <NavCard
          path="/suggestions/new"
          label="Suggestion Box"
          description="Submit a suggestion to management or directly to the owner."
          icon={
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2v10z"
                stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
              <path d="M8 10h.01M12 10h.01M16 10h.01" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
            </svg>
          }
        />
      </motion.div>

      {/* ── Accessibility: font size ──────────────────────────────── */}
      <motion.div variants={itemVariants} className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-wider text-ink-secondary px-1">
          Text Size
        </p>
        <div className="flex gap-2" role="group" aria-label="Text size">
          {(['S', 'M', 'L'] as FontSizeKey[]).map(key => (
            <motion.button
              key={key}
              whileTap={{ scale: 0.97 }}
              onClick={() => void changeFontSize(key)}
              aria-pressed={fontSize === key}
              className={[
                'flex-1 py-2 min-h-[44px] rounded-xl border text-sm font-semibold transition-colors',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark',
                fontSize === key
                  ? 'bg-ink-primary text-cream-card border-ink-primary'
                  : 'border-white/10 text-ink-secondary hover:bg-white/5',
              ].join(' ')}
            >
              {key}
            </motion.button>
          ))}
        </div>
      </motion.div>

      {/* ── Sign out ──────────────────────────────────────────────── */}
      <motion.div variants={itemVariants} className="pt-2 border-t border-white/10">
        <motion.button
          whileTap={{ scale: 0.97 }}
          onClick={signOut}
          className="w-full flex items-center justify-center gap-2 py-3 rounded-xl
            text-status-failed text-sm font-semibold
            hover:bg-status-failed/10 active:bg-status-failed/20 transition-colors
            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-status-failed"
        >
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
            <path d="M7 9h8M12 6l3 3-3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            <path d="M11 3.5H4a1 1 0 00-1 1v9a1 1 0 001 1h7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
          </svg>
          Sign Out
        </motion.button>
      </motion.div>

      </div>
    </motion.div>
  )
}
