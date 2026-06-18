import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { useAuthStore } from '../stores/authStore'
import { useFontSizePref, type FontSizeKey } from '../lib/fontSizePref'

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
    <button
      onClick={() => navigate(path)}
      className={[
        'w-full flex items-center gap-4 p-4 rounded-2xl border transition-colors text-left',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark',
        danger
          ? 'border-status-failed/20 bg-status-failed/5 hover:bg-status-failed/10'
          : 'border-white/10 bg-transparent hover:bg-white/5/40 active:bg-white/5/60',
      ].join(' ')}
    >
      <span className={danger ? 'text-status-failed shrink-0' : 'text-slate-300/70 shrink-0'}>
        {icon}
      </span>
      <div className="flex-1 min-w-0">
        <p className={`text-sm font-semibold ${danger ? 'text-status-failed' : 'text-white'}`}>
          {label}
        </p>
        <p className="text-xs text-slate-400/50 mt-0.5">{description}</p>
      </div>
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true"
        className="text-slate-400/50 shrink-0">
        <path d="M6 4l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </button>
  )
}

export default function ProfileScreen() {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const clearAuth = useAuthStore((s) => s.clearAuth)
  const { size: fontSize, changeSize: changeFontSize } = useFontSizePref()

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
        <h1 className="font-serif text-2xl font-bold text-white">PROFILE.</h1>
        <p className="text-xs text-white/30 mt-1">KURAHIA STAFF</p>
      </div>

      <div className="p-4 space-y-6">

      {/* ── Identity card ─────────────────────────────────────────── */}
      <motion.div variants={itemVariants} className="flex items-center gap-4 -mt-2">
        <div className="w-14 h-14 rounded-full bg-primary-dark flex items-center justify-center
          text-white text-xl font-bold shrink-0 ring-4 ring-cream-card">
          {user?.username?.[0]?.toUpperCase() ?? '?'}
        </div>
        <div>
          <p className="text-base font-bold text-white">{user?.username}</p>
          <p className="text-sm text-slate-400/50">
            {roleName(user?.role_level ?? 0)}
            {user?.department ? ` · ${user.department}` : ''}
          </p>
        </div>
      </motion.div>

      {/* ── HR actions ────────────────────────────────────────────── */}
      <motion.div variants={itemVariants} className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-wider text-slate-400/50 px-1">
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
        <p className="text-xs font-semibold uppercase tracking-wider text-slate-400/50 px-1">
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
        <p className="text-xs font-semibold uppercase tracking-wider text-slate-300/70 px-1">
          Text Size
        </p>
        <div className="flex gap-2" role="group" aria-label="Text size">
          {(['S', 'M', 'L'] as FontSizeKey[]).map(key => (
            <button
              key={key}
              onClick={() => void changeFontSize(key)}
              aria-pressed={fontSize === key}
              className={[
                'flex-1 py-2 min-h-[44px] rounded-xl border text-sm font-semibold transition-colors',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark',
                fontSize === key
                  ? 'bg-ink-primary text-white border-ink-primary'
                  : 'border-white/10 text-slate-300/70 hover:bg-white/5',
              ].join(' ')}
            >
              {key}
            </button>
          ))}
        </div>
      </motion.div>

      {/* ── Sign out ──────────────────────────────────────────────── */}
      <motion.div variants={itemVariants} className="pt-2 border-t border-white/10">
        <button
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
        </button>
      </motion.div>

      </div>
    </motion.div>
  )
}
