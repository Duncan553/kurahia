import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'

function roleName(level: number): string {
  if (level >= 10) return 'Owner'
  if (level >= 5) return 'Manager'
  if (level >= 3) return 'Gate Staff'
  return 'Staff'
}

function NavCard({ label, description, path, icon }: {
  label: string; description: string; path: string
  icon: React.ReactNode
}) {
  const navigate = useNavigate()
  return (
    <button
      onClick={() => navigate(path)}
      className="w-full flex items-center gap-4 p-4 rounded-2xl border border-cream-alt
        bg-cream-card hover:bg-cream-alt/40 active:bg-cream-alt/60 transition-colors text-left
        focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sage-dark"
    >
      <span className="shrink-0 text-ink-secondary">{icon}</span>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-ink-primary">{label}</p>
        <p className="text-xs text-ink-tertiary mt-0.5">{description}</p>
      </div>
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true"
        className="text-ink-tertiary shrink-0">
        <path d="M6 4l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </button>
  )
}

export default function ProfileScreen() {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const clearAuth = useAuthStore((s) => s.clearAuth)

  function signOut() { clearAuth(); navigate('/pin') }

  return (
    <div className="p-4 space-y-6 max-w-md mx-auto">

      {/* User card */}
      <div className="flex items-center gap-4 pt-2">
        <div className="w-14 h-14 rounded-full bg-sage-dark flex items-center justify-center
          text-cream-card text-xl font-bold shrink-0">
          {user?.username?.[0]?.toUpperCase() ?? '?'}
        </div>
        <div>
          <p className="text-base font-bold text-ink-primary">{user?.username}</p>
          <p className="text-sm text-ink-tertiary">{roleName(user?.role_level ?? 0)}</p>
        </div>
      </div>

      {/* Quick nav */}
      <div className="space-y-3">
        <p className="text-xs font-semibold uppercase tracking-wider text-ink-tertiary px-1">Actions</p>
        <NavCard
          path="/conduct"
          label="Code of Conduct"
          description="Review and sign the employee conduct rules."
          icon={
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M9 12l2 2 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              <path d="M7 3H4a1 1 0 00-1 1v16a1 1 0 001 1h16a1 1 0 001-1V8l-5-5H7z"
                stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
              <path d="M14 3v5h5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
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
                stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
              <path d="M8 10h.01M12 10h.01M16 10h.01" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
          }
        />
      </div>

      {/* Sign out */}
      <div className="pt-2 border-t border-cream-alt">
        <button
          onClick={signOut}
          className="w-full flex items-center justify-center gap-2 py-3 rounded-xl
            text-status-failed text-sm font-semibold
            hover:bg-status-failed/10 active:bg-status-failed/20 transition-colors
            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-status-failed"
        >
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
            <path d="M7 9h8M12 6l3 3-3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M11 3.5H4a1 1 0 00-1 1v9a1 1 0 001 1h7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
          Sign Out
        </button>
      </div>
    </div>
  )
}
