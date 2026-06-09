import { motion } from 'framer-motion'
import type { ComponentPropsWithoutRef } from 'react'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'
export type ButtonSize = 'sm' | 'md' | 'lg'

// HTML drag + animationStart handlers conflict with Framer Motion's own signatures.
type HTMLMotionConflicts =
  | 'onDrag' | 'onDragEnd' | 'onDragStart'
  | 'onDragEnter' | 'onDragExit' | 'onDragLeave' | 'onDragOver'
  | 'onDragCapture' | 'onDragEndCapture' | 'onDragStartCapture'
  | 'onDragEnterCapture' | 'onDragExitCapture' | 'onDragLeaveCapture' | 'onDragOverCapture'
  | 'onAnimationStart' | 'onAnimationStartCapture'

export interface ButtonProps extends Omit<ComponentPropsWithoutRef<'button'>, HTMLMotionConflicts> {
  variant?: ButtonVariant
  size?: ButtonSize
  loading?: boolean
}

const VARIANT: Record<ButtonVariant, string> = {
  primary:   'bg-sage-dark text-cream-card hover:bg-sage-main',
  secondary: 'bg-cream-card text-ink-primary border border-sage-dark hover:bg-cream-alt',
  ghost:     'bg-transparent text-ink-secondary hover:bg-cream-alt',
  danger:    'bg-status-failed text-white hover:opacity-90',
}

// sm: min-h-[44px] with compact py fills the touch target with invisible space
// md/lg: min-h-[44px] directly, content vertically centred
const SIZE: Record<ButtonSize, string> = {
  sm: 'text-sm  px-3 py-1   min-h-[44px] rounded',
  md: 'text-base px-5 py-2.5 min-h-[44px] rounded',
  lg: 'text-base px-7 py-3   min-h-[44px] rounded',
}

function Spinner() {
  return (
    <motion.svg
      animate={{ rotate: 360 }}
      transition={{ duration: 0.8, repeat: Infinity, ease: 'linear' }}
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden="true"
    >
      <circle
        cx="8"
        cy="8"
        r="6"
        stroke="currentColor"
        strokeWidth="2"
        strokeDasharray="28"
        strokeDashoffset="10"
        strokeLinecap="round"
      />
    </motion.svg>
  )
}

export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  disabled = false,
  children,
  className = '',
  ...rest
}: ButtonProps) {
  const isDisabled = disabled || loading

  return (
    <motion.button
      whileTap={isDisabled ? undefined : { scale: 0.97 }}
      transition={{ duration: 0.1, ease: 'easeOut' }}
      disabled={isDisabled}
      aria-busy={loading ? true : undefined}
      aria-disabled={isDisabled ? true : undefined}
      className={[
        'relative inline-flex items-center justify-center font-medium transition-colors',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sage-dark focus-visible:ring-offset-1',
        'disabled:opacity-50 disabled:cursor-not-allowed',
        VARIANT[variant],
        SIZE[size],
        className,
      ].join(' ')}
      {...rest}
    >
      {loading && (
        <span className="absolute inset-0 flex items-center justify-center">
          <Spinner />
        </span>
      )}
      {/* Keep children rendered (invisible) while loading to preserve button width */}
      <span className={loading ? 'invisible' : undefined}>{children}</span>
    </motion.button>
  )
}
