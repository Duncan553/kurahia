import { useEffect, useState } from 'react'

// Connectivity banner. Offline → amber "showing saved data".
// Reconnect → green "Back online" for 3 seconds, then gone.
export function OfflineBanner() {
  const [state, setState] = useState<'online' | 'offline' | 'reconnected'>(
    navigator.onLine ? 'online' : 'offline'
  )

  useEffect(() => {
    const goOffline = () => setState('offline')
    const goOnline = () => {
      setState('reconnected')
      const t = setTimeout(() => setState('online'), 3000)
      return () => clearTimeout(t)
    }
    window.addEventListener('offline', goOffline)
    window.addEventListener('online', goOnline)
    return () => {
      window.removeEventListener('offline', goOffline)
      window.removeEventListener('online', goOnline)
    }
  }, [])

  if (state === 'online') return null
  return (
    <div
      role="status"
      className={`shrink-0 text-center text-xs font-semibold py-1.5 text-white ${
        state === 'offline' ? 'bg-status-pending' : 'bg-status-paid'
      }`}
    >
      {state === 'offline' ? 'Offline — showing saved data' : 'Back online'}
    </div>
  )
}
