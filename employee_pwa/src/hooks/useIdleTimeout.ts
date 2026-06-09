import { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'

const IDLE_MS = 10 * 60 * 1000  // 10 minutes
const EVENTS = ['mousemove', 'keydown', 'touchstart', 'pointerdown', 'scroll'] as const

// Wire now — apply per-screen in F-7+.
// Redirects to /pin after IDLE_MS of inactivity (screen lock, not full logout).
export function useIdleTimeout(enabled = true) {
  const navigate = useNavigate()
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (!enabled) return

    function reset() {
      if (timer.current) clearTimeout(timer.current)
      timer.current = setTimeout(() => navigate('/pin', { replace: true }), IDLE_MS)
    }

    reset()
    EVENTS.forEach((e) => window.addEventListener(e, reset, { passive: true }))

    return () => {
      if (timer.current) clearTimeout(timer.current)
      EVENTS.forEach((e) => window.removeEventListener(e, reset))
    }
  }, [enabled, navigate])
}
