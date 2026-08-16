import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { enableAudio, playTestTone, isAudioEnabled } from '../lib/audio'

interface Props {
  station: 'KITCHEN' | 'BAR'
}

export default function AudioEnableSplash({ station }: Props) {
  const [visible, setVisible] = useState(!isAudioEnabled())

  async function handleEnable() {
    enableAudio()
    await playTestTone(station)
    setVisible(false)
  }

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.3 }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-ink-primary/40 backdrop-blur-sm"
        >
          <motion.div
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.95, opacity: 0 }}
            transition={{ type: 'spring', damping: 20, stiffness: 300 }}
            className="mx-6 max-w-sm w-full p-8 rounded-3xl bg-cream-card border border-cream-alt shadow-xl text-center"
          >
            <div className="mx-auto mb-5 w-16 h-16 rounded-full bg-cream-alt flex items-center justify-center">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path d="M11 5L6 9H2v6h4l5 4V5z" stroke="currentColor" strokeWidth="1.5"
                  strokeLinecap="round" strokeLinejoin="round" className="text-primary-dark"/>
                <path d="M15.54 8.46a5 5 0 010 7.07M19.07 4.93a10 10 0 010 14.14"
                  stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"
                  className="text-primary-dark"/>
              </svg>
            </div>
            <h2 className="text-lg font-bold font-serif text-ink-primary mb-2">
              {station === 'KITCHEN' ? 'Kitchen' : 'Bar'} Station
            </h2>
            <p className="text-sm text-ink-secondary mb-6 leading-relaxed">
              Tap to enable order alerts for this shift.
              You&rsquo;ll hear a tone when new orders arrive.
            </p>
            <button
              onClick={handleEnable}
              className="w-full py-3.5 rounded-2xl bg-[#fa5c29] text-white font-semibold
                text-sm transition-transform active:scale-[0.97]
                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark focus-visible:ring-offset-2"
            >
              Enable Audio Alerts
            </button>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
