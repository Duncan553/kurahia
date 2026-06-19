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
  primary:   'bg-gradient-to-b from-emerald-500 to-emerald-700 text-white shadow-[0_4px_14px_rgba(16,185,129,0.3)] hover:from-emerald-400 hover:to-emerald-600 hover:shadow-[0_6px_20px_rgba(16,185,129,0.4)] border border-emerald-500/30',
  secondary: 'bg-white/8 text-white/90 border border-white/15 backdrop-blur-md hover:bg-white/14 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]',
  ghost:     'bg-transparent text-white/50 hover:text-emerald-400 hover:bg-emerald-500/8 hover:shadow-[0_0_12px_rgba(16,185,129,0.1)]',
  danger:    'bg-gradient-to-b from-red-500 to-red-700 text-white shadow-[0_4px_14px_rgba(239,68,68,0.3)] hover:from-red-400 hover:to-red-600 border border-red-500/30',
}

// sm: min-h-[44px] with compact py fills the touch target with invisible space
// md/lg: min-h-[44px] directly, content vertically centred
const SIZE: Record<ButtonSize, string> = {
  sm: 'text-sm  px-4 py-1.5 min-h-[44px] rounded-xl',
  md: 'text-base px-5 py-2.5 min-h-[44px] rounded-xl',
  lg: 'text-base px-7 py-3.5 min-h-[44px] rounded-xl',
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
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-dark focus-visible:ring-offset-1',
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
