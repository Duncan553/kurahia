import { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'

const IDLE_MS = 10 * 60 * 1000  // 10 minutes

// Watches for any user interaction and redirects to /kiosk/welcome after IDLE_MS of silence.
export function useKioskIdle() {
  const navigate  = useNavigate()
  const timerRef  = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  useEffect(() => {
    function reset() {
      clearTimeout(timerRef.current)
      timerRef.current = setTimeout(() => navigate('/kiosk/welcome'), IDLE_MS)
    }

    const events = ['touchstart', 'mousedown', 'scroll', 'keydown'] as const
    events.forEach((e) => window.addEventListener(e, reset, { passive: true }))
    reset()  // arm on mount

    return () => {
      clearTimeout(timerRef.current)
      events.forEach((e) => window.removeEventListener(e, reset))
    }
  }, [navigate])
}
