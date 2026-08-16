import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../../stores/authStore'
import { useKioskStore } from '../../stores/kioskStore'

export default function KioskLaunchScreen() {
  const navigate     = useNavigate()
  const user         = useAuthStore((s) => s.user)
  const activateKiosk = useKioskStore((s) => s.activateKiosk)

  function handleActivate() {
    if (!user?.username) return
    activateKiosk(user.username)
    navigate('/kiosk/menu')
  }

  return (
    <div className="min-h-screen bg-ticket-paper flex flex-col items-center justify-center p-8 gap-8">
      <div className="text-center space-y-2">
        <h1 className="font-serif text-4xl font-bold text-tea-brown tracking-widest">
          KIOSK MODE
        </h1>
        <p className="text-sm text-ticket-ink/60 tracking-wide">
          Waterfront Kurahia · Menu Browse
        </p>
      </div>

      <div className="w-full max-w-sm bg-ticket-alt rounded-2xl p-5 space-y-2 border border-tea-brown/20">
        <p className="text-sm font-semibold text-ticket-ink">Before you continue</p>
        <ul className="text-sm text-ticket-ink/70 space-y-1 list-disc list-inside">
          <li>Tablet will lock to menu-only display</li>
          <li>Your staff PIN is required to exit</li>
          <li>Back button is disabled in kiosk mode</li>
          <li>Auto-returns to welcome screen after 10 min</li>
        </ul>
      </div>

      <button
        onClick={handleActivate}
        className="w-full max-w-sm py-4 rounded-2xl bg-tea-brown text-ticket-paper
          font-semibold text-base tracking-wide
          hover:bg-tea-brown/90 active:scale-[0.99] transition-all
          focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tea-brown"
      >
        Activate Menu Kiosk
      </button>

      <button
        onClick={() => navigate(-1)}
        className="min-h-[44px] text-sm text-ticket-ink/50 hover:text-ticket-ink/80
          transition-colors focus-visible:outline-none"
      >
        Cancel
      </button>
    </div>
  )
}
