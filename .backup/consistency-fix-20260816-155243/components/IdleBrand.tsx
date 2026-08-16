import { useState, useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

const IDLE_TIMEOUT_MS = 5 * 60_000

export default function IdleBrand() {
  const [idle, setIdle] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout>>(undefined)

  function resetTimer() {
    setIdle(false)
    clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => setIdle(true), IDLE_TIMEOUT_MS)
  }

  useEffect(() => {
    const events = ['mousedown', 'touchstart', 'keydown', 'scroll']
    events.forEach(e => window.addEventListener(e, resetTimer, { passive: true }))
    resetTimer()
    return () => {
      events.forEach(e => window.removeEventListener(e, resetTimer))
      clearTimeout(timerRef.current)
    }
  }, [])

  return (
    <AnimatePresence>
      {idle && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 1.5 }}
          onClick={resetTimer}
          className="fixed inset-0 z-[100] flex items-center justify-center cursor-pointer"
          style={{ background: 'linear-gradient(135deg, #2E3E38 0%, #1A3636 50%, #40534C 100%)' }}
        >
          <div className="text-center">
            <motion.div
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ duration: 1, delay: 0.3, ease: 'easeOut' }}
            >
              <motion.p
                className="font-serif text-6xl md:text-8xl font-bold text-white/90 tracking-tight"
                animate={{ opacity: [0.6, 1, 0.6] }}
                transition={{ duration: 4, repeat: Infinity, ease: 'easeInOut' }}
              >
                KURAHIA
              </motion.p>
              <motion.p
                className="text-sm md:text-base text-white/40 tracking-[0.4em] uppercase mt-4"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 1, duration: 0.8 }}
              >
                Waterfront Country Club
              </motion.p>
              <motion.p
                className="text-xs text-white/25 tracking-[0.3em] uppercase mt-2"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 1.5, duration: 0.8 }}
              >
                Juja &middot; Kiambu &middot; Kenya
              </motion.p>
            </motion.div>

            <motion.p
              className="text-[10px] text-white/20 mt-12"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 2.5, duration: 1 }}
            >
              Tap anywhere to wake
            </motion.p>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
