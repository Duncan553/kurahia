import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useKioskStore } from '../../stores/kioskStore'

export default function KioskWelcomeScreen() {
  const navigate    = useNavigate()
  const kioskMode   = useKioskStore((s) => s.kioskMode)

  // Guard — if kiosk mode was deactivated (e.g. store cleared), bounce to staff home
  useEffect(() => {
    if (!kioskMode) navigate('/', { replace: true })
  }, [kioskMode, navigate])

  // Disable back navigation
  useEffect(() => {
    window.history.pushState(null, '', window.location.href)
    const handler = () => window.history.pushState(null, '', window.location.href)
    window.addEventListener('popstate', handler)
    return () => window.removeEventListener('popstate', handler)
  }, [])

  return (
    <div
      className="min-h-screen bg-ticket-paper flex flex-col items-center justify-center
        select-none cursor-pointer overflow-hidden"
      onContextMenu={(e) => e.preventDefault()}
      onClick={() => navigate('/kiosk/menu')}
      style={{ touchAction: 'pan-y', overscrollBehavior: 'none' }}
    >
      {/* Torn-edge texture strips */}
      <div className="absolute top-0 left-0 right-0 h-1 bg-tea-brown/10" />
      <div className="absolute bottom-0 left-0 right-0 h-1 bg-tea-brown/10" />

      <div className="flex flex-col items-center gap-6 px-8 text-center">
        <p className="font-serif text-xl font-bold text-tea-brown/60 tracking-[0.4em] uppercase">
          Waterfront Kurahia
        </p>

        <h1 className="font-serif text-7xl font-bold text-tea-brown tracking-widest leading-none">
          KARIBU
        </h1>

        <div className="w-24 h-px bg-tea-brown/30 my-2" />

        <p className="text-base text-ticket-ink/50 tracking-widest uppercase">
          Tap anywhere to view menu
        </p>
      </div>
    </div>
  )
}
