import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'

export interface HelpTooltipProps {
  title: string
  children: React.ReactNode
  position?: 'top' | 'bottom' | 'left' | 'right'
}

export function HelpTooltip({ title, children, position = 'top' }: HelpTooltipProps) {
  const [open, setOpen] = useState(false)

  const positionClasses = {
    top: 'bottom-full left-1/2 -translate-x-1/2 mb-2',
    bottom: 'top-full left-1/2 -translate-x-1/2 mt-2',
    left: 'right-full top-1/2 -translate-y-1/2 mr-2',
    right: 'left-full top-1/2 -translate-y-1/2 ml-2',
  }

  return (
    <span className="relative inline-block">
      <button
        onClick={() => setOpen(!open)}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        className="w-5 h-5 rounded-full bg-white/10 border border-white/15
          flex items-center justify-center text-xs text-ink-tertiary
          hover:bg-primary-main/20 hover:text-primary-main hover:border-primary-main/30
          transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-main"
        aria-label={`Help: ${title}`}
      >
        ?
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: 0.15 }}
            className={`absolute z-50 w-64 p-3 rounded-xl glass-card text-sm
              ${positionClasses[position]}`}
          >
            <p className="font-semibold text-ink-primary mb-1">{title}</p>
            <div className="text-ink-secondary leading-relaxed">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </span>
  )
}
