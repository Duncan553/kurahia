import { motion, useReducedMotion } from 'framer-motion'
import type { ReactNode } from 'react'
import { Button } from './Button'

export interface EmptyStateProps {
  icon: ReactNode
  title: string
  description?: string
  actionLabel?: string
  onAction?: () => void
}

export function EmptyState({ icon, title, description, actionLabel, onAction }: EmptyStateProps) {
  const reduced = useReducedMotion()

  return (
    <motion.div
      initial={{ opacity: reduced ? 1 : 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: reduced ? 0 : 0.2, ease: 'easeOut' }}
      className="flex flex-col items-center justify-center text-center px-6 py-16 gap-4"
    >
      <div className="text-ink-tertiary" aria-hidden="true">
        {icon}
      </div>
      <h3 className="text-lg font-semibold text-ink-primary">{title}</h3>
      {description && (
        <p className="text-sm text-ink-secondary max-w-xs">{description}</p>
      )}
      {actionLabel && onAction && (
        <Button variant="secondary" size="sm" onClick={onAction}>
          {actionLabel}
        </Button>
      )}
    </motion.div>
  )
}
