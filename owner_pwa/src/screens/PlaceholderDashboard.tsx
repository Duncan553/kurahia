import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'
import { Button } from '@shared'

// Temporary placeholder until F-15 (Owner Dashboard)
export default function PlaceholderDashboard() {
  const navigate = useNavigate()
  const { user, clearAuth } = useAuthStore()

  function signOut() {
    clearAuth()
    navigate('/pin')
  }

  return (
    <div className="min-h-screen bg-cream-card flex items-center justify-center p-6">
      <div className="text-center space-y-4">
        <h1 className="text-3xl font-bold font-serif text-ink-primary">Kurahia Owner</h1>
        {user && (
          <p className="text-base text-ink-secondary">
            Signed in as <strong>{user.username}</strong> · level {user.role_level}
          </p>
        )}
        <p className="text-sm text-ink-tertiary">Dashboard coming in F-15.</p>
        <Button variant="ghost" onClick={signOut}>Sign out</Button>
      </div>
    </div>
  )
}
