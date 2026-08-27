import { useNavigate } from 'react-router-dom'
import { EmptyState, Icon } from '@shared'

/**
 * Shown when a station tablet is asked for an address that doesn't exist.
 *
 * Before this, the catch-all route rendered StationLoginScreen, and it sat
 * OUTSIDE AuthGate — so any unknown path showed a login screen to someone who
 * was already signed in. A typo, a stale bookmark or an old link read as "your
 * session ended", sending staff to hunt for a sign-in problem that wasn't there.
 *
 * It also made automated screenshots dangerous: a run that mistyped a route got
 * a plausible-looking login page instead of an error, which is exactly how an
 * earlier capture ended up with eight identical login screenshots filed under
 * eight different dashboard names.
 *
 * Unauthenticated visitors still reach /login — AuthGate sends them there before
 * this screen is ever reached. This is only for "signed in, wrong address".
 */
export default function NotFoundScreen() {
  const navigate = useNavigate()
  return (
    <div className="flex flex-col items-center justify-center h-full p-6 text-center">
      <EmptyState
        icon={<Icon name="alert" size={40} />}
        title="Page not found"
        description="This tablet has no screen at that address. You are still signed in."
        actionLabel="Go back"
        onAction={() => navigate(-1)}
      />
    </div>
  )
}
