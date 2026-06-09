import { motion } from 'framer-motion'
import type { ComponentPropsWithoutRef, ReactNode } from 'react'

export type CardPadding = 'sm' | 'md' | 'lg'
export type CardShadow = 'none' | 'sm' | 'md'

export interface CardProps extends ComponentPropsWithoutRef<'div'> {
  padding?: CardPadding
  shadow?: CardShadow
  border?: boolean
  tappable?: boolean
  selected?: boolean
  children: ReactNode
  onClick?: () => void
}

const PADDING: Record<CardPadding, string> = {
  sm: 'p-3',
  md: 'p-5',
  lg: 'p-7',
}

const SHADOW: Record<CardShadow, string> = {
  none: '',
  sm:   'shadow-sm',
  md:   'shadow-md',
}

export function Card({
  padding = 'md',
  shadow = 'sm',
  border = false,
  tappable = false,
  selected = false,
  children,
  className = '',
  onClick,
  ...rest
}: CardProps) {
  const base = [
    'rounded-xl bg-cream-card transition-all',
    PADDING[padding],
    SHADOW[shadow],
    border || selected ? 'border-2' : '',
    selected
      ? 'bg-sage-light border-sage-dark'
      : border
        ? 'border-cream-alt'
        : '',
    tappable ? 'cursor-pointer' : '',
    className,
  ].join(' ')

  if (tappable) {
    return (
      <motion.div
        whileHover={{ translateY: -2, boxShadow: '0 4px 12px rgba(0,0,0,0.10)' }}
        whileTap={{ scale: 0.99 }}
        transition={{ duration: 0.15, ease: 'easeOut' as const }}
        className={base}
        onClick={onClick}
        role={onClick ? 'button' : undefined}
        tabIndex={onClick ? 0 : undefined}
        onKeyDown={onClick ? (e) => { if (e.key === 'Enter' || e.key === ' ') onClick() } : undefined}
        {...(rest as Record<string, unknown>)}
      >
        {children}
      </motion.div>
    )
  }

  return (
    <div className={base} onClick={onClick} {...rest}>
      {children}
    </div>
  )
}
