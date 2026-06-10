import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../../stores/authStore'
import { useKioskStore } from '../../stores/kioskStore'

export default function KioskFeedbackLaunchScreen() {
  const navigate      = useNavigate()
  const user          = useAuthStore((s) => s.user)
  const activateKiosk = useKioskStore((s) => s.activateKiosk)

  function handleActivate() {
    if (!user?.username) return
    activateKiosk(user.username)
    navigate('/kiosk/feedback')
  }

  return (
    <div className="min-h-screen bg-ticket-paper flex flex-col items-center justify-center p-8 gap-8">
      <div className="text-center space-y-2">
        <h1 className="font-serif text-4xl font-bold text-tea-brown tracking-widest">
          FEEDBACK KIOSK
        </h1>
        <p className="text-sm text-ticket-ink/60 tracking-wide">
          Waterfront Kurahia · Guest Feedback
        </p>
      </div>

      <div className="w-full max-w-sm bg-ticket-alt rounded-2xl p-5 space-y-2 border border-tea-brown/20">
        <p className="text-sm font-semibold text-ticket-ink">Before you continue</p>
        <ul className="text-sm text-ticket-ink/70 space-y-1 list-disc list-inside">
          <li>Tablet will lock to feedback collection display</li>
          <li>Guests rate their visit anonymously</li>
          <li>Tap bottom-right corner 3× to exit at any time</li>
        </ul>
      </div>

      <button
        onClick={handleActivate}
        className="w-full max-w-sm min-h-[56px] rounded-2xl bg-tea-brown text-ticket-paper
          text-lg font-semibold tracking-wide
          hover:bg-tea-brown/90 active:scale-[0.99] transition-all
          focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tea-brown"
      >
        Activate Feedback Kiosk
      </button>

      <button
        onClick={() => navigate(-1)}
        className="text-sm text-ticket-ink/50 hover:text-ticket-ink underline transition-colors
          min-h-[44px] flex items-center focus-visible:outline-none"
      >
        Cancel
      </button>
    </div>
  )
}
